# Standards, Taxonomies and Metrics

**Status:** Draft 0.1 — Phase 0  
**Important:** This document maps public abstracts and official guidance. It does not reproduce paid standards or establish conformance. Obtain and review applicable standards before making a standards-conformance claim.

## 1. Standards and guidance map

| Reference | Relevant scope | VoxRigor use | Important limitation |
|---|---|---|---|
| ISO/IEC 30107-1:2023 | PAD framework, terms and definitions | Vocabulary and classification of capture-device presentation attacks | Does not cover overall system-level security or attacks outside capture-device presentation. |
| ISO/IEC 30107-3:2023 | PAD performance assessment and reporting | PAD test protocol/report design and attack classification | Excludes overall system security/vulnerability assessment; covered attacks occur at the biometric capture device. |
| ISO/IEC 19792:2025 | General principles, requirements and guidance for biometric-system security evaluation | Overall biometric security evaluation context: recognition performance, PAD and privacy | Does not cover non-biometric parts such as databases or communication channels. |
| ISO/IEC 19795-1:2021 (corrected 2024) | Biometric performance testing/reporting, error and throughput rates, test protocols | Ordinary ASV performance methodology, sample reporting, bias and limitations | Explicitly excludes measurement of deliberate attempts to subvert the system, such as presentation attacks. |
| ISO/IEC DIS 19795-1, Edition 3 (2026 draft) | Proposed revision of 19795-1 | Monitor during development | Draft/enquiry status; do not treat it as a published replacement until ISO updates its status. |
| ISO/IEC 2382-37:2022 | Biometrics vocabulary | Terminology reference | Check for a newer edition/draft at release. |
| NIST SP 800-63B-4 (2025) | US federal digital identity remote-authentication guidance | Important limitation and context for digital-authentication claims | Section 3.2.3.2 says biometric comparison based on voice SHALL NOT be used within this framework. This is not a universal worldwide ban, nor a statement that all deployed commercial systems are illegal. |
| OWASP API Security Top 10:2023 | API security risks | Taxonomy for relevant target-application checks | Does not provide biometric performance or PAD methodology. |
| OWASP WSTG v4.2 | Web application testing | Authentication, authorization, session management, business logic and transport security test guidance | General web guidance; map only where relevant to a voice-authentication application. WSTG 5.0 is under development as of this snapshot. |

## 2. Layer separation — mandatory reporting rule

A single global "voice authentication security score" is not acceptable in the initial releases. The framework must report separate layers and may summarize them only with a clearly justified, versioned model that does not hide missing tests.

### 2.1 Speaker verification (ASV)

This is the comparison between a probe utterance and an enrolled speaker template/reference under a declared trial protocol.

Report, as applicable:

- False Match Rate (FMR): proportion of non-mated comparison trials incorrectly treated as matches, with the exact trial denominator stated.
- False Non-Match Rate (FNMR): proportion of mated comparison trials incorrectly treated as non-matches, with the exact trial denominator stated.
- ROC and DET curves.
- EER as a descriptive operating-point summary, not a substitute for a declared deployment operating point.
- Threshold, threshold-selection partition, score direction and calibration method.
- Per-condition/per-group results where data and sample sizes support meaningful analysis.

Do not casually equate biometric comparison error rates (FMR/FNMR) with end-to-end operational FAR/FRR. If the system exposes operational accept/reject outcomes, define the population, attack/trial type and denominator for those rates separately.

### 2.2 Presentation Attack Detection (PAD)

PAD concerns detection of a presentation attack at the biometric capture device.

Report, where the protocol and labels support it:

- APCER (Attack Presentation Classification Error Rate), with attack species/condition breakdown.
- BPCER (Bona Fide Presentation Classification Error Rate).
- Counts and denominators per attack species and bona fide condition.
- Operating threshold and how it was selected.
- Device, sensor, presentation path and test conditions.

Do not call a digitally injected audio file a presentation attack unless it was actually presented at the capture device in the sense of the applicable PAD protocol. Keep digital injection as a separate application/sensor-integrity test class. Avoid inventing one aggregate PAD score that conceals weak attack species.

### 2.3 Joint spoofing-aware speaker verification

Where a protocol evaluates both target-speaker recognition and spoofing countermeasures, use its specified joint metrics. For ASVspoof 5:

- Track 1 stand-alone deepfake detection: minDCF is primary; actDCF, Cllr and EER are secondary.
- Track 2 spoofing-aware speaker verification: a-DCF is primary; min t-DCF and t-EER are secondary.

Only report these as ASVspoof 5-compatible results when the exact trial protocol, score semantics, priors, costs and official evaluation implementation are followed. Do not apply those metrics to an unrelated application test and call it an ASVspoof result.

### 2.4 Audio robustness

Robustness tests measure changes under declared recording/channel conditions such as resampling, codec, compression, noise, reverberation and microphone/channel variation.

Report:

- baseline and transformed-condition metrics;
- absolute and relative change;
- sample counts and exclusions;
- transformation parameters and random seeds;
- whether the transformation represents an expected channel condition, a stress test or a security attack.

A model that rejects a genuine utterance after ordinary compression has a robustness/reliability weakness; that alone does not prove authentication bypass.

### 2.5 Authentication protocol and application security

These tests usually have explicit expected outcomes rather than population-level biometric rates. Report:

- test ID/version and preconditions;
- test account/role category (redacted identifier);
- operation and state transition tested;
- expected and observed status;
- response/evidence hashes and timestamps;
- whether state changed;
- reproducibility steps and remediation;
- result status and limitations.

Examples include stale challenge rejection, one-time challenge consumption, authorization of enrollment changes, session invalidation and rate-limit enforcement.

## 3. Statistical reporting requirements

- Always report denominator and class counts.
- Use confidence intervals for rates where sample size allows; choose and document a suitable method (for example, Wilson interval for a binomial proportion).
- For speaker-level datasets, do not treat all utterances as fully independent when the design clusters samples by speaker. Consider speaker-clustered bootstrap or another justified analysis.
- Threshold selection/calibration uses development data; final test data is not used to tune thresholds.
- Report missingness, exclusions and label-quality issues.
- Do not compare model metrics across different datasets/protocols as if they share the same difficulty or population.
- When results are too small for stable inference, mark the result exploratory or inconclusive.

## 4. Normative mapping policy

- Maintain a machine-readable mapping with fields: `framework_test_id`, `standard_or_taxonomy`, `edition`, `clause_reference` (only when verified from an authorized copy), `relationship` (`informed_by`, `mapped_to`, `compatible_with`), `mapping_status` and `notes`.
- Do not copy copyrighted standard text into the repository. Use identifiers, short descriptions and links to the official publisher pages.
- A mapping does not equal conformity assessment or certification.
- Re-check standards status at each tagged release.

## 5. Public references

- ISO/IEC 30107-1:2023: https://www.iso.org/standard/83828.html
- ISO/IEC 30107-3:2023: https://www.iso.org/standard/79520.html
- ISO/IEC 19792:2025: https://committee.iso.org/standard/84753.html
- ISO/IEC 19795-1:2021: https://www.iso.org/standard/73515.html
- ISO/IEC DIS 19795-1 (2026): https://www.iso.org/standard/93355.html
- ISO/IEC 2382-37:2022: https://www.iso.org/standard/73514.html
- NIST SP 800-63B-4: https://pages.nist.gov/800-63-4/sp800-63b.html
- OWASP API Security: https://owasp.org/www-project-api-security/
- OWASP WSTG v4.2: https://owasp.org/www-project-web-security-testing-guide/
- ASVspoof 5 evaluation plan: https://www.asvspoof.org/file/ASVspoof5___Evaluation_Plan_Phase2.pdf
- ASVspoof 5 metric implementations: https://github.com/asvspoof-challenge/asvspoof5/tree/main/evaluation-package
