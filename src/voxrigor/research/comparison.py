"""Paired comparison of multiple ASV research experiments on identical trial sets."""

from __future__ import annotations

import html
import json
import os
import platform
import random
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from voxrigor import __version__
from voxrigor.benchmarking.dataset import ScoreDataset, ScoreTrial
from voxrigor.benchmarking.errors import MetricError
from voxrigor.benchmarking.metrics import evaluate_scores
from voxrigor.benchmarking.models import BenchmarkTask, ScoreDirection
from voxrigor.research.experiment import (
    LoadedResearchExperiment,
    ResearchExperimentError,
    load_research_experiment,
)
from voxrigor.research.runner import _operating_rates, build_research_report


class ComparisonSystemReference(BaseModel):
    """One model/system's independently calibrated experiment manifest."""

    model_config = ConfigDict(extra="forbid")

    system_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,79}$")
    experiment_manifest: str = Field(min_length=1, max_length=500)

    @field_validator("experiment_manifest")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if (
            "\x00" in normalized
            or PurePosixPath(normalized).is_absolute()
            or PureWindowsPath(normalized).is_absolute()
            or PureWindowsPath(value).drive
            or ".." in PurePosixPath(normalized).parts
        ):
            raise ValueError("experiment_manifest must be a relative path inside the comparison folder")
        return normalized


class PairedComparisonBootstrapConfig(BaseModel):
    """Cluster bootstrap settings for paired metric differences between systems."""

    model_config = ConfigDict(extra="forbid")

    cluster_column: Literal["speaker_id", "source_id"]
    replicates: int = Field(default=1000, ge=100, le=5000)
    seed: int = Field(default=2026, ge=0, le=4294967295)
    confidence_level: float = Field(default=0.95, gt=0.5, lt=1, allow_inf_nan=False)


class ResearchComparisonManifest(BaseModel):
    """A paired, multi-system comparison with model-specific calibration."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = "0.1"
    comparison_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$")
    description: str = Field(min_length=1, max_length=1000)
    reference_system_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,79}$")
    systems: list[ComparisonSystemReference] = Field(min_length=2, max_length=8)
    paired_cluster_bootstrap: PairedComparisonBootstrapConfig | None = None

    @model_validator(mode="after")
    def validate_system_references(self) -> ResearchComparisonManifest:
        system_ids = [item.system_id for item in self.systems]
        manifests = [item.experiment_manifest for item in self.systems]
        if len(set(system_ids)) != len(system_ids):
            raise ValueError("system_id values must be unique in a comparison")
        if len(set(manifests)) != len(manifests):
            raise ValueError("experiment_manifest paths must be unique in a comparison")
        if self.reference_system_id not in system_ids:
            raise ValueError("reference_system_id must name one of the declared systems")
        return self


class ResearchComparisonError(ValueError):
    """Raised when systems cannot be compared as a paired ASV experiment."""


@dataclass(frozen=True, slots=True)
class LoadedComparisonSystem:
    system_id: str
    manifest_path: Path
    experiment: LoadedResearchExperiment


@dataclass(frozen=True, slots=True)
class LoadedResearchComparison:
    manifest_path: Path
    manifest: ResearchComparisonManifest
    systems: tuple[LoadedComparisonSystem, ...]


def _resolve_child(root: Path, relative_path: str) -> Path:
    resolved_root = root.resolve()
    candidate = (resolved_root / relative_path).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ResearchComparisonError("comparison paths must remain inside the comparison folder") from exc
    if not candidate.is_file():
        raise ResearchComparisonError(f"declared experiment manifest does not exist: {relative_path}")
    return candidate


def _trial_signature(record: ScoreTrial) -> tuple[object, ...]:
    return (
        record.label,
        record.split,
        record.condition,
        record.attack_species,
        record.speaker_id,
        record.source_id,
    )


def _validate_paired_datasets(
    datasets: list[ScoreDataset],
    *,
    description: str,
) -> None:
    """Require exact trial identity/label/condition/group alignment across systems."""

    if not datasets:
        raise ResearchComparisonError(f"{description} has no datasets to compare")
    first = datasets[0]
    first_manifest = first.manifest
    first_by_id = {record.trial_id: record for record in first.records}
    for dataset in datasets[1:]:
        manifest = dataset.manifest
        if manifest.protocol_id != first_manifest.protocol_id:
            raise ResearchComparisonError(f"{description} protocol_id differs between systems")
        if manifest.evaluation_split != first_manifest.evaluation_split:
            raise ResearchComparisonError(f"{description} split differs between systems")
        by_id = {record.trial_id: record for record in dataset.records}
        if set(by_id) != set(first_by_id):
            missing = len(set(first_by_id) - set(by_id))
            extra = len(set(by_id) - set(first_by_id))
            raise ResearchComparisonError(
                f"{description} trials are not paired: {missing} missing and {extra} extra trial_id values"
            )
        for trial_id, reference_record in first_by_id.items():
            if _trial_signature(by_id[trial_id]) != _trial_signature(reference_record):
                raise ResearchComparisonError(
                    f"{description} label, split, condition or group metadata differs for trial_id {trial_id}"
                )


def load_research_comparison(path: Path) -> LoadedResearchComparison:
    """Load comparison metadata and each model's independent research experiment."""

    manifest_path = path.resolve()
    if not manifest_path.is_file():
        raise ResearchComparisonError(f"comparison manifest not found: {path}")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = ResearchComparisonManifest.model_validate(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ResearchComparisonError("comparison manifest is unreadable or invalid") from exc

    root = manifest_path.parent
    loaded_systems: list[LoadedComparisonSystem] = []
    try:
        for reference in manifest.systems:
            experiment_path = _resolve_child(root, reference.experiment_manifest)
            experiment = load_research_experiment(experiment_path)
            if experiment.manifest.system_id != reference.system_id:
                raise ResearchComparisonError(
                    f"declared system_id {reference.system_id} does not match "
                    f"experiment system_id {experiment.manifest.system_id}"
                )
            loaded_systems.append(
                LoadedComparisonSystem(
                    system_id=reference.system_id,
                    manifest_path=experiment_path,
                    experiment=experiment,
                )
            )
    except (ResearchExperimentError, OSError, ValueError) as exc:
        if isinstance(exc, ResearchComparisonError):
            raise
        raise ResearchComparisonError("a system experiment failed validation") from exc

    first = loaded_systems[0].experiment
    first_domains = [item.domain_id for item in first.evaluation_datasets]
    first_calibration = first.calibration_dataset
    for system in loaded_systems[1:]:
        experiment = system.experiment
        if experiment.manifest.target_fmr != first.manifest.target_fmr:
            raise ResearchComparisonError("all systems must declare the same target_fmr")
        if experiment.manifest.probability_threshold != first.manifest.probability_threshold:
            raise ResearchComparisonError("all systems must declare the same probability_threshold")
        if [item.domain_id for item in experiment.evaluation_datasets] != first_domains:
            raise ResearchComparisonError("all systems must declare the same ordered evaluation domains")
        calibration = experiment.calibration_dataset
        if calibration.manifest.protocol_id != first_calibration.manifest.protocol_id:
            raise ResearchComparisonError("calibration protocol_id differs between systems")
        if calibration.manifest.evaluation_split != first_calibration.manifest.evaluation_split:
            raise ResearchComparisonError("calibration split differs between systems")

    calibration_datasets = [item.experiment.calibration_dataset for item in loaded_systems]
    try:
        _validate_paired_datasets(calibration_datasets, description="calibration datasets")
        for domain_index, domain_id in enumerate(first_domains):
            paired = [
                item.experiment.evaluation_datasets[domain_index].dataset
                for item in loaded_systems
            ]
            _validate_paired_datasets(paired, description=f"evaluation domain {domain_id}")
    except ResearchComparisonError:
        raise

    return LoadedResearchComparison(
        manifest_path=manifest_path,
        manifest=manifest,
        systems=tuple(loaded_systems),
    )


def _system_point_metrics(
    report: dict[str, object], domain_id: str
) -> dict[str, object]:
    evaluations = cast(list[dict[str, object]], report["evaluation_datasets"])
    item = next(entry for entry in evaluations if entry["domain_id"] == domain_id)
    raw_metrics = cast(dict[str, object], item["raw_score_metrics"])
    eer = cast(dict[str, object], raw_metrics["eer"])
    operating = cast(dict[str, object], item["transferred_operating_point"])
    fmr = cast(dict[str, object], operating["fmr"])
    fnmr = cast(dict[str, object], operating["fnmr"])
    calibration = cast(dict[str, object], item["calibration_metrics"])
    return {
        "eer": cast(float, eer["value"]),
        "roc_auc": cast(float, raw_metrics["roc_auc"]),
        "fmr_at_model_threshold": cast(float, fmr["rate"]),
        "fnmr_at_model_threshold": cast(float, fnmr["rate"]),
        "brier_score": cast(float, calibration["brier_score"]),
        "expected_calibration_error": cast(float, calibration["expected_calibration_error"]),
        "sample_counts": cast(dict[str, int], calibration["sample_counts"]),
    }


def _paired_cluster_bootstrap_deltas(
    datasets_by_system: dict[str, ScoreDataset],
    directions: dict[str, ScoreDirection],
    thresholds: dict[str, float],
    point_deltas: dict[str, dict[str, float]],
    reference_system_id: str,
    config: PairedComparisonBootstrapConfig,
) -> dict[str, object]:
    """Resample matched clusters once and apply the same sampled trial IDs to every system."""

    reference_dataset = datasets_by_system[reference_system_id]
    clusters: dict[str, list[str]] = {}
    for record in reference_dataset.records:
        cluster_id = getattr(record, config.cluster_column)
        if not isinstance(cluster_id, str) or not cluster_id.strip():
            raise ResearchComparisonError(
                f"paired bootstrap requires non-empty {config.cluster_column} values"
            )
        clusters.setdefault(cluster_id, []).append(record.trial_id)
    cluster_ids = sorted(clusters)
    if len(cluster_ids) < 2:
        raise ResearchComparisonError("paired bootstrap requires at least two distinct clusters")
    clusters_by_label = {
        label: {
            cluster_id
            for cluster_id, trial_ids in clusters.items()
            if any(
                next(record for record in reference_dataset.records if record.trial_id == trial_id).label
                == label
                for trial_id in trial_ids
            )
        }
        for label in ("target", "nontarget")
    }
    insufficient = [label for label, ids in clusters_by_label.items() if len(ids) < 2]
    if insufficient:
        raise ResearchComparisonError(
            "paired bootstrap requires at least two clusters containing each class: "
            + ", ".join(insufficient)
        )

    records_by_system = {
        system_id: {record.trial_id: record for record in dataset.records}
        for system_id, dataset in datasets_by_system.items()
    }
    metrics = ("eer", "roc_auc", "fmr_at_model_threshold", "fnmr_at_model_threshold")
    delta_samples: dict[str, dict[str, list[float]]] = {
        system_id: {metric: [] for metric in metrics}
        for system_id in datasets_by_system
        if system_id != reference_system_id
    }
    invalid = 0
    generator = random.Random(config.seed)
    for _ in range(config.replicates):
        selected_clusters = generator.choices(cluster_ids, k=len(cluster_ids))
        selected_trial_ids = [
            trial_id for cluster_id in selected_clusters for trial_id in clusters[cluster_id]
        ]
        points: dict[str, dict[str, float]] = {}
        try:
            for system_id in datasets_by_system:
                sampled = [
                    records_by_system[system_id][trial_id]
                    for trial_id in selected_trial_ids
                ]
                raw_metrics, _, _ = evaluate_scores(
                    sampled, BenchmarkTask.ASV, directions[system_id], threshold=None
                )
                operating = _operating_rates(
                    sampled, directions[system_id], thresholds[system_id]
                )
                eer = cast(dict[str, object], raw_metrics["eer"])
                fmr = cast(dict[str, object], operating["fmr"])
                fnmr = cast(dict[str, object], operating["fnmr"])
                points[system_id] = {
                    "eer": cast(float, eer["value"]),
                    "roc_auc": cast(float, raw_metrics["roc_auc"]),
                    "fmr_at_model_threshold": cast(float, fmr["rate"]),
                    "fnmr_at_model_threshold": cast(float, fnmr["rate"]),
                }
        except MetricError:
            invalid += 1
            continue

        reference_points = points[reference_system_id]
        for system_id, values in delta_samples.items():
            for metric in metrics:
                values[metric].append(points[system_id][metric] - reference_points[metric])

    valid = len(next(iter(delta_samples.values()))[metrics[0]]) if delta_samples else 0
    minimum_valid = ceil(config.replicates * 0.8)
    if valid < minimum_valid:
        raise ResearchComparisonError(
            f"paired bootstrap produced {valid}/{config.replicates} valid replicates; "
            f"at least {minimum_valid} are required (80%)"
        )
    tail = (1.0 - config.confidence_level) / 2.0
    result: dict[str, object] = {}
    for system_id, values in delta_samples.items():
        result[system_id] = {
            metric: {
                "point_difference": point_deltas[system_id][metric],
                "percentile_interval": [
                    _percentile(values[metric], tail),
                    _percentile(values[metric], 1.0 - tail),
                ],
                "valid_replicates": len(values[metric]),
            }
            for metric in metrics
        }
    return {
        "method": "paired nonparametric cluster bootstrap; same sampled clusters/trials for every system",
        "cluster_column": config.cluster_column,
        "cluster_count": len(cluster_ids),
        "clusters_by_class": {
            label: len(ids) for label, ids in clusters_by_label.items()
        },
        "replicates_requested": config.replicates,
        "replicates_valid": valid,
        "replicates_invalid": invalid,
        "seed": config.seed,
        "confidence_level": config.confidence_level,
        "minimum_valid_fraction": 0.8,
        "difference_direction": "system metric minus reference-system metric",
        "systems_vs_reference": result,
        "estimand_note": (
            "Paired intervals quantify evaluation-cluster sampling variability on shared trial IDs. "
            "Each system's calibration mapping and operating threshold are fitted on its own matched "
            "calibration dataset and held fixed. Intervals do not include model training or calibration "
            "set/threshold-selection uncertainty."
        ),
    }


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ResearchComparisonError("cannot calculate a percentile from an empty sample")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def build_research_comparison_report(
    loaded: LoadedResearchComparison,
) -> dict[str, object]:
    """Build model-specific research reports and paired performance differences."""

    system_reports = {
        system.system_id: build_research_report(system.experiment)
        for system in loaded.systems
    }
    reference_id = loaded.manifest.reference_system_id
    domain_ids = [
        item.domain_id for item in loaded.systems[0].experiment.evaluation_datasets
    ]
    systems: list[dict[str, object]] = []
    for system in loaded.systems:
        report = system_reports[system.system_id]
        systems.append(
            {
                "system_id": system.system_id,
                "system_provenance": report["system"],
                "calibration": report["calibration"],
                "threshold_policy": report["threshold_policy"],
            }
        )

    domain_results: list[dict[str, object]] = []
    for domain_index, domain_id in enumerate(domain_ids):
        metrics_by_system = {
            system.system_id: _system_point_metrics(system_reports[system.system_id], domain_id)
            for system in loaded.systems
        }
        reference_metrics = metrics_by_system[reference_id]
        metric_deltas: dict[str, dict[str, float]] = {}
        for system_id, metrics in metrics_by_system.items():
            if system_id == reference_id:
                continue
            metric_deltas[system_id] = {
                metric: cast(float, metrics[metric]) - cast(float, reference_metrics[metric])
                for metric in (
                    "eer",
                    "roc_auc",
                    "fmr_at_model_threshold",
                    "fnmr_at_model_threshold",
                    "brier_score",
                    "expected_calibration_error",
                )
            }

        domain_result: dict[str, object] = {
            "domain_id": domain_id,
            "trial_alignment": "exact trial_id, label, split, condition and group alignment validated",
            "systems": metrics_by_system,
            "differences_vs_reference": metric_deltas,
            "reference_system_id": reference_id,
            "interpretation": (
                "Differences are descriptive. Negative EER/FMR/FNMR/Brier/ECE differences favor "
                "the compared system; positive ROC-AUC differences favor the compared system."
            ),
        }
        if loaded.manifest.paired_cluster_bootstrap is not None:
            datasets = {
                system.system_id: system.experiment.evaluation_datasets[domain_index].dataset
                for system in loaded.systems
            }
            directions = {
                system.system_id: datasets[system.system_id].manifest.score_direction
                for system in loaded.systems
            }
            thresholds = {
                system.system_id: cast(
                    float,
                    cast(dict[str, object], system_reports[system.system_id]["threshold_policy"])[
                        "calibration_threshold_normalized_higher_is_genuine"
                    ],
                )
                for system in loaded.systems
            }
            paired_delta_metrics = {
                system_id: {
                    metric: value
                    for metric, value in delta.items()
                    if metric in ("eer", "roc_auc", "fmr_at_model_threshold", "fnmr_at_model_threshold")
                }
                for system_id, delta in metric_deltas.items()
            }
            domain_result["paired_cluster_bootstrap"] = _paired_cluster_bootstrap_deltas(
                datasets,
                directions,
                thresholds,
                paired_delta_metrics,
                reference_id,
                loaded.manifest.paired_cluster_bootstrap,
            )
        domain_results.append(domain_result)

    return {
        "schema_version": "0.1",
        "comparison_id": loaded.manifest.comparison_id,
        "description": loaded.manifest.description,
        "reference_system_id": reference_id,
        "systems": systems,
        "evaluation_domains": domain_results,
        "generated_at": datetime.now(UTC).isoformat(),
        "framework_version": __version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "methodology": (
            "Every system was independently calibrated and assigned an operating threshold using "
            "its own calibration dataset. Comparison was performed on exact matched evaluation trials."
        ),
        "warnings": [
            "Score-producer provenance is only verified when every system experiment supplies valid sidecars.",
            "Automated software validation does not demonstrate real-world biometric performance.",
        ],
    }


def _render_comparison_html(report: dict[str, object]) -> str:
    rows: list[str] = []
    domains = cast(list[dict[str, object]], report["evaluation_domains"])
    for domain in domains:
        systems = cast(dict[str, dict[str, object]], domain["systems"])
        for system_id, metrics in systems.items():
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(domain['domain_id']))}</td>"
                f"<td>{html.escape(system_id)}</td>"
                f"<td>{cast(float, metrics['eer']):.6f}</td>"
                f"<td>{cast(float, metrics['roc_auc']):.6f}</td>"
                f"<td>{cast(float, metrics['fmr_at_model_threshold']):.6f}</td>"
                f"<td>{cast(float, metrics['fnmr_at_model_threshold']):.6f}</td>"
                "</tr>"
            )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        "<title>VoxRigor Paired Model Comparison</title><body>"
        f"<h1>{html.escape(str(report['comparison_id']))}</h1>"
        f"<p>{html.escape(str(report['description']))}</p>"
        f"<p>Reference system: {html.escape(str(report['reference_system_id']))}</p>"
        "<p>Each system uses its own calibration-fitted mapping and frozen threshold. "
        "Evaluation trials were paired and checked for matching trial identity and metadata.</p>"
        "<table><thead><tr><th>Domain</th><th>System</th><th>EER</th><th>ROC-AUC</th>"
        "<th>FMR at system threshold</th><th>FNMR at system threshold</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></body></html>\n"
    )


def _atomic_write(path: Path, content: str) -> None:
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as handle:
            temporary_name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name is not None and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def run_research_comparison(manifest_path: Path, output_root: Path) -> Path:
    """Run paired multi-system comparison and write JSON/HTML reports."""

    loaded = load_research_comparison(manifest_path)
    report = build_research_comparison_report(loaded)
    run_id = str(uuid4())
    run_dir = output_root / loaded.manifest.comparison_id / run_id
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
        _atomic_write(run_dir / "report.json", json.dumps(report, indent=2, sort_keys=True) + "\n")
        _atomic_write(run_dir / "report.html", _render_comparison_html(report))
    except OSError as exc:
        raise ResearchComparisonError("could not write the research comparison report") from exc
    return run_dir
