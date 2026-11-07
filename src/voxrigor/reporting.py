"""Atomic local storage and basic JSON/HTML report rendering."""

from __future__ import annotations

import html
import json
import os
import shutil
import tempfile
from pathlib import Path

from voxrigor.errors import ReportError
from voxrigor.models import RunReport


def write_report(report: RunReport, output_root: Path) -> Path:
    """Write report.json and report.html under a run-specific directory."""

    run_dir = output_root / str(report.run_id)
    run_dir.mkdir(parents=True, exist_ok=False)
    try:
        json_path = run_dir / "report.json"
        html_path = run_dir / "report.html"
        _atomic_write(json_path, report.model_dump_json(indent=2) + "\n")
        _atomic_write(html_path, render_html(report))
        return run_dir
    except ReportError:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise
    except OSError as exc:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise ReportError(f"Could not write run report to {run_dir}: {exc}") from exc


def render_html(report: RunReport) -> str:
    """Render a self-contained report with all dynamic text HTML-escaped."""

    rows: list[str] = []
    for result in report.results:
        rows.append(
            "<tr>"
            f"<td>{html.escape(result.test.test_id)}</td>"
            f"<td>{html.escape(result.test.name)}</td>"
            f"<td>{html.escape(result.status.value)}</td>"
            f"<td>{html.escape(result.test.category)}</td>"
            "</tr>"
        )
    table_rows = "\n".join(rows) or '<tr><td colspan="4">No tests executed</td></tr>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VoxRigor run {html.escape(str(report.run_id))}</title>
  <style>
    body {{
      font-family: system-ui, sans-serif;
      max-width: 980px;
      margin: 2rem auto;
      padding: 0 1rem;
      color: #18212b;
    }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #d7dde5; text-align: left; padding: .65rem; }}
    code {{ overflow-wrap: anywhere; }}
    .notice {{
      background: #fff7df;
      border: 1px solid #efd58c;
      padding: 1rem;
      border-radius: .5rem;
    }}
  </style>
</head>
<body>
  <h1>VoxRigor run report</h1>
  <p><strong>Project:</strong> {html.escape(report.project_name)}</p>
  <p><strong>Run ID:</strong> <code>{html.escape(str(report.run_id))}</code></p>
  <p><strong>Framework:</strong> {html.escape(report.provenance.framework_version)}</p>
  <p><strong>Started (UTC):</strong> {html.escape(report.started_at.isoformat())}</p>
  <p><strong>Finished (UTC):</strong> {html.escape(report.finished_at.isoformat())}</p>
  <div class="notice"><strong>Interpretation:</strong> This report describes only the listed
  tests and conditions. An inconclusive or no-issue-observed result is not proof that a system
  is secure.</div>
  <h2>Summary</h2>
  <pre>{html.escape(json.dumps(report.summary.model_dump(), indent=2))}</pre>
  <h2>Test results</h2>
  <table><thead><tr><th>ID</th><th>Test</th><th>Status</th><th>Category</th></tr></thead>
  <tbody>{table_rows}</tbody></table>
  <h2>Provenance</h2>
  <pre>{html.escape(json.dumps(report.provenance.model_dump(mode="json"), indent=2))}</pre>
</body>
</html>
"""


def load_report(path: Path) -> RunReport:
    """Load a previously written JSON report."""

    try:
        return RunReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReportError(f"Could not load report {path}: {exc}") from exc


def _atomic_write(path: Path, content: str) -> None:
    """Write UTF-8 text atomically and clean temporary files on failure."""

    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except OSError as exc:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)
        raise ReportError(f"Could not write {path}: {exc}") from exc
