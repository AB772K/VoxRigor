from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from voxrigor.biometrics.audio import load_audio_file, resample_audio
from voxrigor.biometrics.contracts import AudioSignal
from voxrigor.biometrics.errors import AudioInputError
from voxrigor.biometrics.trials import AudioTrial, AudioTrialManifest


def base_asv(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "dataset_id": "local-asv-extra",
        "dataset_name": "Local ASV",
        "dataset_version": "1",
        "task": "asv",
        "protocol_id": "asv-extra",
        "model_id": "ecapa-tdnn",
        "evaluation_split": "test",
        "trials": [
            {
                "trial_id": "target",
                "label": "target",
                "enrollment_audio": "audio/a.wav",
                "probe_audio": "audio/b.wav",
            },
            {
                "trial_id": "nontarget",
                "label": "nontarget",
                "enrollment_audio": "audio/a.wav",
                "probe_audio": "audio/c.wav",
            },
        ],
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "field,value",
    [
        ("dataset_name", " "),
        ("dataset_version", " "),
        ("protocol_id", " "),
        ("license_name", " "),
    ],
)
def test_manifest_rejects_whitespace_metadata(field: str, value: str) -> None:
    with pytest.raises(ValueError):
        AudioTrialManifest.model_validate(base_asv(**{field: value}))


def test_manifest_rejects_invalid_source_url() -> None:
    with pytest.raises(ValueError, match="http or https"):
        AudioTrialManifest.model_validate(base_asv(source_url="javascript:alert(1)"))


def test_manifest_rejects_threshold_without_declared_source() -> None:
    with pytest.raises(ValueError, match="source to be declared"):
        AudioTrialManifest.model_validate(base_asv(operating_threshold=0.4))


def test_manifest_rejects_external_threshold_with_selection_split() -> None:
    with pytest.raises(ValueError, match="external threshold"):
        AudioTrialManifest.model_validate(
            base_asv(
                operating_threshold=0.4,
                threshold_source="external",
                threshold_selection_split="dev",
            )
        )


def test_manifest_rejects_development_threshold_without_named_splits() -> None:
    with pytest.raises(ValueError, match="named, separate"):
        AudioTrialManifest.model_validate(
            base_asv(
                evaluation_split="all",
                operating_threshold=0.4,
                threshold_source="development_split",
                threshold_selection_split="dev",
            )
        )


def test_manifest_rejects_development_threshold_without_selection_split() -> None:
    with pytest.raises(ValueError, match="named, separate"):
        AudioTrialManifest.model_validate(
            base_asv(
                operating_threshold=0.4,
                threshold_source="development_split",
            )
        )


def test_manifest_requires_group_columns_when_disjointness_requested() -> None:
    with pytest.raises(ValueError, match="group_columns are required"):
        AudioTrialManifest.model_validate(base_asv(require_group_disjointness=True))


def test_manifest_rejects_duplicate_group_columns() -> None:
    with pytest.raises(ValueError, match="must not contain duplicates"):
        AudioTrialManifest.model_validate(base_asv(group_columns=["speaker_id", "speaker_id"]))


def test_manifest_rejects_attack_species_on_asv_trial() -> None:
    payload = base_asv()
    payload["trials"][0]["attack_species"] = "replay"  # type: ignore[index]
    with pytest.raises(ValueError, match="only valid for PAD"):
        AudioTrialManifest.model_validate(payload)


def test_manifest_rejects_mixed_asv_and_pad_audio_fields() -> None:
    payload = base_asv()
    payload["trials"][0]["audio"] = "audio/mixed.wav"  # type: ignore[index]
    with pytest.raises(ValueError, match="ASV trials require"):
        AudioTrialManifest.model_validate(payload)


def test_trial_normalizes_blank_optional_identifiers() -> None:
    trial = AudioTrial(
        trial_id="trial",
        label="target",
        enrollment_audio="enroll.wav",
        probe_audio="probe.wav",
        speaker_id="  ",
        source_id=" ",
    )
    assert trial.speaker_id is None
    assert trial.source_id is None


def test_audio_signal_rejects_multidimensional_array() -> None:
    with pytest.raises(ValueError, match="one-dimensional"):
        AudioSignal(
            samples=np.zeros((2, 2), dtype=np.float32),
            sample_rate_hz=16000,
            source_sha256="a" * 64,
            source_format="wav",
        )


def test_audio_signal_rejects_nested_sample_lists() -> None:
    with pytest.raises(ValueError, match="numeric sequence"):
        AudioSignal(
            samples=[[0.1, 0.2], [0.3, 0.4]],
            sample_rate_hz=16000,
            source_sha256="a" * 64,
            source_format="wav",
        )


def test_same_rate_resampling_rejects_non_finite_audio() -> None:
    signal = AudioSignal(
        samples=np.asarray([0.1, np.nan], dtype=np.float32),
        sample_rate_hz=16000,
        source_sha256="a" * 64,
        source_format="wav",
    )
    with pytest.raises(AudioInputError, match="finite"):
        resample_audio(signal, 16000)


def test_audio_decoder_rejects_unsupported_sample_rate(tmp_path: Path) -> None:
    path = tmp_path / "low-rate.wav"
    sf.write(path, np.zeros(1000, dtype=np.float32), 4000)
    with pytest.raises(AudioInputError, match="outside the supported"):
        load_audio_file(path)


def test_audio_decoder_rejects_non_finite_float_samples(tmp_path: Path) -> None:
    path = tmp_path / "non-finite.wav"
    samples = np.asarray([0.0, np.nan, np.inf, -np.inf] * 500, dtype=np.float32)
    sf.write(path, samples, 16000, subtype="FLOAT")
    with pytest.raises(AudioInputError, match="NaN or infinite"):
        load_audio_file(path)


def test_audio_decoder_rejects_non_positive_duration_limit(tmp_path: Path) -> None:
    path = tmp_path / "short.wav"
    sf.write(path, np.zeros(1000, dtype=np.float32), 16000)
    with pytest.raises(AudioInputError, match="positive finite"):
        load_audio_file(path, max_duration_seconds=0)
