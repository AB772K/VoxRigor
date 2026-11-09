# Phase 3 — Biometric Model Integrations

**Status:** Phase 3 implementation gates passed on the development branch. The follow-up pipeline is awaiting owner review in PR #4. Approved-dataset baseline comparison remains a research validation task; this is not a claim of biometric accuracy or stable model certification.

## Included adapters

- ECAPA-TDNN speaker embeddings through SpeechBrain / PyTorch.
- AASIST-L presentation-attack detection through ONNX Runtime CPU.
- Optional heavyweight dependencies; the base install remains lightweight.
- Local audio decoding, duration bounds, mono conversion, resampling and source hashing.
- Pinned upstream revisions and model artifact SHA-256 provenance.
- CLI discovery, fetch and single-file scoring.

ECAPA returns raw cosine similarity. AASIST-L returns the class-1 bona-fide logit. Neither is a calibrated probability or universal authentication decision. AASIST-L is the lightweight variant, not full AASIST.

## Batch model-to-benchmark workflow

```powershell
voxrigor models score-trials --manifest .\audio-trials.json --output-dir .\runs\inference\asv-example
voxrigor benchmark run .\runs\inference\asv-example\benchmark.json --output .\runs\benchmarks
```

For ASV, each trial declares enrollment/probe recordings and target/nontarget labels. ECAPA generates cosine scores. For PAD, each trial declares one recording, bonafide/spoof labels, and an attack species for spoof trials. AASIST-L generates bona-fide logits.

The scorer emits scores.csv, a schema 0.2 benchmark manifest and a hashed inference-provenance sidecar. The score-producer record retains framework version, model ID, immutable revision, backend, score semantics, artifact hashes, and source-manifest/provenance hashes.

The sidecar contains pseudonymous trial IDs and source-audio hashes, not file paths, waveforms or embeddings. The Phase 2 loader verifies sidecar integrity before evaluation.

See AUDIO_TRIAL_MANIFEST.md for the manifest format and security rules.

## Real-checkpoint validation

The default CI suite uses deterministic fake runtimes and does not download weights. The manually dispatched real-model-smoke.yml workflow downloads pinned checkpoints and exercises the adapters using generated non-biometric audio. A successful smoke test proves runtime/checkpoint execution only; it does not demonstrate biometric accuracy or PAD effectiveness.

## Limitations

- No custom model training or fine-tuning.
- No full AASIST PyTorch adapter or GPU ONNX provider selection.
- No automatic threshold calibration.
- No generalization claim across datasets, languages, generators, devices or threats.
- AASIST-L uses one deterministic reference window; this is not a multi-crop evaluation protocol.
