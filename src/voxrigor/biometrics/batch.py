"""Batch audio-trial inference and loss-aware handoff to the Phase 2 evaluator."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from voxrigor import __version__
from voxrigor.benchmarking.models import (
    BenchmarkTask,
    DatasetManifest,
    ScoreDirection,
    ScoreProducer,
)
from voxrigor.biometrics.aasist_onnx import AASISTLONNXAdapter
from voxrigor.biometrics.audio import load_audio_file
from voxrigor.biometrics.contracts import ModelScore
from voxrigor.biometrics.ecapa import ECAPATDNNAdapter
from voxrigor.biometrics.errors import ModelIntegrationError
from voxrigor.biometrics.trials import AudioTrialManifest


class TrialManifestError(ModelIntegrationError):
    """An audio-trial manifest or its referenced files are invalid."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_audio_trial_manifest(path: Path) -> AudioTrialManifest:
    """Load and validate a JSON audio-trial manifest."""

    source = Path(path).expanduser()
    try:
        raw: Any = json.loads(source.read_text(encoding="utf-8"))
        return AudioTrialManifest.model_validate(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise TrialManifestError("Audio-trial manifest is missing, unreadable or invalid") from exc


def _resolve_audio_path(manifest_directory: Path, relative_path: str) -> Path:
    """Resolve a trial audio path without allowing traversal or symlink escape."""

    base = manifest_directory.resolve()
    candidate = (base / relative_path).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise TrialManifestError(
            "Audio paths must resolve within the audio-trial manifest directory"
        ) from exc
    if not candidate.is_file():
        raise TrialManifestError("A referenced audio file does not exist or is not a regular file")
    return candidate


def _write_json(path: Path, payload: dict[str, object]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_scores(path: Path, rows: list[dict[str, object]]) -> None:
    columns = [
        "trial_id",
        "label",
        "score",
        "split",
        "condition",
        "attack_species",
        "speaker_id",
        "source_id",
    ]
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())


def _build_adapter(manifest: AudioTrialManifest, cache_dir: Path, device: str) -> Any:
    if manifest.model_id == "ecapa-tdnn":
        return ECAPATDNNAdapter(cache_dir=cache_dir / "ecapa-tdnn", device=device)
    model_path = AASISTLONNXAdapter.fetch_pretrained_model(cache_dir / "huggingface")
    return AASISTLONNXAdapter(model_path)


def run_trial_inference(
    manifest_path: Path,
    output_dir: Path,
    *,
    cache_dir: Path,
    device: str = "cpu",
) -> Path:
    """Run a model on a local audio-trial manifest and create validated outputs.

    Creates scores.csv, benchmark.json and inference-provenance.json as one
    output directory. Raw waveforms and input file paths are never copied to
    the output artifacts.
    """

    source_manifest = Path(manifest_path).expanduser().resolve()
    manifest = load_audio_trial_manifest(source_manifest)
    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise TrialManifestError("Refusing to overwrite an existing inference output directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    adapter: Any | None = None
    score_rows: list[dict[str, object]] = []
    trial_provenance: list[dict[str, object]] = []
    descriptor: dict[str, object] | None = None
    artifact_hashes: tuple[str, ...] = ()

    condition_provenance_file: str | None = None
    condition_provenance_hash: str | None = None
    try:
        if manifest.condition_provenance_file is not None:
            source_condition_path = _resolve_audio_path(
                source_manifest.parent, manifest.condition_provenance_file
            )
            expected_condition_hash = manifest.condition_provenance_sha256
            actual_condition_hash = _sha256_file(source_condition_path)
            if actual_condition_hash != expected_condition_hash:
                raise TrialManifestError(
                    "Audio-condition provenance sidecar SHA-256 does not match the audio-trial manifest"
                )
            condition_provenance_file = "condition-provenance.json"
            copied_condition_path = temporary / condition_provenance_file
            with (
                source_condition_path.open("rb") as source_handle,
                copied_condition_path.open("xb") as output_handle,
            ):
                shutil.copyfileobj(source_handle, output_handle)
                output_handle.flush()
                os.fsync(output_handle.fileno())
            condition_provenance_hash = _sha256_file(copied_condition_path)
            if condition_provenance_hash != expected_condition_hash:
                raise TrialManifestError(
                    "Copied audio-condition provenance sidecar failed its SHA-256 check"
                )

        adapter = _build_adapter(manifest, Path(cache_dir).expanduser(), device)
        adapter.load()
        for trial in manifest.trials:
            if manifest.task is BenchmarkTask.ASV:
                enrollment_path = _resolve_audio_path(
                    source_manifest.parent, trial.enrollment_audio or ""
                )
                probe_path = _resolve_audio_path(source_manifest.parent, trial.probe_audio or "")
                enrollment = load_audio_file(enrollment_path)
                probe = load_audio_file(probe_path)
                result = adapter.score(enrollment, probe)
            else:
                audio_path = _resolve_audio_path(source_manifest.parent, trial.audio or "")
                audio = load_audio_file(audio_path)
                result = adapter.score(audio)

            _validate_score_result(result, manifest.model_id)
            if descriptor is None:
                descriptor = result.model.to_dict()
                artifact_hashes = result.model_artifact_sha256
                if not artifact_hashes:
                    raise TrialManifestError(
                        "Model adapter did not provide artifact SHA-256 hashes"
                    )
            elif result.model_artifact_sha256 != artifact_hashes:
                raise TrialManifestError("Model artifact hashes changed during one inference run")

            score_rows.append(
                {
                    "trial_id": trial.trial_id,
                    "label": trial.label,
                    "score": result.score,
                    "split": trial.split,
                    "condition": trial.condition,
                    "attack_species": trial.attack_species or "",
                    "speaker_id": trial.speaker_id or "",
                    "source_id": trial.source_id or "",
                }
            )
            trial_provenance.append(
                {
                    "trial_id": trial.trial_id,
                    "input_sha256": list(result.input_sha256),
                    "score": result.score,
                    "score_type": result.score_type,
                    "preprocessing": list(result.preprocessing),
                    "model_artifact_sha256": list(result.model_artifact_sha256),
                }
            )
        if descriptor is None:
            raise TrialManifestError("Audio-trial manifest contains no executable trials")

        scores_path = temporary / "scores.csv"
        _write_scores(scores_path, score_rows)
        inference_path = temporary / "inference-provenance.json"
        input_manifest_hash = _sha256_file(source_manifest)
        inference_document: dict[str, object] = {
            "schema_version": "0.1",
            "generated_at": datetime.now(UTC).isoformat(),
            "framework": "VoxRigor",
            "framework_version": __version__,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "input_manifest_sha256": input_manifest_hash,
            "model": descriptor,
            "model_artifact_sha256": list(artifact_hashes),
            "trial_count": len(trial_provenance),
            "trials": trial_provenance,
            "privacy_note": "Contains pseudonymous trial IDs and hashes, not audio paths, waveforms or embeddings.",
        }
        _write_json(inference_path, inference_document)
        producer = ScoreProducer(
            framework_version=__version__,
            model_id=str(descriptor["model_id"]),
            model_revision=str(descriptor["source_revision"]),
            backend=str(descriptor["backend"]),
            score_type=str(descriptor["score_type"]),
            score_direction=ScoreDirection.HIGHER_IS_GENUINE,
            calibrated=bool(descriptor.get("calibrated", False)),
            model_artifact_sha256=list(artifact_hashes),
            inference_manifest_sha256=input_manifest_hash,
            inference_provenance_file="inference-provenance.json",
            inference_provenance_sha256=_sha256_file(inference_path),
            condition_provenance_file=condition_provenance_file,
            condition_provenance_sha256=condition_provenance_hash,
        )
        benchmark_manifest = DatasetManifest(
            schema_version="0.2",
            dataset_id=manifest.dataset_id,
            dataset_name=manifest.dataset_name,
            dataset_version=manifest.dataset_version,
            task=manifest.task,
            protocol_id=manifest.protocol_id,
            score_file="scores.csv",
            score_file_sha256=_sha256_file(scores_path),
            evaluation_split=manifest.evaluation_split,
            score_direction=ScoreDirection.HIGHER_IS_GENUINE,
            operating_threshold=manifest.operating_threshold,
            threshold_source=manifest.threshold_source,
            threshold_selection_split=manifest.threshold_selection_split,
            source_url=manifest.source_url,
            license_name=manifest.license_name,
            citation=manifest.citation,
            access_date=manifest.access_date,
            require_group_disjointness=manifest.require_group_disjointness,
            group_columns=manifest.group_columns,
            score_producer=producer,
        )
        benchmark_path = temporary / "benchmark.json"
        _write_json(benchmark_path, benchmark_manifest.model_dump(mode="json"))
        from voxrigor.benchmarking.dataset import load_score_dataset

        load_score_dataset(benchmark_path)
        temporary.rename(output)
        return output
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    finally:
        if adapter is not None:
            adapter.unload()


def _validate_score_result(result: ModelScore, expected_model_id: str) -> None:
    if result.model.model_id != expected_model_id:
        raise TrialManifestError("Model adapter returned a score from an unexpected model")
    if result.score_direction != "higher_is_genuine":
        raise TrialManifestError(
            "The built-in model adapter returned an unsupported score direction"
        )
    if not result.input_sha256 or not result.preprocessing:
        raise TrialManifestError("Model adapter omitted required input or preprocessing provenance")
