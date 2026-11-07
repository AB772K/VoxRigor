"""Local, privacy-conscious output for score-based benchmark evaluations."""

from __future__ import annotations

import csv
import html
import json
import os
import platform
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from voxrigor import __version__
from voxrigor.benchmarking.dataset import ScoreDataset
from voxrigor.benchmarking.errors import BenchmarkError
from voxrigor.benchmarking.metrics import evaluate_conditions, evaluate_scores
from voxrigor.benchmarking.models import BenchmarkReport


def build_benchmark_report(dataset: ScoreDataset) -> tuple[BenchmarkReport, list[dict[str, float | None]]]:
    manifest = dataset.manifest
    metrics, curve, species = evaluate_scores(
        dataset.records, manifest.task, manifest.score_direction, manifest.operating_threshold
    )
    conditions = evaluate_conditions(
        dataset.records, manifest.task, manifest.score_direction, manifest.operating_threshold
    )
    warnings: list[str] = [
        "This report evaluates supplied decision scores; VoxRigor did not run the upstream model.",
        "A benchmark result is not a certification or a claim that an authentication system is secure.",
        "Confidence intervals are trial-level and do not correct for speaker/source clustering.",
    ]
    if manifest.threshold_source.value == "development_split":
        warnings.append(
            "Threshold-selection provenance is user-declared. VoxRigor confirms that the named "
            "split exists and differs from the evaluation split, but cannot prove how the threshold was selected."
        )
    if dataset.unknown_columns:
        warnings.append(
            "Unmapped CSV columns were not used: " + ", ".join(dataset.unknown_columns)
        )
    if any(dataset.group_overlap_counts.values()):
        warnings.append(
            "Overlapping group identifiers were observed across splits. Review the dataset protocol; "
            "VoxRigor does not assume speaker/source disjointness unless explicitly required."
        )
    if manifest.task.value == "pad":
        warnings.append(
            "PAD metrics are reported per attack species. Pooled APCER is sample-weighted and is not a substitute for species-level results."
        )
    if manifest.license_name.strip().lower() == "unspecified":
        warnings.append("Dataset license is unspecified; review source terms before sharing or redistributing data/results.")
    if not manifest.group_columns:
        warnings.append(
            "No speaker/source group columns were declared; no cross-split group-overlap audit was performed."
        )
    elif len(dataset.split_counts) < 2:
        warnings.append(
            "Group columns were supplied, but fewer than two splits are present; "
            "cross-split group separation could not be assessed."
        )
    report = BenchmarkReport(
        run_id=str(uuid4()),
        generated_at=datetime.now(UTC).isoformat(),
        framework_version=__version__,
        python_version=platform.python_version(),
        platform=platform.platform(),
        dataset={
            "dataset_id": manifest.dataset_id,
            "dataset_name": manifest.dataset_name,
            "dataset_version": manifest.dataset_version,
            "task": manifest.task.value,
            "protocol_id": manifest.protocol_id,
            "evaluation_split": manifest.evaluation_split,
            "score_direction": manifest.score_direction.value,
            "score_file_name": dataset.score_path.name,
            "source_url": manifest.source_url,
            "license_name": manifest.license_name,
            "citation": manifest.citation,
            "access_date": manifest.access_date.isoformat() if manifest.access_date else None,
            "threshold_source": manifest.threshold_source.value,
            "threshold_selection_split": manifest.threshold_selection_split,
            "group_columns": manifest.group_columns,
            "require_group_disjointness": manifest.require_group_disjointness,
        },
        provenance={
            "score_file_sha256": dataset.score_file_sha256,
            "dataset_manifest_sha256": dataset.manifest_sha256,
            "metric_implementation": "voxrigor-score-metrics-0.1",
        },
        sample_accounting={
            "input_rows": dataset.input_rows,
            "evaluated_rows": len(dataset.records),
            "other_split_rows": dataset.other_split_rows,
        },
        label_counts=dataset.label_counts,
        split_counts=dataset.split_counts,
        split_label_counts=dataset.split_label_counts,
        group_overlap_counts=dataset.group_overlap_counts,
        metrics=metrics,
        condition_metrics=conditions,
        attack_species_metrics=species,
        warnings=warnings,
    )
    return report, curve


def write_benchmark_report(
    report: BenchmarkReport,
    output_root: Path,
    curve: list[dict[str, float | None]],
) -> Path:
    run_dir = output_root / str(report.run_id)
    created_run_dir = False
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        run_dir.mkdir(parents=False, exist_ok=False)
        created_run_dir = True
        _atomic_write(run_dir / "report.json", report.model_dump_json(indent=2) + "\n")
        _atomic_write(run_dir / "report.html", render_benchmark_html(report))
        if curve:
            _write_csv_atomic(
                run_dir / "roc_curve.csv",
                ["threshold_normalized", "fmr", "fnmr", "tpr"],
                curve,
            )
        if report.attack_species_metrics:
            _write_csv_atomic(
                run_dir / "pad_attack_species.csv",
                ["attack_species", "apcer_errors", "apcer_trials", "apcer_rate", "ci95_lower", "ci95_upper"],
                [
                    {
                        "attack_species": item["attack_species"],
                        "apcer_errors": item["apcer"]["errors"],
                        "apcer_trials": item["apcer"]["trials"],
                        "apcer_rate": item["apcer"]["rate"],
                        "ci95_lower": item["apcer"]["confidence_interval"][0],
                        "ci95_upper": item["apcer"]["confidence_interval"][1],
                    }
                    for item in report.attack_species_metrics
                ],
            )
        return run_dir
    except Exception as exc:
        if created_run_dir:
            shutil.rmtree(run_dir, ignore_errors=True)
        if isinstance(exc, BenchmarkError):
            raise
        raise BenchmarkError("Could not write benchmark report") from exc


def render_benchmark_html(report: BenchmarkReport) -> str:
    data = report.model_dump(mode="json")
    dataset = data["dataset"]
    metric_json = html.escape(json.dumps(data["metrics"], indent=2, ensure_ascii=False))
    condition_json = html.escape(json.dumps(data["condition_metrics"], indent=2, ensure_ascii=False))
    species_json = html.escape(json.dumps(data["attack_species_metrics"], indent=2, ensure_ascii=False))
    warning_items = "".join(f"<li>{html.escape(item)}</li>" for item in report.warnings)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>VoxRigor benchmark {html.escape(str(report.run_id))}</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#17202a}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:1rem;border-radius:.5rem}}
.notice{{background:#fff7df;border:1px solid #efd58c;padding:1rem;border-radius:.5rem}}
</style></head><body>
<h1>VoxRigor Offline Benchmark Report</h1>
<p><strong>Dataset:</strong> {html.escape(str(dataset['dataset_name']))} ({html.escape(str(dataset['dataset_id']))})</p>
<p><strong>Task:</strong> {html.escape(str(dataset['task']).upper())} · <strong>Protocol:</strong> {html.escape(str(dataset['protocol_id']))}</p>
<p><strong>Evaluation split:</strong> {html.escape(str(dataset['evaluation_split']))}</p>
<p><strong>Run ID:</strong> <code>{html.escape(str(report.run_id))}</code></p>
<div class="notice"><strong>Interpretation:</strong> VoxRigor evaluated supplied score trials. It did not run or independently validate the upstream biometric model. Results are protocol- and dataset-specific and are not certification.</div>
<h2>Sample accounting</h2><pre>{html.escape(json.dumps(data['sample_accounting'],indent=2))}</pre>
<h2>Label counts</h2><pre>{html.escape(json.dumps(data['label_counts'],indent=2))}</pre>
<h2>Split label counts</h2><pre>{html.escape(json.dumps(data['split_label_counts'],indent=2))}</pre>
<h2>Metrics</h2><pre>{metric_json}</pre>
<h2>Condition breakdown</h2><pre>{condition_json}</pre>
<h2>Attack-species breakdown</h2><pre>{species_json}</pre>
<h2>Warnings and limitations</h2><ul>{warning_items}</ul>
<h2>Provenance</h2><pre>{html.escape(json.dumps(data['provenance'],indent=2))}</pre>
</body></html>"""


def load_benchmark_report(path: Path) -> BenchmarkReport:
    try:
        return BenchmarkReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, ValidationError) as exc:
        raise BenchmarkError("Benchmark report is missing or invalid") from exc


def _atomic_write(path: Path, content: str) -> None:
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except OSError as exc:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
        raise BenchmarkError("Failed to atomically write benchmark output") from exc


def _write_csv_atomic(path: Path, columns: list[str], rows: list[dict[str, object]]) -> None:
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temp_name = handle.name
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                safe_row = {key: _safe_csv_value(value) for key, value in row.items()}
                writer.writerow(safe_row)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except OSError as exc:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
        raise BenchmarkError("Failed to write benchmark CSV output") from exc


def _safe_csv_value(value: object) -> object:
    """Neutralize spreadsheet formula prefixes in untrusted string cells."""

    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@", "\t", "\r"}:
        return "'" + value
    return value
