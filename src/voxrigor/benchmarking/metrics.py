"""Auditable score-based ASV and PAD metrics using only the Python standard library."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from statistics import NormalDist

from voxrigor.benchmarking.dataset import ScoreTrial
from voxrigor.benchmarking.errors import MetricError
from voxrigor.benchmarking.models import BenchmarkTask, ScoreDirection

CONFIDENCE_LEVEL = 0.95


def wilson_interval(
    errors: int, trials: int, confidence_level: float = CONFIDENCE_LEVEL
) -> dict[str, float | int]:
    """Return a two-sided Wilson score interval for a binomial proportion.

    The interval is trial-level. It does not correct for correlation between
    trials from the same speaker, source recording, or other cluster.
    """

    if trials <= 0:
        raise MetricError("Wilson interval requires at least one trial")
    if errors < 0 or errors > trials:
        raise MetricError("Wilson error count must be between zero and trial count")
    if not 0 < confidence_level < 1:
        raise MetricError("confidence_level must be between zero and one")

    proportion = errors / trials
    z = NormalDist().inv_cdf(1 - (1 - confidence_level) / 2)
    z_squared = z * z
    denominator = 1 + z_squared / trials
    center = (proportion + z_squared / (2 * trials)) / denominator
    margin = (
        z
        * ((proportion * (1 - proportion) / trials) + z_squared / (4 * trials * trials)) ** 0.5
        / denominator
    )
    lower = 0.0 if errors == 0 else max(0.0, center - margin)
    upper = 1.0 if errors == trials else min(1.0, center + margin)
    return {
        "errors": errors,
        "trials": trials,
        "rate": proportion,
        "confidence_level": confidence_level,
        "confidence_interval": [lower, upper],
    }


def _normalize(score: float, direction: ScoreDirection) -> float:
    return score if direction is ScoreDirection.HIGHER_IS_GENUINE else -score


def _asv_curve(
    target_scores: list[float], nontarget_scores: list[float]
) -> tuple[list[dict[str, float | None]], float, dict[str, float]]:
    """Compute a tie-aware empirical ROC curve, trapezoidal AUC and interpolated EER."""

    target_total = len(target_scores)
    nontarget_total = len(nontarget_scores)
    if target_total == 0 or nontarget_total == 0:
        raise MetricError("ASV metrics require at least one target and one nontarget trial")

    values = sorted(set(target_scores + nontarget_scores), reverse=True)
    target_at_score = Counter(target_scores)
    nontarget_at_score = Counter(nontarget_scores)
    target_accepted = 0
    nontarget_accepted = 0
    curve: list[dict[str, float | None]] = [
        {"threshold_normalized": None, "fmr": 0.0, "fnmr": 1.0, "tpr": 0.0}
    ]
    for value in values:
        target_accepted += target_at_score[value]
        nontarget_accepted += nontarget_at_score[value]
        fmr = nontarget_accepted / nontarget_total
        fnmr = (target_total - target_accepted) / target_total
        curve.append(
            {
                "threshold_normalized": value,
                "fmr": fmr,
                "fnmr": fnmr,
                "tpr": 1.0 - fnmr,
            }
        )

    auc = 0.0
    for left, right in zip(curve, curve[1:], strict=False):
        x0 = float(left["fmr"])
        x1 = float(right["fmr"])
        y0 = float(left["tpr"])
        y1 = float(right["tpr"])
        auc += (x1 - x0) * (y0 + y1) / 2

    eer_result: dict[str, float] | None = None
    for left, right in zip(curve, curve[1:], strict=False):
        difference_left = float(left["fmr"]) - float(left["fnmr"])
        difference_right = float(right["fmr"]) - float(right["fnmr"])
        if difference_left == 0:
            value = float(left["fmr"])
            eer_result = {
                "value": value,
                "fmr_at_intersection": value,
                "fnmr_at_intersection": value,
            }
            break
        if difference_left < 0 <= difference_right:
            if difference_right == difference_left:
                fraction = 0.0
            else:
                fraction = -difference_left / (difference_right - difference_left)
            fmr = float(left["fmr"]) + fraction * (float(right["fmr"]) - float(left["fmr"]))
            fnmr = float(left["fnmr"]) + fraction * (float(right["fnmr"]) - float(left["fnmr"]))
            value = (fmr + fnmr) / 2
            eer_result = {
                "value": value,
                "fmr_at_intersection": fmr,
                "fnmr_at_intersection": fnmr,
            }
            break
    if eer_result is None:
        raise MetricError("Could not locate the EER crossing on the empirical ROC curve")
    return curve, auc, eer_result


def _operating_rates(
    target_scores: list[float], nontarget_scores: list[float], threshold: float
) -> dict[str, dict[str, float | int | list[float]]]:
    false_matches = sum(score >= threshold for score in nontarget_scores)
    false_nonmatches = sum(score < threshold for score in target_scores)
    return {
        "fmr": wilson_interval(false_matches, len(nontarget_scores)),
        "fnmr": wilson_interval(false_nonmatches, len(target_scores)),
    }


def _asv_metrics_for_records(
    records: Iterable[ScoreTrial], direction: ScoreDirection, threshold: float | None
) -> tuple[dict[str, object], list[dict[str, float | None]]]:
    selected = list(records)
    target = [_normalize(row.score, direction) for row in selected if row.label == "target"]
    nontarget = [_normalize(row.score, direction) for row in selected if row.label == "nontarget"]
    if not target or not nontarget:
        raise MetricError("ASV evaluation requires both target and nontarget trials")
    curve, auc, eer = _asv_curve(target, nontarget)

    operating: dict[str, object] | None = None
    if threshold is not None:
        normalized_threshold = _normalize(threshold, direction)
        operating = {
            "threshold_original_scale": threshold,
            "threshold_normalized_higher_is_genuine": normalized_threshold,
            **_operating_rates(target, nontarget, normalized_threshold),
        }
    return (
        {
            "task": "asv",
            "class_counts": {"target": len(target), "nontarget": len(nontarget)},
            "score_direction": direction.value,
            "acceptance_rule": "normalized_score >= normalized_threshold",
            "operating_point": operating,
            "eer": {
                **eer,
                "method": "linear interpolation between adjacent empirical ROC points",
                "is_deployment_threshold": False,
            },
            "roc_auc": auc,
            "confidence_interval_note": (
                "FMR/FNMR intervals are 95% trial-level Wilson score intervals; "
                "they do not account for speaker/source clustering."
            ),
        },
        curve,
    )


def _pad_metrics_for_records(
    records: Iterable[ScoreTrial], direction: ScoreDirection, threshold: float
) -> tuple[dict[str, object], list[dict[str, object]]]:
    selected = list(records)
    bona_fide = [_normalize(row.score, direction) for row in selected if row.label == "bonafide"]
    spoof = [row for row in selected if row.label == "spoof"]
    if not bona_fide or not spoof:
        raise MetricError("PAD evaluation requires both bonafide and spoof presentations")
    normalized_threshold = _normalize(threshold, direction)

    bona_fide_errors = sum(score < normalized_threshold for score in bona_fide)
    bpcer = wilson_interval(bona_fide_errors, len(bona_fide))
    by_species: dict[str, list[float]] = defaultdict(list)
    for row in spoof:
        if not row.attack_species:
            raise MetricError("Every spoof presentation must have an attack_species label")
        by_species[row.attack_species].append(_normalize(row.score, direction))

    species_results: list[dict[str, object]] = []
    pooled_errors = 0
    for species, scores in sorted(by_species.items()):
        errors = sum(score >= normalized_threshold for score in scores)
        pooled_errors += errors
        species_results.append(
            {
                "attack_species": species,
                "apcer": wilson_interval(errors, len(scores)),
            }
        )
    pooled_apcer = wilson_interval(pooled_errors, len(spoof))
    metrics: dict[str, object] = {
        "task": "pad",
        "class_counts": {"bonafide": len(bona_fide), "spoof": len(spoof)},
        "score_direction": direction.value,
        "acceptance_rule": "normalized_score >= normalized_threshold means bona fide accepted",
        "operating_point": {
            "threshold_original_scale": threshold,
            "threshold_normalized_higher_is_genuine": normalized_threshold,
            "bpcer": bpcer,
            "pooled_apcer": pooled_apcer,
            "pooled_apcer_note": (
                "Sample-weighted across the attack species in this file; inspect per-species "
                "APCER and do not treat the pooled value as a replacement for species-level reporting."
            ),
        },
        "confidence_interval_note": (
            "APCER/BPCER intervals are 95% trial-level Wilson score intervals; "
            "they do not account for speaker/source clustering."
        ),
    }
    return metrics, species_results


def evaluate_scores(
    records: Iterable[ScoreTrial],
    task: BenchmarkTask,
    direction: ScoreDirection,
    threshold: float | None,
) -> tuple[dict[str, object], list[dict[str, float | None]], list[dict[str, object]]]:
    """Evaluate already-filtered score trials for one task."""

    rows = tuple(records)
    if task is BenchmarkTask.ASV:
        metrics, curve = _asv_metrics_for_records(rows, direction, threshold)
        return metrics, curve, []
    if threshold is None:
        raise MetricError("PAD evaluation requires a predeclared operating threshold")
    metrics, species = _pad_metrics_for_records(rows, direction, threshold)
    return metrics, [], species


def evaluate_conditions(
    records: Iterable[ScoreTrial],
    task: BenchmarkTask,
    direction: ScoreDirection,
    threshold: float | None,
) -> list[dict[str, object]]:
    """Return per-condition metrics without silently dropping one-class conditions."""

    grouped: dict[str, list[ScoreTrial]] = defaultdict(list)
    for row in records:
        grouped[row.condition].append(row)
    results: list[dict[str, object]] = []
    required = {"target", "nontarget"} if task is BenchmarkTask.ASV else {"bonafide", "spoof"}
    for condition, rows in sorted(grouped.items()):
        counts = Counter(row.label for row in rows)
        entry: dict[str, object] = {
            "condition": condition,
            "trial_count": len(rows),
            "class_counts": dict(sorted(counts.items())),
        }
        if not required.issubset(counts):
            entry["status"] = "not_computable"
            entry["reason"] = "condition does not contain every required class"
        else:
            try:
                metrics, _, species = evaluate_scores(rows, task, direction, threshold)
                entry["status"] = "computed"
                entry["metrics"] = metrics
                if species:
                    entry["attack_species_metrics"] = species
            except MetricError:
                entry["status"] = "not_computable"
                entry["reason"] = "metrics could not be computed for this condition"
        results.append(entry)
    return results
