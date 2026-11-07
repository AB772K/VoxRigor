from __future__ import annotations

from pathlib import Path
from typing import Any

from typer.testing import CliRunner

import voxrigor.biometrics.cli as cli_module
from voxrigor.biometrics.cli import models_app
from voxrigor.biometrics.errors import ModelLoadError


class FakeResult:
    @staticmethod
    def to_dict() -> dict[str, object]:
        return {"model": {"model_id": "test-model"}, "score": 0.75}


class FakeECAPA:
    def __init__(self, **_kwargs: object) -> None:
        self.unloaded = False

    def score_files(self, _enrollment: Path, _probe: Path) -> FakeResult:
        return FakeResult()

    def load(self) -> None:
        return None

    def unload(self) -> None:
        self.unloaded = True


class FakeAASIST:
    fetched_path: Path | None = None
    instances: list[FakeAASIST] = []

    def __init__(self, model_path: Path) -> None:
        self.model_path = model_path
        self.unloaded = False
        self.instances.append(self)

    def score_file(self, _audio: Path) -> FakeResult:
        return FakeResult()

    def unload(self) -> None:
        self.unloaded = True

    @staticmethod
    def fetch_pretrained_model(cache_dir: Path | None = None) -> Path:
        assert cache_dir is not None
        return FakeAASIST.fetched_path or cache_dir / "model.onnx"

    @staticmethod
    def sha256_model(_path: Path) -> str:
        return "a" * 64


def test_models_list_is_available_without_loading_ml_runtimes() -> None:
    result = CliRunner().invoke(models_app, ["list"])
    assert result.exit_code == 0
    assert "ecapa-tdnn" in result.output
    assert "aasist-l-onnx" in result.output
    assert "not universal authentication decisions" in result.output


def test_score_ecapa_cli_returns_json_and_unloads(monkeypatch: Any, tmp_path: Path) -> None:
    enrollment = tmp_path / "enrollment.wav"
    probe = tmp_path / "probe.wav"
    enrollment.touch()
    probe.touch()
    instances: list[FakeECAPA] = []

    def factory(**kwargs: object) -> FakeECAPA:
        instance = FakeECAPA(**kwargs)
        instances.append(instance)
        return instance

    monkeypatch.setattr(cli_module, "ECAPATDNNAdapter", factory)
    result = CliRunner().invoke(
        models_app,
        [
            "score-ecapa",
            "--enrollment",
            str(enrollment),
            "--probe",
            str(probe),
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"score": 0.75' in result.output
    assert instances[0].unloaded


def test_score_ecapa_cli_normalizes_adapter_failure(monkeypatch: Any, tmp_path: Path) -> None:
    enrollment = tmp_path / "enrollment.wav"
    probe = tmp_path / "probe.wav"
    enrollment.touch()
    probe.touch()

    class FailedECAPA(FakeECAPA):
        def score_files(self, _enrollment: Path, _probe: Path) -> FakeResult:
            raise ModelLoadError("checkpoint unavailable")

    monkeypatch.setattr(cli_module, "ECAPATDNNAdapter", FailedECAPA)
    result = CliRunner().invoke(
        models_app,
        [
            "score-ecapa",
            "--enrollment",
            str(enrollment),
            "--probe",
            str(probe),
        ],
    )
    assert result.exit_code == 2
    assert "checkpoint unavailable" in result.output


def test_score_aasist_cli_accepts_existing_local_model(monkeypatch: Any, tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    model = tmp_path / "model.onnx"
    audio.touch()
    model.touch()
    instances: list[FakeAASIST] = []

    def factory(path: Path) -> FakeAASIST:
        instance = FakeAASIST(path)
        instances.append(instance)
        return instance

    monkeypatch.setattr(cli_module, "AASISTLONNXAdapter", factory)
    result = CliRunner().invoke(
        models_app,
        ["score-aasist-l", "--audio", str(audio), "--model-path", str(model)],
    )
    assert result.exit_code == 0, result.output
    assert '"score": 0.75' in result.output
    assert instances[0].model_path == model
    assert instances[0].unloaded


def test_score_aasist_cli_fetches_model_when_path_omitted(monkeypatch: Any, tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    audio.touch()
    model = tmp_path / "downloaded.onnx"
    model.touch()
    FakeAASIST.fetched_path = model
    FakeAASIST.instances = []
    monkeypatch.setattr(cli_module, "AASISTLONNXAdapter", FakeAASIST)
    result = CliRunner().invoke(
        models_app, ["score-aasist-l", "--audio", str(audio), "--cache-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert FakeAASIST.instances[0].model_path == model
    assert FakeAASIST.instances[0].unloaded
    FakeAASIST.fetched_path = None


def test_score_aasist_cli_normalizes_model_failure(monkeypatch: Any, tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    model = tmp_path / "model.onnx"
    audio.touch()
    model.touch()

    class FailedAASIST(FakeAASIST):
        def score_file(self, _audio: Path) -> FakeResult:
            raise ModelLoadError("ONNX model failed")

    monkeypatch.setattr(cli_module, "AASISTLONNXAdapter", FailedAASIST)
    result = CliRunner().invoke(
        models_app,
        ["score-aasist-l", "--audio", str(audio), "--model-path", str(model)],
    )
    assert result.exit_code == 2
    assert "ONNX model failed" in result.output


def test_fetch_ecapa_cli_normalizes_load_failure(monkeypatch: Any, tmp_path: Path) -> None:
    class FailedECAPA(FakeECAPA):
        def load(self) -> None:
            raise ModelLoadError("model file missing")

    monkeypatch.setattr(cli_module, "ECAPATDNNAdapter", FailedECAPA)
    result = CliRunner().invoke(models_app, ["fetch", "ecapa-tdnn", "--cache-dir", str(tmp_path)])
    assert result.exit_code == 2
    assert "model file missing" in result.output


def test_default_model_cache_uses_xdg_on_posix(monkeypatch: Any) -> None:
    monkeypatch.setattr(cli_module.os, "name", "posix")
    monkeypatch.setenv("XDG_CACHE_HOME", "/tmp/voxrigor-cache")
    assert cli_module.default_model_cache() == Path("/tmp/voxrigor-cache/voxrigor/models")
