"""Development-only Platt calibration and evaluation reliability metrics."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from voxrigor.benchmarking.dataset import ScoreTrial
from voxrigor.benchmarking.metrics import wilson_interval
from voxrigor.benchmarking.models import ScoreDirection


def normalize_score(score: float, direction: ScoreDirection) -> float:
    """Convert scores to the invariant convention: larger means more genuine."""

    return score if direction is ScoreDirection.HIGHER_IS_GENUINE else -score


@dataclass(frozen=True, slots=True)
class PlattCalibrator:
    """Two-parameter logistic mapping fitted only on the calibration partition."""

    mean: float
    scale: float
    intercept: float
    slope: float
    regularization: float
    iterations: int

    def predict_probability(self, normalized_score: float) -> float:
        feature = (normalized_score - self.mean) / self.scale
        logit = max(-60.0, min(60.0, self.intercept + self.slope * feature))
        return 1.0 / (1.0 + math.exp(-logit))


def fit_platt_calibrator(
    records: Iterable[ScoreTrial],
    direction: ScoreDirection,
    *,
    regularization: float = 1e-6,
    max_iterations: int = 200,
) -> PlattCalibrator:
    """Fit regularized logistic calibration from target and nontarget development scores."""

    selected = tuple(records)
    normalized = [normalize_score(row.score, direction) for row in selected]
    labels = [1.0 if row.label == "target" else 0.0 for row in selected]
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        raise ValueError("calibration data must contain target and nontarget trials")
    if not 0 < regularization < 1 or max_iterations < 1:
        raise ValueError("invalid calibration optimizer configuration")

    mean = sum(normalized) / len(normalized)
    variance = sum((value - mean) ** 2 for value in normalized) / len(normalized)
    scale = math.sqrt(variance)
    if scale < 1e-12:
        scale = 1.0
    features = [(value - mean) / scale for value in normalized]
    intercept = math.log(positives / negatives)
    slope = 0.0
    iterations = 0

    for iterations in range(1, max_iterations + 1):
        gradient_intercept = 0.0
        gradient_slope = regularization * slope
        hessian_ii = 1e-12
        hessian_is = 0.0
        hessian_ss = regularization
        for feature, label in zip(features, labels, strict=True):
            logit = max(-60.0, min(60.0, intercept + slope * feature))
            probability = 1.0 / (1.0 + math.exp(-logit))
            residual = probability - label
            weight = probability * (1.0 - probability)
            gradient_intercept += residual
            gradient_slope += residual * feature
            hessian_ii += weight
            hessian_is += weight * feature
            hessian_ss += weight * feature * feature

        determinant = hessian_ii * hessian_ss - hessian_is * hessian_is
        if determinant <= 1e-18:
            break
        delta_intercept = (
            gradient_intercept * hessian_ss - gradient_slope * hessian_is
        ) / determinant
        delta_slope = (
            gradient_slope * hessian_ii - gradient_intercept * hessian_is
        ) / determinant
        intercept -= delta_intercept
        slope -= delta_slope
        if max(abs(delta_intercept), abs(delta_slope)) < 1e-8:
            break

    if not math.isfinite(intercept) or not math.isfinite(slope):
        raise ValueError("calibration optimizer did not produce finite parameters")
    return PlattCalibrator(
        mean=mean,
        scale=scale,
        intercept=intercept,
        slope=slope,
        regularization=regularization,
        iterations=iterations,
    )


def evaluate_calibration(
    records: Iterable[ScoreTrial],
    calibrator: PlattCalibrator,
    direction: ScoreDirection,
    *,
    probability_threshold: float = 0.5,
    bin_count: int = 10,
) -> dict[str, object]:
    """Measure calibration quality on a separate evaluation dataset."""

    if not 0 <= probability_threshold <= 1 or bin_count < 2:
        raise ValueError("invalid calibration evaluation configuration")
    selected = tuple(records)
    targets = [row for row in selected if row.label == "target"]
    nontargets = [row for row in selected if row.label == "nontarget"]
    if not targets or not nontargets:
        raise ValueError("evaluation data must contain target and nontarget trials")

    pairs = [
        (
            calibrator.predict_probability(normalize_score(row.score, direction)),
            1.0 if row.label == "target" else 0.0,
        )
        for row in selected
    ]
    brier = sum((probability - label) ** 2 for probability, label in pairs) / len(pairs)
    epsilon = 1e-15
    log_loss = -sum(
        label * math.log(max(epsilon, probability))
        + (1.0 - label) * math.log(max(epsilon, 1.0 - probability))
        for probability, label in pairs
    ) / len(pairs)

    bin_sums: list[list[float]] = [[0.0, 0.0, 0.0] for _ in range(bin_count)]
    for probability, label in pairs:
        index = min(int(probability * bin_count), bin_count - 1)
        bin_sums[index][0] += 1.0
        bin_sums[index][1] += probability
        bin_sums[index][2] += label
    reliability_bins: list[dict[str, float | int]] = []
    expected_calibration_error = 0.0
    for index, (count, probability_sum, label_sum) in enumerate(bin_sums):
        if count == 0:
            continue
        mean_probability = probability_sum / count
        observed_rate = label_sum / count
        expected_calibration_error += count / len(pairs) * abs(mean_probability - observed_rate)
        reliability_bins.append(
            {
                "bin_index": index,
                "count": int(count),
                "mean_probability": mean_probability,
                "observed_target_rate": observed_rate,
            }
        )

    false_matches = sum(probability >= probability_threshold for probability, label in pairs if label == 0)
    false_nonmatches = sum(probability < probability_threshold for probability, label in pairs if label == 1)
    return {
        "probability_threshold": probability_threshold,
        "sample_counts": {"target": len(targets), "nontarget": len(nontargets)},
        "brier_score": brier,
        "log_loss": log_loss,
        "expected_calibration_error": expected_calibration_error,
        "reliability_bins": reliability_bins,
        "fmr": wilson_interval(false_matches, len(nontargets)),
        "fnmr": wilson_interval(false_nonmatches, len(targets)),
        "note": (
            "Calibration parameters were fitted on the separate calibration dataset. "
            "Brier score, log loss, ECE and operating rates here are computed on this evaluation dataset."
        ),
    }
