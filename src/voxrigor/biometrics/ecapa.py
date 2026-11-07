"""SpeechBrain ECAPA-TDNN speaker-embedding adapter."""

from __future__ import annotations

import hashlib
import importlib
import math
from pathlib import Path
from typing import Any, cast

from voxrigor.biometrics.audio import load_audio_file, resample_audio
from voxrigor.biometrics.contracts import AudioSignal, ModelDescriptor, ModelScore
from voxrigor.biometrics.errors import InferenceError, ModelLoadError, OptionalDependencyError

ECAPA_MODEL_ID = "ecapa-tdnn"
ECAPA_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
ECAPA_REVISION = "0f99f2d0ebe89ac095bcc5903c4dd8f72b367286"
ECAPA_SAMPLE_RATE_HZ = 16_000


class ECAPATDNNAdapter:
    """Extract ECAPA-TDNN embeddings and compare utterances using cosine similarity.

    The returned cosine similarity is a raw comparison score, not a calibrated
    probability or a universal accept/reject threshold.
    """

    def __init__(
        self,
        *,
        device: str = "cpu",
        cache_dir: Path | None = None,
        revision: str = ECAPA_REVISION,
        encoder: Any | None = None,
        torch_module: Any | None = None,
    ) -> None:
        if device != "cpu" and not device.startswith("cuda"):
            raise ValueError("device must be 'cpu' or a CUDA device such as 'cuda:0'")
        if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
            raise ValueError("model revision must be a full immutable 40-character lowercase commit SHA")
        self.device = device
        self.cache_dir = Path(cache_dir).expanduser() if cache_dir is not None else None
        self.revision = revision
        self._encoder = encoder
        self._torch = torch_module
        self._artifact_hashes: tuple[str, ...] = ()

    @property
    def descriptor(self) -> ModelDescriptor:
        return ModelDescriptor(
            model_id=ECAPA_MODEL_ID,
            display_name="ECAPA-TDNN (VoxCeleb)",
            task="speaker_verification",
            backend="SpeechBrain / PyTorch",
            source_repository=ECAPA_SOURCE,
            source_revision=self.revision,
            license_name="Apache-2.0",
            expected_sample_rate_hz=ECAPA_SAMPLE_RATE_HZ,
            score_type="cosine_similarity",
            limitations=(
                "Raw cosine similarity is not a calibrated probability.",
                "No universal decision threshold is supplied by this adapter.",
                "The upstream model card makes no performance warranty on other datasets.",
                "The default model revision is pinned to a Hugging Face commit.",
            ),
        )

    def load(self) -> None:
        """Load a pinned local snapshot; ML dependencies are imported lazily."""

        if self._encoder is not None:
            return
        try:
            torch = importlib.import_module("torch")
            classifiers_module = cast(
                Any, importlib.import_module("speechbrain.inference.classifiers")
            )
            hub_module = cast(Any, importlib.import_module("huggingface_hub"))
            encoder_classifier = classifiers_module.EncoderClassifier
            snapshot_download = hub_module.snapshot_download
        except ImportError as exc:
            raise OptionalDependencyError(
                "ECAPA inference requires the speaker extra. Install with: "
                "pip install 'voxrigor[speaker]'"
            ) from exc

        if self.device.startswith("cuda") and not torch.cuda.is_available():
            raise ModelLoadError("CUDA was requested but is not available in this PyTorch install")
        cache_root = self.cache_dir
        if cache_root is not None:
            cache_root.mkdir(parents=True, exist_ok=True)
        try:
            snapshot_path = Path(
                snapshot_download(
                    repo_id=ECAPA_SOURCE,
                    revision=self.revision,
                    cache_dir=str(cache_root) if cache_root is not None else None,
                    allow_patterns=[
                        "hyperparams.yaml",
                        "embedding_model.ckpt",
                        "mean_var_norm_emb.ckpt",
                        "classifier.ckpt",
                        "label_encoder.txt",
                        "config.json",
                    ],
                )
            )
            required_files = (
                "hyperparams.yaml",
                "embedding_model.ckpt",
                "mean_var_norm_emb.ckpt",
                "classifier.ckpt",
                "label_encoder.txt",
            )
            missing = [name for name in required_files if not (snapshot_path / name).is_file()]
            if missing:
                raise ModelLoadError(
                    "Pinned ECAPA model snapshot is missing required files: " + ", ".join(missing)
                )
            self._artifact_hashes = tuple(
                _sha256_file(snapshot_path / name) for name in required_files
            )
            runtime_cache = cache_root / "speechbrain-runtime" if cache_root else None
            self._encoder = encoder_classifier.from_hparams(
                source=str(snapshot_path),
                savedir=str(runtime_cache) if runtime_cache is not None else None,
                overrides={"pretrained_path": str(snapshot_path)},
                run_opts={"device": self.device},
            )
            self._torch = torch
        except ModelLoadError:
            self._encoder = None
            self._torch = None
            self._artifact_hashes = ()
            raise
        except Exception as exc:
            self._encoder = None
            self._torch = None
            self._artifact_hashes = ()
            raise ModelLoadError(
                "SpeechBrain could not load the pinned ECAPA-TDNN model. "
                "Check model access, cache permissions and dependency compatibility."
            ) from exc

    def unload(self) -> None:
        """Release the adapter's model references."""

        self._encoder = None
        self._torch = None
        self._artifact_hashes = ()

    def _embed(self, signal: AudioSignal) -> Any:
        if self._encoder is None or self._torch is None:
            raise ModelLoadError("ECAPA adapter is not loaded; call load() first")
        np = _numpy()
        normalized = resample_audio(signal, ECAPA_SAMPLE_RATE_HZ)
        waveform = self._torch.from_numpy(
            np.asarray(normalized.samples, dtype=np.float32)
        ).unsqueeze(0).to(self.device)
        try:
            with self._torch.inference_mode():
                embedding = self._encoder.encode_batch(waveform)
            vector = np.asarray(embedding.detach().cpu().numpy(), dtype=np.float64).reshape(-1)
        except Exception as exc:
            raise InferenceError("ECAPA-TDNN embedding extraction failed") from exc
        if vector.size == 0 or not np.isfinite(vector).all():
            raise InferenceError("ECAPA-TDNN returned an empty or non-finite embedding")
        norm = float(np.linalg.norm(vector))
        if not math.isfinite(norm) or norm == 0.0:
            raise InferenceError("ECAPA-TDNN returned a zero-norm embedding")
        return vector / norm

    @staticmethod
    def cosine_similarity(reference_embedding: Any, probe_embedding: Any) -> float:
        """Calculate cosine similarity with dimension and finite-value checks."""

        np = _numpy()
        reference = np.asarray(reference_embedding, dtype=np.float64).reshape(-1)
        probe = np.asarray(probe_embedding, dtype=np.float64).reshape(-1)
        if reference.size == 0 or reference.shape != probe.shape:
            raise InferenceError("Speaker embeddings must be non-empty and have equal dimensions")
        if not np.isfinite(reference).all() or not np.isfinite(probe).all():
            raise InferenceError("Speaker embeddings contain non-finite values")
        reference_norm = float(np.linalg.norm(reference))
        probe_norm = float(np.linalg.norm(probe))
        if reference_norm == 0.0 or probe_norm == 0.0:
            raise InferenceError("Cosine similarity is undefined for a zero-norm embedding")
        score = float(np.dot(reference, probe) / (reference_norm * probe_norm))
        return max(-1.0, min(1.0, score))

    def score(self, enrollment: AudioSignal, probe: AudioSignal) -> ModelScore:
        """Compare enrollment and probe audio and return a raw similarity score."""

        self.load()
        reference_embedding = self._embed(enrollment)
        probe_embedding = self._embed(probe)
        score = self.cosine_similarity(reference_embedding, probe_embedding)
        return ModelScore(
            model=self.descriptor,
            score=score,
            score_type="cosine_similarity",
            score_direction="higher_is_genuine",
            calibrated=False,
            input_sha256=(enrollment.source_sha256, probe.source_sha256),
            preprocessing=(
                "decoded as mono float32",
                "resampled to 16000 Hz with scipy.signal.resample_poly when required",
                "SpeechBrain ECAPA encode_batch preprocessing",
                "L2-normalized embeddings compared using cosine similarity",
            ),
            notes=(
                "This is a raw similarity score, not a probability or authentication decision.",
                "Calibrate thresholds only on a separate development set under a declared protocol.",
            ),
            model_artifact_sha256=self._artifact_hashes,
        )

    def score_files(self, enrollment_path: Path, probe_path: Path) -> ModelScore:
        """Decode two local audio files and compare their speaker embeddings."""

        enrollment = load_audio_file(enrollment_path)
        probe = load_audio_file(probe_path)
        return self.score(enrollment, probe)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _numpy() -> Any:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise OptionalDependencyError(
            "ECAPA inference requires NumPy. Install with: pip install 'voxrigor[speaker]'"
        ) from exc
    return np
