# Initial Test Catalogue

**Status:** Draft 0.1 — planned tests only. No test in this catalogue is implemented or validated yet.

## 1. Test design requirements

Every test definition must specify:

- stable test ID and version;
- category and objective;
- security/reliability question being answered;
- preconditions and supported target/model capabilities;
- permitted side effects and cleanup;
- input and output schema;
- expected result semantics;
- required evidence;
- metric definitions and denominators if statistical;
- limitations and false-positive considerations;
- standards/taxonomy mapping, if verified;
- authorization and safety requirements.

## 2. First offline benchmark tests

| ID | Category | Test objective | Required evidence |
|---|---|---|---|
| DATA-001 | Dataset integrity | Validate required columns, label set, unique trial IDs and file references. | Input/accepted/rejected counts and reasons. |
| DATA-002 | Split leakage audit | Detect known speaker/source overlap across declared splits. | Overlap counts and IDs in a redacted/local artifact. |
| DATA-003 | Duplicate audit | Find exact file hashes and duplicate trial IDs. | Hash-based duplicate summary. |
| ASV-001 | Speaker verification metrics | Compute metrics from declared mated/non-mated scores and protocol. | Metric values, denominators, score semantics and threshold source. |
| PAD-001 | PAD metrics | Compute supported PAD metrics from bona-fide/attack labels and attack-species metadata. | Per-species and pooled counts/rates with threshold metadata. |
| REP-001 | Reproducibility manifest | Re-run a fixed synthetic score fixture and compare outputs. | Config hash, schema version and comparison result. |

## 3. Audio robustness and presentation tests (later)

| ID | Category | Test objective | Important boundary |
|---|---|---|---|
| AUD-ROB-001 | Audio robustness | Evaluate declared resampling conditions. | Robustness condition, not automatically an attack. |
| AUD-ROB-002 | Audio robustness | Evaluate codec/compression conditions. | Record exact codec, bitrate/profile and tool version. |
| AUD-ROB-003 | Audio robustness | Evaluate controlled background-noise conditions. | Record source/SNR and avoid claiming general real-world coverage. |
| AUD-ROB-004 | Audio robustness | Evaluate controlled reverberation/channel conditions. | Record impulse response/source/parameters. |
| PAD-PRES-001 | PAD presentation | Evaluate replay audio presented through a controlled loudspeaker/microphone capture path. | Must actually be presented at the capture device; record rig, device and environment. |
| PAD-PRES-002 | PAD presentation | Evaluate approved synthetic/converted speech fixtures when presented through the controlled capture path. | Use authorized/licensed fixtures; no bundled impersonation engine. |
| INJ-DIG-001 | Digital injection | Test a documented digital audio injection point in a reference app. | Not a PAD presentation test; report separately as sensor/application integrity. |

## 4. Authentication protocol and application tests (later)

All tests use a local/reference target and disposable test identities until remote authorized testing is explicitly designed and reviewed.

| ID | Category | Test objective | Expected secure behavior |
|---|---|---|---|
| AUTH-ENR-001 | Enrollment | Verify that only an authorized identity can enroll or replace a voice template. | Unauthorized enrollment/re-enrollment is denied and auditable. |
| AUTH-ENR-002 | Enrollment | Verify re-enrollment invalidates or appropriately supersedes prior enrollment material. | State follows the declared policy; no stale authorization remains. |
| AUTH-CHAL-001 | Challenge | Verify challenge uniqueness and binding to the relevant user/session/transaction. | Duplicate or mismatched challenge is rejected. |
| AUTH-CHAL-002 | Challenge | Verify expired challenges cannot be accepted. | Expired challenge is rejected. |
| AUTH-CHAL-003 | Challenge | Verify a one-time challenge cannot be successfully consumed more than once. | Subsequent reuse is rejected and state is consistent. |
| AUTH-REPLAY-001 | Protocol | Verify replay of a completed authentication request cannot create a new authenticated session. | Replay is rejected or idempotently handled according to the documented design. |
| AUTH-SESS-001 | Session | Verify session token rotation and binding after authentication. | Previous/anonymous session is invalidated or rotated as designed. |
| AUTH-SESS-002 | Session | Verify logout/revocation and expiration behavior. | Revoked/expired session is not accepted. |
| AUTH-FALL-001 | Fallback | Verify fallback does not silently reduce assurance or bypass required authorization. | Step-up/fallback follows the documented policy. |
| API-AUTHZ-001 | API authorization | Verify object-level authorization for enrollment records and test-user resources. | A test identity cannot access another identity's protected object. |
| API-AUTHZ-002 | API authorization | Verify function-level authorization for administrative biometric operations. | Unauthorized roles are denied. |
| API-RATE-001 | Resource controls | Verify configured rate limits and lockout controls using bounded test attempts. | Limit is enforced without causing uncontrolled account/service impact. |

## 5. Result interpretation

- `vulnerable`: the defined security failure was reproduced and evidence meets the test's proof criteria.
- `no_issue_observed`: the test completed and the expected control behavior was observed under the specified conditions; this is not proof of global security.
- `inconclusive`: evidence, sample size, target behavior or environment is insufficient/ambiguous.
- `unsupported`: target/model lacks the required capability or the test is not applicable.
- `execution_error`: the runner could not validly execute the test.

A test that cannot execute must never be recorded as `no_issue_observed`.

## 6. Severity policy

Do not assign severity solely from an attack name. Severity requires context: required preconditions, attacker position, privileges, affected identities, repeatability, impact, existing controls, compensating controls and business consequences. For application findings, a recognized scoring system may be included with the exact version and rationale; biometric benchmark rates must not be converted automatically into CVSS.
