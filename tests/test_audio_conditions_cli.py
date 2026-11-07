from __future__ import annotations

from pathlib import Path
from typing import Any

from typer.testing import CliRunner

import voxrigor.biometrics.conditions_cli as cli_module
from voxrigor.biometrics.conditions import ConditionManifestError
from voxrigor.biometrics.conditions_cli import audio_app


def test_audio_conditions_cli_reports_output_paths(monkeypatch: Any, tmp_path: Path) -> None:
    manifest = tmp_path / "experiment.json"
    manifest.write_text("{}", encoding="utf-8")
    destination = tmp_path / "generated"
    captured: dict[str, object] = {}

    def fake_generate(source: Path, output: Path) -> Path:
        captured["source"] = source
        captured["output"] = output
        return output / "audio-trials.json"

    monkeypatch.setattr(cli_module, "generate_condition_dataset", fake_generate)
    result = CliRunner().invoke(
        audio_app,
        [
            "conditions",
            "generate",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(destination),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "audio-trials.json" in result.output
    assert "conditions-provenance.json" in result.output
    assert captured["source"] == manifest
    assert captured["output"] == destination


def test_audio_conditions_cli_normalizes_errors(monkeypatch: Any, tmp_path: Path) -> None:
    manifest = tmp_path / "experiment.json"
    manifest.write_text("{}", encoding="utf-8")

    def fail(*_args: object, **_kwargs: object) -> Path:
        raise ConditionManifestError("unsafe experiment")

    monkeypatch.setattr(cli_module, "generate_condition_dataset", fail)
    result = CliRunner().invoke(
        audio_app,
        [
            "conditions",
            "generate",
            "--manifest",
            str(manifest),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 2
    assert "unsafe experiment" in result.output
