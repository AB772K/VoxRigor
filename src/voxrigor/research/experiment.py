"""Versioned manifest loading for score-only research experiments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from voxrigor.benchmarking.dataset import ScoreDataset, load_score_dataset
from voxrigor.benchmarking.errors import BenchmarkError
from voxrigor.benchmarking.models import BenchmarkTask


class ResearchExperimentError(ValueError):
    """Raised when a research experiment is invalid or cannot be evaluated."""


class EvaluationDatasetReference(BaseModel):
    """One independent evaluation dataset and its domain/condition label."""

    model_config = ConfigDict(extra="forbid")

    domain_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,79}$")
    dataset_manifest: str = Field(min_length=1, max_length=500)

    @field_validator("dataset_manifest")
    @classmethod
    def validate_relative_manifest_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if (
            "\x00" in normalized
            or PurePosixPath(normalized).is_absolute()
            or PureWindowsPath(normalized).is_absolute()
            or PureWindowsPath(value).drive
            or ".." in PurePosixPath(normalized).parts
        ):
            raise ValueError(
                "dataset_manifest must be a relative path inside the experiment folder"
            )
        return normalized


class ClusterBootstrapConfig(BaseModel):
    """Reproducible cluster resampling settings for held-out evaluation uncertainty."""

    model_config = ConfigDict(extra="forbid")

    cluster_column: Literal["speaker_id", "source_id"]
    replicates: int = Field(default=1000, ge=100, le=5000)
    seed: int = Field(default=2026, ge=0, le=4294967295)
    confidence_level: float = Field(default=0.95, gt=0.5, lt=1, allow_inf_nan=False)


class ResearchExperimentManifest(BaseModel):
    """Experiment design that separates calibration data from evaluation data."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    experiment_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$")
    description: str = Field(min_length=1, max_length=1000)
    system_id: str = Field(min_length=1, max_length=120)
    calibration_dataset_manifest: str = Field(min_length=1, max_length=500)
    evaluation_datasets: list[EvaluationDatasetReference] = Field(min_length=2, max_length=20)
    target_fmr: float = Field(gt=0, lt=1, allow_inf_nan=False)
    probability_threshold: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    group_columns: list[Literal["speaker_id", "source_id"]] = Field(default_factory=list)
    require_group_disjointness: bool = False
    cluster_bootstrap: ClusterBootstrapConfig | None = None
    stratify_by_condition: bool = False

    @field_validator("calibration_dataset_manifest")
    @classmethod
    def validate_calibration_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if (
            "\x00" in normalized
            or PurePosixPath(normalized).is_absolute()
            or PureWindowsPath(normalized).is_absolute()
            or PureWindowsPath(value).drive
            or ".." in PurePosixPath(normalized).parts
        ):
            raise ValueError(
                "calibration_dataset_manifest must be a relative path inside the experiment folder"
            )
        return normalized

    @model_validator(mode="after")
    def validate_unique_evaluation_references(self) -> ResearchExperimentManifest:
        domains = [item.domain_id for item in self.evaluation_datasets]
        manifests = [item.dataset_manifest for item in self.evaluation_datasets]
        if len(set(domains)) != len(domains):
            raise ValueError("evaluation domain_id values must be unique")
        if len(set(manifests)) != len(manifests):
            raise ValueError("evaluation dataset_manifest paths must be unique")
        if len(set(self.group_columns)) != len(self.group_columns):
            raise ValueError("group_columns must not contain duplicates")
        if self.require_group_disjointness and not self.group_columns:
            raise ValueError("group_columns are required when group disjointness is enforced")
        if self.calibration_dataset_manifest in manifests:
            raise ValueError("calibration data must be separate from every evaluation manifest")
        return self


@dataclass(frozen=True, slots=True)
class LoadedEvaluationDataset:
    domain_id: str
    manifest_path: Path
    dataset: ScoreDataset


@dataclass(frozen=True, slots=True)
class LoadedResearchExperiment:
    manifest_path: Path
    manifest: ResearchExperimentManifest
    calibration_manifest_path: Path
    calibration_dataset: ScoreDataset
    evaluation_datasets: tuple[LoadedEvaluationDataset, ...]


def _resolve_child_path(root: Path, relative_path: str) -> Path:
    resolved_root = root.resolve()
    candidate = (resolved_root / relative_path).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ResearchExperimentError(
            "experiment dataset paths must remain inside the experiment folder"
        ) from exc
    if not candidate.is_file():
        raise ResearchExperimentError(f"declared dataset manifest does not exist: {relative_path}")
    return candidate


def load_research_experiment(path: Path) -> LoadedResearchExperiment:
    """Load a strict experiment manifest and all referenced score datasets."""

    manifest_path = path.resolve()
    if not manifest_path.is_file():
        raise ResearchExperimentError(f"research experiment manifest not found: {path}")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = ResearchExperimentManifest.model_validate(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ResearchExperimentError(
            "research experiment manifest is unreadable or invalid"
        ) from exc

    root = manifest_path.parent
    calibration_path = _resolve_child_path(root, manifest.calibration_dataset_manifest)
    evaluation_paths = [
        (reference, _resolve_child_path(root, reference.dataset_manifest))
        for reference in manifest.evaluation_datasets
    ]
    if len({calibration_path, *(item[1] for item in evaluation_paths)}) != 1 + len(
        evaluation_paths
    ):
        raise ResearchExperimentError("each experiment dataset manifest path must be unique")

    try:
        calibration = load_score_dataset(calibration_path)
        evaluations = tuple(
            LoadedEvaluationDataset(
                domain_id=reference.domain_id,
                manifest_path=dataset_path,
                dataset=load_score_dataset(dataset_path),
            )
            for reference, dataset_path in evaluation_paths
        )
    except (BenchmarkError, OSError, ValueError) as exc:
        raise ResearchExperimentError(
            "a referenced dataset manifest or score file failed validation"
        ) from exc

    all_datasets = [calibration, *(item.dataset for item in evaluations)]
    if any(dataset.manifest.task is not BenchmarkTask.ASV for dataset in all_datasets):
        raise ResearchExperimentError(
            "Phase 6 score-calibration experiments currently support ASV datasets only"
        )
    dataset_ids = [dataset.manifest.dataset_id for dataset in all_datasets]
    if len(set(dataset_ids)) != len(dataset_ids):
        raise ResearchExperimentError("dataset_id values must be unique within an experiment")

    return LoadedResearchExperiment(
        manifest_path=manifest_path,
        manifest=manifest,
        calibration_manifest_path=calibration_path,
        calibration_dataset=calibration,
        evaluation_datasets=evaluations,
    )
