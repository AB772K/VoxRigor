from __future__ import annotations

import math

import pytest

from voxrigor.biometrics.contracts import AudioSignal, ModelDescriptor, ModelScore


def descriptor() -> ModelDescriptor:
    return ModelDescriptor(
        model_id="test-model",
        display_name="Test model",
        task="speaker_verification",
        backend="test",
        source_repository="example/model",
        source_revision="a" * 40,
        license_name="MIT",
        expected_sample_rate_hz=16000,
        score_type="cosine_similarity",
    )


def test_audio_signal_rejects_invalid_sample_rate_and_format() -> None:
    with pytest.raises(ValueError, match="sample_rate_hz"):
        AudioSignal(samples=[0.1], sample_rate_hz=0, source_sha256="a" * 64, source_format="wav")
    with pytest.raises(ValueError, match="source_format"):
        AudioSignal(samples=[0.1], sample_rate_hz=16000, source_sha256="a" * 64, source_format=" ")


def test_audio_signal_rejects_empty_samples_and_bad_hash() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        AudioSignal(samples=[], sample_rate_hz=16000, source_sha256="a" * 64, source_format="wav")
    with pytest.raises(ValueError, match="SHA-256"):
        AudioSignal(samples=[0.1], sample_rate_hz=16000, source_sha256="z" * 64, source_format="wav")


@pytest.mark.parametrize("score", [math.nan, math.inf, -math.inf])
def test_model_score_rejects_non_finite_score(score: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        ModelScore(
            model=descriptor(),
            score=score,
            score_type="cosine_similarity",
            score_direction="higher_is_genuine",
            calibrated=False,
            input_sha256=("b" * 64,),
            preprocessing=("decode",),
        )


def test_model_score_requires_input_hash_and_valid_artifact_hash() -> None:
    with pytest.raises(ValueError, match="at least one input hash"):
        ModelScore(
            model=descriptor(),
            score=0.5,
            score_type="cosine_similarity",
            score_direction="higher_is_genuine",
            calibrated=False,
            input_sha256=(),
            preprocessing=("decode",),
        )
    with pytest.raises(ValueError, match="SHA-256"):
        ModelScore(
            model=descriptor(),
            score=0.5,
            score_type="cosine_similarity",
            score_direction="higher_is_genuine",
            calibrated=False,
            input_sha256=("b" * 64,),
            preprocessing=("decode",),
            model_artifact_sha256=("bad-hash",),
        )


def test_model_descriptor_and_score_serialize_without_waveforms() -> None:
    result = ModelScore(
        model=descriptor(),
        score=0.5,
        score_type="cosine_similarity",
        score_direction="higher_is_genuine",
        calibrated=False,
        input_sha256=("b" * 64,),
        preprocessing=("mono float32",),
    )
    payload = result.to_dict()
    assert payload["model"]["model_id"] == "test-model"
    assert payload["score"] == 0.5
    assert "samples" not in payload
