from pathlib import Path

from typer.testing import CliRunner

from voxrigor.cli import app

runner = CliRunner()


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Reproducible security research" in result.stdout


def test_init_validate_list_run_and_report(tmp_path: Path) -> None:
    project_dir = tmp_path / "research"
    init_result = runner.invoke(app, ["init", str(project_dir), "--name", "CLI Lab"])
    assert init_result.exit_code == 0, init_result.stdout

    manifest_path = project_dir / "voxrigor.json"
    validate_result = runner.invoke(app, ["validate", str(manifest_path)])
    assert validate_result.exit_code == 0, validate_result.stdout

    list_result = runner.invoke(app, ["tests"])
    assert list_result.exit_code == 0
    assert "core.runtime-info" in list_result.stdout

    run_result = runner.invoke(
        app,
        ["run", "--project", str(manifest_path), "--output", str(project_dir / "runs")],
    )
    assert run_result.exit_code == 0, run_result.stdout
    report_files = list((project_dir / "runs").glob("*/report.json"))
    assert len(report_files) == 1

    report_result = runner.invoke(app, ["report", str(report_files[0])])
    assert report_result.exit_code == 0, report_result.stdout
    assert "CLI Lab" in report_result.stdout


def test_cli_validation_failure_has_nonzero_exit(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate", str(tmp_path / "missing.json")])
    assert result.exit_code == 2
    assert "not found" in result.output.lower()
