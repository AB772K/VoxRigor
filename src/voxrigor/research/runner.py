"""Cross-dataset ASV experiment orchestration and reproducible reporting."""

from __future__ import annotations

import html
import json
import os
import platform
import random
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime
from itertools import combinations
from math import ceil, inf, nextafter
from pathlib import Path
from typing import cast
from uuid import uuid4

from voxrigor import __version__
from voxrigor.benchmarking.dataset import ScoreDataset, ScoreTrial
from voxrigor.benchmarking.errors import MetricError
from voxrigor.benchmarking.metrics import evaluate_scores, wilson_interval
from voxrigor.benchmarking.models import BenchmarkTask, ScoreDirection
from voxrigor.research.calibration import (
    evaluate_calibration,
    fit_platt_calibrator,
    normalize_score,
)
from voxrigor.research.experiment import (
    ClusterBootstrapConfig,
    LoadedResearchExperiment,
    ResearchExperimentError,
    load_research_experiment,
)


def _select_threshold_at_target_fmr(
    records: Iterable[ScoreTrial],
    direction: ScoreDirection,
    target_fmr: float,
) -> float:
    """Select the lowest development threshold whose empirical FMR meets the target."""

    normalized = [normalize_score(row.score, direction) for row in records]
    nontarget = [
        normalize_score(row.score, direction) for row in records if row.label == "nontarget"
    ]
    if not nontarget:
        raise ResearchExperimentError("calibration data must contain nontarget trials")
    candidates = sorted(set(normalized))
    candidates.append(nextafter(max(candidates), inf))
    selected = candidates[-1]
    for threshold in candidates:
        observed_fmr = sum(score >= threshold for score in nontarget) / len(nontarget)
        if observed_fmr <= target_fmr:
            selected = threshold
            break
    return selected


def _operating_rates(
    records: Iterable[ScoreTrial],
    direction: ScoreDirection,
    threshold: float,
) -> dict[str, object]:
    selected = tuple(records)
    targets = [normalize_score(row.score, direction) for row in selected if row.label == "target"]
    nontargets = [
        normalize_score(row.score, direction) for row in selected if row.label == "nontarget"
    ]
    false_matches = sum(score >= threshold for score in nontargets)
    false_nonmatches = sum(score < threshold for score in targets)
    return {
        "threshold_normalized_higher_is_genuine": threshold,
        "threshold_original_scale": (
            threshold if direction is ScoreDirection.HIGHER_IS_GENUINE else -threshold
        ),
        "fmr": wilson_interval(false_matches, len(nontargets)),
        "fnmr": wilson_interval(false_nonmatches, len(targets)),
    }


def _dataset_summary(dataset: ScoreDataset) -> dict[str, object]:
    manifest = dataset.manifest
    return {
        "dataset_id": manifest.dataset_id,
        "dataset_name": manifest.dataset_name,
        "dataset_version": manifest.dataset_version,
        "protocol_id": manifest.protocol_id,
        "evaluation_split": manifest.evaluation_split,
        "score_direction": manifest.score_direction.value,
        "score_file_sha256": dataset.score_file_sha256,
        "manifest_sha256": dataset.manifest_sha256,
        "score_producer": (
            manifest.score_producer.model_dump(mode="json")
            if manifest.score_producer is not None
            else None
        ),
        "sample_counts": {
            "input_rows": dataset.input_rows,
            "evaluated_rows": len(dataset.records),
            "other_split_rows": dataset.other_split_rows,
            "labels": dataset.label_counts,
        },
        "license_name": manifest.license_name,
        "source_url": manifest.source_url,
    }


def _score_producer_signature(dataset: ScoreDataset) -> tuple[object, ...] | None:
    producer = dataset.manifest.score_producer
    if producer is None:
        return None
    if producer.score_direction is not dataset.manifest.score_direction:
        raise ResearchExperimentError(
            f"score producer direction disagrees with dataset manifest for {dataset.manifest.dataset_id}"
        )
    if producer.calibrated:
        raise ResearchExperimentError(
            "input score producers must declare calibrated=false; this experiment fits its own calibrator"
        )
    return (
        producer.model_id,
        producer.model_revision,
        producer.backend,
        producer.score_type,
        tuple(producer.model_artifact_sha256),
        producer.calibrated,
    )


def _group_overlap_report(
    loaded: LoadedResearchExperiment, warnings: list[str]
) -> list[dict[str, object]]:
    if not loaded.manifest.group_columns:
        warnings.append(
            "No speaker/source group columns were configured; cross-dataset identity overlap was not assessed."
        )
        return []

    datasets: list[tuple[str, ScoreDataset]] = [
        ("calibration", loaded.calibration_dataset),
        *((item.domain_id, item.dataset) for item in loaded.evaluation_datasets),
    ]
    report: list[dict[str, object]] = []
    for column in loaded.manifest.group_columns:
        group_sets: dict[str, set[str]] = {}
        for name, dataset in datasets:
            values = {
                value
                for row in dataset.records
                if (value := getattr(row, column)) is not None and value != ""
            }
            missing = len(dataset.records) - sum(
                getattr(row, column) is not None and getattr(row, column) != ""
                for row in dataset.records
            )
            if not values or missing:
                message = f"Group column {column} is absent or incomplete in dataset {dataset.manifest.dataset_id}."
                if loaded.manifest.require_group_disjointness:
                    raise ResearchExperimentError(message)
                warnings.append(message)
            group_sets[name] = values

        overlaps: list[dict[str, object]] = []
        for (left_name, _), (right_name, _) in combinations(datasets, 2):
            overlap = group_sets[left_name] & group_sets[right_name]
            overlaps.append(
                {
                    "left_dataset": left_name,
                    "right_dataset": right_name,
                    "overlap_count": len(overlap),
                }
            )
            if overlap:
                message = (
                    f"{len(overlap)} {column} identifier(s) overlap between "
                    f"{left_name} and {right_name}."
                )
                if loaded.manifest.require_group_disjointness:
                    raise ResearchExperimentError(message)
                warnings.append(message)
        report.append({"group_column": column, "pairwise_overlaps": overlaps})
    return report


def _validate_score_lineage(
    loaded: LoadedResearchExperiment, warnings: list[str]
) -> dict[str, object]:
    datasets = [loaded.calibration_dataset, *(item.dataset for item in loaded.evaluation_datasets)]
    signatures = [_score_producer_signature(dataset) for dataset in datasets]
    if all(signature is None for signature in signatures):
        warnings.append(
            "No verified score-producer sidecars were supplied; system identity relies on the experiment declaration and score-file hashes."
        )
        return {"system_id": loaded.manifest.system_id, "verified_model_provenance": None}
    if any(signature is None for signature in signatures):
        raise ResearchExperimentError(
            "either every dataset must provide score-producer provenance or none may provide it"
        )
    if len(set(signatures)) != 1:
        raise ResearchExperimentError(
            "score-producer model, revision, backend, score type and artifact hashes must match across datasets"
        )
    producer = datasets[0].manifest.score_producer
    assert producer is not None
    return {
        "system_id": loaded.manifest.system_id,
        "verified_model_provenance": {
            "model_id": producer.model_id,
            "model_revision": producer.model_revision,
            "backend": producer.backend,
            "score_type": producer.score_type,
            "model_artifact_sha256": producer.model_artifact_sha256,
        },
    }


def _percentile(values: list[float], probability: float) -> float:
    """Calculate a linearly interpolated percentile from finite bootstrap values."""

    if not values:
        raise ResearchExperimentError("cannot calculate a percentile from an empty sample")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] + fraction * (
        ordered[upper_index] - ordered[lower_index]
    )


def _cluster_bootstrap_uncertainty(
    records: tuple[ScoreTrial, ...],
    direction: ScoreDirection,
    threshold: float,
    config: ClusterBootstrapConfig,
    point_metrics: dict[str, object],
    point_operating_point: dict[str, object],
) -> dict[str, object]:
    """Estimate held-out metric uncertainty by resampling complete clusters."""

    clusters: dict[str, list[ScoreTrial]] = {}
    for record in records:
        cluster_id = getattr(record, config.cluster_column)
        if not isinstance(cluster_id, str) or not cluster_id.strip():
            raise ResearchExperimentError(
                f"cluster bootstrap requires a non-empty {config.cluster_column} value on every evaluation trial"
            )
        clusters.setdefault(cluster_id, []).append(record)

    cluster_ids = sorted(clusters)
    if len(cluster_ids) < 2:
        raise ResearchExperimentError(
            "cluster bootstrap requires at least two distinct clusters per evaluation dataset"
        )

    clusters_by_label = {
        label: {
            cluster_id
            for cluster_id, cluster_records in clusters.items()
            if any(record.label == label for record in cluster_records)
        }
        for label in ("target", "nontarget")
    }
    insufficient = [
        label for label, values in clusters_by_label.items() if len(values) < 2
    ]
    if insufficient:
        raise ResearchExperimentError(
            "cluster bootstrap requires at least two distinct clusters containing each class: "
            + ", ".join(insufficient)
        )

    bootstrap_values: dict[str, list[float]] = {
        "eer": [],
        "roc_auc": [],
        "fmr": [],
        "fnmr": [],
    }
    invalid_replicates = 0
    generator = random.Random(config.seed)
    for _ in range(config.replicates):
        sampled_records: list[ScoreTrial] = []
        for selected_cluster in generator.choices(cluster_ids, k=len(cluster_ids)):
            sampled_records.extend(clusters[selected_cluster])
        try:
            metrics, _, _ = evaluate_scores(
                sampled_records, BenchmarkTask.ASV, direction, threshold=None
            )
            operating = _operating_rates(sampled_records, direction, threshold)
        except MetricError:
            invalid_replicates += 1
            continue

        eer = cast(dict[str, object], metrics["eer"])
        fmr = cast(dict[str, object], operating["fmr"])
        fnmr = cast(dict[str, object], operating["fnmr"])
        bootstrap_values["eer"].append(cast(float, eer["value"]))
        bootstrap_values["roc_auc"].append(cast(float, metrics["roc_auc"]))
        bootstrap_values["fmr"].append(cast(float, fmr["rate"]))
        bootstrap_values["fnmr"].append(cast(float, fnmr["rate"]))

    valid_replicates = len(bootstrap_values["eer"])
    minimum_valid = ceil(config.replicates * 0.8)
    if valid_replicates < minimum_valid:
        raise ResearchExperimentError(
            f"cluster bootstrap produced {valid_replicates}/{config.replicates} valid replicates; "
            f"at least {minimum_valid} are required (80%)"
        )

    tail_probability = (1.0 - config.confidence_level) / 2.0
    point_eer = cast(float, cast(dict[str, object], point_metrics["eer"])["value"])
    point_auc = cast(float, point_metrics["roc_auc"])
    point_fmr = cast(float, cast(dict[str, object], point_operating_point["fmr"])["rate"])
    point_fnmr = cast(float, cast(dict[str, object], point_operating_point["fnmr"])["rate"])

    def interval(name: str, point_estimate: float) -> dict[str, object]:
        values = bootstrap_values[name]
        return {
            "point_estimate": point_estimate,
            "percentile_interval": [
                _percentile(values, tail_probability),
                _percentile(values, 1.0 - tail_probability),
            ],
            "valid_replicates": len(values),
        }

    return {
        "method": "nonparametric cluster bootstrap; complete clusters sampled with replacement",
        "cluster_column": config.cluster_column,
        "cluster_count": len(cluster_ids),
        "clusters_by_class": {
            label: len(values) for label, values in clusters_by_label.items()
        },
        "replicates_requested": config.replicates,
        "replicates_valid": valid_replicates,
        "replicates_invalid": invalid_replicates,
        "seed": config.seed,
        "confidence_level": config.confidence_level,
        "minimum_valid_fraction": 0.8,
        "metrics": {
            "eer": interval("eer", point_eer),
            "roc_auc": interval("roc_auc", point_auc),
            "fmr_at_frozen_threshold": interval("fmr", point_fmr),
            "fnmr_at_frozen_threshold": interval("fnmr", point_fnmr),
        },
        "estimand_note": (
            "Intervals resample the configured cluster unit in this held-out evaluation dataset only. "
            "The calibration mapping and operating threshold remain fixed, so these intervals do not "
            "include calibration-set or threshold-selection uncertainty. The results are only as "
            "representative as the supplied cluster identifiers and sampling frame."
        ),
    }


def build_research_report(loaded: LoadedResearchExperiment) -> dict[str, object]:
    """Fit only on the declared calibration dataset and evaluate on held-out datasets."""

    warnings: list[str] = []
    calibration = loaded.calibration_dataset
    directions = {
        dataset.manifest.score_direction
        for dataset in [calibration, *(item.dataset for item in loaded.evaluation_datasets)]
    }
    if len(directions) != 1:
        raise ResearchExperimentError(
            "score_direction must be identical across calibration and evaluation datasets"
        )
    direction = next(iter(directions))
    system = _validate_score_lineage(loaded, warnings)
    overlap = _group_overlap_report(loaded, warnings)

    calibrator = fit_platt_calibrator(calibration.records, direction)
    raw_threshold = _select_threshold_at_target_fmr(
        calibration.records, direction, loaded.manifest.target_fmr
    )
    original_threshold = (
        raw_threshold if direction is ScoreDirection.HIGHER_IS_GENUINE else -raw_threshold
    )

    evaluation_results: list[dict[str, object]] = []
    for item in loaded.evaluation_datasets:
        dataset = item.dataset
        raw_metrics, _, _ = evaluate_scores(
            dataset.records, BenchmarkTask.ASV, direction, threshold=None
        )
        transferred_operating_point = _operating_rates(
            dataset.records, direction, raw_threshold
        )
        evaluation_result: dict[str, object] = {
            "domain_id": item.domain_id,
            "dataset": _dataset_summary(dataset),
            "raw_score_metrics": raw_metrics,
            "transferred_operating_point": transferred_operating_point,
            "calibration_metrics": evaluate_calibration(
                dataset.records,
                calibrator,
                direction,
                probability_threshold=loaded.manifest.probability_threshold,
            ),
        }
        if loaded.manifest.cluster_bootstrap is not None:
            evaluation_result["cluster_bootstrap_uncertainty"] = (
                _cluster_bootstrap_uncertainty(
                    dataset.records,
                    direction,
                    raw_threshold,
                    loaded.manifest.cluster_bootstrap,
                    raw_metrics,
                    transferred_operating_point,
                )
            )
        evaluation_results.append(evaluation_result)

    return {
        "schema_version": "0.1",
        "experiment_id": loaded.manifest.experiment_id,
        "description": loaded.manifest.description,
        "system": system,
        "generated_at": datetime.now(UTC).isoformat(),
        "framework_version": __version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "calibration": {
            "dataset": _dataset_summary(calibration),
            "fit_partition": "declared calibration dataset only",
            "method": "regularized Platt logistic calibration",
            "parameters": {
                "score_mean": calibrator.mean,
                "score_scale": calibrator.scale,
                "intercept": calibrator.intercept,
                "slope": calibrator.slope,
                "regularization": calibrator.regularization,
                "iterations": calibrator.iterations,
            },
            "sample_counts": {
                "target": calibration.label_counts.get("target", 0),
                "nontarget": calibration.label_counts.get("nontarget", 0),
            },
        },
        "threshold_policy": {
            "method": "lowest calibration-set threshold satisfying the empirical target FMR",
            "calibration_target_fmr": loaded.manifest.target_fmr,
            "calibration_threshold_normalized_higher_is_genuine": raw_threshold,
            "calibration_threshold_original_scale": original_threshold,
            "transfer_rule": "frozen threshold applied unchanged to every evaluation dataset",
            "probability_threshold": loaded.manifest.probability_threshold,
            "selection_partition": "calibration dataset only",
        },
        "group_overlap": overlap,
        "evaluation_datasets": evaluation_results,
        "warnings": warnings,
        "interpretation": (
            "Cross-dataset results describe only the declared datasets, score protocol and evaluation splits. "
            "They do not establish population-wide generalization or production authentication security."
        ),
    }


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


def _render_html(report: dict[str, object]) -> str:
    rows: list[str] = []
    evaluation_datasets = cast(list[dict[str, object]], report["evaluation_datasets"])
    for result in evaluation_datasets:
        dataset = cast(dict[str, object], result["dataset"])
        metrics = cast(dict[str, object], result["raw_score_metrics"])
        eer = cast(dict[str, object], metrics["eer"])
        calibration = cast(dict[str, object], result["calibration_metrics"])
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(result['domain_id']))}</td>"
            f"<td>{html.escape(str(dataset['dataset_id']))}</td>"
            f"<td>{cast(float, eer['value']):.6f}</td>"
            f"<td>{cast(float, metrics['roc_auc']):.6f}</td>"
            f"<td>{cast(float, calibration['brier_score']):.6f}</td>"
            f"<td>{cast(float, calibration['expected_calibration_error']):.6f}</td>"
            "</tr>"
        )
    warnings_list = cast(list[str], report["warnings"])
    warnings = "".join(f"<li>{html.escape(item)}</li>" for item in warnings_list)
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        "<title>VoxRigor Research Experiment</title><body>"
        f"<h1>{html.escape(str(report['experiment_id']))}</h1>"
        f"<p>{html.escape(str(report['description']))}</p>"
        "<p>Calibration and threshold selection use only the declared calibration dataset.</p>"
        "<table><thead><tr><th>Domain</th><th>Dataset</th><th>Raw EER</th>"
        "<th>Raw ROC-AUC</th><th>Brier</th><th>ECE</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table><h2>Warnings and limitations</h2><ul>"
        + warnings
        + "</ul></body></html>\n"
    )


def run_research_experiment(manifest_path: Path, output_root: Path) -> Path:
    """Execute a Phase 6 experiment and write a JSON and HTML report."""

    loaded = load_research_experiment(manifest_path)
    report = build_research_report(loaded)
    run_id = str(uuid4())
    run_dir = output_root / loaded.manifest.experiment_id / run_id
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
        _atomic_write(run_dir / "report.json", json.dumps(report, indent=2, sort_keys=True) + "\n")
        _atomic_write(run_dir / "report.html", _render_html(report))
    except OSError as exc:
        raise ResearchExperimentError("could not write the research experiment report") from exc
    return run_dir
