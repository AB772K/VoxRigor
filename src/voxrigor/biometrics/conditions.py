"""Deterministic, local-only audio condition generation with provenance."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from voxrigor import __version__
from voxrigor.biometrics.audio import load_audio_file, resample_audio
from voxrigor.biometrics.contracts import AudioSignal
from voxrigor.biometrics.errors import AudioInputError, ModelIntegrationError
from voxrigor.biometrics.trials import AudioTrial, AudioTrialManifest


MAX_SCENARIOS = 32
MAX_TRANSFORMS_PER_SCENARIO = 8
MAX_EXPANDED_TRIALS = 2_000
MAX_GENERATED_AUDIO_BYTES = 1_073_741_824
MAX_IMPULSE_RESPONSE_SECONDS = 2.0
MAX_AUDIO_DURATION_SECONDS = 120.0


class ConditionManifestError(ModelIntegrationError):
    """An audio-condition manifest or its referenced files are invalid."""


class ResampleTransform(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["resample"]
    target_sample_rate_hz: int = Field(ge=8_000, le=192_000)


class GaussianNoiseTransform(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["gaussian_noise"]
    snr_db: float = Field(ge=-20.0, le=80.0, allow_inf_nan=False)
    seed: int = Field(ge=0, le=4_294_967_295)


class MuLawTransform(BaseModel):
    """G.711-style mu-law companding at the 8 kHz narrowband rate."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["mulaw"]
    sample_rate_hz: Literal[8_000] = 8_000


class ReverberationTransform(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["reverberation"]
    impulse_response: str = Field(min_length=1, max_length=500)
    wet_mix: float = Field(default=0.35, ge=0.0, le=1.0, allow_inf_nan=False)

    @field_validator("impulse_response")
    @classmethod
    def validate_relative_ir_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        posix = PurePosixPath(normalized)
        windows = PureWindowsPath(value)
        if (
            "\x00" in value
            or posix.is_absolute()
            or windows.is_absolute()
            or windows.drive
            or ".." in posix.parts
        ):
            raise ValueError("impulse_response must be a relative path within the manifest folder")
        return normalized


ConditionTransform = Annotated[
    ResampleTransform | GaussianNoiseTransform | MuLawTransform | ReverberationTransform,
    Field(discriminator="kind"),
]


class AudioConditionScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    target: Literal["audio", "probe", "enrollment", "both"] = "probe"
    transforms: list[ConditionTransform] = Field(
        default_factory=list, max_length=MAX_TRANSFORMS_PER_SCENARIO
    )


class AudioConditionExperiment(BaseModel):
    """A clean baseline and controlled transformation scenarios."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    source_manifest: str = Field(min_length=1, max_length=500)
    scenarios: list[AudioConditionScenario] = Field(min_length=1, max_length=MAX_SCENARIOS)

    @field_validator("source_manifest")
    @classmethod
    def validate_source_manifest_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        posix = PurePosixPath(normalized)
        windows = PureWindowsPath(value)
        if (
            "\x00" in value
            or posix.is_absolute()
            or windows.is_absolute()
            or windows.drive
            or ".." in posix.parts
        ):
            raise ValueError("source_manifest must be a relative path within the manifest folder")
        return normalized

    @model_validator(mode="after")
    def require_clean_baseline_and_unique_scenarios(self) -> AudioConditionExperiment:
        identifiers = [scenario.scenario_id for scenario in self.scenarios]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("scenario_id values must be unique")
        clean = [item for item in self.scenarios if item.scenario_id == "clean"]
        if len(clean) != 1 or clean[0].transforms:
            raise ValueError("exactly one clean scenario with no transformations is required")
        return self


def _numpy() -> Any:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment-dependent
        from voxrigor.biometrics.errors import OptionalDependencyError

        raise OptionalDependencyError(
            "Audio conditions require NumPy. Install with: pip install 'voxrigor[audio]'"
        ) from exc
    return np


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_samples(signal: AudioSignal) -> str:
    np = _numpy()
    samples = np.ascontiguousarray(signal.samples, dtype="<f4")
    digest = hashlib.sha256()
    digest.update(str(signal.sample_rate_hz).encode("ascii"))
    digest.update(b"\0")
    digest.update(samples.tobytes())
    return digest.hexdigest()


def _resolve_local_file(base_dir: Path, relative_path: str) -> Path:
    base = base_dir.resolve()
    candidate = (base / relative_path).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ConditionManifestError("Input paths must resolve inside the experiment directory") from exc
    if not candidate.is_file():
        raise ConditionManifestError("A referenced local input file does not exist")
    return candidate


def load_condition_experiment(path: Path) -> AudioConditionExperiment:
    source = Path(path).expanduser()
    try:
        payload: Any = json.loads(source.read_text(encoding="utf-8"))
        return AudioConditionExperiment.model_validate(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ConditionManifestError("Audio-condition manifest is missing, unreadable or invalid") from exc


def _derive_seed(seed: int, trial_id: str, role: str, operation_index: int) -> int:
    material = f"{seed}:{trial_id}:{role}:{operation_index}".encode()
    return int.from_bytes(hashlib.sha256(material).digest()[:4], "big")


def _signal_from_samples(signal: AudioSignal, samples: Any, sample_rate_hz: int) -> AudioSignal:
    np = _numpy()
    output = np.ascontiguousarray(samples, dtype=np.float32)
    if output.ndim != 1 or output.size == 0 or not np.isfinite(output).all():
        raise AudioInputError("Audio transformation produced empty or non-finite mono samples")
    return AudioSignal(
        samples=output,
        sample_rate_hz=sample_rate_hz,
        source_sha256=signal.source_sha256,
        source_format=signal.source_format,
    )


def _apply_one(
    signal: AudioSignal,
    operation: ConditionTransform,
    base_dir: Path,
    *,
    effective_seed: int | None,
) -> tuple[AudioSignal, dict[str, object]]:
    np = _numpy()
    before_hash = _sha256_samples(signal)
    details: dict[str, object] = operation.model_dump(mode="json")
    output = signal

    if isinstance(operation, ResampleTransform):
        output = resample_audio(signal, operation.target_sample_rate_hz)
    elif isinstance(operation, GaussianNoiseTransform):
        samples = np.asarray(signal.samples, dtype=np.float64)
        rms = float(np.sqrt(np.mean(np.square(samples))))
        if not math.isfinite(rms) or rms <= 1e-12:
            raise AudioInputError("Gaussian-noise SNR requires a non-silent input signal")
        noise_rms = rms / (10.0 ** (operation.snr_db / 20.0))
        generator = np.random.default_rng(effective_seed)
        noise = generator.normal(0.0, noise_rms, samples.size)
        output = _signal_from_samples(signal, samples + noise, signal.sample_rate_hz)
        details["seed"] = effective_seed
    elif isinstance(operation, MuLawTransform):
        narrowband = resample_audio(signal, operation.sample_rate_hz)
        samples = np.asarray(narrowband.samples, dtype=np.float64)
        peak = float(np.max(np.abs(samples)))
        if peak > 1.0:
            raise AudioInputError(
                "G.711 mu-law simulation requires samples within [-1, 1]; no clipping is applied"
            )
        mu = 255.0
        compressed = np.sign(samples) * np.log1p(mu * np.abs(samples)) / math.log1p(mu)
        encoded = np.rint((compressed + 1.0) * 127.5)
        quantized = (encoded / 127.5) - 1.0
        decoded = np.sign(quantized) * (
            np.power(1.0 + mu, np.abs(quantized)) - 1.0
        ) / mu
        output = _signal_from_samples(narrowband, decoded, operation.sample_rate_hz)
    elif isinstance(operation, ReverberationTransform):
        impulse_path = _resolve_local_file(base_dir, operation.impulse_response)
        impulse = load_audio_file(
            impulse_path, max_duration_seconds=MAX_IMPULSE_RESPONSE_SECONDS
        )
        if impulse.sample_rate_hz != signal.sample_rate_hz:
            raise AudioInputError(
                "Reverberation impulse response must use the same sample rate as the input"
            )
        impulse_samples = np.asarray(impulse.samples, dtype=np.float64)
        impulse_peak = float(np.max(np.abs(impulse_samples)))
        if not math.isfinite(impulse_peak) or impulse_peak <= 1e-12:
            raise AudioInputError("Reverberation impulse response must not be silent")
        try:
            from scipy.signal import fftconvolve
        except ImportError as exc:  # pragma: no cover - environment-dependent
            from voxrigor.biometrics.errors import OptionalDependencyError

            raise OptionalDependencyError(
                "Reverberation requires SciPy. Install with: pip install 'voxrigor[audio]'"
            ) from exc
        normalized_ir = impulse_samples / impulse_peak
        dry = np.asarray(signal.samples, dtype=np.float64)
        wet = fftconvolve(dry, normalized_ir, mode="full")
        dry_padded = np.pad(dry, (0, wet.size - dry.size))
        mixed = (1.0 - operation.wet_mix) * dry_padded + operation.wet_mix * wet
        output = _signal_from_samples(signal, mixed, signal.sample_rate_hz)
        details.pop("impulse_response", None)
        details["impulse_response_sha256"] = impulse.source_sha256

    details["input_sample_sha256"] = before_hash
    details["output_sample_sha256"] = _sha256_samples(output)
    details["input_sample_rate_hz"] = signal.sample_rate_hz
    details["output_sample_rate_hz"] = output.sample_rate_hz
    details["input_duration_seconds"] = len(signal.samples) / signal.sample_rate_hz  # type: ignore[arg-type]
    details["output_duration_seconds"] = len(output.samples) / output.sample_rate_hz  # type: ignore[arg-type]
    return output, details


def _apply_chain(
    signal: AudioSignal,
    operations: list[ConditionTransform],
    base_dir: Path,
    *,
    trial_id: str,
    role: str,
) -> tuple[AudioSignal, list[dict[str, object]]]:
    current = signal
    provenance: list[dict[str, object]] = []
    for index, operation in enumerate(operations):
        seed = (
            _derive_seed(operation.seed, trial_id, role, index)
            if isinstance(operation, GaussianNoiseTransform)
            else None
        )
        current, details = _apply_one(
            current, operation, base_dir, effective_seed=seed
        )
        details["index"] = index
        details["kind"] = operation.kind
        provenance.append(details)
    return current, provenance


def _write_audio(path: Path, signal: AudioSignal) -> str:
    np = _numpy()
    try:
        import soundfile as sf  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - environment-dependent
        from voxrigor.biometrics.errors import OptionalDependencyError

        raise OptionalDependencyError(
            "Audio export requires SoundFile. Install with: pip install 'voxrigor[audio]'"
        ) from exc
    samples = np.asarray(signal.samples, dtype=np.float32)
    if samples.ndim != 1 or samples.size == 0 or not np.isfinite(samples).all():
        raise AudioInputError("Refusing to export invalid audio samples")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # FLOAT WAV preserves over-range samples. No implicit PCM clipping or normalization.
        sf.write(str(path), samples, signal.sample_rate_hz, format="WAV", subtype="FLOAT")
        info = sf.info(str(path))
        if info.frames != samples.size or info.samplerate != signal.sample_rate_hz:
            raise AudioInputError("Exported audio metadata does not match the transformed signal")
        return _sha256_file(path)
    except AudioInputError:
        raise
    except Exception as exc:
        raise AudioInputError("Could not write transformed audio as FLOAT WAV") from exc


def _export_endpoint(
    signal: AudioSignal,
    output_root: Path,
    trial_id: str,
    scenario_id: str,
    role: str,
) -> tuple[str, str, float, float]:
    np = _numpy()
    relative = (
        Path("audio")
        / f"{hashlib.sha256(f'{trial_id}:{scenario_id}:{role}'.encode()).hexdigest()}.wav"
    )
    digest = _write_audio(output_root / relative, signal)
    samples = np.asarray(signal.samples, dtype=np.float64)
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(np.square(samples))))
    return relative.as_posix(), digest, peak, rms


def generate_condition_dataset(experiment_path: Path, output_dir: Path) -> Path:
    """Generate an immutable clean-plus-conditions audio dataset and sidecar."""

    experiment_source = Path(experiment_path).expanduser().resolve()
    experiment = load_condition_experiment(experiment_source)
    source_manifest_path = _resolve_local_file(experiment_source.parent, experiment.source_manifest)
    try:
        from voxrigor.biometrics.batch import load_audio_trial_manifest

        source_manifest = load_audio_trial_manifest(source_manifest_path)
    except ModelIntegrationError:
        raise
    except Exception as exc:
        raise ConditionManifestError("Source audio-trial manifest is invalid") from exc

    expanded_count = len(source_manifest.trials) * len(experiment.scenarios)
    if expanded_count > MAX_EXPANDED_TRIALS:
        raise ConditionManifestError(
            f"Condition expansion exceeds the {MAX_EXPANDED_TRIALS}-trial safety limit"
        )
    if source_manifest.task.value == "pad":
        if any(scenario.target != "audio" for scenario in experiment.scenarios):
            raise ConditionManifestError("PAD scenarios must use target='audio'")
    elif any(scenario.target == "audio" for scenario in experiment.scenarios):
        raise ConditionManifestError("ASV scenarios must target probe, enrollment or both")

    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise ConditionManifestError("Refusing to overwrite an existing condition output directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    generated_trials: list[AudioTrial] = []
    trial_records: list[dict[str, object]] = []
    generated_bytes = 0

    try:
        for trial in source_manifest.trials:
            for scenario in experiment.scenarios:
                new_trial_id = "c-" + hashlib.sha256(
                    f"{trial.trial_id}:{scenario.scenario_id}".encode()
                ).hexdigest()[:32]
                endpoint_records: list[dict[str, object]] = []
                endpoint_values: dict[str, str] = {}

                if source_manifest.task.value == "asv":
                    roles = ("enrollment", "probe")
                    input_refs = {
                        "enrollment": trial.enrollment_audio,
                        "probe": trial.probe_audio,
                    }
                else:
                    roles = ("audio",)
                    input_refs = {"audio": trial.audio}

                for role in roles:
                    relative_input = input_refs[role]
                    if not relative_input:
                        raise ConditionManifestError("Source trial is missing an audio reference")
                    source_path = _resolve_local_file(source_manifest_path.parent, relative_input)
                    original_signal = load_audio_file(
                        source_path, max_duration_seconds=MAX_AUDIO_DURATION_SECONDS
                    )
                    is_targeted = (
                        role == scenario.target
                        or scenario.target == "both"
                        or scenario.target == "audio" and role == "audio"
                    )
                    if is_targeted and scenario.transforms:
                        final_signal, transform_records = _apply_chain(
                            original_signal,
                            scenario.transforms,
                            experiment_source.parent,
                            trial_id=trial.trial_id,
                            role=role,
                        )
                    else:
                        final_signal = original_signal
                        transform_records = []

                    generated_bytes += len(final_signal.samples) * 4  # type: ignore[arg-type]
                    if generated_bytes > MAX_GENERATED_AUDIO_BYTES:
                        raise ConditionManifestError(
                            "Generated audio exceeds the 1 GiB output safety limit"
                        )
                    relative_output, output_hash, peak, rms = _export_endpoint(
                        final_signal, temporary, trial.trial_id, scenario.scenario_id, role
                    )
                    endpoint_values[role] = relative_output
                    endpoint_records.append(
                        {
                            "role": role,
                            "source_audio_sha256": original_signal.source_sha256,
                            "output_audio_sha256": output_hash,
                            "output_sample_rate_hz": final_signal.sample_rate_hz,
                            "output_sample_count": len(final_signal.samples),  # type: ignore[arg-type]
                            "peak_absolute_amplitude": peak,
                            "rms_amplitude": rms,
                            "transformations": transform_records,
                        }
                    )

                generated_trials.append(
                    AudioTrial(
                        trial_id=new_trial_id,
                        label=trial.label,
                        split=trial.split,
                        condition=scenario.scenario_id,
                        audio=endpoint_values.get("audio"),
                        enrollment_audio=endpoint_values.get("enrollment"),
                        probe_audio=endpoint_values.get("probe"),
                        attack_species=trial.attack_species,
                        speaker_id=trial.speaker_id,
                        source_id=trial.source_id,
                    )
                )
                trial_records.append(
                    {
                        "generated_trial_id": new_trial_id,
                        "source_trial_id": trial.trial_id,
                        "scenario_id": scenario.scenario_id,
                        "target": scenario.target,
                        "endpoints": endpoint_records,
                    }
                )

        sidecar = temporary / "conditions-provenance.json"
        sidecar_payload: dict[str, object] = {
            "schema_version": "0.1",
            "framework": "VoxRigor",
            "framework_version": __version__,
            "generated_at": datetime.now(UTC).isoformat(),
            "python_version": platform.python_version(),
            "experiment_manifest_sha256": _sha256_file(experiment_source),
            "source_audio_trial_manifest_sha256": _sha256_file(source_manifest_path),
            "scenario_count": len(experiment.scenarios),
            "source_trial_count": len(source_manifest.trials),
            "generated_trial_count": len(generated_trials),
            "generated_audio_bytes": generated_bytes,
            "scenarios": [
                {
                    "scenario_id": scenario.scenario_id,
                    "target": scenario.target,
                    "transforms": [
                        {
                            key: value
                            for key, value in operation.model_dump(mode="json").items()
                            if key != "impulse_response"
                        }
                        for operation in scenario.transforms
                    ],
                }
                for scenario in experiment.scenarios
            ],
            "trials": trial_records,
            "privacy_note": "Contains pseudonymous trial IDs, audio hashes and transformation metadata; no input paths, waveforms or embeddings.",
        }
        with sidecar.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(sidecar_payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        manifest_payload = source_manifest.model_dump(mode="json")
        manifest_payload["dataset_id"] = "condition-" + hashlib.sha256(
            _sha256_file(experiment_source).encode("ascii")
        ).hexdigest()[:20]
        manifest_payload["dataset_name"] = (
            source_manifest.dataset_name[:125] + " (audio conditions)"
        )[:160]
        manifest_payload["trials"] = [trial.model_dump(mode="json") for trial in generated_trials]
        manifest_payload["condition_provenance_file"] = "conditions-provenance.json"
        manifest_payload["condition_provenance_sha256"] = _sha256_file(sidecar)
        output_manifest = AudioTrialManifest.model_validate(manifest_payload)
        manifest_path = temporary / "audio-trials.json"
        with manifest_path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(
                output_manifest.model_dump(mode="json"),
                handle,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        temporary.rename(output)
        return output / "audio-trials.json"
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
