"""CLI commands for discovering, fetching and exercising model adapters."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from voxrigor.biometrics.aasist_onnx import AASISTLONNXAdapter, AASISTL_REVISION
from voxrigor.biometrics.catalog import list_builtin_models
from voxrigor.biometrics.ecapa import ECAPATDNNAdapter
from voxrigor.biometrics.errors import ModelIntegrationError

models_app = typer.Typer(
    name="models",
    help="Discover and run optional biometric model adapters.",
    no_args_is_help=True,
    add_completion=False,
)


def default_model_cache() -> Path:
    """Return an OS-appropriate local model cache directory."""

    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return base / "voxrigor" / "models"


def _handle_model_error(error: Exception) -> NoReturn:
    typer.secho(f"Error: {error}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=2) from error


@models_app.command("list")
def models_list() -> None:
    """List built-in model adapters without importing ML runtimes."""

    for descriptor in list_builtin_models():
        typer.echo(f"{descriptor.model_id} — {descriptor.display_name}")
        typer.echo(f"  Task: {descriptor.task}")
        typer.echo(f"  Backend: {descriptor.backend}")
        typer.echo(f"  Source: {descriptor.source_repository}@{descriptor.source_revision}")
        typer.echo(f"  License: {descriptor.license_name}")
    typer.echo("Note: adapters provide raw scores, not universal authentication decisions.")


@models_app.command("fetch")
def models_fetch(
    model_id: Annotated[
        str, typer.Argument(help="Built-in model ID: ecapa-tdnn or aasist-l-onnx.")
    ],
    cache_dir: Annotated[
        Path, typer.Option("--cache-dir", help="Local model cache directory.")
    ] = default_model_cache(),
) -> None:
    """Download a pinned model artifact or populate the SpeechBrain model cache."""

    try:
        if model_id == "ecapa-tdnn":
            adapter = ECAPATDNNAdapter(cache_dir=cache_dir / "ecapa-tdnn")
            adapter.load()
            adapter.unload()
            typer.echo(f"ECAPA-TDNN cached under: {cache_dir / 'ecapa-tdnn'}")
            typer.echo(f"Revision: {adapter.revision}")
        elif model_id == "aasist-l-onnx":
            model_path = AASISTLONNXAdapter.fetch_pretrained_model(cache_dir / "huggingface")
            typer.echo(f"AASIST-L ONNX: {model_path}")
            typer.echo(f"SHA-256: {AASISTLONNXAdapter.sha256_model(model_path)}")
            typer.echo(f"Revision: {AASISTL_REVISION}")
        else:
            _handle_model_error(ValueError(f"Unsupported model ID: {model_id}"))
    except (ModelIntegrationError, OSError) as exc:
        _handle_model_error(exc)


@models_app.command("score-ecapa")
def models_score_ecapa(
    enrollment: Annotated[Path, typer.Option("--enrollment", exists=True, dir_okay=False)],
    probe: Annotated[Path, typer.Option("--probe", exists=True, dir_okay=False)],
    cache_dir: Annotated[
        Path, typer.Option("--cache-dir", help="Local SpeechBrain model cache directory.")
    ] = default_model_cache() / "ecapa-tdnn",
    device: Annotated[str, typer.Option("--device", help="cpu or cuda[:index].")] = "cpu",
) -> None:
    """Compute an uncalibrated ECAPA-TDNN cosine similarity for two local files."""

    try:
        adapter = ECAPATDNNAdapter(cache_dir=cache_dir, device=device)
        result = adapter.score_files(enrollment, probe)
        typer.echo(json.dumps(result.to_dict(), indent=2))
        adapter.unload()
    except (ModelIntegrationError, OSError, ValueError) as exc:
        _handle_model_error(exc)


@models_app.command("score-aasist-l")
def models_score_aasist_l(
    audio: Annotated[Path, typer.Option("--audio", exists=True, dir_okay=False)],
    model_path: Annotated[
        Path | None,
        typer.Option("--model-path", help="Existing local AASIST-L ONNX file; omit to fetch it."),
    ] = None,
    cache_dir: Annotated[
        Path, typer.Option("--cache-dir", help="Local Hugging Face model cache directory.")
    ] = default_model_cache() / "huggingface",
) -> None:
    """Compute an uncalibrated AASIST-L bona-fide logit for one local file."""

    try:
        selected_path = model_path or AASISTLONNXAdapter.fetch_pretrained_model(cache_dir)
        adapter = AASISTLONNXAdapter(selected_path)
        result = adapter.score_file(audio)
        typer.echo(json.dumps(result.to_dict(), indent=2))
        adapter.unload()
    except (ModelIntegrationError, OSError, ValueError) as exc:
        _handle_model_error(exc)
