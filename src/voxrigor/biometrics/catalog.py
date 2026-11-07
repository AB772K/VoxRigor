"""Static metadata for built-in, optional biometric model integrations."""

from __future__ import annotations

from pathlib import Path

from voxrigor.biometrics.aasist_onnx import AASISTLONNXAdapter
from voxrigor.biometrics.contracts import ModelDescriptor
from voxrigor.biometrics.ecapa import ECAPATDNNAdapter


def list_builtin_models() -> tuple[ModelDescriptor, ...]:
    """Describe built-in adapters without importing heavyweight ML runtimes."""

    return (
        ECAPATDNNAdapter().descriptor,
        AASISTLONNXAdapter(Path("model-not-loaded.onnx")).descriptor,
    )
