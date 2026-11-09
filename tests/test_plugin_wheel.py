from __future__ import annotations

import json
import os
import subprocess
import sys
import venv
from pathlib import Path

from voxrigor.models import ProjectManifest

REPOSITORY_ROOT = Path(__file__).parents[1]
EXAMPLE_PLUGIN_ROOT = REPOSITORY_ROOT / "examples" / "plugins" / "demo-voice"


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )


def _build_wheel(source: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(destination),
            str(source),
        ],
        cwd=REPOSITORY_ROOT,
    )
    wheels = sorted(destination.glob("*.whl"))
    assert len(wheels) == 1, f"Expected exactly one wheel in {destination}, got {wheels}"
    return wheels[0]


def _venv_executable(environment: Path, command: str) -> Path:
    if os.name == "nt":
        scripts = environment / "Scripts"
        suffix = ".exe" if command in {"python", "voxrigor"} else ""
        return scripts / f"{command}{suffix}"
    return environment / "bin" / command


def test_independent_example_plugin_wheel_installs_and_runs_in_clean_venv(
    tmp_path: Path,
) -> None:
    """Build both wheels, install them into a fresh venv, then use the real entry point."""

    core_wheel = _build_wheel(REPOSITORY_ROOT, tmp_path / "core-wheel")
    plugin_wheel = _build_wheel(EXAMPLE_PLUGIN_ROOT, tmp_path / "plugin-wheel")

    environment = tmp_path / "clean-venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = _venv_executable(environment, "python")
    cli = _venv_executable(environment, "voxrigor")

    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            str(core_wheel),
            str(plugin_wheel),
        ],
        cwd=tmp_path,
    )

    listing = _run([str(cli), "plugins", "list"], cwd=tmp_path)
    assert "demo.voice" in listing.stdout
    assert "no plugin code was imported" in listing.stdout.lower()

    config_path = tmp_path / "voxrigor.plugins.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "enabled_plugins": [{"plugin_id": "demo.voice", "granted_permissions": []}],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    validation = _run(
        [str(cli), "plugins", "validate", str(config_path)],
        cwd=tmp_path,
    )
    assert "plugin configuration is valid" in validation.stdout.lower()
    assert "no plugin code was imported" in validation.stdout.lower()

    disabled_listing = _run([str(cli), "tests"], cwd=tmp_path)
    assert "core.runtime-info" in disabled_listing.stdout
    assert "demo.voice.sdk-diagnostic" not in disabled_listing.stdout

    project_path = tmp_path / "voxrigor.json"
    project_path.write_text(
        ProjectManifest(name="Wheel-installed plugin integration").model_dump_json(indent=2),
        encoding="utf-8",
    )
    output_root = tmp_path / "runs"
    result = _run(
        [
            str(cli),
            "run",
            "--project",
            str(project_path),
            "--plugin-config",
            str(config_path),
            "--test-id",
            "demo.voice.sdk-diagnostic",
            "--output",
            str(output_root),
        ],
        cwd=tmp_path,
    )
    assert "no sandbox is provided" in result.stdout.lower()

    reports = list(output_root.rglob("report.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text(encoding="utf-8"))
    plugin_results = [
        item for item in report["results"] if item["test"]["test_id"] == "demo.voice.sdk-diagnostic"
    ]
    assert len(plugin_results) == 1
    assert plugin_results[0]["status"] == "inconclusive"
    assert plugin_results[0]["measurements"] == {
        "plugin_id": "demo.voice",
        "project_name": "Wheel-installed plugin integration",
        "sdk_contract": "0.1",
        "result": "plugin test executed",
    }
