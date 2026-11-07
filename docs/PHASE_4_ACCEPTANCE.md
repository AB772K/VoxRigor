# Phase 4 Acceptance Criteria

## Implemented slice — automated gates

- [ ] Condition experiment manifest has strict types and a mandatory clean baseline.
- [ ] ASV scenarios explicitly target probe, enrollment or both; PAD scenarios target the audio record.
- [ ] Resampling validates rates and preserves deterministic sample accounting.
- [ ] Gaussian noise uses a fixed, derived per-trial seed and measured input SNR.
- [ ] μ-law conversion is deterministic, narrowband at 8 kHz and refuses implicit clipping.
- [ ] Reverberation uses an explicit local impulse response, validates sample-rate compatibility and records its hash.
- [ ] Transform order, input/output sample hashes, seeds, rates, durations and amplitudes are recorded.
- [ ] FLOAT WAV exports preserve over-range values; no hidden clipping or normalization occurs.
- [ ] Input path traversal and symlink escapes are rejected.
- [ ] Generated trial IDs are unique and condition labels are retained for per-condition reports.
- [ ] Output size, trial expansion, input duration and IR duration have explicit hard limits.
- [ ] Condition-provenance SHA-256 is copied into score-producer metadata and verified by Phase 2.
- [ ] No source audio paths, raw audio, or embeddings are written to condition provenance.
- [ ] Ruff, formatting, strict Mypy, tests and the 85% coverage gate pass on all six CI combinations.

## Research and physical presentation gates — still open

- [ ] Run the transforms on an approved dataset and quantify ASV/PAD changes with confidence intervals.
- [ ] Compare transformation outputs and resampling behavior with independently validated reference implementations.
- [ ] Define and document codec/telephony conditions beyond μ-law companding.
- [ ] Design and validate a local speaker/room/microphone presentation rig with calibration metadata.
- [ ] Demonstrate that physical replay and digital injection are separate labels and result categories.
- [ ] Validate that generated conditions do not leak source identity across train/development/evaluation splits.

A passing transformation unit test is not evidence of biometric accuracy, PAD effectiveness or real-world channel realism.
