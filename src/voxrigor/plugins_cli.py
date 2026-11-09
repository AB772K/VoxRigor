"""CLI commands for explicit third-party plugin discovery and configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from voxrigor.plugins import (
    PLUGIN_ENTRY_POINT_GROUP,
    PluginLoadError,
    discover_installed_plugins,
    validate_plugin_config,
)

plugins_app = typer.Typer(
    name="plugins",
    help="Discover installed plugins and validate the explicit plugin allow-list.",
    no_args_is_help=True,
    add_completion=False,
)


@plugins_app.command("list")
def list_plugins() -> None:
    """List installed plugin entry-point metadata without importing plugin code."""

    try:
        installed = discover_installed_plugins()
    except PluginLoadError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    if not installed:
        typer.echo(f"No installed plugins found in entry-point group {PLUGIN_ENTRY_POINT_GROUP!r}.")
        return

    for plugin in installed:
        typer.echo(f"{plugin.plugin_id}")
        typer.echo(f"  Entry point: {plugin.entry_point}")
        typer.echo(f"  Distribution: {plugin.distribution}")
    typer.echo(f"Total: {len(installed)} installed plugin entry point(s)")
    typer.echo("Discovery reads package metadata only; no plugin code was imported.")


@plugins_app.command("validate")
def validate_plugins(
    config_path: Annotated[
        Path, typer.Argument(help="Explicit plugin allow-list JSON file.")
    ],
) -> None:
    """Validate enabled plugin IDs and grants without importing plugin code."""

    try:
        config = validate_plugin_config(config_path)
    except PluginLoadError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    typer.secho("Plugin configuration is valid.", fg=typer.colors.GREEN)
    if not config.enabled_plugins:
        typer.echo("No plugins are enabled.")
    for plugin in config.enabled_plugins:
        grants = ", ".join(item.value for item in plugin.granted_permissions) or "none"
        typer.echo(f"{plugin.plugin_id}: granted permissions = {grants}")
    typer.echo("Validation reads package metadata only; no plugin code was imported.")
