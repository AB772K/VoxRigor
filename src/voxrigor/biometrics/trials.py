"""Validated, path-safe audio-trial manifests for model-backed inference."""

from __future__ import annotations

from datetime import date
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from voxrigor.benchmarking.models import BenchmarkTask, ThresholdSource


class AudioTrial(BaseModel):
    """One pseudonymized ASV comparison or PAD audio trial."""

    model_config = ConfigDict(extra="forbid")
    trial_id: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=32)
    split: str = Field(default="test", min_length=1, max_length=80)
    condition: str = Field(default="unspecified", min_length=1, max_length=120)
    audio: str | None = None
    enrollment_audio: str | None = None
    probe_audio: str | None = None
    attack_species: str | None = Field(default=None, max_length=120)
    speaker_id: str | None = Field(default=None, max_length=160)
    source_id: str | None = Field(default=None, max_length=160)

    @field_validator("trial_id", "split", "condition")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must contain a non-whitespace character")
        return cleaned

    @field_validator("label")
    @classmethod
    def normalize_label(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("label must not be blank")
        return cleaned

    @field_validator(
        "audio", "enrollment_audio", "probe_audio", "attack_species", "speaker_id", "source_id"
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("audio", "enrollment_audio", "probe_audio")
    @classmethod
    def require_safe_relative_audio_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
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
            raise ValueError("audio paths must be relative and must not traverse parent folders")
        return normalized


class AudioTrialManifest(BaseModel):
    """Dataset metadata and relative audio paths consumed by score-trials."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["0.1"] = "0.1"
    dataset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$")
    dataset_name: str = Field(min_length=1, max_length=160)
    dataset_version: str = Field(min_length=1, max_length=80)
    task: BenchmarkTask
    protocol_id: str = Field(min_length=1, max_length=120)
    model_id: Literal["ecapa-tdnn", "aasist-l-onnx"]
    evaluation_split: str = Field(default="test", min_length=1, max_length=80)
    operating_threshold: float | None = None
    threshold_source: ThresholdSource = ThresholdSource.NOT_PROVIDED
    threshold_selection_split: str | None = Field(default=None, max_length=80)
    source_url: str | None = Field(default=None, max_length=1000)
    license_name: str = Field(default="unspecified", min_length=1, max_length=160)
    citation: str | None = Field(default=None, max_length=2000)
    access_date: date | None = None
    require_group_disjointness: bool = False
    group_columns: list[Literal["speaker_id", "source_id"]] = Field(default_factory=list)
    condition_provenance_file: str | None = Field(default=None, max_length=500)
    condition_provenance_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    trials: list[AudioTrial] = Field(min_length=2)

    @field_validator(
        "dataset_name", "dataset_version", "protocol_id", "evaluation_split", "license_name"
    )
    @classmethod
    def reject_whitespace_only(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must contain a non-whitespace character")
        return cleaned

    @field_validator("threshold_selection_split")
    @classmethod
    def normalize_threshold_split(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("threshold_selection_split must not be blank")
        return cleaned

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from urllib.parse import urlparse

        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source_url must be an http or https URL")
        return value

    @field_validator("condition_provenance_file")
    @classmethod
    def validate_condition_provenance_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
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
            raise ValueError("condition provenance path must be relative to the manifest directory")
        return normalized

    @model_validator(mode="after")
    def validate_trials_and_threshold(self) -> AudioTrialManifest:
        if (self.condition_provenance_file is None) != (self.condition_provenance_sha256 is None):
            raise ValueError("condition provenance file and SHA-256 must be provided together")
        if self.task is BenchmarkTask.ASV and self.model_id != "ecapa-tdnn":
            raise ValueError("ASV audio trials require model_id='ecapa-tdnn'")
        if self.task is BenchmarkTask.PAD and self.model_id != "aasist-l-onnx":
            raise ValueError("PAD audio trials require model_id='aasist-l-onnx'")
        if len({trial.trial_id for trial in self.trials}) != len(self.trials):
            raise ValueError("trial_id values must be unique")
        allowed = (
            {"target", "nontarget"} if self.task is BenchmarkTask.ASV else {"bonafide", "spoof"}
        )
        for trial in self.trials:
            if trial.label not in allowed:
                raise ValueError(f"trial {trial.trial_id!r} has an invalid {self.task.value} label")
            if self.task is BenchmarkTask.ASV:
                if not trial.enrollment_audio or not trial.probe_audio or trial.audio:
                    raise ValueError("ASV trials require enrollment_audio and probe_audio only")
                if trial.attack_species:
                    raise ValueError("attack_species is only valid for PAD trials")
            else:
                if not trial.audio or trial.enrollment_audio or trial.probe_audio:
                    raise ValueError("PAD trials require audio and must not contain ASV paths")
                if trial.label == "spoof" and not trial.attack_species:
                    raise ValueError("every PAD spoof trial requires attack_species")
        if len(set(self.group_columns)) != len(self.group_columns):
            raise ValueError("group_columns must not contain duplicates")
        if self.require_group_disjointness and not self.group_columns:
            raise ValueError("group_columns are required when group disjointness is enforced")
        if self.operating_threshold is None:
            if self.threshold_source is not ThresholdSource.NOT_PROVIDED:
                raise ValueError("threshold_source must be not_provided without a threshold")
            if self.threshold_selection_split is not None:
                raise ValueError("threshold_selection_split requires an operating threshold")
        else:
            if self.threshold_source is ThresholdSource.NOT_PROVIDED:
                raise ValueError("an operating threshold requires its source to be declared")
            if self.threshold_source is ThresholdSource.DEVELOPMENT_SPLIT:
                if self.evaluation_split == "all" or not self.threshold_selection_split:
                    raise ValueError(
                        "development threshold requires named, separate selection and evaluation splits"
                    )
                if self.threshold_selection_split == self.evaluation_split:
                    raise ValueError("threshold selection split must differ from evaluation split")
            elif self.threshold_selection_split is not None:
                raise ValueError("external threshold must not specify a selection split")
        if self.task is BenchmarkTask.PAD and self.operating_threshold is None:
            raise ValueError("PAD inference requires a predeclared operating threshold")
        return self
