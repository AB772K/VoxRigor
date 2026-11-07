from __future__ import annotations

from pathlib import Path
from typing import Any

from typer.testing import CliRunner

import voxrigor.biometrics.cli as cli_module
from voxrigor.biometrics.cli import models_app


def test_score_trials_cli_reports_three_output_artifacts(
    monkeypatch: Any, tmp_path: Path
) -> None:
    source = tmp_path / "trials.json"
    source.write_text("{}", encoding="utf-8")
    output = tmp_path / "out"
    output.mkdir()
    captured: dict[str, object] = {}

    def fake_run(manifest: Path, destination: Path, **kwargs: object) -> Path:
        captured["manifest"] = manifest
        captured["destination"] = destination
        captured.update(kwargs)
        return destination

    monkeypatch.setattr(cli_module, "run_trial_inference", fake_run)
    result = CliRunner().invoke(
        models_app,
        [
            "score-trials",
            "--manifest",
            str(source),
            "--output-dir",
            str(output),
            "--device",
            "cpu",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "scores.csv" in result.output
    assert "benchmark.json" in result.output
    assert "inference-provenance.json" in result.output
    assert captured["manifest"] == source
    assert captured["destination"] == output
    assert captured["device"] == "cpu"


def test_score_trials_cli_normalizes_execution_errors(
    monkeypatch: Any, tmp_path: Path
) -> None:
    source = tmp_path / "trials.json"
    source.write_text("{}", encoding="utf-8")

    def fail(*_args: object, **_kwargs: object) -> Path:
        raise cli_module.ModelIntegrationError("deliberate test error")

    monkeypatch.setattr(cli_module, "run_trial_inference", fail)
    result = CliRunner().invoke(
        models_app,
        ["score-trials", "--manifest", str(source), "--output-dir", str(tmp_path / "out")],
    )
    assert result.exit_code == 2
    assert "deliberate test error" in result.output
