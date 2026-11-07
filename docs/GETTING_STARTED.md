# Getting Started

## Requirements

- Python 3.11–3.13.
- No GPU or machine-learning framework is required for core commands.

## Install the core package

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Create and validate a local project

```powershell
voxrigor init .\my-voice-research --name "My Voice Research"
voxrigor validate .\my-voice-research\voxrigor.json
```

## Phase 2: offline score evaluation

See [BENCHMARK_DATA_FORMAT.md](BENCHMARK_DATA_FORMAT.md) for the CSV and manifest formats.

## Phase 3: optional biometric model adapters

The core package does not install PyTorch, SpeechBrain or ONNX Runtime.

Install an adapter:

```powershell
# ECAPA-TDNN speaker verification
python -m pip install -e ".[speaker]"

# AASIST-L ONNX anti-spoofing
python -m pip install -e ".[pad-onnx]"
```

For the speaker extra, PyTorch and TorchAudio binaries must be mutually compatible. If package resolution fails for your CPU/CUDA platform, install a matched pair from the official PyTorch selector first, then install the remaining optional dependencies.

List the model adapters without loading model weights:

```powershell
voxrigor models list
```

Fetch/cache a model explicitly:

```powershell
voxrigor models fetch ecapa-tdnn
voxrigor models fetch aasist-l-onnx
```

Score two local recordings with ECAPA-TDNN:

```powershell
voxrigor models score-ecapa --enrollment .\samples\enrollment.wav --probe .\samples\probe.wav
```

Score a local recording with AASIST-L:

```powershell
voxrigor models score-aasist-l --audio .\samples\utterance.wav
```

ECAPA returns raw cosine similarity. AASIST-L returns a raw bona-fide logit. Neither is a probability or universal threshold. AASIST-L is the lightweight AASIST variant, not full AASIST.

See [PHASE_3_IMPLEMENTATION.md](PHASE_3_IMPLEMENTATION.md), [THIRD_PARTY_MODELS.md](THIRD_PARTY_MODELS.md) and [PHASE_3_ACCEPTANCE.md](PHASE_3_ACCEPTANCE.md) for provenance, licensing, preprocessing and validation limitations.

Model files are downloaded only when a user explicitly invokes fetch or inference. Audio is processed locally and is not uploaded by VoxRigor.

## Safety and privacy

Do not commit audio recordings, biometric embeddings, access tokens or other sensitive material to source control. Review run artifacts before sharing. Only test systems and recordings you own or are explicitly authorized to assess.
