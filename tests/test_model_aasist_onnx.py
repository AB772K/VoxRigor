from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

from voxrigor.biometrics.aasist_onnx import AASISTLONNXAdapter
from voxrigor.biometrics.contracts import AudioSignal
from voxrigor.biometrics.errors import InferenceError, ModelLoadError


class FakeSession:
    def __init__(self, _path: str, providers: list[str]) -> None:
        assert providers == ["CPUExecutionProvider"]

    @staticmethod
    def get_inputs() -> list[Any]:
        return [SimpleNamespace(name="wav", type="tensor(float)", shape=["batch", 64600])]

    @staticmethod
    def get_outputs() -> list[Any]:
        return [
            SimpleNamespace(name="hidden", type="tensor(float)", shape=["batch", 128]),
            SimpleNamespace(name="logits", type="tensor(float)", shape=["batch", 2]),
        ]

    def run(self, outputs: list[str], inputs: dict[str, np.ndarray]) -> list[np.ndarray]:
        assert outputs == ["logits"]
        assert inputs["wav"].shape == (1, 64600)
        return [np.asarray([[0.1, 1.7]], dtype=np.float32)]


def _signal() -> AudioSignal:
    return AudioSignal(
        samples=np.ones(64600, dtype=np.float32),
        sample_rate_hz=16000,
        source_sha256="d" * 64,
        source_format="wav",
    )


def test_aasist_l_adapter_loads_cpu_onnx_and_returns_bonafide_logit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_path = tmp_path / "model.onnx"
    model_path.write_bytes(b"test-model-artifact")
    module = ModuleType("onnxruntime")
    module.InferenceSession = FakeSession  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "onnxruntime", module)

    adapter = AASISTLONNXAdapter(model_path)
    result = adapter.score(_signal())

    assert result.model.model_id == "aasist-l-onnx"
    assert result.model.display_name.startswith("AASIST-L")
    assert result.score == pytest.approx(1.7)
    assert result.score_type == "bonafide_logit"
    assert result.calibrated is False
    assert result.input_sha256 == ("d" * 64,)
    assert len(result.model_artifact_sha256) == 1
    assert len(result.model_artifact_sha256[0]) == 64


def test_aasist_l_rejects_missing_model(tmp_path: Path) -> None:
    adapter = AASISTLONNXAdapter(tmp_path / "missing.onnx")
    with pytest.raises(ModelLoadError, match="does not exist"):
        adapter.load()


def test_aasist_l_rejects_invalid_logits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model_path = tmp_path / "model.onnx"
    model_path.write_bytes(b"test-model-artifact")

    class BadSession(FakeSession):
        def run(self, outputs: list[str], inputs: dict[str, np.ndarray]) -> list[np.ndarray]:
            return [np.asarray([[float("nan"), 0.1]], dtype=np.float32)]

    module = ModuleType("onnxruntime")
    module.InferenceSession = BadSession  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "onnxruntime", module)

    with pytest.raises(InferenceError, match="invalid logits"):
        AASISTLONNXAdapter(model_path).score(_signal())


def test_aasist_l_fetch_uses_immutable_model_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def fake_download(**kwargs: object) -> str:
        captured.update(kwargs)
        return str(tmp_path / "aasist-l.onnx")

    module = ModuleType("huggingface_hub")
    module.hf_hub_download = fake_download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)

    result = AASISTLONNXAdapter.fetch_pretrained_model(tmp_path / "cache")
    assert result.name == "aasist-l.onnx"
    assert captured["repo_id"] == "SpeechAntiSpoofingBenchmarks/AASIST-L"
    assert captured["revision"] == "2bc4bf063f34f081cafa5d51c2e72bbfa5d39715"
    assert captured["filename"] == "aasist-l.onnx"
