from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from voxrigor.biometrics.audio import (
    AASIST_L_WINDOW_SAMPLES,
    load_audio_file,
    prepare_aasist_l_window,
    resample_audio,
)
from voxrigor.biometrics.contracts import AudioSignal
from voxrigor.biometrics.errors import AudioInputError


def test_load_audio_file_converts_stereo_to_mono_and_hashes_source(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    stereo = np.column_stack((np.ones(1600), -np.ones(1600))).astype(np.float32) * 0.25
    sf.write(path, stereo, 16000, subtype="FLOAT")

    signal = load_audio_file(path)

    assert signal.sample_rate_hz == 16000
    assert signal.samples.shape == (1600,)
    assert np.allclose(signal.samples, 0.0, atol=1e-6)
    assert len(signal.source_sha256) == 64
    assert signal.source_format == "wav"


def test_audio_decoder_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(AudioInputError, match="does not exist"):
        load_audio_file(tmp_path / "missing.wav")


def test_audio_decoder_enforces_duration_limit(tmp_path: Path) -> None:
    path = tmp_path / "long.wav"
    sf.write(path, np.zeros(16000, dtype=np.float32), 16000)
    with pytest.raises(AudioInputError, match="duration exceeds"):
        load_audio_file(path, max_duration_seconds=0.5)


def test_resample_audio_preserves_source_hash_and_expected_length() -> None:
    original = AudioSignal(
        samples=np.ones(8000, dtype=np.float32),
        sample_rate_hz=8000,
        source_sha256="a" * 64,
        source_format="wav",
    )
    converted = resample_audio(original, 16000)
    assert converted.sample_rate_hz == 16000
    assert converted.samples.shape == (16000,)
    assert converted.source_sha256 == original.source_sha256


def test_aasist_window_tiles_short_audio_and_truncates_long_audio() -> None:
    short = AudioSignal(
        samples=np.array([0.25, -0.25], dtype=np.float32),
        sample_rate_hz=16000,
        source_sha256="b" * 64,
        source_format="wav",
    )
    tiled = prepare_aasist_l_window(short)
    assert tiled.shape == (1, AASIST_L_WINDOW_SAMPLES)
    assert np.array_equal(tiled[0, :6], np.array([0.25, -0.25] * 3, dtype=np.float32))

    long_samples = np.arange(AASIST_L_WINDOW_SAMPLES + 100, dtype=np.float32)
    long = AudioSignal(
        samples=long_samples,
        sample_rate_hz=16000,
        source_sha256="c" * 64,
        source_format="wav",
    )
    truncated = prepare_aasist_l_window(long)
    assert truncated.shape == (1, AASIST_L_WINDOW_SAMPLES)
    assert np.array_equal(truncated[0], long_samples[:AASIST_L_WINDOW_SAMPLES])


@pytest.mark.parametrize(
    ("frames", "channels", "message"),
    [
        (48_000, 9, "channel count exceeds"),
        (40_000_000, 1, "128 MiB memory limit"),
    ],
)
def test_audio_decoder_rejects_oversized_decode_before_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    frames: int,
    channels: int,
    message: str,
) -> None:
    path = tmp_path / "oversized.wav"
    path.write_bytes(b"fixture")
    read_called = False

    def fake_info(_path: str) -> SimpleNamespace:
        return SimpleNamespace(frames=frames, channels=channels, samplerate=48_000)

    def fail_read(*_args: object, **_kwargs: object) -> None:
        nonlocal read_called
        read_called = True
        raise AssertionError("decoder must reject metadata before allocating the sample buffer")

    monkeypatch.setattr(sf, "info", fake_info)
    monkeypatch.setattr(sf, "read", fail_read)

    with pytest.raises(AudioInputError, match=message):
        load_audio_file(path)

    assert not read_called
