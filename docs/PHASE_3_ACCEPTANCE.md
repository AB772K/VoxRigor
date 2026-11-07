# Phase 3 Acceptance Criteria

Phase 3 is integrated only when automated gates pass and real-checkpoint evidence is recorded.

## Automated gates

- [ ] Core installation imports VoxRigor without PyTorch, SpeechBrain, ONNX Runtime or Hugging Face Hub.
- [ ] models list works with core dependencies only.
- [ ] Audio decoding rejects missing, empty, too-long, unsupported-rate and non-finite files.
- [ ] Stereo-to-mono and resampling behavior are deterministic.
- [ ] AASIST-L fixed-window preprocessing is tested against its published wrapper.
- [ ] ECAPA validates finite, non-zero embeddings and computes raw cosine similarity.
- [ ] ECAPA uses an immutable model revision and local checkpoint snapshot.
- [ ] AASIST-L validates ONNX input and unique two-class output.
- [ ] Results include source-audio hashes, model revision, score semantics and artifact hashes.
- [ ] Audio-trial manifests reject path traversal, duplicate IDs, invalid labels and model/task mismatches.
- [ ] Batch inference emits Phase 2-compatible scores and a hashed provenance sidecar.
- [ ] Phase 2 verifies score and inference-sidecar hashes.
- [ ] Reports preserve model provenance.
- [ ] Tests cover missing optional dependencies, inference failures and trial validation.
- [ ] Ruff, formatting, strict Mypy, tests and the configured 85% coverage gate pass on all supported CI environments.

## Real-checkpoint gates

- [ ] ECAPA smoke workflow loads its pinned SpeechBrain checkpoint and emits finite embeddings and cosine scores.
- [ ] AASIST-L smoke workflow loads its pinned ONNX checkpoint and emits finite logits.
- [ ] Model revisions and artifact hashes are saved as CI artifacts.
- [ ] At least one approved evaluation dataset is scored end-to-end and consumed by Phase 2.
- [ ] No raw audio, source paths or embeddings are committed or placed in default reports.

Fake-runtime tests do not satisfy real-checkpoint gates. Synthetic smoke audio validates runtime execution only, not biometric performance.
