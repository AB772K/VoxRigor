# VoxRigor

**Open-source voice authentication security testing and evaluation framework**

Research openly. Test rigorously. Report honestly.

> **Project status:** Phase 0 — research, requirements definition and architecture design. VoxRigor is not yet an implemented or validated security testing product. Features described in this repository are planned unless explicitly marked as implemented.

## About

I am developing VoxRigor as an independent security researcher to help fellow security researchers, biometric researchers, developers and security engineers examine the security and reliability of voice-authentication systems.

Voice authentication is not just a speaker-recognition model. Its security depends on the full chain: enrollment, reference-template handling, audio capture, presentation-attack detection (PAD), speaker verification, challenge-response logic, APIs, session management, recovery and operational controls.

VoxRigor aims to provide a local-first, extensible and reproducible framework for evaluating these layers through documented test cases, model and dataset adapters, authorized target-application adapters, evidence-backed results and machine-readable reports.

## Project objectives

- Evaluate speaker-verification systems using clearly defined biometric performance protocols.
- Evaluate presentation-attack detection at the capture boundary using controlled, documented test conditions.
- Measure robustness to audio-channel and recording-condition changes without confusing ordinary robustness failures with security attacks.
- Assess authentication protocol and application workflows, including enrollment, challenge freshness, replay resistance, session lifecycle and recovery.
- Support model-, dataset- and target-application adapters so researchers are not locked to one vendor or model.
- Preserve experimental provenance: dataset version, sample accounting, configuration, model/checkpoint hashes, software versions, seeds and result-schema version.
- Produce evidence-backed reports that distinguish a reproduced finding from an inconclusive or unsupported test.
- Keep biometric data local by default and avoid collecting or transmitting voice recordings to a project-operated service.

## What VoxRigor is — and is not

**It is intended to be:** an open-source research and security-assessment framework for authorized evaluation of voice-biometric systems and the applications that use them.

**It is not intended to be:** a voice-cloning product, a general-purpose deepfake generator, a general web vulnerability scanner, a voice-agent conversational QA platform, a biometric certification authority, or a guarantee that a tested system is secure or compliant with any regulation or standard.

## Planned assessment layers

1. Speaker verification (ASV): comparison-score evaluation and operating-point analysis.
2. Presentation attack detection (PAD): testing of attacks presented at the biometric capture device.
3. Audio robustness: condition-specific evaluation under transformations such as codec changes, noise and reverberation.
4. Authentication protocol: challenge lifecycle, freshness, replay controls and enrollment/session workflows.
5. Application/API security: authorization, authentication, resource limits and sensitive workflow protections.
6. End-to-end evaluation: evidence-linked analysis of interactions between the preceding layers.

These layers will be reported separately. A PAD result does not establish application security; a model benchmark does not establish end-to-end authentication security.

## Development principles

- **Evidence before severity:** a finding requires a defined test, observable evidence and reproducible conditions.
- **Honest uncertainty:** results include `vulnerable`, `no_issue_observed`, `inconclusive`, `unsupported` and `execution_error` states.
- **Reproducibility:** no silent dataset filtering, undocumented threshold tuning or untracked model weights.
- **Privacy by default:** local processing, explicit artifact retention and redaction of secrets and personal data.
- **Safe operation:** only owned or explicitly authorized targets; conservative defaults and bounded tests.
- **Modularity:** optional machine-learning dependencies; documented adapter and plugin contracts.
- **No unsupported compliance claims:** mappings to standards are informative and versioned, not certifications.

## Current roadmap

See [`docs/ROADMAP.md`](docs/ROADMAP.md). Phase 0 documents are being prepared before major implementation begins.

## Responsible use

VoxRigor must only be used against systems and data that the operator owns or is explicitly authorized to assess. Do not use real customer voice recordings or biometric templates without a lawful basis, informed authorization and appropriate safeguards. Do not use the project to impersonate real people, bypass third-party authentication, or conduct tests outside an agreed scope.

## Licensing

The original VoxRigor source code and documentation are intended to be distributed under Apache License 2.0. Third-party datasets, pretrained models, model weights, test fixtures and dependencies retain their own licenses and terms. See [`docs/DATASET_AND_MODEL_POLICY.md`](docs/DATASET_AND_MODEL_POLICY.md).

## Contributing

The repository is in the specification stage. Contributions are welcome after the initial architecture and contribution rules are finalized. Please open an issue before proposing a major feature so that scope, methodology, licensing and safety can be reviewed.
