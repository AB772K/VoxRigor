# Architecture Decision Register

**Status:** Proposed decisions — Phase 0  
**Last updated:** 2026-11-07

## ADR-001 — Use Python as the primary language

**Status:** Proposed  
**Decision:** Use Python for the first implementation.  
**Reason:** audio/ML research ecosystem, approachable plugin development and good CLI/testing support.  
**Consequences:** isolate optional ML dependencies; test supported Python versions and platform combinations before declaring compatibility.

## ADR-002 — Keep the core free of mandatory ML dependencies

**Status:** Proposed  
**Decision:** The base package must run offline score/trial evaluation without PyTorch.  
**Reason:** smaller installs, fewer dependency conflicts and useful functionality for users who already have model scores.  
**Consequences:** model adapters use optional extras and a stable scoring interface.

## ADR-003 — Separate biometric, PAD, audio robustness and application-security result domains

**Status:** Proposed  
**Decision:** Use separate test categories and domain-specific metrics.  
**Reason:** ISO/IEC 30107 PAD scope, ISO/IEC 19795 performance testing and application/API testing measure different things.  
**Consequences:** no undifferentiated global security score in initial releases.

## ADR-004 — Local-first execution

**Status:** Proposed  
**Decision:** No project-hosted data processing or telemetry is required.  
**Reason:** voice samples and embeddings are sensitive; researchers need reproducibility and control.  
**Consequences:** filesystem artifacts and user-controlled retention in the initial release.

## ADR-005 — Filesystem storage before database storage

**Status:** Proposed  
**Decision:** Use run directories, manifests and content-addressed artifacts initially.  
**Reason:** no server/database requirement and easy portability.  
**Consequences:** design stable artifact schemas before adding optional storage backends.

## ADR-006 — Explicit plugin enablement; no sandbox claim

**Status:** Proposed  
**Decision:** plugins must be deliberately installed/enabled; in-process plugins are trusted code.  
**Reason:** Python plugin imports are not a security boundary.  
**Consequences:** show plugin metadata and permissions; consider isolated workers in a later phase.

## ADR-007 — Score-file evaluation is the first usable vertical slice

**Status:** Proposed  
**Decision:** deliver manifest validation, score/trial ingestion, metrics, provenance and reports before mandatory model inference or remote target tests.  
**Reason:** it is testable, useful to researchers and avoids coupling core reliability to large/fast-changing model stacks.  
**Consequences:** initial release can evaluate existing scores; model inference arrives as optional adapters.

## ADR-008 — Do not bundle datasets or pretrained model weights by default

**Status:** Proposed  
**Decision:** distribute adapters and download instructions; users obtain external data and checkpoints under their terms.  
**Reason:** licensing, size, provenance and privacy.  
**Consequences:** dataset/model inventory and license review become release gates.

## ADR-009 — No general-purpose voice-cloning capability

**Status:** Proposed  
**Decision:** accept authorized test fixtures and optional external adapter integrations; do not build a general voice-cloning engine into VoxRigor.  
**Reason:** the project is a security assessment framework, not an impersonation product.  
**Consequences:** synthetic-audio test provenance and use authorization must be recorded.
