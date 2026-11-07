"""CLI for generating reproducible audio-condition datasets."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer

from voxrigor.biometrics.conditions import ConditionManifestError, generate_condition_dataset
from voxrigor.biometrics.errors import ModelIntegrationError

audio_app = typer.Typer(
    name="audio",
    help="Generate and inspect local audio-condition datasets.",
    no_args_is_help=True,
    add_completion=False,
)
conditions_app = typer.Typer(
    name="conditions",
    help="Create controlled, reproducible audio conditions.",
    no_args_is_help=True,
    add_completion=False,
)
audio_app.add_typer(conditions_app, name="conditions")


def _handle_condition_error(error: Exception) -> NoReturn:
    typer.secho(f"Error: {error}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=2) from error


@conditions_app.command("generate")
def conditions_generate(
    manifest_path: Annotated[
        Path,
        typer.Option("--manifest", exists=True, dir_okay=False, help="Condition experiment JSON."),
    ],
    output_dir: Annotated[
        Path, typer.Option("--output-dir", help="New output directory for generated audio.")
    ],
) -> None:
    """Generate a clean baseline and transformed local audio-trial dataset."""

    try:
        generated_manifest = generate_condition_dataset(manifest_path, output_dir)
    except (ModelIntegrationError, OSError, ValueError) as exc:
        _handle_condition_error(exc)
    typer.secho("Audio-condition dataset generated.", fg=typer.colors.GREEN)
    typer.echo(f"Audio-trial manifest: {generated_manifest}")
    typer.echo(f"Condition provenance: {generated_manifest.parent / 'conditions-provenance.json'}")
    typer.echo("Audio remains local; FLOAT WAV export does not silently clip or normalize samples.")
