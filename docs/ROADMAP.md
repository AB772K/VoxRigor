# Development Roadmap

**Status:** Phase 7 — experimental plugin SDK and integrations.  
**Planning basis:** milestone and acceptance-gate driven; calendar estimates intentionally omitted.  
**Current state:** Phase 1–3 and the Phase 5 local protocol/lifecycle engine are integrated into main. Phase 4 digital audio-condition generation and provenance are implemented; physical presentation hardware remains open. Phase 6 includes a score-only ASV cross-dataset calibration runner, optional deterministic cluster-bootstrap intervals for held-out evaluation metrics, condition-stratified evaluation using Phase 4 labels with frozen calibration/threshold transfer, a paired comparison runner for independently calibrated systems on identical trials, and an optional two-stage bootstrap that includes calibration-fit and threshold-selection variability. Phase 6 research infrastructure is implemented, but approved representative datasets, empirical multi-model-family studies, model-training/hyperparameter uncertainty and justified custom-model experiments remain open. Phase 7's experimental plugin contract, independently installable example-wheel integration and SDK versioning/deprecation policy are implemented and validated. The isolated-worker architecture is documented; platform backend implementation, adversarial isolation tests and signed publisher/distribution provenance remain open.

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

Exit gate: each transform has known input/output behavior, no silent clipping/resampling and reproducible test artifacts; PAD reports separate capture presentation from digital injection. The first Phase 4 slice covers digital audio-condition generation; physical presentation hardware integration remains a separately scoped extension.

## Phase 5 — Reference application and protocol/API security engine

**Goal:** assess an end-to-end voice-authentication workflow in a controlled environment.

Build:
- deliberately testable local reference authentication service;
- REST target adapter;
- explicit scope manifest and allowlist enforcement;
- disposable test-account lifecycle;
- challenge, enrollment, replay/session and authorization tests;
- request/time/resource bounds;
- evidence capture and redaction.

Exit gate: end-to-end tests demonstrate both a known vulnerable fixture and a fixed fixture, with verified outcomes and safe cleanup. Out-of-scope targets are refused.

## Phase 6 — Research and custom AI experiments

**Goal:** pursue original research only after stable baselines and valid test protocols exist.

Build:
- cross-dataset/generalization experiments;
- calibration and operating-point studies;
- attack-condition analysis;
- model fine-tuning/training recipes when justified by a research hypothesis;
- ablations and independent test splits;
- model cards and experiment cards.

Exit gate: any proposed improvement generalizes beyond the training/development data and is independently reproducible. No custom model is included as a default until its value and limitations are demonstrated.

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
