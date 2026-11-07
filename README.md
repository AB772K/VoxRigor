# VoxRigor

**Open-source voice authentication security testing and evaluation framework**

Research openly. Test rigorously. Report honestly.

> **Project status:** Phase 1 core-framework prototype. The current bundled test is a runtime diagnostic only. VoxRigor does not yet evaluate voice biometrics, audio attacks, authentication protocols, or target applications.

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
- Automated tests and cross-platform CI configuration.

The current `core.runtime-info` diagnostic returns `inconclusive` by design. It does not test a biometric model or security control. Machine-readable schemas are provided under [`schemas/`](schemas/).

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

## Responsible use

VoxRigor is intended for authorized research and evaluation. This Phase 1 prototype is offline-only and has no network target adapter. Future target testing must enforce explicit scope, use test identities, bound requests, and document authorization. Do not use real customer voice recordings or biometric templates without an appropriate lawful basis, informed authorization and safeguards.

## Licensing

Original VoxRigor code and documentation are distributed under Apache License 2.0. Third-party datasets, pretrained models, model weights, fixtures and dependencies retain their own licenses and terms. See [`docs/DATASET_AND_MODEL_POLICY.md`](docs/DATASET_AND_MODEL_POLICY.md).
