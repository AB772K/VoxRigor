"""Command-line interface for the VoxRigor Phase 1 core."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError

from voxrigor import __version__
from voxrigor.benchmarking.dataset import load_score_dataset, sha256_file
from voxrigor.benchmarking.errors import BenchmarkError, DatasetManifestError, ScoreFileError
from voxrigor.benchmarking.models import (
    BenchmarkTask,
    DatasetManifest,
    ScoreDirection,
    ThresholdSource,
)
from voxrigor.benchmarking.reporting import load_benchmark_report
from voxrigor.benchmarking.runner import run_benchmark
from voxrigor.biometrics.cli import models_app
from voxrigor.errors import ManifestError, ProjectExistsError, ReportError, TestNotFoundError
from voxrigor.manifest import DEFAULT_MANIFEST, create_manifest, load_manifest
from voxrigor.reporting import load_report, write_report
from voxrigor.testing import TestRunner, build_default_registry

DEFAULT_PROJECT_PATH = Path(".")
DEFAULT_MANIFEST_PATH = Path(DEFAULT_MANIFEST)
DEFAULT_RUN_OUTPUT = Path("runs")

app = typer.Typer(
    name="voxrigor",
    help="Reproducible security research for voice-authentication systems.",
    no_args_is_help=True,
    add_completion=False,
)
benchmark_app = typer.Typer(
    name="benchmark",
    help="Offline evaluation of precomputed ASV/PAD score-trial files.",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(benchmark_app, name="benchmark")
app.add_typer(models_app, name="models")


def _handle_error(error: Exception) -> NoReturn:
    typer.secho(f"Error: {error}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=2) from error


@app.callback()
def main() -> None:
    """VoxRigor core commands. Phase 1 supports offline diagnostics only."""


@app.command()
def version() -> None:
    """Display the installed framework version."""

    typer.echo(f"VoxRigor {__version__}")


@app.command()
def init(
    path: Annotated[
        Path, typer.Argument(help="Directory in which to create the project.")
    ] = DEFAULT_PROJECT_PATH,
    name: Annotated[
        str, typer.Option("--name", help="Human-readable project name.")
    ] = "VoxRigor Research",
    description: Annotated[
        str, typer.Option("--description", help="Optional project description.")
    ] = "",
) -> None:
    """Create a new offline project manifest."""

    manifest_path = path / DEFAULT_MANIFEST
    try:
        manifest = create_manifest(manifest_path, name=name, description=description)
    except (ProjectExistsError, ValidationError, OSError) as exc:
        _handle_error(exc)
    typer.secho(f"Created project manifest: {manifest_path}", fg=typer.colors.GREEN)
    typer.echo(f"Project ID: {manifest.project_id}")
    typer.echo("Mode: offline (network target testing is not available in this version)")


@app.command()
def validate(
    manifest_path: Annotated[
        Path, typer.Argument(help="Path to voxrigor.json.")
    ] = DEFAULT_MANIFEST_PATH,
) -> None:
    """Validate a project manifest."""

    try:
        manifest = load_manifest(manifest_path)
    except ManifestError as exc:
        _handle_error(exc)
    typer.secho("Manifest is valid.", fg=typer.colors.GREEN)
    typer.echo(f"Name: {manifest.name}")
    typer.echo(f"Project ID: {manifest.project_id}")
    typer.echo(f"Schema: {manifest.schema_version}")
    typer.echo(f"Scope: {manifest.scope.mode}")


@app.command("tests")
def list_tests() -> None:
    """List built-in tests available in this installation."""

    descriptors = build_default_registry().list()
    for descriptor in descriptors:
        typer.echo(f"{descriptor.test_id} [{descriptor.version}] — {descriptor.name}")
        typer.echo(f"  Category: {descriptor.category}")
        typer.echo(f"  {descriptor.description}")
    typer.echo(f"Total: {len(descriptors)} test(s)")


@app.command()
def run(
    manifest_path: Annotated[
        Path, typer.Option("--project", help="Project manifest path.")
    ] = DEFAULT_MANIFEST_PATH,
    output: Annotated[
        Path, typer.Option("--output", help="Directory for local run artifacts.")
    ] = DEFAULT_RUN_OUTPUT,
    test_id: Annotated[
        list[str] | None,
        typer.Option("--test-id", help="Test identifier; repeat to select multiple."),
    ] = None,
    seed: Annotated[
        int | None,
        typer.Option("--seed", min=0, help="Optional experiment seed recorded in provenance."),
    ] = None,
) -> None:
    """Execute selected built-in diagnostic tests and save a local report."""

    try:
        manifest = load_manifest(manifest_path)
        report = TestRunner(build_default_registry()).run(
            manifest=manifest,
            test_ids=test_id,
            random_seed=seed,
        )
        run_dir = write_report(report, output)
    except (ManifestError, TestNotFoundError, ReportError, OSError, ValueError) as exc:
        _handle_error(exc)
    typer.secho("Run completed.", fg=typer.colors.GREEN)
    typer.echo(f"Run ID: {report.run_id}")
    typer.echo(f"Results: {report.summary.total}")
    typer.echo(f"Inconclusive: {report.summary.inconclusive}")
    typer.echo(f"Report: {run_dir / 'report.html'}")
    typer.echo("Note: the built-in runtime test is diagnostic only, not a security assessment.")


@app.command()
def report(
    report_path: Annotated[Path, typer.Argument(help="Path to a VoxRigor report.json.")],
) -> None:
    """Validate and summarize an existing JSON run report."""

    try:
        loaded = load_report(report_path)
    except ReportError as exc:
        _handle_error(exc)
    typer.echo(f"Run ID: {loaded.run_id}")
    typer.echo(f"Project: {loaded.project_name}")
    typer.echo(f"Tests: {loaded.summary.total}")
    typer.echo(json.dumps(loaded.summary.model_dump(), indent=2))


@benchmark_app.command("init")
def benchmark_init(
    scores_file: Annotated[
        Path, typer.Argument(help="CSV containing trial_id,label,score columns.")
    ],
    manifest_path: Annotated[
        Path | None, typer.Option("--manifest", help="Output dataset manifest JSON path.")
    ] = None,
    task: Annotated[
        BenchmarkTask, typer.Option("--task", help="Benchmark task: asv or pad.")
    ] = BenchmarkTask.ASV,
    dataset_id: Annotated[str, typer.Option("--dataset-id")] = "local-dataset",
    dataset_name: Annotated[str, typer.Option("--dataset-name")] = "Local score dataset",
    dataset_version: Annotated[str, typer.Option("--dataset-version")] = "1.0",
    protocol_id: Annotated[str, typer.Option("--protocol-id")] = "user-defined",
    evaluation_split: Annotated[str, typer.Option("--evaluation-split")] = "all",
    score_direction: Annotated[
        ScoreDirection, typer.Option("--score-direction")
    ] = ScoreDirection.HIGHER_IS_GENUINE,
    threshold: Annotated[
        float | None,
        typer.Option("--threshold", help="Operating threshold in the original score scale."),
    ] = None,
    threshold_source: Annotated[
        ThresholdSource, typer.Option("--threshold-source")
    ] = ThresholdSource.NOT_PROVIDED,
    threshold_selection_split: Annotated[
        str | None, typer.Option("--threshold-selection-split")
    ] = None,
    source_url: Annotated[str | None, typer.Option("--source-url")] = None,
    license_name: Annotated[str, typer.Option("--license")] = "unspecified",
    citation: Annotated[str | None, typer.Option("--citation")] = None,
    access_date: Annotated[
        str | None, typer.Option("--access-date", help="Dataset access date (YYYY-MM-DD).")
    ] = None,
) -> None:
    """Create and validate a dataset manifest for a precomputed score CSV."""

    if not scores_file.is_file():
        _handle_error(ScoreFileError("Score CSV does not exist"))
    # Keep the manifest beside its score CSV by default so the relative
    # manifest path works across Windows drive letters as well as POSIX paths.
    manifest_path = manifest_path or scores_file.with_name("benchmark.json")
    if manifest_path.exists():
        _handle_error(DatasetManifestError("Refusing to overwrite an existing dataset manifest"))

    created_manifest = False
    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        relative_score_path = Path(
            os.path.relpath(scores_file.resolve(), manifest_path.parent.resolve())
        ).as_posix()
        manifest = DatasetManifest(
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            task=task,
            protocol_id=protocol_id,
            score_file=relative_score_path,
            score_file_sha256=sha256_file(scores_file.resolve()),
            evaluation_split=evaluation_split,
            score_direction=score_direction,
            operating_threshold=threshold,
            threshold_source=threshold_source,
            threshold_selection_split=threshold_selection_split,
            source_url=source_url,
            license_name=license_name,
            citation=citation,
            access_date=date.fromisoformat(access_date) if access_date else None,
        )
        content = manifest.model_dump_json(indent=2) + "\n"
        with manifest_path.open("x", encoding="utf-8", newline="\n") as handle:
            created_manifest = True
            handle.write(content)
        dataset = load_score_dataset(manifest_path)
    except (BenchmarkError, OSError, ValueError) as exc:
        if created_manifest:
            manifest_path.unlink(missing_ok=True)
        _handle_error(exc)
    typer.secho("Dataset manifest created and score CSV validated.", fg=typer.colors.GREEN)
    typer.echo(f"Manifest: {manifest_path}")
    typer.echo(f"Dataset: {manifest.dataset_name} ({manifest.dataset_id})")
    typer.echo(f"Task: {manifest.task.value.upper()}")
    typer.echo(f"Evaluation trials: {len(dataset.records)} / {dataset.input_rows}")
    typer.echo(f"Labels: {json.dumps(dataset.label_counts, sort_keys=True)}")


@benchmark_app.command("validate")
def benchmark_validate(
    manifest_path: Annotated[Path, typer.Argument(help="Dataset manifest JSON path.")],
) -> None:
    """Validate dataset metadata, score-file integrity and selected-split records."""

    try:
        dataset = load_score_dataset(manifest_path)
    except BenchmarkError as exc:
        _handle_error(exc)
    typer.secho("Dataset manifest and score file are valid.", fg=typer.colors.GREEN)
    typer.echo(f"Dataset: {dataset.manifest.dataset_name}")
    typer.echo(f"Protocol: {dataset.manifest.protocol_id}")
    typer.echo(f"Task: {dataset.manifest.task.value.upper()}")
    typer.echo(f"Split counts: {json.dumps(dataset.split_counts, sort_keys=True)}")
    typer.echo(f"Evaluation label counts: {json.dumps(dataset.label_counts, sort_keys=True)}")
    typer.echo(f"Score SHA-256: {dataset.score_file_sha256}")
    typer.echo(f"Unmapped columns: {json.dumps(dataset.unknown_columns)}")


@benchmark_app.command("run")
def benchmark_run(
    manifest_path: Annotated[Path, typer.Argument(help="Dataset manifest JSON path.")],
    output: Annotated[
        Path, typer.Option("--output", help="Directory for local benchmark runs.")
    ] = Path("runs/benchmarks"),
) -> None:
    """Evaluate a declared score-trial split and write JSON/HTML/CSV outputs."""

    try:
        run_dir = run_benchmark(manifest_path, output)
        report = load_benchmark_report(run_dir / "report.json")
    except BenchmarkError as exc:
        _handle_error(exc)
    typer.secho("Offline benchmark completed.", fg=typer.colors.GREEN)
    typer.echo(f"Run ID: {report.run_id}")
    typer.echo(f"Dataset: {report.dataset['dataset_name']}")
    typer.echo(f"Task: {report.dataset['task']}")
    typer.echo(f"Evaluated rows: {report.sample_accounting['evaluated_rows']}")
    typer.echo(f"Report: {run_dir / 'report.html'}")
    typer.echo("Note: results apply only to the supplied scores and declared protocol.")


if __name__ == "__main__":
    app()
