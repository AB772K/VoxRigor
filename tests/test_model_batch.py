from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from voxrigor.benchmarking.dataset import load_score_dataset
from voxrigor.benchmarking.errors import ScoreFileError
from voxrigor.benchmarking.reporting import build_benchmark_report
from voxrigor.biometrics.batch import TrialManifestError
from voxrigor.biometrics.contracts import AudioSignal, ModelDescriptor, ModelScore

import voxrigor.biometrics.batch as batch


def descriptor(model_id: str, task: str, score_type: str) -> ModelDescriptor:
    return ModelDescriptor(
        model_id=model_id,
        display_name=model_id,
        task=task,  # type: ignore[arg-type]
        backend="deterministic-test-runtime",
        source_repository="example/model",
        source_revision="a" * 40,
        license_name="MIT",
        expected_sample_rate_hz=16000,
        score_type=score_type,
    )


class FakeECAPA:
    def __init__(self, **_kwargs: Any) -> None:
        self.loaded = False
        self.unloaded = False
        self.descriptor = descriptor("ecapa-tdnn", "speaker_verification", "cosine_similarity")

    def load(self) -> None:
        self.loaded = True

    def score(self, enrollment: AudioSignal, probe: AudioSignal) -> ModelScore:
        assert self.loaded
        score = 0.9 if probe.source_sha256 == "b" * 64 else 0.1
        return ModelScore(
            model=self.descriptor,
            score=score,
            score_type="cosine_similarity",
            score_direction="higher_is_genuine",
            calibrated=False,
            input_sha256=(enrollment.source_sha256, probe.source_sha256),
            preprocessing=("deterministic test preprocessing",),
            model_artifact_sha256=("c" * 64,),
        )

    def unload(self) -> None:
        self.unloaded = True


class FakeAASIST:
    def __init__(self, _path: Path) -> None:
        self.loaded = False
        self.unloaded = False
        self.descriptor = descriptor(
            "aasist-l-onnx", "presentation_attack_detection", "bonafide_logit"
        )

    @staticmethod
    def fetch_pretrained_model(_cache: Path) -> Path:
        return Path("fake-model.onnx")

    def load(self) -> None:
        self.loaded = True

    def score(self, audio: AudioSignal) -> ModelScore:
        assert self.loaded
        score = 1.2 if audio.source_sha256 == "b" * 64 else -0.8
        return ModelScore(
            model=self.descriptor,
            score=score,
            score_type="bonafide_logit",
            score_direction="higher_is_genuine",
            calibrated=False,
            input_sha256=(audio.source_sha256,),
            preprocessing=("deterministic test preprocessing",),
            model_artifact_sha256=("d" * 64,),
        )

    def unload(self) -> None:
        self.unloaded = True


def fake_audio(path: Path) -> AudioSignal:
    digest = "e" * 64 if "nontarget" in path.name or "spoof" in path.name else "b" * 64
    return AudioSignal(
        samples=[0.1, -0.1, 0.2],
        sample_rate_hz=16000,
        source_sha256=digest,
        source_format="wav",
    )


def write_asv_manifest(root: Path) -> Path:
    audio_dir = root / "audio"
    audio_dir.mkdir()
    for name in ("enroll.wav", "probe-target.wav", "probe-nontarget.wav"):
        (audio_dir / name).write_bytes(b"placeholder-not-a-real-audio-file")
    payload = {
        "dataset_id": "local-asv-test",
        "dataset_name": "Local ASV test",
        "dataset_version": "1",
        "task": "asv",
        "protocol_id": "local-v1",
        "model_id": "ecapa-tdnn",
        "evaluation_split": "test",
        "operating_threshold": 0.5,
        "threshold_source": "external",
        "license_name": "synthetic-test-fixture",
        "trials": [
            {
                "trial_id": "target-001",
                "label": "target",
                "split": "test",
                "enrollment_audio": "audio/enroll.wav",
                "probe_audio": "audio/probe-target.wav",
            },
            {
                "trial_id": "nontarget-001",
                "label": "nontarget",
                "split": "test",
                "enrollment_audio": "audio/enroll.wav",
                "probe_audio": "audio/probe-nontarget.wav",
            },
        ],
    }
    path = root / "audio-trials.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_pad_manifest(root: Path) -> Path:
    audio_dir = root / "audio"
    audio_dir.mkdir()
    for name in ("genuine.wav", "spoof.wav"):
        (audio_dir / name).write_bytes(b"placeholder-not-a-real-audio-file")
    payload = {
        "dataset_id": "local-pad-test",
        "dataset_name": "Local PAD test",
        "dataset_version": "1",
        "task": "pad",
        "protocol_id": "local-v1",
        "model_id": "aasist-l-onnx",
        "evaluation_split": "test",
        "operating_threshold": 0.0,
        "threshold_source": "external",
        "license_name": "synthetic-test-fixture",
        "trials": [
            {
                "trial_id": "genuine-001",
                "label": "bonafide",
                "split": "test",
                "audio": "audio/genuine.wav",
            },
            {
                "trial_id": "spoof-001",
                "label": "spoof",
                "split": "test",
                "attack_species": "synthetic-test",
                "audio": "audio/spoof.wav",
            },
        ],
    }
    path = root / "audio-trials.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_asv_batch_exports_phase2_scores_and_verified_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_asv_manifest(tmp_path)
    monkeypatch.setattr(batch, "ECAPATDNNAdapter", FakeECAPA)
    monkeypatch.setattr(batch, "load_audio_file", fake_audio)
    output = batch.run_trial_inference(source, tmp_path / "out", cache_dir=tmp_path / "cache")

    dataset = load_score_dataset(output / "benchmark.json")
    assert len(dataset.records) == 2
    assert dataset.manifest.schema_version == "0.2"
    assert dataset.manifest.score_producer is not None
    assert dataset.manifest.score_producer.model_id == "ecapa-tdnn"
    with (output / "scores.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["label"] for row in rows] == ["target", "nontarget"]
    assert float(rows[0]["score"]) > float(rows[1]["score"])
    sidecar_text = (output / "inference-provenance.json").read_text(encoding="utf-8")
    assert "probe-target.wav" not in sidecar_text
    assert "input_sha256" in sidecar_text
    report, _ = build_benchmark_report(dataset)
    assert report.dataset["score_producer"]["model_id"] == "ecapa-tdnn"  # type: ignore[index]
    assert report.provenance["inference_provenance_sha256"]


def test_pad_batch_exports_attack_species_and_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_pad_manifest(tmp_path)
    monkeypatch.setattr(batch, "AASISTLONNXAdapter", FakeAASIST)
    monkeypatch.setattr(batch, "load_audio_file", fake_audio)
    output = batch.run_trial_inference(source, tmp_path / "out", cache_dir=tmp_path / "cache")

    dataset = load_score_dataset(output / "benchmark.json")
    assert dataset.manifest.task.value == "pad"
    assert dataset.records[1].attack_species == "synthetic-test"
    assert dataset.manifest.score_producer is not None
    assert dataset.manifest.score_producer.score_type == "bonafide_logit"


def test_batch_refuses_to_overwrite_existing_output(tmp_path: Path) -> None:
    source = write_asv_manifest(tmp_path)
    output = tmp_path / "out"
    output.mkdir()
    with pytest.raises(batch.TrialManifestError, match="overwrite"):
        batch.run_trial_inference(source, output, cache_dir=tmp_path / "cache")


def test_batch_rejects_audio_path_that_resolves_outside_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_asv_manifest(tmp_path)
    outside = tmp_path.parent / "outside.wav"
    outside.write_bytes(b"outside")
    link = tmp_path / "audio" / "escape.wav"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is unavailable on this runner")
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["trials"][0]["probe_audio"] = "audio/escape.wav"
    source.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(batch, "ECAPATDNNAdapter", FakeECAPA)
    monkeypatch.setattr(batch, "load_audio_file", fake_audio)
    with pytest.raises(batch.TrialManifestError, match="resolve within"):
        batch.run_trial_inference(source, tmp_path / "out", cache_dir=tmp_path / "cache")


def test_batch_cleans_temporary_directory_and_unloads_on_audio_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_asv_manifest(tmp_path)
    instances: list[FakeECAPA] = []

    def build(**kwargs: Any) -> FakeECAPA:
        instance = FakeECAPA(**kwargs)
        instances.append(instance)
        return instance

    def fail_audio(_path: Path) -> AudioSignal:
        raise OSError("synthetic decode failure")

    monkeypatch.setattr(batch, "ECAPATDNNAdapter", build)
    monkeypatch.setattr(batch, "load_audio_file", fail_audio)
    with pytest.raises(OSError, match="decode failure"):
        batch.run_trial_inference(source, tmp_path / "out", cache_dir=tmp_path / "cache")
    assert instances and instances[0].unloaded
    assert not (tmp_path / "out").exists()
    assert not list(tmp_path.glob(".out.*"))


def test_batch_rejects_changed_model_artifact_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_asv_manifest(tmp_path)

    class ChangingECAPA(FakeECAPA):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.calls = 0

        def score(self, enrollment: AudioSignal, probe: AudioSignal) -> ModelScore:
            self.calls += 1
            result = super().score(enrollment, probe)
            if self.calls == 2:
                return ModelScore(
                    model=result.model,
                    score=result.score,
                    score_type=result.score_type,
                    score_direction=result.score_direction,
                    calibrated=result.calibrated,
                    input_sha256=result.input_sha256,
                    preprocessing=result.preprocessing,
                    model_artifact_sha256=("f" * 64,),
                )
            return result

    monkeypatch.setattr(batch, "ECAPATDNNAdapter", ChangingECAPA)
    monkeypatch.setattr(batch, "load_audio_file", fake_audio)
    with pytest.raises(batch.TrialManifestError, match="changed"):
        batch.run_trial_inference(source, tmp_path / "out", cache_dir=tmp_path / "cache")
    assert not (tmp_path / "out").exists()


def test_batch_rejects_adapter_without_model_artifact_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_asv_manifest(tmp_path)

    class NoHashECAPA(FakeECAPA):
        def score(self, enrollment: AudioSignal, probe: AudioSignal) -> ModelScore:
            result = super().score(enrollment, probe)
            return ModelScore(
                model=result.model,
                score=result.score,
                score_type=result.score_type,
                score_direction=result.score_direction,
                calibrated=result.calibrated,
                input_sha256=result.input_sha256,
                preprocessing=result.preprocessing,
            )

    monkeypatch.setattr(batch, "ECAPATDNNAdapter", NoHashECAPA)
    monkeypatch.setattr(batch, "load_audio_file", fake_audio)
    with pytest.raises(batch.TrialManifestError, match="artifact SHA-256"):
        batch.run_trial_inference(source, tmp_path / "out", cache_dir=tmp_path / "cache")


def test_batch_cleans_temp_directory_if_adapter_creation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_pad_manifest(tmp_path)

    from voxrigor.biometrics.errors import ModelLoadError

    def fail_fetch(_cache: Path) -> Path:
        raise ModelLoadError("model unavailable")

    monkeypatch.setattr(batch.AASISTLONNXAdapter, "fetch_pretrained_model", staticmethod(fail_fetch))
    with pytest.raises(ModelLoadError, match="unavailable"):
        batch.run_trial_inference(source, tmp_path / "out", cache_dir=tmp_path / "cache")
    assert not (tmp_path / "out").exists()
    assert not list(tmp_path.glob(".out.*"))


def test_provenance_sidecar_tampering_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_asv_manifest(tmp_path)
    monkeypatch.setattr(batch, "ECAPATDNNAdapter", FakeECAPA)
    monkeypatch.setattr(batch, "load_audio_file", fake_audio)
    output = batch.run_trial_inference(source, tmp_path / "out", cache_dir=tmp_path / "cache")
    sidecar = output / "inference-provenance.json"
    sidecar.write_text(sidecar.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ScoreFileError, match="provenance sidecar SHA-256"):
        load_score_dataset(output / "benchmark.json")
