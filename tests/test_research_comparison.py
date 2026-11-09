from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from voxrigor.cli import app
from voxrigor.research.comparison import (
    ResearchComparisonError,
    build_research_comparison_report,
    load_research_comparison,
    run_research_comparison,
)

runner = CliRunner()


def _write_score_dataset(
    directory: Path,
    dataset_id: str,
    rows: list[tuple[str, str, float, str, str]],
    *,
    split: str,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    csv_lines = ["trial_id,label,score,split,speaker_id,source_id,condition"]
    for trial_id, label, score, speaker_id, source_id in rows:
        csv_lines.append(f"{trial_id},{label},{score},{split},{speaker_id},{source_id},clean")
    csv_text = "\n".join(csv_lines) + "\n"
    score_path = directory / "scores.csv"
    score_path.write_text(csv_text, encoding="utf-8", newline="\n")
    manifest: dict[str, Any] = {
        "schema_version": "0.1",
        "dataset_id": dataset_id,
        "dataset_name": dataset_id,
        "dataset_version": "1.0",
        "task": "asv",
        "protocol_id": "paired-asv-v1",
        "score_file": "scores.csv",
        "score_file_sha256": hashlib.sha256(score_path.read_bytes()).hexdigest(),
        "evaluation_split": split,
        "score_direction": "higher_is_genuine",
        "group_columns": ["speaker_id", "source_id"],
        "license_name": "synthetic-test-only",
    }
    manifest_path = directory / "benchmark.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def _rows(
    scores: list[float],
    labels: list[str],
    prefix: str,
) -> list[tuple[str, str, float, str, str]]:
    return [
        (
            f"{prefix}-{index + 1}",
            label,
            score,
            f"speaker-{index + 1:02d}",
            f"recording-{index + 1:02d}",
        )
        for index, (score, label) in enumerate(zip(scores, labels, strict=True))
    ]


def _system_experiment(
    root: Path,
    *,
    system_id: str,
    calibration_scores: list[float],
    in_domain_scores: list[float],
    cross_domain_scores: list[float],
    evaluation_trial_suffix: str = "",
    mismatch_label: bool = False,
) -> Path:
    system_root = root / system_id
    calibration_labels = [
        "target",
        "target",
        "target",
        "target",
        "nontarget",
        "nontarget",
        "nontarget",
        "nontarget",
    ]
    evaluation_labels = [
        "target",
        "target",
        "target",
        "target",
        "nontarget",
        "nontarget",
        "nontarget",
        "nontarget",
    ]
    calibration_rows = _rows(calibration_scores, calibration_labels, "dev")
    in_rows = _rows(in_domain_scores, evaluation_labels, "in")
    cross_rows = _rows(cross_domain_scores, evaluation_labels, "cross")
    if evaluation_trial_suffix:
        in_rows[0] = (
            f"in-alt-{evaluation_trial_suffix}",
            in_rows[0][1],
            in_rows[0][2],
            in_rows[0][3],
            in_rows[0][4],
        )
    if mismatch_label:
        row = in_rows[0]
        in_rows[0] = (row[0], "nontarget", row[2], row[3], row[4])

    _write_score_dataset(
        system_root / "calibration",
        "shared-development",
        calibration_rows,
        split="development",
    )
    _write_score_dataset(
        system_root / "evaluation-in-domain",
        "shared-in-domain",
        in_rows,
        split="test",
    )
    _write_score_dataset(
        system_root / "evaluation-cross-domain",
        "shared-cross-domain",
        cross_rows,
        split="test",
    )

    experiment = {
        "schema_version": "0.1",
        "experiment_id": f"{system_id}-experiment",
        "description": f"Synthetic paired test for {system_id}.",
        "system_id": system_id,
        "calibration_dataset_manifest": "calibration/benchmark.json",
        "evaluation_datasets": [
            {
                "domain_id": "in_domain",
                "dataset_manifest": "evaluation-in-domain/benchmark.json",
            },
            {
                "domain_id": "cross_domain",
                "dataset_manifest": "evaluation-cross-domain/benchmark.json",
            },
        ],
        "target_fmr": 0.1,
        "probability_threshold": 0.5,
    }
    path = system_root / "experiment.json"
    path.write_text(json.dumps(experiment, indent=2), encoding="utf-8")
    return path


def _comparison_manifest(
    root: Path,
    *,
    reference_system_id: str = "model-a",
    paired_bootstrap: bool = True,
    mismatch_trial_ids: bool = False,
    mismatch_labels: bool = False,
) -> Path:
    labels = [
        "target",
        "target",
        "target",
        "target",
        "nontarget",
        "nontarget",
        "nontarget",
        "nontarget",
    ]
    del labels
    model_a = _system_experiment(
        root,
        system_id="model-a",
        calibration_scores=[0.96, 0.90, 0.84, 0.78, 0.38, 0.32, 0.26, 0.20],
        in_domain_scores=[0.96, 0.91, 0.86, 0.81, 0.40, 0.35, 0.30, 0.25],
        cross_domain_scores=[0.91, 0.86, 0.81, 0.76, 0.55, 0.50, 0.45, 0.40],
    )
    model_b = _system_experiment(
        root,
        system_id="model-b",
        calibration_scores=[0.82, 0.76, 0.70, 0.64, 0.62, 0.56, 0.50, 0.44],
        in_domain_scores=[0.80, 0.72, 0.64, 0.56, 0.62, 0.58, 0.50, 0.44],
        cross_domain_scores=[0.76, 0.70, 0.64, 0.58, 0.66, 0.60, 0.54, 0.48],
        evaluation_trial_suffix="changed" if mismatch_trial_ids else "",
        mismatch_label=mismatch_labels,
    )
    manifest: dict[str, Any] = {
        "schema_version": "0.1",
        "comparison_id": "paired-model-comparison",
        "description": "Synthetic paired model comparison test.",
        "reference_system_id": reference_system_id,
        "systems": [
            {"system_id": "model-a", "experiment_manifest": "model-a/experiment.json"},
            {"system_id": "model-b", "experiment_manifest": "model-b/experiment.json"},
        ],
    }
    if paired_bootstrap:
        manifest["paired_cluster_bootstrap"] = {
            "cluster_column": "speaker_id",
            "replicates": 200,
            "seed": 2026,
            "confidence_level": 0.95,
        }
    path = root / "comparison.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    assert model_a.is_file() and model_b.is_file()
    return path


def test_paired_comparison_reports_system_deltas_and_deterministic_bootstrap(
    tmp_path: Path,
) -> None:
    manifest = _comparison_manifest(tmp_path)
    loaded = load_research_comparison(manifest)
    first = build_research_comparison_report(loaded)
    second = build_research_comparison_report(loaded)

    assert first["reference_system_id"] == "model-a"
    assert {item["system_id"] for item in first["systems"]} == {"model-a", "model-b"}
    assert [item["domain_id"] for item in first["evaluation_domains"]] == [
        "in_domain",
        "cross_domain",
    ]
    in_domain = first["evaluation_domains"][0]
    assert in_domain["systems"]["model-a"]["eer"] < in_domain["systems"]["model-b"]["eer"]
    assert in_domain["differences_vs_reference"]["model-b"]["eer"] > 0
    bootstrap = in_domain["paired_cluster_bootstrap"]
    assert bootstrap["replicates_requested"] == 200
    assert bootstrap["replicates_valid"] >= 160
    assert bootstrap == second["evaluation_domains"][0]["paired_cluster_bootstrap"]
    delta = bootstrap["systems_vs_reference"]["model-b"]["eer"]
    assert delta["point_difference"] > 0
    lower, upper = delta["percentile_interval"]
    assert lower <= upper


def test_paired_comparison_writes_json_html_and_cli_reports(tmp_path: Path) -> None:
    manifest = _comparison_manifest(tmp_path, paired_bootstrap=False)
    run_dir = run_research_comparison(manifest, tmp_path / "runs")
    assert (run_dir / "report.json").is_file()
    html_report = (run_dir / "report.html").read_text(encoding="utf-8")
    assert "Paired Model Comparison" in html_report
    assert "model-a" in html_report and "model-b" in html_report

    cli_result = runner.invoke(
        app,
        [
            "research",
            "compare",
            str(manifest),
            "--output",
            str(tmp_path / "cli-runs"),
        ],
    )
    assert cli_result.exit_code == 0, cli_result.output
    assert "Paired research comparison completed" in cli_result.output


def test_paired_comparison_rejects_unmatched_trial_ids(tmp_path: Path) -> None:
    manifest = _comparison_manifest(tmp_path, mismatch_trial_ids=True)
    with pytest.raises(ResearchComparisonError, match="trials are not paired"):
        load_research_comparison(manifest)


def test_paired_comparison_rejects_label_or_group_metadata_mismatch(
    tmp_path: Path,
) -> None:
    manifest = _comparison_manifest(tmp_path, mismatch_labels=True)
    with pytest.raises(ResearchComparisonError, match="metadata differs"):
        load_research_comparison(manifest)


def test_paired_comparison_rejects_unknown_reference_and_duplicate_systems(
    tmp_path: Path,
) -> None:
    manifest = _comparison_manifest(tmp_path, paired_bootstrap=False)
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw["reference_system_id"] = "missing-system"
    manifest.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    with pytest.raises(ResearchComparisonError, match="reference_system_id"):
        load_research_comparison(manifest)

    raw["reference_system_id"] = "model-a"
    raw["systems"][1]["system_id"] = "model-a"
    manifest.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    with pytest.raises(ResearchComparisonError, match="unique"):
        load_research_comparison(manifest)
