from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import soundfile as sf

import voxrigor.biometrics.batch as batch
from voxrigor.benchmarking.dataset import load_score_dataset
from voxrigor.benchmarking.errors import ScoreFileError
from voxrigor.benchmarking.reporting import build_benchmark_report
from voxrigor.biometrics.batch import load_audio_trial_manifest
from voxrigor.biometrics.conditions import (
    AudioConditionExperiment,
    ConditionManifestError,
    GaussianNoiseTransform,
    MuLawTransform,
    ResampleTransform,
    ReverberationTransform,
    _apply_chain,
    _apply_one,
    generate_condition_dataset,
)
from voxrigor.biometrics.contracts import AudioSignal, ModelDescriptor, ModelScore
from voxrigor.biometrics.errors import AudioInputError


def make_signal(
    sample_rate_hz: int = 16000,
    seconds: float = 0.5,
    *,
    phase: float = 0.0,
) -> AudioSignal:
    count = int(sample_rate_hz * seconds)
    time = np.arange(count, dtype=np.float32) / sample_rate_hz
    samples = 0.35 * np.sin(2 * np.pi * 220.0 * time + phase)
    return AudioSignal(
        samples=samples.astype(np.float32),
        sample_rate_hz=sample_rate_hz,
        source_sha256=hashlib.sha256(f"{sample_rate_hz}:{phase}".encode()).hexdigest(),
        source_format="wav",
    )


def write_wav(path: Path, signal: AudioSignal) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, signal.samples, signal.sample_rate_hz, subtype="FLOAT")


def make_source_manifest(root: Path) -> Path:
    audio = root / "source-audio"
    audio.mkdir(parents=True)
    signals = {
        "enroll.wav": make_signal(phase=0.0),
        "probe-target.wav": make_signal(phase=0.05),
        "probe-nontarget.wav": make_signal(phase=1.5),
    }
    for name, signal in signals.items():
        write_wav(audio / name, signal)
    payload = {
        "dataset_id": "local-asv-conditions",
        "dataset_name": "Local ASV conditions test",
        "dataset_version": "1",
        "task": "asv",
        "protocol_id": "local-asv-v1",
        "model_id": "ecapa-tdnn",
        "evaluation_split": "test",
        "license_name": "synthetic-test-fixture",
        "trials": [
            {
                "trial_id": "trial-target",
                "label": "target",
                "split": "test",
                "enrollment_audio": "source-audio/enroll.wav",
                "probe_audio": "source-audio/probe-target.wav",
                "speaker_id": "speaker-a",
                "source_id": "source-a",
            },
            {
                "trial_id": "trial-nontarget",
                "label": "nontarget",
                "split": "test",
                "enrollment_audio": "source-audio/enroll.wav",
                "probe_audio": "source-audio/probe-nontarget.wav",
                "speaker_id": "speaker-a",
                "source_id": "source-b",
            },
        ],
    }
    path = root / "source-trials.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def make_experiment(root: Path, source_manifest: Path) -> Path:
    payload = {
        "schema_version": "0.1",
        "source_manifest": source_manifest.name,
        "scenarios": [
            {"scenario_id": "clean", "target": "probe", "transforms": []},
            {
                "scenario_id": "noise-20db",
                "target": "probe",
                "transforms": [{"kind": "gaussian_noise", "snr_db": 20.0, "seed": 1122}],
            },
            {
                "scenario_id": "telephony-mulaw",
                "target": "probe",
                "transforms": [{"kind": "mulaw"}],
            },
        ],
    }
    path = root / "conditions.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_resample_transform_changes_rate_and_sample_count(tmp_path: Path) -> None:
    original = make_signal()
    transformed, record = _apply_one(
        original,
        ResampleTransform(kind="resample", target_sample_rate_hz=8000),
        tmp_path,
        effective_seed=None,
    )
    assert transformed.sample_rate_hz == 8000
    assert transformed.samples.shape == (4000,)
    assert record["input_sample_rate_hz"] == 16000
    assert record["output_sample_rate_hz"] == 8000
    assert record["input_sample_sha256"] != record["output_sample_sha256"]


def test_gaussian_noise_is_reproducible_and_uses_effective_seed(tmp_path: Path) -> None:
    original = make_signal()
    operation = GaussianNoiseTransform(kind="gaussian_noise", snr_db=18.0, seed=99)
    first, first_record = _apply_one(original, operation, tmp_path, effective_seed=123456)
    second, second_record = _apply_one(original, operation, tmp_path, effective_seed=123456)
    third, _ = _apply_one(original, operation, tmp_path, effective_seed=123457)
    assert np.array_equal(first.samples, second.samples)
    assert not np.array_equal(first.samples, third.samples)
    assert first_record == second_record
    assert first_record["seed"] == 123456


def test_gaussian_noise_rejects_silent_input(tmp_path: Path) -> None:
    silent = AudioSignal(
        samples=np.zeros(1000, dtype=np.float32),
        sample_rate_hz=16000,
        source_sha256="a" * 64,
        source_format="wav",
    )
    with pytest.raises(AudioInputError, match="non-silent"):
        _apply_one(
            silent,
            GaussianNoiseTransform(kind="gaussian_noise", snr_db=20.0, seed=1),
            tmp_path,
            effective_seed=1,
        )


def test_mulaw_transform_is_narrowband_and_quantized(tmp_path: Path) -> None:
    original = make_signal()
    transformed, record = _apply_one(
        original, MuLawTransform(kind="mulaw"), tmp_path, effective_seed=None
    )
    assert transformed.sample_rate_hz == 8000
    assert transformed.samples.size == original.samples.size // 2
    assert record["kind"] == "mulaw"
    assert np.max(np.abs(transformed.samples)) <= 1.0


def test_mulaw_refuses_over_range_audio_without_clipping(tmp_path: Path) -> None:
    original = AudioSignal(
        samples=np.full(8000, 1.2, dtype=np.float32),
        sample_rate_hz=8000,
        source_sha256="b" * 64,
        source_format="wav",
    )
    with pytest.raises(AudioInputError, match="no clipping"):
        _apply_one(original, MuLawTransform(kind="mulaw"), tmp_path, effective_seed=None)


def test_reverberation_uses_local_ir_and_records_its_hash(tmp_path: Path) -> None:
    original = make_signal()
    ir_path = tmp_path / "impulse.wav"
    ir = AudioSignal(
        samples=np.asarray([1.0, 0.4, 0.2, 0.1], dtype=np.float32),
        sample_rate_hz=16000,
        source_sha256="c" * 64,
        source_format="wav",
    )
    write_wav(ir_path, ir)
    transformed, record = _apply_one(
        original,
        ReverberationTransform(kind="reverberation", impulse_response="impulse.wav", wet_mix=0.5),
        tmp_path,
        effective_seed=None,
    )
    assert transformed.samples.size == original.samples.size + 3
    assert transformed.sample_rate_hz == original.sample_rate_hz
    assert record["impulse_response_sha256"] == hashlib.sha256(ir_path.read_bytes()).hexdigest()
    assert "impulse_response" not in record
    assert np.isfinite(transformed.samples).all()


def test_reverberation_rejects_ir_with_wrong_sample_rate(tmp_path: Path) -> None:
    sf.write(tmp_path / "impulse.wav", np.ones(100, dtype=np.float32), 8000, subtype="FLOAT")
    with pytest.raises(AudioInputError, match="same sample rate"):
        _apply_one(
            make_signal(16000),
            ReverberationTransform(
                kind="reverberation", impulse_response="impulse.wav", wet_mix=0.5
            ),
            tmp_path,
            effective_seed=None,
        )


def test_condition_manifest_requires_clean_baseline_and_unique_scenarios() -> None:
    with pytest.raises(ValueError, match="clean scenario"):
        AudioConditionExperiment.model_validate(
            {
                "source_manifest": "source.json",
                "scenarios": [{"scenario_id": "noise", "transforms": []}],
            }
        )
    with pytest.raises(ValueError, match="unique"):
        AudioConditionExperiment.model_validate(
            {
                "source_manifest": "source.json",
                "scenarios": [
                    {"scenario_id": "clean", "transforms": []},
                    {"scenario_id": "clean", "transforms": []},
                ],
            }
        )


@pytest.mark.parametrize("path", ["../outside.wav", "/etc/passwd", r"C:\secret\ir.wav"])
def test_reverberation_manifest_rejects_unsafe_ir_paths(path: str) -> None:
    with pytest.raises(ValueError, match="relative path"):
        ReverberationTransform(kind="reverberation", impulse_response=path)


def test_transform_chain_records_order_and_derived_noise_seed(tmp_path: Path) -> None:
    original = make_signal()
    operations = [
        ResampleTransform(kind="resample", target_sample_rate_hz=8000),
        GaussianNoiseTransform(kind="gaussian_noise", snr_db=25.0, seed=42),
    ]
    first, records = _apply_chain(original, operations, tmp_path, trial_id="trial-1", role="probe")
    second, records_2 = _apply_chain(
        original, operations, tmp_path, trial_id="trial-1", role="probe"
    )
    assert np.array_equal(first.samples, second.samples)
    assert [item["kind"] for item in records] == ["resample", "gaussian_noise"]
    assert records == records_2
    assert records[1]["seed"] == records_2[1]["seed"]


def _install_fake_ecapa(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeECAPA:
        def __init__(self, **_kwargs: Any) -> None:
            self.descriptor = ModelDescriptor(
                model_id="ecapa-tdnn",
                display_name="Test ECAPA",
                task="speaker_verification",
                backend="deterministic-test",
                source_repository="test/model",
                source_revision="d" * 40,
                license_name="MIT",
                expected_sample_rate_hz=16000,
                score_type="cosine_similarity",
            )

        def load(self) -> None:
            return None

        def score(self, enrollment: AudioSignal, probe: AudioSignal) -> ModelScore:
            return ModelScore(
                model=self.descriptor,
                score=0.5,
                score_type="cosine_similarity",
                score_direction="higher_is_genuine",
                calibrated=False,
                input_sha256=(enrollment.source_sha256, probe.source_sha256),
                preprocessing=("Phase 4 generated FLOAT WAV decoded locally",),
                model_artifact_sha256=("e" * 64,),
            )

        def unload(self) -> None:
            return None

    monkeypatch.setattr(batch, "ECAPATDNNAdapter", FakeECAPA)


def test_generate_conditions_and_run_phase2_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_manifest = make_source_manifest(tmp_path)
    experiment = make_experiment(tmp_path, source_manifest)
    generated_path = generate_condition_dataset(experiment, tmp_path / "condition-output")
    generated = load_audio_trial_manifest(generated_path)
    assert len(generated.trials) == 6
    assert generated.condition_provenance_file == "conditions-provenance.json"
    sidecar_path = generated_path.parent / generated.condition_provenance_file
    assert (
        hashlib.sha256(sidecar_path.read_bytes()).hexdigest()
        == generated.condition_provenance_sha256
    )
    sidecar_text = sidecar_path.read_text(encoding="utf-8")
    assert "source-audio/" not in sidecar_text
    sidecar_document = json.loads(sidecar_text)
    assert not any("waveform" in key.lower() for key in sidecar_document)
    assert "embeddings" not in sidecar_document
    assert {trial.condition for trial in generated.trials} == {
        "clean",
        "noise-20db",
        "telephony-mulaw",
    }
    assert len({trial.trial_id for trial in generated.trials}) == 6
    for trial in generated.trials:
        assert trial.enrollment_audio and trial.probe_audio
        assert (generated_path.parent / trial.enrollment_audio).is_file()
        assert (generated_path.parent / trial.probe_audio).is_file()

    _install_fake_ecapa(monkeypatch)
    inference_dir = batch.run_trial_inference(
        generated_path,
        tmp_path / "inference-output",
        cache_dir=tmp_path / "model-cache",
    )
    dataset = load_score_dataset(inference_dir / "benchmark.json")
    assert len(dataset.records) == 6
    assert dataset.manifest.score_producer is not None
    assert dataset.manifest.score_producer.condition_provenance_file == "condition-provenance.json"
    report, _ = build_benchmark_report(dataset)
    assert report.provenance["condition_provenance_sha256"] == generated.condition_provenance_sha256


def test_phase2_rejects_modified_condition_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_manifest = make_source_manifest(tmp_path)
    experiment = make_experiment(tmp_path, source_manifest)
    generated_path = generate_condition_dataset(experiment, tmp_path / "condition-output")
    _install_fake_ecapa(monkeypatch)
    inference_dir = batch.run_trial_inference(
        generated_path,
        tmp_path / "inference-output",
        cache_dir=tmp_path / "cache",
    )
    sidecar = inference_dir / "condition-provenance.json"
    sidecar.write_text(sidecar.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ScoreFileError, match="Audio-condition provenance sidecar"):
        load_score_dataset(inference_dir / "benchmark.json")


def test_generate_conditions_refuses_to_overwrite(tmp_path: Path) -> None:
    source_manifest = make_source_manifest(tmp_path)
    experiment = make_experiment(tmp_path, source_manifest)
    output = tmp_path / "condition-output"
    output.mkdir()
    with pytest.raises(ConditionManifestError, match="overwrite"):
        generate_condition_dataset(experiment, output)
