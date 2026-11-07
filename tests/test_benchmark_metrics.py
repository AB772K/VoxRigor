import pytest

from voxrigor.benchmarking.dataset import ScoreTrial
from voxrigor.benchmarking.errors import MetricError
from voxrigor.benchmarking.metrics import evaluate_conditions, evaluate_scores, wilson_interval
from voxrigor.benchmarking.models import BenchmarkTask, ScoreDirection


def _asv_rows() -> list[ScoreTrial]:
    values = [
        ("t1", "target", 0.9),
        ("t2", "target", 0.8),
        ("t3", "target", 0.4),
        ("n1", "nontarget", 0.7),
        ("n2", "nontarget", 0.3),
        ("n3", "nontarget", 0.2),
    ]
    return [ScoreTrial(i, label, score, "test", "all", None, None, None) for i, label, score in values]


def test_asv_operating_point_uses_declared_inclusive_threshold() -> None:
    metrics, curve, species = evaluate_scores(
        _asv_rows(), BenchmarkTask.ASV, ScoreDirection.HIGHER_IS_GENUINE, 0.5
    )
    operating = metrics["operating_point"]
    assert operating["fmr"]["errors"] == 1
    assert operating["fmr"]["trials"] == 3
    assert operating["fnmr"]["errors"] == 1
    assert operating["fnmr"]["trials"] == 3
    assert abs(metrics["eer"]["value"] - (1 / 3)) < 1e-12
    assert 0.0 <= metrics["roc_auc"] <= 1.0
    assert len(curve) == 7
    assert species == []


def test_asv_lower_is_genuine_is_equivalent_after_normalization() -> None:
    higher, _, _ = evaluate_scores(
        _asv_rows(), BenchmarkTask.ASV, ScoreDirection.HIGHER_IS_GENUINE, 0.5
    )
    inverted_rows = [
        ScoreTrial(row.trial_id, row.label, -row.score, row.split, row.condition,
                   row.attack_species, row.speaker_id, row.source_id)
        for row in _asv_rows()
    ]
    lower, _, _ = evaluate_scores(
        inverted_rows, BenchmarkTask.ASV, ScoreDirection.LOWER_IS_GENUINE, -0.5
    )
    assert lower["roc_auc"] == higher["roc_auc"]
    assert lower["eer"]["value"] == higher["eer"]["value"]
    assert lower["operating_point"]["fmr"]["rate"] == higher["operating_point"]["fmr"]["rate"]


def test_tied_asv_scores_produce_chance_level_auc_and_eer() -> None:
    rows = [
        ScoreTrial("t1", "target", 0.5, "test", "all", None, None, None),
        ScoreTrial("t2", "target", 0.5, "test", "all", None, None, None),
        ScoreTrial("n1", "nontarget", 0.5, "test", "all", None, None, None),
        ScoreTrial("n2", "nontarget", 0.5, "test", "all", None, None, None),
    ]
    metrics, _, _ = evaluate_scores(rows, BenchmarkTask.ASV, ScoreDirection.HIGHER_IS_GENUINE, 0.5)
    assert metrics["roc_auc"] == 0.5
    assert metrics["eer"]["value"] == 0.5


def test_wilson_interval_handles_zero_observed_errors() -> None:
    result = wilson_interval(0, 20)
    assert result["rate"] == 0.0
    assert result["confidence_interval"][0] == 0.0
    assert result["confidence_interval"][1] > 0.0


def test_pad_reports_each_attack_species_and_bpcer() -> None:
    rows = [
        ScoreTrial("b1", "bonafide", 0.9, "test", "clean", None, None, None),
        ScoreTrial("b2", "bonafide", 0.4, "test", "clean", None, None, None),
        ScoreTrial("s1", "spoof", 0.8, "test", "replay", "replay", None, None),
        ScoreTrial("s2", "spoof", 0.1, "test", "replay", "replay", None, None),
        ScoreTrial("s3", "spoof", 0.7, "test", "synthetic", "synthetic", None, None),
    ]
    metrics, curve, species = evaluate_scores(
        rows, BenchmarkTask.PAD, ScoreDirection.HIGHER_IS_GENUINE, 0.5
    )
    assert metrics["operating_point"]["bpcer"]["rate"] == 0.5
    assert metrics["operating_point"]["pooled_apcer"]["rate"] == 2 / 3
    assert {row["attack_species"] for row in species} == {"replay", "synthetic"}
    assert curve == []


def test_one_class_condition_is_reported_not_computable() -> None:
    rows = [
        ScoreTrial("t1", "target", 0.9, "test", "clean", None, None, None),
        ScoreTrial("n1", "nontarget", 0.1, "test", "noise-only", None, None, None),
    ]
    results = evaluate_conditions(rows, BenchmarkTask.ASV, ScoreDirection.HIGHER_IS_GENUINE, 0.5)
    assert {row["status"] for row in results} == {"not_computable"}


def test_invalid_wilson_counts_are_rejected() -> None:
    with pytest.raises(MetricError):
        wilson_interval(2, 1)
    with pytest.raises(MetricError):
        wilson_interval(0, 0)


def test_asv_without_both_classes_is_rejected() -> None:
    rows = [ScoreTrial("t1", "target", 0.9, "test", "all", None, None, None)]
    with pytest.raises(MetricError, match="both target and nontarget"):
        evaluate_scores(rows, BenchmarkTask.ASV, ScoreDirection.HIGHER_IS_GENUINE, None)


def test_pad_without_threshold_is_rejected() -> None:
    rows = [
        ScoreTrial("b1", "bonafide", 0.9, "test", "all", None, None, None),
        ScoreTrial("s1", "spoof", 0.1, "test", "all", "replay", None, None),
    ]
    with pytest.raises(MetricError, match="predeclared operating threshold"):
        evaluate_scores(rows, BenchmarkTask.PAD, ScoreDirection.HIGHER_IS_GENUINE, None)
