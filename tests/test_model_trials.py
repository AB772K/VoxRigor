from __future__ import annotations

import json
from pathlib import Path

import pytest

from voxrigor.biometrics.batch import TrialManifestError, load_audio_trial_manifest
from voxrigor.biometrics.trials import AudioTrial, AudioTrialManifest


def base_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "dataset_id": "local-asv-test",
        "dataset_name": "Local ASV",
        "dataset_version": "1",
        "task": "asv",
        "protocol_id": "asv-v1",
        "model_id": "ecapa-tdnn",
        "evaluation_split": "test",
        "trials": [
            {
                "trial_id": "target-1",
                "label": "target",
                "enrollment_audio": "audio/enroll.wav",
                "probe_audio": "audio/probe.wav",
            },
            {
                "trial_id": "nontarget-1",
                "label": "nontarget",
                "enrollment_audio": "audio/enroll.wav",
                "probe_audio": "audio/impostor.wav",
            },
        ],
    }
    payload.update(overrides)
    return payload


def test_asv_manifest_parses_and_normalizes_labels() -> None:
    payload = base_manifest()
    trials = payload["trials"]
    assert isinstance(trials, list)
    trials[0]["label"] = " TARGET "
    manifest = AudioTrialManifest.model_validate(payload)
    assert manifest.trials[0].label == "target"
    assert manifest.trials[0].enrollment_audio == "audio/enroll.wav"


@pytest.mark.parametrize(
    "audio_path",
    [
        "../outside.wav",
        "/etc/passwd",
        r"C:\private\voice.wav",
        r"C:relative-drive-path.wav",
        "folder/../../secret.wav",
    ],
)
def test_audio_trial_rejects_unsafe_paths(audio_path: str) -> None:
    with pytest.raises(ValueError, match="relative|traverse"):
        AudioTrial(
            trial_id="trial-1",
            label="target",
            enrollment_audio=audio_path,
            probe_audio="probe.wav",
        )


def test_manifest_rejects_duplicate_trial_ids() -> None:
    payload = base_manifest()
    payload["trials"][1]["trial_id"] = "target-1"  # type: ignore[index]
    with pytest.raises(ValueError, match="unique"):
        AudioTrialManifest.model_validate(payload)


def test_manifest_rejects_asv_pad_model_mismatch() -> None:
    with pytest.raises(ValueError, match="ASV audio trials require"):
        AudioTrialManifest.model_validate(base_manifest(model_id="aasist-l-onnx"))


def test_manifest_rejects_unknown_asv_label() -> None:
    payload = base_manifest()
    payload["trials"][0]["label"] = "spoof"  # type: ignore[index]
    with pytest.raises(ValueError, match="invalid asv label"):
        AudioTrialManifest.model_validate(payload)


def test_pad_manifest_requires_attack_species_and_threshold() -> None:
    payload = {
        "dataset_id": "local-pad-test",
        "dataset_name": "Local PAD",
        "dataset_version": "1",
        "task": "pad",
        "protocol_id": "pad-v1",
        "model_id": "aasist-l-onnx",
        "trials": [
            {"trial_id": "b", "label": "bonafide", "audio": "audio/b.wav"},
            {"trial_id": "s", "label": "spoof", "audio": "audio/s.wav"},
        ],
    }
    with pytest.raises(ValueError, match="attack_species"):
        AudioTrialManifest.model_validate(payload)
    payload["trials"][1]["attack_species"] = "replay"  # type: ignore[index]
    with pytest.raises(ValueError, match="predeclared operating threshold"):
        AudioTrialManifest.model_validate(payload)


def test_manifest_rejects_incorrect_threshold_provenance() -> None:
    payload = base_manifest(
        operating_threshold=0.5,
        threshold_source="development_split",
        threshold_selection_split="test",
    )
    with pytest.raises(ValueError, match="must differ"):
        AudioTrialManifest.model_validate(payload)


def test_manifest_load_errors_are_normalized(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(TrialManifestError, match="missing, unreadable or invalid"):
        load_audio_trial_manifest(missing)
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(TrialManifestError, match="missing, unreadable or invalid"):
        load_audio_trial_manifest(broken)


def test_manifest_rejects_parent_traversal_after_backslash_normalization() -> None:
    with pytest.raises(ValueError, match="relative|traverse"):
        AudioTrial(
            trial_id="trial-1",
            label="target",
            enrollment_audio=r"folder\..\..\private.wav",
            probe_audio="probe.wav",
        )
