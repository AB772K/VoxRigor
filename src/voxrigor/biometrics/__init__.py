"""Optional biometric model adapters for VoxRigor."""

from voxrigor.biometrics.aasist_onnx import AASISTLONNXAdapter
from voxrigor.biometrics.contracts import AudioSignal, ModelDescriptor, ModelScore
from voxrigor.biometrics.ecapa import ECAPATDNNAdapter

__all__ = [
    "AASISTLONNXAdapter",
    "AudioSignal",
    "ECAPATDNNAdapter",
    "ModelDescriptor",
    "ModelScore",
]
