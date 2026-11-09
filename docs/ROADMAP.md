# Development Roadmap

**Status:** Phase 6 — research and custom-AI experiment infrastructure.  
**Planning basis:** milestone and acceptance-gate driven; calendar estimates intentionally omitted.  
**Current state:** Phase 1, Phase 2, Phase 3 model adapters and the Phase 3 model-to-benchmark follow-up are integrated into main. Phase 4 deterministic digital audio-condition generation and provenance checks are implemented; physical presentation hardware and approved-dataset experiments remain open. Phase 5's loopback-only protocol/API engine and lifecycle extension are implemented and passed the six-environment CI matrix. Phase 5 general target adapters and full recovery/fallback workflows remain future integration work. Phase 6 starts with score-based cross-dataset experiments, calibration and operating-point transfer; custom training is deferred until supported by a research hypothesis and approved data.

## Phase 0 — Research, product specification and threat modeling

**Goal:** finalize the product boundary and test methodology before substantial implementation.

Deliverables:
- Project charter and target-user definition.
- Product requirements and non-functional requirements.
- Threat model, privacy model and authorization model.
- Competitor/related-work analysis.
- Standards and metrics map.
- Dataset/model licensing and provenance policy.
- Initial test catalogue.
- Architecture proposal and decisions.
- Phase acceptance criteria and research questions.

Exit gate: no unresolved ambiguity that would change the first vertical slice's architecture or safety controls. Open issues can remain if explicitly deferred.

## Phase 1 — Core framework foundation

**Goal:** create a lightweight, installable package and deterministic run pipeline.

Build:
- project manifest schema and validator;
- CLI and help system;
- run IDs, logging, error taxonomy and status model;
- test discovery/orchestration;
- provenance manifest and content hashes;
- local result/artifact storage;
- JSON report schema and initial HTML template;
- CI with lint, types and tests.

Exit gate: a dummy test can be discovered, validated, executed and reported in a clean base installation without ML dependencies.

## Phase 2 — Offline benchmark and metrics engine (first useful product slice)

**Goal:** allow a researcher to evaluate declared speaker-verification/PAD scores and trials with transparent sample accounting.

Build:
- dataset manifest and adapter contracts;
- score/trial import formats;
- label, split and sample validation;
- duplicate/overlap checks where metadata supports them;
- metric implementations and reference comparisons;
- confidence interval support where appropriate;
- per-condition result breakdowns;
- reproducibility report.

Exit gate: fixed fixtures reproduce hand-calculated and/or official reference outputs within documented tolerance; no silent sample loss; invalid protocol combinations are rejected. Current implementation supports the normalized CSV score format and generic ASV/PAD metrics only; official challenge formats and challenge-specific cost metrics remain deferred until implemented and independently validated.

**Phase 2 implementation note:** the first implementation is score-only. It does not read audio or run models. This boundary keeps the metrics implementation independently testable and avoids coupling score evaluation to model frameworks.

## Phase 3 — Baseline model integrations

**Goal:** connect existing models without making model inference mandatory for the core.

Build:
- optional SpeechBrain ECAPA-TDNN adapter for speaker verification;
- optional AASIST adapter for anti-spoofing;
- checkpoint inventory, hash verification and preprocessing declarations;
- model score-direction and calibration handling;
- integration tests with small, approved fixtures.

Exit gate: both adapters pass contract tests, model artifacts have provenance/license records, and results are compared with published/official baselines under compatible conditions. Adapter, provenance, batch-inference and CI implementation gates have passed. A representative approved dataset comparison remains open; checkpoint smoke tests are runtime checks, not biometric performance evidence.

## Phase 4 — Audio condition and presentation evaluation

**Goal:** add controlled audio transformations and capture-path PAD test support.

Build:
- audio metadata/format validation;
- controlled resampling, codec, noise and reverberation transforms;
- seed and transform provenance;
- synthetic/consented fixture workflow;
- optional local presentation rig integration design;
- separate labels for physical presentation versus digital injection.

Exit gate: each transform has known input/output behavior, no silent clipping/resampling and reproducible test artifacts; PAD reports separate capture presentation from digital injection. The implemented slice covers deterministic digital audio-condition generation and provenance verification. Physical presentation hardware integration and approved-dataset condition analysis remain open.

## Phase 5 — Reference application and protocol/API security engine

**Goal:** assess an end-to-end voice-authentication workflow in a controlled environment.

Implemented:
- deliberately testable local reference authentication service;
- loopback-only REST client with explicit scope acknowledgement;
- disposable in-memory test identities and fixtures;
- bounded challenge, enrollment, replay/session and authorization tests;
- request/time/resource bounds;
- evidence capture and redaction;
- challenge purpose binding, re-enrollment ownership and session-expiry checks.

Exit gate for the initial local fixture: fixed and vulnerable profiles produce the expected distinct results; scope restrictions and safe bounds are enforced. This implementation gate passed CI run [42593363565](https://github.com/AB772K/VoxRigor/actions/runs/42593363565) on Ubuntu/Windows and Python 3.11–3.13. It does not complete general target adapters, full recovery channels or remote assessment.

## Phase 6 — Research and custom AI experiments

**Goal:** measure whether systems and countermeasures generalize across datasets and attack/capture conditions before proposing custom models.

Build:
- a versioned experiment manifest that links calibration/development data to independent evaluation datasets;
- calibration and reliability metrics fitted only on development/calibration data;
- operating-point selection on calibration data and frozen transfer to evaluation data;
- cross-dataset and cross-condition comparisons with sample, group-overlap and provenance accounting;
- ablations and independent test splits;
- experiment cards, model cards and reproducible research exports;
- model fine-tuning/training recipes only when justified by a falsifiable research hypothesis.

Exit gate: an experiment can be rerun from declared manifests; calibration and thresholds do not inspect evaluation labels; dataset/model lineage and overlap limitations are explicit; a proposed improvement is evaluated on independent data and generalizes beyond training/development data. No custom model is included as a default until its value and limitations are demonstrated.

## Phase 7 — Plugin SDK, integrations and usability

**Goal:** make third-party research extensions practical.

Build:
- stable public plugin contracts;
- plugin packaging and compatibility checks;
- SDK examples and documentation;
- containerized optional workers if isolation is implemented;
- CI example and research export formats;
- backwards-compatibility policy.

Exit gate: an external developer can build, install and test an example plugin using published documentation; trust and permissions are explicit.

## Phase 8 — Reliability review and stable release

**Goal:** release a supportable v1.0.

Build:
- full regression and integration suite;
- supported-environment matrix;
- dependency/SBOM/security review;
- data privacy audit;
- package and release automation;
- docs, demos and known-limitations register;
- independent validation and feedback.

Exit gate: release gates in REQUIREMENTS.md pass, supported capabilities are documented, and the release makes no unsupported security or compliance claims.

## Release policy

- `0.x` releases may change APIs; document breaking changes.
- Report schema and test IDs are versioned independently.
- Do not release a feature as stable until its tests and docs exist.
- Maintain a known-limitations file and disclose unsupported conditions.
- No schedule-driven release may bypass a safety, licensing or reproducibility gate.
