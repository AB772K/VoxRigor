from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

from voxrigor.biometrics.contracts import AudioSignal
from voxrigor.biometrics.ecapa import ECAPATDNNAdapter
from voxrigor.biometrics.errors import InferenceError


class FakeTensor:
    def __init__(self, values: Any) -> None:
        self.values = np.asarray(values, dtype=np.float32)

    def unsqueeze(self, axis: int) -> FakeTensor:
        return FakeTensor(np.expand_dims(self.values, axis))

    def to(self, _device: str) -> FakeTensor:
        return self

    def detach(self) -> FakeTensor:
        return self

    def cpu(self) -> FakeTensor:
        return self

    def numpy(self) -> np.ndarray:
        return self.values


class FakeEncoder:
    def encode_batch(self, waveform: FakeTensor) -> FakeTensor:
        mean = float(np.mean(waveform.values))
        return FakeTensor([[mean + 1.0, 1.0]])


class FakeTorch:
    @staticmethod
    def from_numpy(values: np.ndarray) -> FakeTensor:
        return FakeTensor(values)

    @staticmethod
    @contextmanager
    def inference_mode():
        yield


def _audio(values: list[float], digest: str) -> AudioSignal:
    return AudioSignal(
        samples=np.asarray(values, dtype=np.float32),
        sample_rate_hz=16000,
        source_sha256=digest * 64,
        source_format="wav",
    )


def test_ecapa_adapter_returns_raw_cosine_score_and_provenance() -> None:
    adapter = ECAPATDNNAdapter(encoder=FakeEncoder(), torch_module=FakeTorch())
    result = adapter.score(_audio([0.0, 0.0], "a"), _audio([1.0, 1.0], "b"))

    assert result.model.model_id == "ecapa-tdnn"
    assert result.score_type == "cosine_similarity"
    assert result.score_direction == "higher_is_genuine"
    assert result.calibrated is False
    assert result.input_sha256 == ("a" * 64, "b" * 64)
    assert -1.0 <= result.score <= 1.0
    assert "not a probability" in result.notes[0]


def test_cosine_similarity_rejects_mismatched_dimensions() -> None:
    with pytest.raises(InferenceError, match="equal dimensions"):
        ECAPATDNNAdapter.cosine_similarity([1.0, 0.0], [1.0])


def test_cosine_similarity_rejects_zero_vectors() -> None:
    with pytest.raises(InferenceError, match="zero-norm"):
        ECAPATDNNAdapter.cosine_similarity([0.0, 0.0], [1.0, 0.0])


def test_ecapa_model_descriptor_uses_pinned_revision() -> None:
    descriptor = ECAPATDNNAdapter().descriptor
    assert descriptor.source_revision == "0f99f2d0ebe89ac095bcc5903c4dd8f72b367286"
    assert descriptor.license_name == "Apache-2.0"
    assert descriptor.expected_sample_rate_hz == 16000


def test_ecapa_load_pins_snapshot_and_overrides_pretrained_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    for name in (
        "hyperparams.yaml",
        "embedding_model.ckpt",
        "mean_var_norm_emb.ckpt",
        "classifier.ckpt",
        "label_encoder.txt",
    ):
        (snapshot / name).write_bytes(name.encode("utf-8"))

    captured: dict[str, Any] = {}

    def fake_snapshot_download(**kwargs: Any) -> str:
        captured["snapshot"] = kwargs
        return str(snapshot)

    class FakeEncoderClass:
        @staticmethod
        def from_hparams(**kwargs: Any) -> FakeEncoder:
            captured["hparams"] = kwargs
            return FakeEncoder()

    fake_torch = ModuleType("torch")
    fake_torch.cuda = SimpleNamespace(is_available=lambda: False)  # type: ignore[attr-defined]
    fake_classifiers = ModuleType("speechbrain.inference.classifiers")
    fake_classifiers.EncoderClassifier = FakeEncoderClass  # type: ignore[attr-defined]
    fake_hub = ModuleType("huggingface_hub")
    fake_hub.snapshot_download = fake_snapshot_download  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "speechbrain.inference.classifiers", fake_classifiers)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)

    adapter = ECAPATDNNAdapter(cache_dir=tmp_path / "cache")
    adapter.load()

    snapshot_args = captured["snapshot"]
    assert snapshot_args["repo_id"] == "speechbrain/spkrec-ecapa-voxceleb"
    assert snapshot_args["revision"] == adapter.revision
    hparams_args = captured["hparams"]
    assert hparams_args["source"] == str(snapshot)
    assert hparams_args["overrides"] == {"pretrained_path": str(snapshot)}
    assert len(adapter._artifact_hashes) == 5

    adapter.unload()
    assert adapter._artifact_hashes == ()
