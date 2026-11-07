"""Opt-in real-checkpoint smoke tests using generated non-biometric audio."""
from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from voxrigor.biometrics.aasist_onnx import AASISTLONNXAdapter
from voxrigor.biometrics.ecapa import ECAPATDNNAdapter


def make_synthetic_fixture(path: Path, sample_rate: int = 16000) -> None:
    """Generate deterministic speech-like non-human audio for runtime checks."""
    duration = 5.0
    count = int(sample_rate * duration)
    time = np.arange(count, dtype=np.float32) / sample_rate
    envelope = 0.35 + 0.25 * np.sin(2 * np.pi * 3.1 * time)
    waveform = (
        np.sin(2 * np.pi * 125 * time)
        + 0.45 * np.sin(2 * np.pi * 250 * time + 0.2)
        + 0.22 * np.sin(2 * np.pi * 375 * time + 0.7)
        + 0.10 * np.sin(2 * np.pi * 510 * time + 1.1)
    )
    noise = np.random.default_rng(1701).normal(0.0, 0.004, count).astype(np.float32)
    samples = np.asarray(envelope * waveform / 2.0 + noise, dtype=np.float32)
    if not np.isfinite(samples).all() or float(np.max(np.abs(samples))) >= 1.0:
        raise RuntimeError("Synthetic smoke fixture failed finite/amplitude checks")
    sf.write(path, samples, sample_rate, subtype="PCM_16")


def run(model: str, output: Path, cache_dir: Path) -> dict[str, object]:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="voxrigor-model-smoke-") as temporary:
        audio_path = Path(temporary) / "synthetic-smoke.wav"
        make_synthetic_fixture(audio_path)
        if model == "ecapa-tdnn":
            adapter = ECAPATDNNAdapter(cache_dir=cache_dir / "ecapa-tdnn", device="cpu")
            try:
                result = adapter.score_files(audio_path, audio_path)
                if not math.isfinite(result.score) or len(result.model_artifact_sha256) != 5:
                    raise RuntimeError("ECAPA real-checkpoint smoke assertions failed")
            finally:
                adapter.unload()
        elif model == "aasist-l-onnx":
            model_path = AASISTLONNXAdapter.fetch_pretrained_model(cache_dir / "huggingface")
            adapter = AASISTLONNXAdapter(model_path)
            try:
                result = adapter.score_file(audio_path)
                if not math.isfinite(result.score) or len(result.model_artifact_sha256) != 1:
                    raise RuntimeError("AASIST-L real-checkpoint smoke assertions failed")
            finally:
                adapter.unload()
        else:
            raise ValueError(f"Unsupported model: {model}")
    payload: dict[str, object] = {
        "model_id": result.model.model_id,
        "model_revision": result.model.source_revision,
        "score": result.score,
        "score_type": result.score_type,
        "model_artifact_sha256": list(result.model_artifact_sha256),
        "input_sha256": list(result.input_sha256),
        "status": "real_checkpoint_inference_passed",
        "limitation": "Generated non-human audio validates runtime execution only, not biometric accuracy.",
    }
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["ecapa-tdnn", "aasist-l-onnx"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache/voxrigor/models")
    args = parser.parse_args()
    print(json.dumps(run(args.model, args.output, args.cache_dir), indent=2))


if __name__ == "__main__":
    main()
