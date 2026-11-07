"""Command-line interface for the VoxRigor Phase 1 core."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from pydantic import ValidationError

from voxrigor import __version__
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


if __name__ == "__main__":
    app()
