"""CLI commands for the local-only protocol and API security engine."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from voxrigor import __version__
from voxrigor.protocol.errors import ProtocolError, ScopeManifestError
from voxrigor.protocol.reference import FixtureProfile, create_reference_server
from voxrigor.protocol.runner import CheckStatus, run_protocol_assessment, write_protocol_report
from voxrigor.protocol.scope import load_scope_manifest, write_scope_example

protocol_app = typer.Typer(
    name="protocol",
    help="Local-only protocol and API security testing for voice-authentication workflows.",
    no_args_is_help=True,
    add_completion=False,
)


def _handle_error(error: Exception) -> NoReturn:
    typer.secho(f"Error: {error}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=2) from error


@protocol_app.command("init-scope")
def protocol_init_scope(
    target_url: Annotated[
        str, typer.Option("--target-url", help="Explicit loopback IP and port, e.g. http://127.0.0.1:8765.")
    ],
    output: Annotated[
        Path, typer.Option("--output", help="New scope JSON file; existing files are not overwritten.")
    ] = Path("protocol-scope.json"),
) -> None:
    """Create an explicit local-only protocol scope manifest."""

    try:
        created = write_scope_example(output, target_url)
    except (ProtocolError, OSError, ValueError) as exc:
        _handle_error(exc)
    typer.secho(f"Local scope created: {created}", fg=typer.colors.GREEN)
    typer.echo("Authorization acknowledgement is explicit; only loopback IP targets are accepted.")


@protocol_app.command("serve")
def protocol_serve(
    port: Annotated[int, typer.Option("--port", min=0, max=65535)] = 8765,
    profile: Annotated[
        FixtureProfile, typer.Option("--fixture-profile", help="fixed or intentionally vulnerable local fixture.")
    ] = "fixed",
    challenge_ttl_seconds: Annotated[
        float, typer.Option("--challenge-ttl-seconds", min=0.1, max=120.0)
    ] = 3.0,
) -> None:
    """Start the in-memory reference application on 127.0.0.1 only."""

    try:
        server = create_reference_server(
            profile=profile,
            port=port,
            challenge_ttl_seconds=challenge_ttl_seconds,
        )
    except ValueError as exc:
        _handle_error(exc)
    selected_port = int(server.server_address[1])
    typer.echo(f"VoxRigor reference service ({profile}) listening on http://127.0.0.1:{selected_port}")
    typer.echo("The fixture uses a synthetic assertion. It is not a biometric verifier.")
    typer.echo("Press Ctrl+C to stop. In-memory accounts and sessions are discarded on exit.")
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        typer.echo("\nStopping local reference service.")
    finally:
        server.server_close()


@protocol_app.command("run")
def protocol_run(
    scope_path: Annotated[
        Path, typer.Option("--scope", exists=True, dir_okay=False, help="Explicit local scope JSON.")
    ],
    output_dir: Annotated[
        Path, typer.Option("--output", help="New directory for the redacted report.")
    ] = Path("runs/protocol"),
) -> None:
    """Run bounded protocol checks against an explicitly authorized loopback target."""

    try:
        scope = load_scope_manifest(scope_path)
        report = run_protocol_assessment(scope, framework_version=__version__)
        destination = write_protocol_report(report, output_dir)
    except (ProtocolError, ScopeManifestError, OSError, ValueError) as exc:
        _handle_error(exc)
    typer.secho("Local protocol assessment completed.", fg=typer.colors.GREEN)
    typer.echo(f"Checks recorded: {len(report.findings)}")
    typer.echo(f"HTTP requests: {report.request_count}")
    typer.echo(f"Vulnerable checks: {sum(item.status is CheckStatus.VULNERABLE for item in report.findings)}")
    typer.echo(f"JSON report: {destination / 'report.json'}")
    typer.echo(f"Markdown report: {destination / 'report.md'}")
    typer.echo("no_issue_observed is not a security guarantee.")


@protocol_app.command("demo")
def protocol_demo(
    profile: Annotated[
        FixtureProfile, typer.Option("--fixture-profile", help="fixed or vulnerable.")
    ] = "fixed",
    output_dir: Annotated[
        Path | None, typer.Option("--output", help="New output directory for the demo report.")
    ] = None,
) -> None:
    """Start an ephemeral loopback fixture, run checks, and stop the fixture."""

    try:
        server = create_reference_server(profile=profile, port=0, challenge_ttl_seconds=0.2)
    except ValueError as exc:
        _handle_error(exc)
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        daemon=True,
    )
    thread.start()
    selected_port = int(server.server_address[1])
    destination = output_dir or Path("runs") / f"protocol-demo-{profile}"
    try:
        from voxrigor.protocol.scope import ProtocolScope

        scope = ProtocolScope(
            target_url=f"http://127.0.0.1:{selected_port}",
            target_label=f"VoxRigor {profile} reference fixture",
            authorized=True,
            request_budget=32,
            timeout_seconds=2.0,
            max_test_wait_seconds=1.0,
        )
        report = run_protocol_assessment(scope, framework_version=__version__)
        saved = write_protocol_report(report, destination)
    except (ProtocolError, OSError, ValueError) as exc:
        _handle_error(exc)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
    typer.echo(f"Fixture profile: {profile}")
    typer.echo(f"Findings: {len(report.findings)}")
    typer.echo(f"Vulnerable checks: {sum(item.status is CheckStatus.VULNERABLE for item in report.findings)}")
    typer.echo(f"Report: {saved / 'report.md'}")
