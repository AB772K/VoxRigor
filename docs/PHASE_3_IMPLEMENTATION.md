# Phase 3 — Biometric Model Integrations

**Status:** Implementation candidate; real pretrained-checkpoint validation remains pending.

## Scope

Phase 3 adds optional, model-backed inference adapters without making PyTorch, SpeechBrain or ONNX Runtime dependencies of the base VoxRigor installation.

### ECAPA-TDNN

- Adapter ID: `ecapa-tdnn`
- Upstream model: `speechbrain/spkrec-ecapa-voxceleb`
- Backend: SpeechBrain `EncoderClassifier` / PyTorch
- Interface: `speechbrain.inference.classifiers.EncoderClassifier`
- Model revision: `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- License: Apache-2.0 per upstream model card
- Input: two local audio files, decoded to mono float32 and resampled to 16 kHz if required
- Output: raw cosine similarity between L2-normalized embeddings

The model snapshot is fetched at the pinned revision using Hugging Face Hub. SpeechBrain then loads the local snapshot with `pretrained_path` explicitly overridden to the same local directory. This prevents the upstream YAML from resolving checkpoint references against a mutable repository branch. SHA-256 digests of the snapshot's required model/configuration files are recorded in each score result.

Cosine similarity is not a probability or a deployment threshold. VoxRigor deliberately does not make an accept/reject decision. A threshold must be selected and justified using a separate development split under a declared protocol before scores are evaluated on a held-out test split.

### AASIST-L ONNX

- Adapter ID: `aasist-l-onnx`
- Upstream repository: `SpeechAntiSpoofingBenchmarks/AASIST-L`
- Backend: ONNX Runtime, CPU execution provider
- ONNX artifact revision: `2bc4bf063f34f081cafa5d51c2e72bbfa5d39715`
- Artifact: `aasist-l.onnx`
- License: MIT per upstream model card
- Input: mono float32 waveform at 16 kHz
- Window: deterministic first 64,600 samples; shorter utterances are tile-repeated to match the upstream evaluation wrapper
- Output: class-1 bona-fide logit

This is **AASIST-L**, the lightweight variant, not the full AASIST checkpoint. The output logit is not a calibrated probability. The adapter uses the ONNX artifact and does not execute Python code from the model repository. It inspects graph outputs and selects the unique float32 two-class logits output, allowing an auxiliary hidden output if the export includes one. The loaded ONNX artifact's SHA-256 is recorded.

## Audio handling

The optional audio layer:

1. Reads local files through SoundFile.
2. Enforces a default maximum input duration of 120 seconds based on file metadata before decoding.
3. Converts multi-channel recordings to mono by arithmetic channel averaging.
4. Preserves amplitude; it does not normalize, peak-scale or denoise audio.
5. Resamples using SciPy polyphase resampling when needed.
6. Computes a SHA-256 hash of the source file.
7. Omits the original path and waveform data from score reports.

The default duration limit can be changed by callers of the Python API. Very long dataset processing should use a future streaming/batch interface rather than increasing the limit indiscriminately.

## Optional installation

The base install remains lightweight.

```powershell
# ECAPA-TDNN speaker verification
python -m pip install -e ".[speaker]"

# AASIST-L ONNX anti-spoofing
python -m pip install -e ".[pad-onnx]"
```

For the speaker extra, PyTorch and TorchAudio binaries must be mutually compatible. If installation resolution fails on a particular CPU/CUDA platform, install a matched pair using the official PyTorch selector before installing the remaining optional dependencies. SpeechBrain 1.1.2 requires PyTorch and TorchAudio 2.7.1 or newer; verify the compatibility matrix for the chosen platform.

## CLI

```powershell
# Discover adapters without loading ML runtimes
voxrigor models list

# Explicitly fetch/cache model artifacts
voxrigor models fetch ecapa-tdnn
voxrigor models fetch aasist-l-onnx

# Compare two local recordings; result is an uncalibrated cosine similarity
voxrigor models score-ecapa --enrollment .\samples\enrollment.wav --probe .\samples\probe.wav

# Score a local recording with AASIST-L
voxrigor models score-aasist-l --audio .\samples\utterance.wav
```

The commands process audio locally. Model downloads occur only when a fetch or scoring command explicitly needs a model that is not already cached. No audio is uploaded by VoxRigor.

## Python API

```python
from pathlib import Path

from voxrigor.biometrics import AASISTLONNXAdapter, ECAPATDNNAdapter

speaker = ECAPATDNNAdapter(device="cpu")
speaker_result = speaker.score_files(Path("enrollment.wav"), Path("probe.wav"))
print(speaker_result.to_dict())
speaker.unload()

model_path = AASISTLONNXAdapter.fetch_pretrained_model()
pad = AASISTLONNXAdapter(model_path)
pad_result = pad.score_file(Path("utterance.wav"))
print(pad_result.to_dict())
pad.unload()
```

## Reliability and test boundaries

The automated tests use deterministic fake runtimes and synthetic audio. They verify input handling, preprocessing, adapter contracts, score semantics, immutable Hugging Face revision selection, local checkpoint path override, ONNX graph output selection and error paths.

They do **not** download model weights or establish real-checkpoint inference parity.

Before declaring real-model support stable, a maintainer must perform and record:

- A clean installation of each optional extra.
- A real ECAPA embedding extraction on a consented local sample.
- A real AASIST-L ONNX inference on a consented local sample.
- Output shape, finiteness and repeatability checks.
- A score export and independent Phase 2 metric calculation on a valid held-out protocol.
- CPU memory and runtime measurements.
- Model artifact hashes and resolved revisions.
- Confirmation that installed PyTorch and TorchAudio versions satisfy their compatibility matrix.

## Known limitations

- No custom model training or fine-tuning.
- No batch trial-manifest inference or Phase 2 score-file export yet.
- No threshold calibration or decision policy.
- No official ASVspoof metric implementation.
- No full AASIST PyTorch adapter in this phase.
- No GPU ONNX provider selection.
- No assurance that upstream pretrained models generalize to a new dataset, language, microphone or threat.
- No real-checkpoint tests in default CI.

These limitations are deliberate and must remain visible in release notes.
