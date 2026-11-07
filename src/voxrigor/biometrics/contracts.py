"""Stable, backend-neutral contracts for biometric model inference."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Literal

ModelTask = Literal["speaker_verification", "presentation_attack_detection"]
ScoreDirection = Literal["higher_is_genuine"]


@dataclass(frozen=True, slots=True)
class ModelDescriptor:
    """Provenance and input/output semantics for a pretrained model."""

    model_id: str
    display_name: str
    task: ModelTask
    backend: str
    source_repository: str
    source_revision: str
    license_name: str
    expected_sample_rate_hz: int
    score_type: str
    score_direction: ScoreDirection = "higher_is_genuine"
    calibrated: bool = False
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible model metadata."""

        return asdict(self)


@dataclass(frozen=True, slots=True)
class AudioSignal:
    """Mono floating-point audio and non-identifying file provenance."""

    samples: object
    sample_rate_hz: int
    source_sha256: str
    source_format: str

    def __post_init__(self) -> None:
        if self.sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        if len(self.source_sha256) != 64:
            raise ValueError("source_sha256 must be a SHA-256 hex digest")
        try:
            int(self.source_sha256, 16)
        except ValueError as exc:
            raise ValueError("source_sha256 must be a SHA-256 hex digest") from exc
        if not self.source_format.strip():
            raise ValueError("source_format must not be blank")
        try:
            if len(self.samples) == 0:  # type: ignore[arg-type]
                raise ValueError("audio samples must not be empty")
        except TypeError as exc:
            raise ValueError("audio samples must be a sized one-dimensional sequence") from exc


@dataclass(frozen=True, slots=True)
class ModelScore:
    """A raw model score with explicit score semantics and source provenance."""

    model: ModelDescriptor
    score: float
    score_type: str
    score_direction: ScoreDirection
    calibrated: bool
    input_sha256: tuple[str, ...]
    preprocessing: tuple[str, ...]
    notes: tuple[str, ...] = ()
    model_artifact_sha256: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not math.isfinite(self.score):
            raise ValueError("model score must be finite")
        if not self.input_sha256:
            raise ValueError("at least one input hash is required")
        for value in (*self.input_sha256, *self.model_artifact_sha256):
            if len(value) != 64:
                raise ValueError("input and model artifact hashes must be SHA-256 hex digests")
            try:
                int(value, 16)
            except ValueError as exc:
                raise ValueError("input and model artifact hashes must be SHA-256 hex digests") from exc

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible score metadata without audio content."""

        return {
            "model": self.model.to_dict(),
            "score": self.score,
            "score_type": self.score_type,
            "score_direction": self.score_direction,
            "calibrated": self.calibrated,
            "input_sha256": list(self.input_sha256),
            "preprocessing": list(self.preprocessing),
            "notes": list(self.notes),
            "model_artifact_sha256": list(self.model_artifact_sha256),
        }
