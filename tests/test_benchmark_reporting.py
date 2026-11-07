import json
from pathlib import Path

import pytest

from voxrigor.benchmarking.dataset import load_score_dataset
from voxrigor.benchmarking.errors import BenchmarkError
from voxrigor.benchmarking.reporting import (
    build_benchmark_report,
    load_benchmark_report,
    render_benchmark_html,
    write_benchmark_report,
)

ROOT = Path(__file__).parents[1]


def test_asv_report_writes_json_html_and_roc_csv(tmp_path: Path) -> None:
    dataset = load_score_dataset(ROOT / "examples/fixtures/asv_benchmark.json")
    report, curve = build_benchmark_report(dataset)
    run_dir = write_benchmark_report(report, tmp_path / "runs", curve)

    loaded = load_benchmark_report(run_dir / "report.json")
    html = (run_dir / "report.html").read_text(encoding="utf-8")
    curve_csv = (run_dir / "roc_curve.csv").read_text(encoding="utf-8")

    assert loaded.run_id == report.run_id
    assert "Offline Benchmark Report" in html
    assert "threshold_normalized" in curve_csv
    assert loaded.group_overlap_counts == {}
    assert loaded.sample_accounting["input_rows"] == 10
    assert loaded.split_label_counts["test"] == {"nontarget": 4, "target": 4}


def test_pad_report_writes_species_csv(tmp_path: Path) -> None:
    dataset = load_score_dataset(ROOT / "examples/fixtures/pad_benchmark.json")
    report, curve = build_benchmark_report(dataset)
    run_dir = write_benchmark_report(report, tmp_path / "runs", curve)
    species_csv = (run_dir / "pad_attack_species.csv").read_text(encoding="utf-8")

    assert curve == []
    assert "replay" in species_csv
    assert "synthetic_speech" in species_csv
    assert "voice_conversion" in species_csv


def test_report_html_escapes_untrusted_dataset_name(tmp_path: Path) -> None:
    manifest_path = ROOT / "examples/fixtures/asv_benchmark.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["dataset_name"] = '<img src=x onerror="alert(1)">'
    temp_manifest = tmp_path / "benchmark.json"
    temp_manifest.write_text(json.dumps(raw), encoding="utf-8")
    # The score path is relative to the manifest, so copy the fixture beside it.
    source_scores = ROOT / "examples/fixtures/asv_scores.csv"
    (tmp_path / "asv_scores.csv").write_bytes(source_scores.read_bytes())
    raw["score_file"] = "asv_scores.csv"
    temp_manifest.write_text(json.dumps(raw), encoding="utf-8")

    dataset = load_score_dataset(temp_manifest)
    report, _ = build_benchmark_report(dataset)
    html = render_benchmark_html(report)
    assert '<img src=x onerror="alert(1)">' not in html
    assert "&lt;img" in html


def test_duplicate_run_directory_does_not_delete_existing_report(tmp_path: Path) -> None:
    dataset = load_score_dataset(ROOT / "examples/fixtures/asv_benchmark.json")
    report, curve = build_benchmark_report(dataset)
    run_dir = write_benchmark_report(report, tmp_path / "runs", curve)
    original = (run_dir / "report.json").read_text(encoding="utf-8")

    with pytest.raises(BenchmarkError, match="write benchmark report"):
        write_benchmark_report(report, tmp_path / "runs", curve)

    assert (run_dir / "report.json").read_text(encoding="utf-8") == original


def test_invalid_report_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad-report.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(BenchmarkError, match="missing or invalid"):
        load_benchmark_report(path)


def test_report_records_group_audit_policy(tmp_path: Path) -> None:
    manifest_path = ROOT / "examples/fixtures/asv_benchmark.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["group_columns"] = ["speaker_id"]
    raw["require_group_disjointness"] = False
    scores = ROOT / "examples/fixtures/asv_scores.csv"
    raw["score_file_sha256"] = __import__("hashlib").sha256(scores.read_bytes()).hexdigest()
    temp_manifest = tmp_path / "benchmark.json"
    (tmp_path / "asv_scores.csv").write_bytes(scores.read_bytes())
    raw["score_file"] = "asv_scores.csv"
    temp_manifest.write_text(json.dumps(raw), encoding="utf-8")

    dataset = load_score_dataset(temp_manifest)
    report, _ = build_benchmark_report(dataset)

    assert report.dataset["group_columns"] == ["speaker_id"]
    assert report.dataset["require_group_disjointness"] is False
    assert any("fewer than two splits" in warning for warning in report.warnings) is False


def test_report_warns_when_declared_groups_overlap_across_splits(tmp_path: Path) -> None:
    source_scores = ROOT / "examples/fixtures/asv_scores.csv"
    lines = source_scores.read_text(encoding="utf-8").splitlines()
    # Reuse one pseudonymous speaker ID in dev and test to exercise the overlap warning.
    lines[3] = lines[3].replace("test-spk-01", "dev-spk-01")
    score_text = "\n".join(lines) + "\n"
    (tmp_path / "scores.csv").write_bytes(score_text.encode("utf-8"))
    raw = json.loads((ROOT / "examples/fixtures/asv_benchmark.json").read_text(encoding="utf-8"))
    import hashlib

    raw["score_file"] = "scores.csv"
    raw["score_file_sha256"] = hashlib.sha256(score_text.encode("utf-8")).hexdigest()
    raw["group_columns"] = ["speaker_id"]
    manifest_path = tmp_path / "benchmark.json"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")

    dataset = load_score_dataset(manifest_path)
    report, _ = build_benchmark_report(dataset)

    assert report.group_overlap_counts == {"speaker_id": 1}
    assert any("Overlapping group identifiers" in warning for warning in report.warnings)
