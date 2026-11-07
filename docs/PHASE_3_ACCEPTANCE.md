# Phase 3 Acceptance Criteria

Phase 3 is considered integrated only after all automated gates pass and the manual real-model gates have been recorded.

## Automated gates

- [ ] Core installation imports VoxRigor without importing PyTorch, SpeechBrain, ONNX Runtime or Hugging Face Hub.
- [ ] `voxrigor models list` works with only core dependencies.
- [ ] Audio decoding rejects missing, empty, too-long, unsupported-rate and non-finite files.
- [ ] Stereo-to-mono behavior and resampling are deterministic and tested.
- [ ] AASIST-L fixed-window preprocessing matches the upstream first-window/tile behavior.
- [ ] ECAPA adapter validates finite, non-zero embeddings and computes raw cosine similarity.
- [ ] ECAPA model loading uses a full immutable model commit, a local snapshot and a local checkpoint-path override.
- [ ] AASIST-L adapter validates the ONNX graph input and unique two-class logits output.
- [ ] Model results include model revision, score semantics, source audio hashes and model artifact hashes.
- [ ] Tests cover missing optional dependencies and model/runtime failures.
- [ ] Ruff, formatting, strict Mypy and the complete test suite pass on all supported CI environments.

## Manual real-model gates

- [ ] A clean `.[speaker]` environment loads the pinned SpeechBrain model and computes embeddings.
- [ ] A clean `.[pad-onnx]` environment loads the pinned ONNX artifact and computes a finite bona-fide logit.
- [ ] Resolved artifact hashes and model revisions are recorded.
- [ ] A second independent run produces repeatable scores within a declared tolerance.
- [ ] Output scores are consumed by the Phase 2 evaluator without loss of provenance.
- [ ] No raw voice recordings or biometric embeddings are included in logs, reports or Git commits by default.

Passing unit tests with fake runtimes does not satisfy the manual real-model gates. Do not describe the models as fully validated until those checks have been recorded.
