# VoxRigor Development Roadmap

**Status:** Living plan, updated with the Phase 2 offline evaluator. Calendar estimates are intentionally omitted; phases close against evidence and acceptance criteria.

## Phase 0 — Research and specification

Product charter, requirements, threat model, competitor analysis, standards/metrics mapping, dataset/model license policy, test catalogue and architecture decisions. Documentation is drafted; owner review and finalization remain ongoing.

## Phase 1 — Core framework foundation

Installable Python package, CLI, configuration validation, deterministic test runner, provenance, structured result states, JSON/HTML reporting and CI. Local tests pass; remote cross-platform CI and lint/type gates remain outstanding.

## Phase 2 — Offline benchmark and metrics engine

Precomputed ASV/PAD score CSV ingestion, manifest and SHA-256 validation, split accounting, optional group-overlap auditing, ASV and PAD metrics, condition breakdowns and reproducible JSON/HTML/CSV reports. Generic metrics only; no official challenge compatibility claim. Local suite: 77 passed, 86.56% coverage on Python 3.13.5.

## Phase 3 — Baseline model integrations

Optional ECAPA-TDNN speaker-verification and AASIST anti-spoofing adapters. Verify checkpoint provenance, licensing, preprocessing, score direction and compatibility against published baselines.

## Phase 4 — Audio condition and presentation evaluation

Audio metadata validation, controlled transformations, reproducibility metadata, consented/synthetic fixtures, and separate treatment of physical presentation versus digital injection.

## Phase 5 — Reference application and protocol/API security

Local reference authentication service, REST adapter, explicit scope allowlist, disposable test identities, challenge freshness, replay/session, enrollment, recovery and authorization tests with bounded requests and safe cleanup.

## Phase 6 — Original AI research

Cross-dataset generalization, calibration, attack-condition analysis, model fine-tuning/training only when supported by a research hypothesis, ablation studies and independent evaluation splits.

## Phase 7 — Plugin SDK and integrations

Stable public adapter/plugin interfaces, packaging and compatibility checks, examples, integration guides and backwards-compatibility policy.

## Phase 8 — Reliability and stable release

Full regression/integration tests, supported-environment matrix, SBOM and dependency security review, privacy audit, release automation, documentation and independent validation.

## Release policy

A phase or feature is not marked complete because it works once. It must have documented scope, automated tests, defined limitations and passed acceptance criteria. Generic Phase 2 metrics must not be marketed as official challenge scores or a security certification.