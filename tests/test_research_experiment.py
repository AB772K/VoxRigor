from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from voxrigor.benchmarking.dataset import ScoreTrial
from voxrigor.benchmarking.models import ScoreDirection
from voxrigor.cli import app
from voxrigor.research.calibration import evaluate_calibration, fit_platt_calibrator
from voxrigor.research.experiment import ResearchExperimentError, load_research_experiment
from voxrigor.research.runner import (
    _select_threshold_at_target_fmr,
    build_research_report,
    run_research_experiment,
)

runner = CliRunner()


def _dataset(directory: Path, dataset_id: str, rows: list[tuple[str, float, str]]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    csv_lines = ["trial_id,label,score,split,speaker_id,source_id"]
    for index, (label, score, speaker) in enumerate(rows):
        csv_lines.append(
            f"{dataset_id}-{index},{label},{score},test,{speaker},{dataset_id}-src-{index}"
        )
    csv_text = "\n".join(csv_lines) + "\n"
    score_path = directory / "scores.csv"
    score_path.write_text(csv_text, encoding="utf-8", newline="\n")
    score_sha256 = hashlib.sha256(score_path.read_bytes()).hexdigest()
    manifest: dict[str, Any] = {
        "schema_version": "0.1",
        "dataset_id": dataset_id,
        "dataset_name": dataset_id,
        "dataset_version": "1.0",
        "task": "asv",
        "protocol_id": "synthetic-asv-v1",
        "score_file": "scores.csv",
        "score_file_sha256": score_sha256,
        "evaluation_split": "test",
        "score_direction": "higher_is_genuine",
        "group_columns": ["speaker_id", "source_id"],
        "license_name": "synthetic-test-only",
    }
    manifest_path = directory / "benchmark.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def _experiment(root: Path, *, overlap: bool = False) -> Path:
    calibration = _dataset(
        root / "calibration",
        "calibration-set",
        [
            ("target", 0.95, "cal-a"),
            ("target", 0.85, "cal-b"),
            ("target", 0.75, "cal-c"),
            ("nontarget", 0.40, "cal-d"),
            ("nontarget", 0.30, "cal-e"),
            ("nontarget", 0.20, "cal-f"),
        ],
    )
    shared = "cal-a" if overlap else "eval-a"
    in_domain = _dataset(
        root / "evaluation-in-domain",
        "in-domain-set",
        [
            ("target", 0.90, "eval-b"),
            ("target", 0.70, "eval-c"),
            ("nontarget", 0.45, shared),
            ("nontarget", 0.25, "eval-d"),
        ],
    )
    cross_domain = _dataset(
        root / "evaluation-cross-domain",
        "cross-domain-set",
        [
            ("target", 0.72, "cross-a"),
            ("target", 0.62, "cross-b"),
            ("nontarget", 0.58, "cross-c"),
            ("nontarget", 0.38, "cross-d"),
        ],
    )
    manifest = {
        "schema_version": "0.1",
        "experiment_id": "research-test-01",
        "description": "Synthetic cross-domain calibration test.",
        "system_id": "synthetic-system-v1",
        "calibration_dataset_manifest": "calibration/benchmark.json",
        "evaluation_datasets": [
            {"domain_id": "in_domain", "dataset_manifest": "evaluation-in-domain/benchmark.json"},
            {
                "domain_id": "cross_domain",
                "dataset_manifest": "evaluation-cross-domain/benchmark.json",
            },
        ],
        "target_fmr": 0.1,
        "probability_threshold": 0.5,
        "group_columns": ["speaker_id", "source_id"],
        "require_group_disjointness": True,
    }
    path = root / "experiment.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    assert calibration.is_file() and in_domain.is_file() and cross_domain.is_file()
    return path


def test_platt_calibration_is_monotonic_and_reports_held_out_metrics() -> None:
    records = (
        ScoreTrial("t1", "target", 0.9, "dev", "clean", None, "s1", "r1"),
        ScoreTrial("t2", "target", 0.8, "dev", "clean", None, "s2", "r2"),
        ScoreTrial("n1", "nontarget", 0.2, "dev", "clean", None, "s3", "r3"),
        ScoreTrial("n2", "nontarget", 0.1, "dev", "clean", None, "s4", "r4"),
    )
    calibrator = fit_platt_calibrator(records, ScoreDirection.HIGHER_IS_GENUINE)
    assert calibrator.predict_probability(0.9) > calibrator.predict_probability(0.1)
    metrics = evaluate_calibration(records, calibrator, ScoreDirection.HIGHER_IS_GENUINE)
    assert 0 <= metrics["brier_score"] <= 1
    assert 0 <= metrics["expected_calibration_error"] <= 1
    assert metrics["sample_counts"] == {"target": 2, "nontarget": 2}


def test_platt_calibration_normalizes_lower_is_genuine_direction() -> None:
    records = (
        ScoreTrial("t1", "target", 0.1, "dev", "clean", None, "s1", "r1"),
        ScoreTrial("t2", "target", 0.2, "dev", "clean", None, "s2", "r2"),
        ScoreTrial("n1", "nontarget", 0.8, "dev", "clean", None, "s3", "r3"),
        ScoreTrial("n2", "nontarget", 0.9, "dev", "clean", None, "s4", "r4"),
    )
    calibrator = fit_platt_calibrator(records, ScoreDirection.LOWER_IS_GENUINE)
    assert calibrator.predict_probability(-0.1) > calibrator.predict_probability(-0.9)


def test_threshold_is_selected_from_calibration_only() -> None:
    records = (
        ScoreTrial("t1", "target", 0.9, "dev", "clean", None, None, None),
        ScoreTrial("n1", "nontarget", 0.4, "dev", "clean", None, None, None),
        ScoreTrial("n2", "nontarget", 0.3, "dev", "clean", None, None, None),
    )
    threshold = _select_threshold_at_target_fmr(
        records, ScoreDirection.HIGHER_IS_GENUINE, target_fmr=0.1
    )
    assert threshold > 0.4


def test_full_research_experiment_writes_reports_and_checks_group_disjointness(
    tmp_path: Path,
) -> None:
    manifest = _experiment(tmp_path)
    loaded = load_research_experiment(manifest)
    report = build_research_report(loaded)
    assert len(report["evaluation_datasets"]) == 2
    assert report["calibration"]["fit_partition"] == "declared calibration dataset only"
    assert all(
        item["calibration_metrics"]["sample_counts"] == {"target": 2, "nontarget": 2}
        for item in report["evaluation_datasets"]
    )
    assert all(
        check["overlap_count"] == 0
        for group in report["group_overlap"]
        for check in group["pairwise_overlaps"]
    )

    run_dir = run_research_experiment(manifest, tmp_path / "runs")
    assert (run_dir / "report.json").is_file()
    assert (run_dir / "report.html").is_file()
    saved = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert saved["experiment_id"] == "research-test-01"
    assert "Raw EER" in (run_dir / "report.html").read_text(encoding="utf-8")


def test_group_overlap_is_rejected_when_disjointness_is_required(tmp_path: Path) -> None:
    manifest = _experiment(tmp_path, overlap=True)
    with pytest.raises(ResearchExperimentError, match="overlap"):
        build_research_report(load_research_experiment(manifest))


def test_experiment_manifest_rejects_path_escape_and_duplicate_domains(tmp_path: Path) -> None:
    manifest = _experiment(tmp_path)
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw["calibration_dataset_manifest"] = "../outside.json"
    manifest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ResearchExperimentError, match="invalid"):
        load_research_experiment(manifest)

    raw["calibration_dataset_manifest"] = "calibration/benchmark.json"
    raw["evaluation_datasets"][1]["domain_id"] = "in_domain"
    manifest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ResearchExperimentError, match="invalid"):
        load_research_experiment(manifest)


def test_research_cli_executes_and_emits_machine_readable_report(tmp_path: Path) -> None:
    manifest = _experiment(tmp_path)
    result = runner.invoke(
        app,
        ["research", "evaluate", str(manifest), "--output", str(tmp_path / "cli-runs")],
    )
    assert result.exit_code == 0, result.output
    assert "Machine-readable results" in result.output


def test_calibrator_rejects_single_class_and_bad_configuration() -> None:
    records = (
        ScoreTrial("t1", "target", 0.9, "dev", "clean", None, None, None),
        ScoreTrial("t2", "target", 0.8, "dev", "clean", None, None, None),
    )
    with pytest.raises(ValueError, match="both target and nontarget"):
        fit_platt_calibrator(records, ScoreDirection.HIGHER_IS_GENUINE)
    with pytest.raises(ValueError, match="optimizer configuration"):
        fit_platt_calibrator(
            records + (ScoreTrial("n1", "nontarget", 0.1, "dev", "clean", None, None, None),),
            ScoreDirection.HIGHER_IS_GENUINE,
            regularization=0,
        )


def test_research_manifest_rejects_duplicate_group_columns_and_missing_required_columns(
    tmp_path: Path,
) -> None:
    manifest = _experiment(tmp_path)
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw["group_columns"] = ["speaker_id", "speaker_id"]
    manifest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ResearchExperimentError, match="invalid"):
        load_research_experiment(manifest)

    raw["group_columns"] = ["speaker_id"]
    raw["require_group_disjointness"] = False
    manifest.write_text(json.dumps(raw), encoding="utf-8")
    calibration_path = tmp_path / "calibration" / "benchmark.json"
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    calibration["score_file"] = "missing.csv"
    calibration_path.write_text(json.dumps(calibration), encoding="utf-8")
    with pytest.raises(ResearchExperimentError, match="failed validation"):
        load_research_experiment(manifest)
