# Product Requirements

**Status:** Draft 0.1 — Phase 0  
**Date:** 2026-11-07

## 1. Requirement conventions

- `MUST`: required for the relevant release to be accepted.
- `SHOULD`: strongly recommended; deviations must be documented.
- `MAY`: optional capability.
- `P0`: required for the first usable vertical slice.
- `P1`: required for the first security-testing alpha.
- `P2`: later research or ecosystem capability.

A requirement is not complete when code merely runs. It is complete when its acceptance criteria, tests, documentation and limitations are satisfied.

## 2. Functional requirements

| ID | Priority | Requirement | Acceptance evidence |
|---|---|---|---|
| FR-001 | P0 | The framework MUST create and validate a versioned project manifest. | Valid and invalid manifest fixtures; schema version reported. |
| FR-002 | P0 | A run MUST have a unique run ID and record UTC start/end times. | Run metadata appears in JSON and HTML exports. |
| FR-003 | P0 | The framework MUST support importing externally generated score/trial files without requiring model inference. | A small public or synthetic fixture produces a complete report. |
| FR-004 | P0 | Dataset inputs MUST be validated for required columns, label vocabulary, duplicate identifiers, missing samples and declared split boundaries. | Validation report lists every rejected/unknown record and reason. |
| FR-005 | P0 | Sample accounting MUST reconcile input, accepted, excluded and evaluated counts. | Counts reconcile exactly; no silent row dropping. |
| FR-006 | P0 | Metric implementations MUST declare input semantics, positive class, score direction, threshold policy and denominators. | Metric unit tests against hand-calculated fixtures and/or a trusted reference. |
| FR-007 | P0 | Results MUST use explicit statuses: `vulnerable`, `no_issue_observed`, `inconclusive`, `unsupported`, `execution_error`. | Status semantics tested and documented. |
| FR-008 | P0 | Reports MUST record framework version, test ID/version, config hash, dataset identity, model/checkpoint identity when applicable, software versions and seed where used. | Provenance completeness test. |
| FR-009 | P0 | The framework MUST export a versioned JSON report and human-readable HTML report. | Schema validation and HTML smoke test. |
| FR-010 | P0 | Core CLI functionality MUST operate without installing ML frameworks. | Clean environment installs core extras and runs score-file example. |
| FR-011 | P1 | The framework MUST expose a documented `ModelAdapter` interface for ASV and PAD scoring. | Contract tests with dummy adapters. |
| FR-012 | P1 | The framework MUST expose a documented `DatasetAdapter` interface. | Contract tests with synthetic and one external dataset adapter. |
| FR-013 | P1 | The framework MUST support controlled audio transformations with recorded parameters and deterministic seeds where applicable. | Transformation metadata and reproducibility tests. |
| FR-014 | P1 | The framework MUST expose a target-application adapter for explicitly authorized local/reference systems. | End-to-end test against local reference service. |
| FR-015 | P1 | A target test MUST require an explicit scope declaration and enforce target allowlists. | Negative tests prove out-of-scope targets are refused. |
| FR-016 | P1 | HTTP target tests MUST use bounded timeouts, request limits and conservative concurrency. | Safety tests enforce configured ceilings. |
| FR-017 | P1 | Protocol tests MUST support test identities and fixture data, not require real customer accounts. | Reference application test suite uses disposable accounts. |
| FR-018 | P1 | Evidence artifacts MUST be referenced by hash and stored separately from ordinary logs. | Artifact manifest and hash validation tests. |
| FR-019 | P1 | Reports MUST redact configured secrets and avoid embedding raw audio by default. | Secret-redaction and artifact-policy tests. |
| FR-020 | P2 | The framework SHOULD support third-party test plugins with a stable, versioned interface. | External example plugin passes contract suite. |
| FR-021 | P2 | Plugins MUST NOT be described as sandboxed unless an actual isolation mechanism is implemented and validated. | Documentation and architecture review. |
| FR-022 | P2 | The framework MAY offer CI integrations that run a selected non-destructive test profile. | CI example against local/reference target. |
| FR-023 | P2 | The framework MAY support a research export such as CSV/Parquet plus a provenance manifest. | Round-trip and provenance tests. |

## 3. Non-functional requirements

### NFR-SEC — Security

- Credentials MUST be loaded from environment variables or an approved secret provider, not committed in manifests or logs.
- Network access MUST be disabled unless a target adapter and scope explicitly enable it.
- Plugin loading MUST be explicit and documented. Python in-process plugins are arbitrary code; they are not sandboxed.
- Untrusted model checkpoints MUST NOT be loaded automatically. Checkpoint provenance, hashes, formats and upstream security advisories MUST be checked. Prefer safer model formats where available; `weights_only=True` alone must not be treated as a universal security guarantee.
- Dependency versions MUST be pinned for reproducible releases, scanned and updated through reviewed changes.

### NFR-PRIV — Privacy

- Local processing MUST be the default.
- No audio, embeddings, templates, credentials or report contents may be sent to project-operated telemetry because no such telemetry is required.
- Raw audio retention MUST be configurable and off by default for generated temporary artifacts.
- Logs MUST avoid raw audio, biometric templates, secrets and unnecessary direct identifiers.
- Test data must be synthetic, appropriately licensed, or collected with documented informed consent and authorization.

### NFR-COR — Correctness and scientific validity

- Metric definitions MUST be explicit and traceable to a protocol or citation.
- The framework MUST distinguish zero-effort impostor trials from deliberate presentation attacks.
- Threshold selection MUST be performed on a declared development set and frozen before final test evaluation.
- Uncertainty, sample size and class/attack-condition counts SHOULD be reported.
- No sample may be excluded without a recorded reason.
- Results from different datasets, protocols, score directions or operating points MUST NOT be pooled without an explicit justified method.

### NFR-REP — Reproducibility

- Dataset and model references MUST include versions and hashes where legally and technically possible.
- Runs MUST record configuration, package versions, platform details and seed settings.
- Determinism limits caused by hardware, libraries or nondeterministic kernels MUST be disclosed.

### NFR-USE — Usability

- Core install and offline example SHOULD require no GPU.
- CLI errors MUST identify the invalid field, file or test and provide a safe corrective hint.
- Reports MUST explain terms and distinguish findings from benchmark performance.

### NFR-MAINT — Maintainability

- Public interfaces MUST be typed and schema-versioned.
- Core code MUST be independent of optional ML frameworks.
- Tests MUST run in CI on supported Python versions and operating systems.
- The project SHOULD maintain a documented deprecation policy for plugin APIs and report schemas.

## 4. Proposed initial acceptance gates

These are engineering targets, not promises of defect-free software:

1. All required CI jobs pass on every release candidate.
2. Core business logic has at least 90% line coverage as a starting quality gate; scope enforcement, credential redaction and result-status logic receive explicit branch-focused tests.
3. Metric outputs match known fixtures/reference implementations within documented numerical tolerances.
4. Same deterministic CPU run, same inputs and same declared software stack reproduce identical sample accounting and metrics within tolerance.
5. Invalid, missing or malformed inputs produce explicit validation or execution errors, never a success status.
6. Every report contains a complete provenance section or explicitly marks unavailable fields.
7. Remote target testing is disabled by default and an out-of-scope target is rejected in automated tests.
8. No release may bundle a dataset, checkpoint or dependency whose redistribution terms have not been reviewed.

Code coverage is only one signal; it does not prove correctness or security.

## 5. Initial release boundary

The first usable release should include FR-001 through FR-010. It should evaluate declared score/trial data and produce a reproducible report. Model inference, audio attack fixtures and target application testing are added only after their respective contracts and safety controls are implemented.
