# VoxRigor Project Charter

**Document status:** Draft 0.1  
**Prepared:** 2026-11-07  
**Project owner:** AB772K  
**Repository:** https://github.com/AB772K/VoxRigor

## 1. Mission

VoxRigor is an open-source, local-first framework for reproducible security evaluation of voice-biometric verification systems and the authentication applications that use them.

The project is being developed by an independent security researcher for fellow security researchers, biometric researchers, developers and product-security engineers. It aims to reduce the amount of bespoke infrastructure required to run carefully specified experiments, compare systems under declared conditions, validate authentication controls and share reproducible evidence.

## 2. Problem statement

Voice-authentication security is a system problem, not a single-model classification problem. An application may use speaker verification and PAD while also depending on enrollment, challenge-response, sensor integrity, an API, session management and account-recovery controls. A strong anti-spoofing model cannot compensate for a replayable challenge or an authorization flaw. Conversely, degraded recognition under codec changes may be a reliability issue rather than an exploitable security weakness.

Existing research platforms and commercial offerings address meaningful parts of this space. VoxRigor must therefore avoid claiming that it invented voice-biometric security testing. Its proposed contribution is a transparent, extensible and independently reproducible open-source workflow that represents and reports different evaluation layers without conflating their methodologies.

## 3. Intended users

- Offensive-security and product-security researchers conducting authorized assessments.
- Speaker-recognition and biometric researchers.
- PAD and synthetic-speech detection researchers.
- Developers building voice-authentication systems.
- Security teams validating biometric authentication controls.
- Academic teams seeking reproducible evaluation pipelines.

## 4. Product outcomes

A user should eventually be able to:

1. Create a project with a versioned manifest and explicit scope.
2. Register a dataset and validate its metadata, integrity and split provenance.
3. connect a supported speaker-verification or PAD model through a documented adapter.
4. Execute a versioned test suite under a declared protocol.
5. Evaluate an authorized local/reference authentication application through a target adapter.
6. Review each result, evidence item, limitation and result status.
7. Export a reproducible HTML/JSON report.
8. Extend the framework with a separately installed adapter or test plugin.

## 5. Proposed differentiators

These are hypotheses to validate, not claims of proven novelty:

- **Cross-layer test representation:** distinct but linkable model, capture/PAD, audio-condition and application-protocol tests.
- **Reproducibility as a first-class feature:** manifests, content hashes, exact sample accounting, software/model provenance and versioned test definitions.
- **Open adapter architecture:** researchers can reuse their own models, datasets and reference applications.
- **Evidence-first reporting:** a finding cannot be asserted solely because a model score or HTTP response looks unusual.
- **Local-first privacy model:** no project-hosted processing or telemetry is required.
- **Open research workflows:** public test specifications and reports can be independently examined and reproduced.

A literature review and user interviews are required before describing these as market gaps or original research contributions.

## 6. Product boundaries

### In scope

- Speaker-verification performance evaluation.
- PAD evaluation in clearly defined capture-device presentation scenarios.
- Audio robustness experiments under documented conditions.
- Authorized protocol and API security checks for voice-authentication workflows.
- Dataset/model adapter interfaces and provenance tracking.
- Evidence management and research reporting.

### Out of scope for the initial product

- Creating or distributing a general-purpose voice-cloning or impersonation engine.
- Generating targeted impersonation audio of real people.
- Testing arbitrary public targets or phone numbers.
- Uncontrolled live telephony, contact-center or third-party production tests.
- General conversational voice-agent quality assurance or speech-to-text benchmarking as a primary purpose.
- Replacing a formal accredited biometric evaluation or security certification.
- Making compliance decisions on behalf of NIST, ISO, regulators or customers.

## 7. Initial product strategy

The first usable release should be an offline evaluation vertical slice: ingest a declared trial/score dataset, validate sample accounting, compute appropriately selected metrics, preserve configuration and provenance, and generate an evidence-linked report. Optional model adapters can then produce scores for that same evaluation interface.

Authorized target-application and protocol testing will follow once scope enforcement, test-account handling, safe defaults and the reference application are implemented and tested.

## 8. Success criteria

The project should not use stars or downloads as its only success measure. Early success means:

- An independent researcher can install and run a documented offline example without assistance.
- A benchmark run can be reproduced from its manifest and declared dependencies.
- Metrics agree with reference implementations on fixed test fixtures within documented numerical tolerance.
- Invalid inputs, missing samples and execution failures are surfaced rather than silently discarded.
- Target testing refuses out-of-scope targets by default.
- Reports state exact test conditions and limitations.
- External researchers can implement a plugin using the published interface and test suite.
- At least one external user can reproduce a reported result and submit useful feedback.

## 9. Non-goals and claims discipline

VoxRigor will not claim to be the first, only, most accurate or fully comprehensive voice-authentication security platform without evidence. It will not claim a system is secure merely because the test suite did not find a weakness. It will not claim ISO/NIST compliance because a metric or standard mapping is present.

## 10. Open questions for Phase 0 closure

- Which narrowly defined use case will form the first public release?
- Which ASVspoof protocols can be supported without violating dataset restrictions?
- Which existing libraries can be integrated rather than duplicated?
- What is the precise plugin trust model?
- Which Python versions and optional dependency combinations will be supported by CI?
- What minimum evidence must accompany a vulnerability finding?
- Which metrics can be independently validated against official implementations?
- What external user group will review the first alpha?
