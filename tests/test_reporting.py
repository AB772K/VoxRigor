from contextlib import suppress
from pathlib import Path

from voxrigor.manifest import create_manifest
from voxrigor.reporting import load_report, render_html, write_report
from voxrigor.testing import TestRunner as Runner
from voxrigor.testing import build_default_registry


def _report(tmp_path: Path):
    manifest_path = tmp_path / "voxrigor.json"
    manifest = create_manifest(manifest_path, "<Research Lab>")
    return Runner(build_default_registry()).run(manifest)


def test_write_and_load_report(tmp_path: Path) -> None:
    report = _report(tmp_path)
    run_dir = write_report(report, tmp_path / "runs")
    loaded = load_report(run_dir / "report.json")

    assert loaded.run_id == report.run_id
    assert (run_dir / "report.html").is_file()
    assert loaded.summary.inconclusive == 1


def test_html_escapes_untrusted_text(tmp_path: Path) -> None:
    report = _report(tmp_path)
    rendered = render_html(report)
    assert "&lt;Research Lab&gt;" in rendered
    assert "<Research Lab>" not in rendered


def test_report_run_directory_is_not_overwritten(tmp_path: Path) -> None:
    report = _report(tmp_path)
    output = tmp_path / "runs"
    write_report(report, output)
    with suppress(FileExistsError):
        write_report(report, output)
        raise AssertionError("Existing run directory must not be overwritten")
