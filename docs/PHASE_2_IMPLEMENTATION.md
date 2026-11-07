# Phase 2 Implementation Record — Offline Benchmark and Metrics Engine

**Status:** Implemented locally in `phase-2-offline-benchmark`; 76 tests pass with 86.51% total coverage on Python 3.13.5. Package wheel build and synthetic ASV/PAD CLI smoke tests pass. GitHub Actions, other Python versions/operating systems, and independent review remain pending until the branch is published.

## Scope

Phase 2 evaluates **precomputed decision scores** in CSV trial files. It does not load waveform audio, perform feature extraction, infer embeddings, call an anti-spoofing network, or assess a target application. Model adapters remain Phase 3; audio transformations and capture-path PAD experiments remain Phase 4.

## Implemented capabilities

- Versioned Pydantic score-dataset manifest.
- Score-file SHA-256 verification and manifest provenance.
- Strict CSV validation: headers, unique trial IDs, finite scores, task-specific labels, required classes and split selection.
- Explicit ASV labels (`target`, `nontarget`) and PAD labels (`bonafide`, `spoof`).
- Operating-threshold provenance (`external` or named `development_split`).
- ASV FMR/FNMR at a declared threshold, Wilson score confidence intervals, empirical ROC, trapezoidal ROC-AUC and linearly interpolated EER.
- PAD BPCER and per-attack-species APCER with Wilson intervals; sample-weighted pooled APCER is clearly labelled as supplementary.
- Condition-specific breakdowns without silently omitting one-class conditions.
- Optional speaker/source split-overlap audit; configured group columns require non-empty values, and disjointness can be enforced explicitly.
- Per-split class counts, including validation that a declared development threshold-selection split contains all required classes.
- JSON, HTML, ROC CSV and PAD species CSV output.
- Synthetic, non-biometric fixtures for automated tests and examples.

## Important metric boundaries

- FMR/FNMR are comparison-trial metrics. They are not automatically equivalent to operational FAR/FRR.
- The EER is an interpolated descriptive point on the empirical ROC and is not treated as a deployment threshold.
- A development threshold is never selected from the evaluation split by the framework. Threshold provenance is user-declared; the tool verifies split separation and class presence, not the researcher's calibration process or threshold-selection calculations.
- PAD APCER is reported per attack species. Pooled APCER is sample-weighted and can conceal attack-species differences.
- Wilson intervals are trial-level and do not account for clustered trials from speakers or source recordings.
- Generic Phase 2 output is not an official ASVspoof result. ASVspoof minDCF, a-DCF, t-DCF and Cllr require their exact official protocol, costs, priors and evaluation implementation.

## Commands

```bash
voxrigor benchmark init ./scores.csv --task asv --dataset-id local-asv --protocol-id local-v1 --evaluation-split test --threshold 0.5 --threshold-source external
voxrigor benchmark validate ./benchmark.json
voxrigor benchmark run ./benchmark.json --output ./runs/benchmarks
```

For PAD, the user must provide a threshold and every spoof record must contain `attack_species`.

## Phase 2 acceptance gates

- Fixed synthetic fixtures reproduce hand-calculated operating-point rates.
- Inverted score conventions produce equivalent normalized results.
- Tied scores are processed as groups and do not create artificial discrimination.
- Malformed CSV, duplicate trial IDs, NaN/Infinity, missing classes and hash mismatch are rejected.
- Split filtering is explicit and sample counts reconcile.
- PAD reports each attack species independently.
- JSON report validates against its versioned schema.
- Local automated suite: 76 passed; 86.51% total coverage (Python 3.13.5).
- Editable install and wheel build pass locally.
- Synthetic ASV and PAD CLI smoke tests produce valid JSON/HTML and task-specific CSV artifacts.
- Ruff, Mypy and remote cross-platform CI remain separate gates and have not yet been verified.

## Known limitations and deferred work

- No audio files are loaded or transformed.
- No model inference or embedding extraction occurs.
- No speaker-clustered bootstrap confidence intervals yet.
- No official ASVspoof metric compatibility claim.
- No calibration curves, minDCF, a-DCF, t-DCF, Cllr or DET plot export yet.
- Group overlap audit is only as reliable as supplied pseudonymous metadata.
