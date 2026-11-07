"""Validated, local-only audio decoding and deterministic preprocessing."""

from __future__ import annotations

import hashlib
import math
from fractions import Fraction
from pathlib import Path
from typing import Any

from voxrigor.biometrics.contracts import AudioSignal
from voxrigor.biometrics.errors import AudioInputError, OptionalDependencyError

DEFAULT_MAX_DURATION_SECONDS = 120.0
SUPPORTED_MIN_SAMPLE_RATE = 8_000
SUPPORTED_MAX_SAMPLE_RATE = 192_000
AASIST_SAMPLE_RATE_HZ = 16_000
AASIST_L_WINDOW_SAMPLES = 64_600


def _numpy() -> Any:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise OptionalDependencyError(
            "Audio operations require NumPy. Install with: pip install 'voxrigor[audio]'"
        ) from exc
    return np


def sha256_path(path: Path) -> str:
    """Hash a file in bounded memory."""

    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise AudioInputError("Could not read the audio file") from exc
    return digest.hexdigest()


def load_audio_file(
    path: Path,
    *,
    max_duration_seconds: float = DEFAULT_MAX_DURATION_SECONDS,
) -> AudioSignal:
    """Decode a local audio file to mono float32 without amplitude normalization."""

    np = _numpy()
    try:
        import soundfile as sf  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise OptionalDependencyError(
            "Audio decoding requires SoundFile. Install with: pip install 'voxrigor[audio]'"
        ) from exc

    source = Path(path).expanduser()
    if not source.is_file():
        raise AudioInputError("Audio input file does not exist or is not a regular file")
    if not math.isfinite(max_duration_seconds) or max_duration_seconds <= 0:
        raise AudioInputError("max_duration_seconds must be a positive finite number")

    try:
        info = sf.info(str(source))
        if info.frames <= 0 or info.channels <= 0:
            raise AudioInputError("Audio file contains no frames or channels")
        if not SUPPORTED_MIN_SAMPLE_RATE <= int(info.samplerate) <= SUPPORTED_MAX_SAMPLE_RATE:
            raise AudioInputError("Audio sample rate is outside the supported 8–192 kHz range")
        duration = info.frames / float(info.samplerate)
        if duration > max_duration_seconds:
            raise AudioInputError(
                f"Audio duration exceeds the configured {max_duration_seconds:g}-second limit"
            )
        decoded, sample_rate = sf.read(
            str(source), dtype="float32", always_2d=True, fill_value=None
        )
    except AudioInputError:
        raise
    except Exception as exc:
        raise AudioInputError("Audio file could not be decoded by SoundFile") from exc

    if decoded.ndim != 2 or decoded.shape[0] == 0:
        raise AudioInputError("Decoded audio has an invalid shape")
    mono = decoded[:, 0] if decoded.shape[1] == 1 else decoded.mean(axis=1, dtype=np.float32)
    mono = np.ascontiguousarray(mono, dtype=np.float32)
    if not np.isfinite(mono).all():
        raise AudioInputError("Audio contains NaN or infinite samples")
    if mono.size == 0:
        raise AudioInputError("Audio contains no usable samples")

    return AudioSignal(
        samples=mono,
        sample_rate_hz=int(sample_rate),
        source_sha256=sha256_path(source),
        source_format=source.suffix.lower().lstrip(".") or "unknown",
    )


def resample_audio(signal: AudioSignal, target_sample_rate_hz: int) -> AudioSignal:
    """Resample mono audio with polyphase filtering and preserve source identity."""

    np = _numpy()
    if target_sample_rate_hz <= 0:
        raise AudioInputError("Target sample rate must be positive")
    if signal.sample_rate_hz == target_sample_rate_hz:
        samples = np.ascontiguousarray(signal.samples, dtype=np.float32)
        return AudioSignal(
            samples=samples,
            sample_rate_hz=target_sample_rate_hz,
            source_sha256=signal.source_sha256,
            source_format=signal.source_format,
        )
    try:
        from scipy.signal import resample_poly  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise OptionalDependencyError(
            "Resampling requires SciPy. Install with: pip install 'voxrigor[audio]'"
        ) from exc

    ratio = Fraction(target_sample_rate_hz, signal.sample_rate_hz)
    try:
        resampled = resample_poly(
            np.asarray(signal.samples, dtype=np.float32), ratio.numerator, ratio.denominator
        )
    except Exception as exc:
        raise AudioInputError("Audio resampling failed") from exc
    output = np.ascontiguousarray(resampled, dtype=np.float32)
    if output.size == 0 or not np.isfinite(output).all():
        raise AudioInputError("Resampling produced empty or non-finite audio")
    return AudioSignal(
        samples=output,
        sample_rate_hz=target_sample_rate_hz,
        source_sha256=signal.source_sha256,
        source_format=signal.source_format,
    )


def prepare_aasist_l_window(signal: AudioSignal) -> object:
    """Prepare the reference AASIST-L 64,600-sample evaluation window."""

    np = _numpy()
    normalized = resample_audio(signal, AASIST_SAMPLE_RATE_HZ)
    samples = np.asarray(normalized.samples, dtype=np.float32).reshape(-1)
    if samples.size == 0:
        raise AudioInputError("AASIST-L cannot process an empty waveform")
    if samples.size >= AASIST_L_WINDOW_SAMPLES:
        fixed = samples[:AASIST_L_WINDOW_SAMPLES]
    else:
        repeats = (AASIST_L_WINDOW_SAMPLES + samples.size - 1) // samples.size
        fixed = np.tile(samples, repeats)[:AASIST_L_WINDOW_SAMPLES]
    return np.ascontiguousarray(fixed.reshape(1, AASIST_L_WINDOW_SAMPLES), dtype=np.float32)
