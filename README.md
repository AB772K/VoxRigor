# VoxRigor

**Open-source voice authentication security testing and evaluation framework**

Research openly. Test rigorously. Report honestly.

> **Project status:** Early research prototype — Phase 1 core framework and Phase 2 offline score-based ASV/PAD evaluation are implemented locally. Phase 2 accepts user-supplied precomputed scores; it does not yet load audio, run models, or test target applications. Cross-platform CI and independent review remain pending.

## About

I am developing VoxRigor as an independent security researcher to help fellow security researchers, biometric researchers, developers and security engineers examine the security and reliability of voice-authentication systems.

Voice authentication is not just a speaker-recognition model. Its security depends on the full chain: enrollment, reference-template handling, audio capture, presentation-attack detection (PAD), speaker verification, challenge-response logic, APIs, session management, recovery and operational controls.

VoxRigor aims to provide a local-first, extensible and reproducible framework for evaluating these layers through documented test cases, model and dataset adapters, authorized target-application adapters, evidence-backed results and machine-readable reports.

## What exists today

- Strict, versioned offline project manifest.
- CLI for project initialization, validation, test discovery, execution and report inspection.
- Explicit built-in test registry.
- Run IDs, UTC timestamps and configuration SHA-256 provenance.
- Typed result statuses and sample-accounting checks.
- Local JSON and self-contained HTML report output.
- Automated tests and cross-platform CI workflow.
- Offline score-trial benchmark engine for precomputed ASV/PAD scores (Phase 2).
- Split-level class accounting, optional speaker/source overlap audits, and dataset/file provenance.

The `core.runtime-info` diagnostic returns `inconclusive` by design. It does not test a biometric model or security control. The Phase 2 benchmark evaluates supplied decision scores only; it does not run an upstream model. Machine-readable schemas are provided under [`schemas/`](schemas/).

## Phase 2: Offline score evaluation

Phase 2 accepts **precomputed scores**, not raw audio. It validates a score CSV and a dataset manifest, checks file integrity and split accounting, calculates supported metrics, and writes reproducible JSON/HTML/CSV artifacts. It does not execute an ASV or PAD model; model integrations are planned for Phase 3.

Example ASV workflow:

```bash
voxrigor benchmark init ./scores.csv --task asv --dataset-id my-asv --protocol-id protocol-v1 --evaluation-split test --threshold 0.5 --threshold-source external
voxrigor benchmark validate ./benchmark.json
voxrigor benchmark run ./benchmark.json --output ./runs/benchmarks
```

For PAD, provide `--task pad`, a predeclared threshold, and an `attack_species` column for every `spoof` row. See [`docs/BENCHMARK_DATA_FORMAT.md`](docs/BENCHMARK_DATA_FORMAT.md) for the full CSV and manifest contract. The example files under [`examples/fixtures/`](examples/fixtures/) contain fabricated scores only and are not performance evidence.

## Planned assessment layers

1. Speaker verification (ASV): comparison-score evaluation and operating-point analysis.
2. Presentation attack detection (PAD): testing of attacks presented at the biometric capture device.
3. Audio robustness: condition-specific evaluation under transformations such as codec changes, noise and reverberation.
4. Authentication protocol: challenge lifecycle, freshness, replay controls and enrollment/session workflows.
5. Application/API security: authorization, authentication, resource limits and sensitive workflow protections.
6. End-to-end evaluation: evidence-linked analysis of interactions between the preceding layers.

These layers will be reported separately. A PAD result does not establish application security; a model benchmark does not establish end-to-end authentication security.

## Quick start

```bash
python -m venv .venv
python -m pip install -e .
voxrigor init ./my-project --name "My Voice Research"
voxrigor validate ./my-project/voxrigor.json
voxrigor tests
voxrigor run --project ./my-project/voxrigor.json --output ./my-project/runs
```

See [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) for Windows PowerShell and report-inspection instructions.

## Development documentation

- [Project charter](docs/PROJECT_CHARTER.md)
- [Requirements](docs/REQUIREMENTS.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Competitor analysis](docs/COMPETITOR_ANALYSIS.md)
- [Standards and metrics](docs/STANDARDS_AND_METRICS.md)
- [Dataset and model policy](docs/DATASET_AND_MODEL_POLICY.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Initial test catalogue](docs/INITIAL_TEST_CATALOG.md)
- [Roadmap](docs/ROADMAP.md)
- [Phase 1 implementation record](docs/PHASE_1_IMPLEMENTATION.md)
- [Phase 1 validation record](docs/PHASE_1_VALIDATION.md)
- [Phase 2 implementation record](docs/PHASE_2_IMPLEMENTATION.md)
- [Benchmark CSV and manifest format](docs/BENCHMARK_DATA_FORMAT.md)

## Responsible use

VoxRigor is intended for authorized research and evaluation. The current implementation is offline-only and has no network target adapter. Future target testing must enforce explicit scope, use test identities, bound requests, and document authorization. Do not use real customer voice recordings or biometric templates without an appropriate lawful basis, informed authorization and safeguards.

## Licensing

Original VoxRigor code and documentation are distributed under Apache License 2.0. Third-party datasets, pretrained models, model weights, fixtures and dependencies retain their own licenses and terms. See [`docs/DATASET_AND_MODEL_POLICY.md`](docs/DATASET_AND_MODEL_POLICY.md).
