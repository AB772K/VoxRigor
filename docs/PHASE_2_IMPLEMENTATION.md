# Phase 2 Implementation Record — Offline Benchmark Engine

**Status:** Implemented on branch `phase-2-offline-benchmark`. Local verification on Python 3.13.5: 77 tests passed, total coverage 86.56%, editable install and wheel build passed, synthetic ASV/PAD CLI smoke tests passed. Ruff, mypy and remote cross-platform CI remain unverified.

## Scope

Phase 2 evaluates precomputed decision scores in CSV trials. It does not load waveform audio, infer embeddings, execute biometric models or test a target application. Model adapters are Phase 3; audio transformations and presentation testing are Phase 4.

## Implemented

- Versioned dataset manifest with provenance and score-file SHA-256 verification.
- Strict CSV validation, unique trial IDs, finite scores, labels, selected split, required classes, and sample accounting.
- Path confinement: score files must resolve inside the manifest directory.
- Optional speaker/source overlap audit, with configurable disjointness enforcement.
- ASV FMR/FNMR at a declared threshold, trial-level Wilson intervals, tie-aware empirical ROC/AUC and interpolated EER.
- PAD BPCER and per-attack-species APCER with Wilson intervals; pooled APCER is explicitly supplementary.
- Per-condition results, JSON/HTML reports, ROC CSV and PAD species CSV.
- Synthetic fixtures, JSON Schemas and automated tests.

## Metric boundaries

FMR/FNMR are comparison-trial metrics and are not automatically equivalent to transaction-level FAR/FRR. EER is descriptive, not a deployment threshold. Threshold provenance is declared by the researcher; the tool checks split separation and class presence but cannot prove how a threshold was derived. Wilson intervals are trial-level and do not adjust for speaker/source clustering. Generic results are not official ASVspoof results.

## Commands

```bash
voxrigor benchmark init ./scores.csv --task asv --dataset-id local-asv --protocol-id local-v1 --evaluation-split test --threshold 0.5 --threshold-source external
voxrigor benchmark validate ./benchmark.json
voxrigor benchmark run ./benchmark.json --output ./runs/benchmarks
```

PAD requires a threshold and an `attack_species` value for every spoof trial.

## Remaining gates

- Run GitHub Actions on Ubuntu and Windows with Python 3.11, 3.12 and 3.13.
- Resolve any Ruff, formatting or mypy failures.
- Obtain independent review of metric definitions and test protocols.
- Add official challenge-specific metrics only with exact protocol, cost and prior definitions and reference comparisons.
