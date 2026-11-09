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


## Run model inference and produce a benchmark

Phase 3 adds a manifest-driven path from local audio trials to the Phase 2 score evaluator.

1. Prepare a local audio dataset and a JSON audio-trial manifest. Use pseudonymous trial and group identifiers. The audio files must be inside the manifest's directory tree.
2. Install the optional model backend required by the selected model.
3. Run model inference to produce a score CSV, benchmark manifest and inference-provenance sidecar.
4. Run the Phase 2 benchmark evaluator against the generated manifest.

Example PowerShell commands:

```powershell
# ECAPA speaker-verification trials
voxrigor models score-trials --manifest .\audio-trials.json --output-dir .\runs\inference\asv-example

# Evaluate generated scores
voxrigor benchmark run .\runs\inference\asv-example\benchmark.json --output .\runs\benchmarks
```

See [AUDIO_TRIAL_MANIFEST.md](AUDIO_TRIAL_MANIFEST.md) for the ASV and PAD manifest formats, labels, threshold requirements, supported metadata and privacy boundaries.

For PAD, use the AASIST-L adapter, one audio path per trial, bonafide/spoof labels, an attack species for every spoof trial and a threshold fixed before evaluation. Never select a threshold using the test split.

The score-producer record identifies the model revision, backend, raw score semantics and artifact hashes. The provenance sidecar records input hashes and preprocessing details. VoxRigor verifies score and sidecar hashes before evaluation.

### Real model smoke tests

After the Phase 3 branch is integrated, repository maintainers can open Actions → Optional real-model smoke tests → Run workflow and select ECAPA, AASIST-L or both. The workflow downloads pinned model artifacts and tests runtime execution using generated non-biometric audio. It is not an accuracy benchmark.


## Phase 4: generate controlled audio conditions

Install the optional audio dependencies and generate a reproducible clean-plus-conditions dataset:

```powershell
python -m pip install -e ".[audio]"
voxrigor audio conditions generate --manifest .\condition-experiment.json --output-dir .\runs\conditions\experiment-01
```

Use the generated `audio-trials.json` as input to `voxrigor models score-trials`, then run the Phase 2 benchmark evaluator. Condition labels are retained so the report can compare clean and transformed trials.

Supported initial conditions are resampling, seeded Gaussian noise, 8 kHz μ-law companding, and reverberation using a local impulse response. A clean baseline is mandatory. Digital transformations are not physical replay tests. See [PHASE_4_IMPLEMENTATION.md](PHASE_4_IMPLEMENTATION.md) and [PHASE_4_ACCEPTANCE.md](PHASE_4_ACCEPTANCE.md).


## Phase 5: local protocol and API security testing

The initial Phase 5 engine is intentionally limited to loopback targets. It does not accept remote hosts or DNS names.

Start the fixed local reference service in one terminal:

```powershell
voxrigor protocol serve --fixture-profile fixed --port 8765 --challenge-ttl-seconds 3
```

Create an explicit scope file and run the protocol checks in another terminal:

```powershell
voxrigor protocol init-scope --target-url http://127.0.0.1:8765 --i-authorize-local-target --output .\protocol-scope.json
voxrigor protocol run --scope .\protocol-scope.json --output .\runs\protocol-fixed
```

The reference fixture uses disposable in-memory accounts and a synthetic test assertion. It does not perform speaker verification, PAD or liveness detection. To verify that the tests detect known control failures, run the intentionally vulnerable fixture using the controlled demonstration command:

```powershell
voxrigor protocol demo --fixture-profile vulnerable --output .\runs\protocol-vulnerable
```

Only run the vulnerable profile on the local fixture. Scope validation accepts loopback IP literals only; the HTTP client disables proxies and redirects and enforces request, response, timeout and total-request limits. Reports exclude request bodies, response payloads, bearer tokens and fixture proofs.

See [PHASE_5_IMPLEMENTATION.md](PHASE_5_IMPLEMENTATION.md) and [PHASE_5_ACCEPTANCE.md](PHASE_5_ACCEPTANCE.md) for supported checks and limitations.
