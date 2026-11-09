from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

import voxrigor.protocol.cli as cli_module
from voxrigor.protocol.cli import protocol_app
from voxrigor.protocol.runner import ProtocolReport
from voxrigor.protocol.scope import ProtocolScope


def test_init_scope_requires_explicit_authorization(tmp_path: Path) -> None:
    destination = tmp_path / "scope.json"
    result = CliRunner().invoke(
        protocol_app,
        [
            "init-scope",
            "--target-url",
            "http://127.0.0.1:8765",
            "--output",
            str(destination),
        ],
    )
    assert result.exit_code == 2
    assert "acknowledgement" in result.output
    assert not destination.exists()


def test_init_scope_creates_acknowledged_loopback_scope(tmp_path: Path) -> None:
    destination = tmp_path / "scope.json"
    result = CliRunner().invoke(
        protocol_app,
        [
            "init-scope",
            "--target-url",
            "http://127.0.0.1:8765",
            "--i-authorize-local-target",
            "--output",
            str(destination),
        ],
    )
    assert result.exit_code == 0, result.output
    assert destination.is_file()
    assert "Local scope created" in result.output


def test_protocol_run_loads_scope_and_writes_redacted_report(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    scope = ProtocolScope(target_url="http://127.0.0.1:8765", authorized=True)
    report = ProtocolReport(
        run_id="cli-test",
        generated_at=datetime.now(UTC),
        framework_version="test",
        target_label="local fixture",
        target_url=scope.target_url,
        request_count=3,
        findings=[],
    )
    captured: dict[str, object] = {}
    scope_path = tmp_path / "scope.json"
    scope_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(cli_module, "load_scope_manifest", lambda _path: scope)
    monkeypatch.setattr(
        cli_module,
        "run_protocol_assessment",
        lambda selected_scope, *, framework_version: (
            captured.update({"scope": selected_scope, "version": framework_version}) or report
        ),
    )

    result = CliRunner().invoke(
        protocol_app,
        [
            "run",
            "--scope",
            str(tmp_path / "scope.json"),
            "--output",
            str(tmp_path / "report"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "report" / "report.json").is_file()
    assert "HTTP requests: 3" in result.output
    assert captured["scope"] is scope
    assert captured["version"] == cli_module.__version__


def test_protocol_serve_stops_and_closes_server_on_keyboard_interrupt(
    monkeypatch: Any,
) -> None:
    state = {"closed": False, "served": False}

    class FakeServer:
        server_address = ("127.0.0.1", 8765)

        def serve_forever(self, *, poll_interval: float) -> None:
            state["served"] = poll_interval == 0.2
            raise KeyboardInterrupt

        def server_close(self) -> None:
            state["closed"] = True

    monkeypatch.setattr(cli_module, "create_reference_server", lambda **_kwargs: FakeServer())
    result = CliRunner().invoke(
        protocol_app,
        ["serve", "--fixture-profile", "fixed", "--port", "8765"],
    )
    assert result.exit_code == 0, result.output
    assert state == {"closed": True, "served": True}
    assert "Stopping local reference service" in result.output


def test_protocol_demo_runs_and_writes_local_report(tmp_path: Path) -> None:
    destination = tmp_path / "demo"
    result = CliRunner().invoke(
        protocol_app,
        [
            "demo",
            "--fixture-profile",
            "fixed",
            "--output",
            str(destination),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (destination / "report.json").is_file()
    assert (destination / "report.md").is_file()
    assert "Fixture profile: fixed" in result.output
