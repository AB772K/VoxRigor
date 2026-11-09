"""CLI commands for reproducible research experiments."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from voxrigor.research.comparison import ResearchComparisonError, run_research_comparison
from voxrigor.research.experiment import ResearchExperimentError
from voxrigor.research.runner import run_research_experiment

research_app = typer.Typer(
    name="research",
    help="Cross-dataset calibration and operating-point research experiments.",
    no_args_is_help=True,
    add_completion=False,
)


@research_app.command("evaluate")
def research_evaluate(
    manifest_path: Annotated[
        Path, typer.Argument(help="Versioned research experiment JSON manifest.")
    ],
    output: Annotated[
        Path, typer.Option("--output", help="Directory for local experiment reports.")
    ] = Path("runs/research"),
) -> None:
    """Fit calibration on development data and evaluate frozen settings on held-out datasets."""

    try:
        run_dir = run_research_experiment(manifest_path, output)
    except (ResearchExperimentError, OSError, ValueError) as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    typer.secho("Research experiment completed.", fg=typer.colors.GREEN)
    typer.echo(f"Report: {run_dir / 'report.html'}")
    typer.echo(f"Machine-readable results: {run_dir / 'report.json'}")
    typer.echo("Calibration and threshold selection used only the declared calibration dataset.")


@research_app.command("compare")
def research_compare(
    manifest_path: Annotated[
        Path, typer.Argument(help="Versioned paired research-comparison JSON manifest.")
    ],
    output: Annotated[
        Path, typer.Option("--output", help="Directory for comparison reports.")
    ] = Path("runs/research-comparisons"),
) -> None:
    """Compare independently calibrated systems on identical held-out ASV trials."""

    try:
        run_dir = run_research_comparison(manifest_path, output)
    except (ResearchComparisonError, ResearchExperimentError, OSError, ValueError) as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    typer.secho("Paired research comparison completed.", fg=typer.colors.GREEN)
    typer.echo(f"Report: {run_dir / 'report.html'}")
    typer.echo(f"Machine-readable results: {run_dir / 'report.json'}")
    typer.echo("Each system used its own calibration dataset and frozen operating threshold.")
