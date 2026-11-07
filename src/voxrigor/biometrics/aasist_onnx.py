"""CPU ONNX Runtime adapter for the AASIST-L anti-spoofing baseline."""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
from typing import Any, cast

from voxrigor.biometrics.audio import load_audio_file, prepare_aasist_l_window
from voxrigor.biometrics.contracts import AudioSignal, ModelDescriptor, ModelScore
from voxrigor.biometrics.errors import InferenceError, ModelLoadError, OptionalDependencyError

AASISTL_MODEL_ID = "aasist-l-onnx"
AASISTL_REPOSITORY = "SpeechAntiSpoofingBenchmarks/AASIST-L"
AASISTL_REVISION = "2bc4bf063f34f081cafa5d51c2e72bbfa5d39715"
AASISTL_FILENAME = "aasist-l.onnx"
AASISTL_SAMPLE_RATE_HZ = 16_000
AASISTL_WINDOW_SAMPLES = 64_600


class AASISTLONNXAdapter:
    """Run AASIST-L using ONNX Runtime's CPU execution provider.

    This is the lightweight AASIST-L variant, not the full AASIST checkpoint.
    Scores are the raw bona-fide logit (output column 1).
    """

    def __init__(self, model_path: Path) -> None:
        self.model_path = Path(model_path).expanduser()
        self._session: Any | None = None
        self._input_name: str | None = None
        self._output_name: str | None = None

    @property
    def descriptor(self) -> ModelDescriptor:
        return ModelDescriptor(
            model_id=AASISTL_MODEL_ID,
            display_name="AASIST-L anti-spoofing baseline (ONNX)",
            task="presentation_attack_detection",
            backend="ONNX Runtime / CPU",
            source_repository=AASISTL_REPOSITORY,
            source_revision=AASISTL_REVISION,
            license_name="MIT",
            expected_sample_rate_hz=AASISTL_SAMPLE_RATE_HZ,
            score_type="bonafide_logit",
            limitations=(
                "This is AASIST-L, the lightweight variant, not full AASIST.",
                "The raw bona-fide logit is not a calibrated probability.",
                "The reference evaluation window is 64600 samples at 16 kHz.",
                "The upstream model card reports substantial cross-dataset degradation.",
            ),
        )

    @classmethod
    def fetch_pretrained_model(cls, cache_dir: Path | None = None) -> Path:
        """Download the pinned ONNX artifact without executing repository Python code."""

        try:
            hub_module = cast(Any, importlib.import_module("huggingface_hub"))
            hf_hub_download = hub_module.hf_hub_download
        except ImportError as exc:
            raise OptionalDependencyError(
                "Downloading AASIST-L requires huggingface-hub. "
                "Install with: pip install 'voxrigor[pad-onnx]'"
            ) from exc
        kwargs: dict[str, object] = {
            "repo_id": AASISTL_REPOSITORY,
            "filename": AASISTL_FILENAME,
            "revision": AASISTL_REVISION,
        }
        if cache_dir is not None:
            cache_dir = Path(cache_dir).expanduser()
            cache_dir.mkdir(parents=True, exist_ok=True)
            kwargs["cache_dir"] = str(cache_dir)
        try:
            path = hf_hub_download(**kwargs)
        except Exception as exc:
            raise ModelLoadError(
                "Could not download the pinned AASIST-L ONNX artifact from Hugging Face"
            ) from exc
        return Path(path)

    @staticmethod
    def sha256_model(path: Path) -> str:
        """Return the SHA-256 of the ONNX artifact actually loaded."""

        digest = hashlib.sha256()
        try:
            with Path(path).open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise ModelLoadError("Could not read the AASIST-L ONNX model file") from exc
        return digest.hexdigest()

    def load(self) -> None:
        """Load and validate a local ONNX model using only CPUExecutionProvider."""

        if self._session is not None:
            return
        if not self.model_path.is_file():
            raise ModelLoadError("AASIST-L ONNX model file does not exist")
        try:
            ort = importlib.import_module("onnxruntime")
        except ImportError as exc:
            raise OptionalDependencyError(
                "AASIST-L inference requires ONNX Runtime. "
                "Install with: pip install 'voxrigor[pad-onnx]'"
            ) from exc

        try:
            session = ort.InferenceSession(
                str(self.model_path), providers=["CPUExecutionProvider"]
            )
            inputs = session.get_inputs()
            outputs = session.get_outputs()
            if len(inputs) != 1 or not outputs:
                raise ModelLoadError("AASIST-L ONNX graph must expose one input and at least one output")
            input_meta = inputs[0]
            if input_meta.type != "tensor(float)":
                raise ModelLoadError("AASIST-L ONNX input must be float32")
            if len(input_meta.shape) != 2 or input_meta.shape[-1] != AASISTL_WINDOW_SAMPLES:
                raise ModelLoadError("AASIST-L ONNX input must have shape [batch, 64600]")
            logits_candidates = [
                item for item in outputs
                if item.type == "tensor(float)"
                and len(item.shape) == 2
                and item.shape[-1] == 2
            ]
            if len(logits_candidates) != 1:
                raise ModelLoadError(
                    "AASIST-L ONNX graph must expose exactly one float32 two-class logits output"
                )
            self._session = session
            self._input_name = input_meta.name
            self._output_name = logits_candidates[0].name
        except ModelLoadError:
            raise
        except Exception as exc:
            raise ModelLoadError("ONNX Runtime could not load or inspect the AASIST-L model") from exc

    def unload(self) -> None:
        """Release the ONNX Runtime session."""

        self._session = None
        self._input_name = None
        self._output_name = None

    def score(self, audio: AudioSignal) -> ModelScore:
        """Return the AASIST-L bona-fide logit for one local audio signal."""

        np = _numpy()
        self.load()
        if self._session is None or self._input_name is None or self._output_name is None:
            raise ModelLoadError("AASIST-L adapter did not initialize correctly")
        waveform = prepare_aasist_l_window(audio)
        try:
            outputs = self._session.run([self._output_name], {self._input_name: waveform})
        except Exception as exc:
            raise InferenceError("AASIST-L ONNX inference failed") from exc
        if len(outputs) != 1:
            raise InferenceError("AASIST-L returned an unexpected number of selected output tensors")
        logits = np.asarray(outputs[0], dtype=np.float64)
        if logits.shape != (1, 2) or not np.isfinite(logits).all():
            raise InferenceError("AASIST-L returned invalid logits; expected finite shape (1, 2)")
        return ModelScore(
            model=self.descriptor,
            score=float(logits[0, 1]),
            score_type="bonafide_logit",
            score_direction="higher_is_genuine",
            calibrated=False,
            input_sha256=(audio.source_sha256,),
            preprocessing=(
                "decoded as mono float32",
                "resampled to 16000 Hz with scipy.signal.resample_poly when required",
                "deterministic first-64600-sample window; short clips tile-repeated",
                "no waveform amplitude normalization",
            ),
            notes=(
                "Score is the raw class-1 bona-fide logit, not a probability.",
                "AASIST-L is a PAD countermeasure; it does not verify speaker identity.",
            ),
            model_artifact_sha256=(self.sha256_model(self.model_path),),
        )

    def score_file(self, audio_path: Path) -> ModelScore:
        """Decode a local audio file and run AASIST-L inference."""

        return self.score(load_audio_file(audio_path))


def _numpy() -> Any:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise OptionalDependencyError(
            "AASIST-L inference requires NumPy. Install with: pip install 'voxrigor[pad-onnx]'"
        ) from exc
    return np
