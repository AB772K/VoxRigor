# VoxRigor Threat Model

**Status:** Draft 0.1 — Phase 0  
**Method:** Asset, trust-boundary and abuse-case analysis; STRIDE is used as a prompt, not as a certification.

## 1. Security objectives

VoxRigor must protect the operator's environment and the confidentiality/integrity of biometric test data while ensuring test results are not misleading. It must prevent accidental or unauthorized testing outside a declared scope and avoid treating untrusted models, plugins or datasets as safe code.

## 2. Assets

| Asset | Security property | Example risk |
|---|---|---|
| Raw voice samples | Confidentiality, integrity, lawful use | Exposure of biometric or personal data |
| Biometric templates/embeddings | Confidentiality, integrity | Identity inference or misuse |
| Dataset labels and split metadata | Integrity | Corrupted metrics, leakage or false conclusions |
| Model weights/checkpoints | Integrity, provenance | Malicious or compromised checkpoint execution |
| Target credentials and tokens | Confidentiality | Account compromise through logs/configs |
| Scope manifest | Integrity | Testing an unauthorized host or account |
| Test definitions/plugins | Integrity, availability | Malicious or destructive plugin behavior |
| Evidence and reports | Confidentiality, integrity | Disclosure of PII or fabricated findings |
| Run configuration and provenance | Integrity, availability | Unreproducible or misattributed results |
| Developer machine and CI runner | Confidentiality, integrity, availability | Code execution, resource exhaustion or secret theft |

## 3. Trust boundaries

1. **Operator ↔ VoxRigor CLI:** command-line arguments, config files and environment variables are untrusted input.
2. **VoxRigor ↔ Target application:** HTTP or other target communication crosses a network boundary and may affect account state.
3. **VoxRigor ↔ Dataset files:** metadata and audio files may be malformed, mislabeled, unexpectedly large or maliciously crafted.
4. **VoxRigor ↔ Model/checkpoint:** model packages and weights may have different licenses, provenance and serialization risks.
5. **VoxRigor ↔ Plugins:** plugins are third-party code and may execute with the privileges of the process unless isolated.
6. **VoxRigor ↔ Report consumer:** exported files may contain sensitive information and must be treated as controlled artifacts.
7. **Developer ↔ CI/package registry:** build dependencies, release credentials and package publication channels are supply-chain assets.

## 4. Threat actors and failure sources

- A malicious or compromised plugin author.
- A malicious dataset or model artifact provider.
- An unauthorized operator attempting to use the tool against an external service.
- An attacker who can influence a target API response or test input.
- An accidental operator error, such as an incorrect host, account or dataset split.
- A compromised dependency, CI action or package release credential.
- A well-intentioned researcher who misinterprets a metric or overstates a result.

## 5. Main abuse cases and mitigations

| ID | Abuse case | Impact | Planned mitigation |
|---|---|---|---|
| TM-01 | Operator points a test at an unowned/public target | Unauthorized activity | Loopback/reference target default; explicit scope manifest; remote access opt-in; allowlist enforcement and audit record |
| TM-02 | Test loops cause lockouts, account damage or service load | Availability/account impact | Disposable test accounts; request caps; rate limits; bounded concurrency/timeouts; non-destructive default profile |
| TM-03 | Audio or metadata parser is given malformed/oversized data | Crash/resource exhaustion | Size/duration limits; strict format validation; streaming where feasible; isolated parser tests |
| TM-04 | Malicious model checkpoint is loaded | Code execution or memory corruption | Trusted source allowlist, hash verification, supported-format policy, patched framework versions, no automatic remote checkpoint loading |
| TM-05 | Plugin executes arbitrary code | Host compromise/data theft | Explicit plugin installation/enablement; provenance and version display; no claim of sandboxing; later consider separate process/container with narrow IPC |
| TM-06 | Dataset split leaks speakers/source utterances | Invalid research results | Split provenance, group overlap checks, duplicate/source hash checks, explicit limitation when metadata absent |
| TM-07 | Report leaks voice, identity or API secret | Privacy/security breach | Local-only default; redaction; no raw audio embedding; controlled evidence directory; retention configuration |
| TM-08 | Metric or score direction is interpreted incorrectly | False security conclusion | Typed metric metadata; explicit positive class/score direction; reference fixtures; protocol-specific metric profile |
| TM-09 | Threshold tuned against test data | Inflated performance | Threshold selection only on development/calibration partition; freeze and record operating point |
| TM-10 | A missing/inconclusive test is reported as passed | False assurance | Strict result-state model; separate execution errors; report denominators and unsupported tests |
| TM-11 | CI dependency/action is compromised | Supply-chain compromise | Pin third-party actions by full commit SHA; dependency lock; SBOM; least-privilege CI tokens; secret scanning |
| TM-12 | Test accidentally records bystanders or non-consenting voices | Privacy harm | Consent and data provenance requirements; no ambient recording by default; test-specific retention and deletion |

## 6. Scope and authorization model

### Default mode

- Offline score/dataset evaluation.
- No target network requests.
- No microphone capture.
- No outbound telemetry.

### Local target mode

- Target address must resolve to an explicit loopback or isolated lab target by default.
- Test accounts and synthetic fixtures are required.
- Test suite must state which state changes it may perform.

### Remote authorized mode (later release)

- Disabled by default.
- Requires a scope manifest listing exact hostnames/addresses, permitted ports, test window, account IDs/roles, contact and stop conditions.
- The operator must affirm authorization.
- DNS resolution and redirects must not escape the allowlist; redirects to unlisted hosts must be refused.
- Request count, concurrency, duration and retry limits must be enforced.
- No destructive tests, brute-force testing, account takeover attempts against real users or uncontrolled telephony in the initial product.

A checkbox or CLI acknowledgement is not legal authorization. The operator remains responsible for permission and scope.

## 7. Privacy model

- Do not collect voice recordings unless required by the specific declared test.
- Prefer synthetic, public-domain/appropriately licensed or consented test audio.
- Do not store raw audio in ordinary logs or reports.
- Record hashes and metadata where possible instead of copying raw audio into every artifact.
- Provide explicit artifact retention/deletion controls.
- Never upload data to a project server; future integrations must be opt-in and documented.
- Treat speaker embeddings as sensitive biometric-derived information, not anonymous data.

## 8. Model and plugin supply-chain rules

A model card and a package license do not prove that a particular checkpoint is safe to deserialize. The framework must not accept arbitrary remote checkpoints by URL. Model adapters must declare code source, checkpoint source, checkpoint hash, license, framework versions and preprocessing requirements. A plugin running inside the main Python process is trusted code with that process's permissions; Python entry points do not create a sandbox.

A January 2026 PyTorch security advisory documented a checkpoint-loading vulnerability affecting versions up to 2.9.1 even with `weights_only=True`; this illustrates why that flag alone cannot be treated as a universal boundary. Release policy must check current upstream advisories and patched versions at implementation time.

## 9. Residual risks

- A researcher can still export or misuse data outside the tool.
- A local target can be misconfigured to reach external resources.
- Hardware audio presentation tests can be affected by room, speaker, microphone and device differences.
- A test suite can miss unknown attack classes.
- Dataset metadata may be incomplete or wrong.
- A statistically stable result may still fail to generalize to a deployment population.

Residual risks must be listed in every relevant report and project release notes.
