import json
from pathlib import Path

from typer.testing import CliRunner

from voxrigor.cli import app

runner = CliRunner()


def test_benchmark_init_validate_and_run(tmp_path: Path) -> None:
    scores = tmp_path / "scores.csv"
    scores.write_text(
        "trial_id,label,score,split\n"
        "t1,target,0.9,test\n"
        "t2,target,0.8,test\n"
        "n1,nontarget,0.2,test\n"
        "n2,nontarget,0.1,test\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "benchmark.json"
    init = runner.invoke(
        app,
        [
            "benchmark", "init", str(scores), "--manifest", str(manifest),
            "--task", "asv", "--dataset-id", "local-test", "--dataset-name", "Local Test",
            "--protocol-id", "synthetic-test", "--evaluation-split", "test", "--threshold", "0.5",
            "--threshold-source", "external",
        ],
    )
    assert init.exit_code == 0, init.output
    validate = runner.invoke(app, ["benchmark", "validate", str(manifest)])
    assert validate.exit_code == 0, validate.output
    run = runner.invoke(app, ["benchmark", "run", str(manifest), "--output", str(tmp_path / "runs")])
    assert run.exit_code == 0, run.output
    report_files = list((tmp_path / "runs").glob("*/report.json"))
    assert len(report_files) == 1
    report = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert report["metrics"]["task"] == "asv"
    assert report["sample_accounting"]["evaluated_rows"] == 4
    assert report["metrics"]["operating_point"]["fmr"]["rate"] == 0.0
    assert list(report_files[0].parent.glob("roc_curve.csv"))


def test_benchmark_pad_requires_threshold(tmp_path: Path) -> None:
    scores = tmp_path / "pad.csv"
    scores.write_text(
        "trial_id,label,score,attack_species\n"
        "b,bonafide,0.9,\n"
        "s,spoof,0.1,replay\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["benchmark", "init", str(scores), "--task", "pad", "--dataset-id", "pad-test"],
    )
    assert result.exit_code == 2
    assert "operating_threshold" in result.output


def test_benchmark_init_does_not_overwrite_manifest(tmp_path: Path) -> None:
    scores = tmp_path / "scores.csv"
    scores.write_text(
        "trial_id,label,score\nt,target,0.9\nn,nontarget,0.1\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "benchmark.json"
    manifest.write_text("do not replace", encoding="utf-8")
    result = runner.invoke(app, ["benchmark", "init", str(scores), "--manifest", str(manifest)])
    assert result.exit_code == 2
    assert manifest.read_text(encoding="utf-8") == "do not replace"


def test_benchmark_run_uses_new_runner_and_report_command(tmp_path: Path) -> None:
    scores = tmp_path / "scores.csv"
    scores.write_text(
        "trial_id,label,score\nt1,target,0.9\nt2,target,0.8\nn1,nontarget,0.2\nn2,nontarget,0.1\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "benchmark.json"
    created = runner.invoke(
        app,
        ["benchmark", "init", str(scores), "--manifest", str(manifest), "--task", "asv"],
    )
    assert created.exit_code == 0, created.output
    executed = runner.invoke(app, ["benchmark", "run", str(manifest), "--output", str(tmp_path / "runs")])
    assert executed.exit_code == 0, executed.output
    report_path = next((tmp_path / "runs").glob("*/report.json"))
    assert "Local score dataset" in report_path.read_text(encoding="utf-8")
