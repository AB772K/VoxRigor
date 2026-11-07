# Phase 4 Acceptance Criteria

## Implemented slice — automated gates

- [x] Condition experiment manifest has strict types and a mandatory clean baseline.
- [x] ASV scenarios explicitly target probe, enrollment or both; PAD scenarios target the audio record.
- [x] Resampling validates rates and preserves deterministic sample accounting.
- [x] Gaussian noise uses a fixed, derived per-trial seed and measured input SNR.
- [x] μ-law conversion is deterministic, narrowband at 8 kHz and refuses implicit clipping.
- [x] Reverberation uses an explicit local impulse response, validates sample-rate compatibility and records its hash.
- [x] Transform order, input/output sample hashes, seeds, rates, durations and amplitudes are recorded.
- [x] FLOAT WAV exports preserve over-range values; no hidden clipping or normalization occurs.
- [x] Input path traversal and symlink escapes are rejected.
- [x] Generated trial IDs are unique and condition labels are retained for per-condition reports.
- [x] Output size, trial expansion, input duration and IR duration have explicit hard limits.
- [x] Condition-provenance SHA-256 is copied into score-producer metadata and verified by Phase 2.
- [x] No source audio paths, raw audio, or embeddings are written to condition provenance.
- [x] Ruff, formatting, strict Mypy, tests and the 85% coverage gate pass on all six CI combinations.

## Research and physical presentation gates — still open

- [ ] Run the transforms on an approved dataset and quantify ASV/PAD changes with confidence intervals.
- [ ] Compare transformation outputs and resampling behavior with independently validated reference implementations.
- [ ] Define and document codec/telephony conditions beyond μ-law companding.
- [ ] Design and validate a local speaker/room/microphone presentation rig with calibration metadata.
- [ ] Demonstrate that physical replay and digital injection are separate labels and result categories.
- [ ] Validate that generated conditions do not leak source identity across train/development/evaluation splits.

The implemented-slice automated gates passed in CI run 42413468715 on Ubuntu and Windows with Python 3.11, 3.12 and 3.13. The suite completed 172 tests and 86.65% coverage on each Linux Python job; the Windows matrix also passed.

A passing transformation unit test is not evidence of biometric accuracy, PAD effectiveness or real-world channel realism.
