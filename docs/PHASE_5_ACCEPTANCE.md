# Phase 5 Acceptance Criteria

## Initial local-only implementation gates

- [x] Protocol scope requires explicit authorization acknowledgement and rejects all non-loopback targets, DNS names, URL credentials, custom paths and fragments.
- [x] Target client disables proxy discovery and refuses redirects.
- [x] Client permits only the approved HTTP methods and fixed route allowlist.
- [x] Request count, timeout, request body and response body limits are enforced.
- [x] Reference server binds only to 127.0.0.1 and does not log request bodies, identities or tokens.
- [x] Reference accounts, challenges, sessions and enrollments are disposable in-memory fixtures.
- [x] Fixed fixture enforces challenge expiry, single use, subject binding, session revocation, object authorization, function authorization and rate limiting.
- [x] Vulnerable fixture intentionally demonstrates challenge replay, subject-binding, expiry, BOLA, BFLA and rate-limit failures.
- [x] Report statuses distinguish vulnerable, no issue observed, inconclusive, unsupported and execution error.
- [x] Reports exclude request/response payloads, Authorization headers, bearer tokens and fixture proofs.
- [x] CLI supports reference service start, scope initialization, protocol run and local demo.
- [x] Tests cover negative scope cases, fixed/vulnerable fixture behavior, request budgets and report redaction.
- [x] Ruff, formatting, strict Mypy, tests and the configured coverage gate pass on Ubuntu/Windows and Python 3.11–3.13.

## Lifecycle extension — implemented and validated

- [x] Challenge records include a server-side purpose and mismatched-purpose verification is rejected by the fixed fixture.
- [x] The reference fixture supports an enrollment re-enrollment operation with owner/admin authorization and a monotonically increasing fixture version.
- [x] Session expiry is independently tested; the vulnerable profile deliberately retains expired sessions for detection validation.
- [x] Challenge and session expiry use monotonic time in the reference fixture; runner waiting remains bounded by scope configuration.
- [x] Tests cover enrollment/re-enrollment ownership, challenge-purpose binding and session expiry.
- [x] Latest lifecycle branch-head CI passed all six combinations: Ubuntu and Windows, Python 3.11, 3.12 and 3.13. Ruff lint, Ruff format, strict Mypy and tests passed; Linux coverage was 85.58% (85% configured minimum).

The lifecycle CI run is [42593363565](https://github.com/AB772K/VoxRigor/actions/runs/42593363565). The earlier implementation run [42592810707](https://github.com/AB772K/VoxRigor/actions/runs/42592810707) also passed the same six-environment matrix. Earlier failed runs are retained in Actions history; they were intermediate commits, not the current validated branch head.

## Research and integration gates — still open

- [ ] Define a versioned target-adapter contract for other local reference services.
- [ ] Add a user-configurable API schema without allowing scope expansion or arbitrary request injection.
- [ ] Add account creation/cleanup lifecycle and documented rollback for target state changes.
- [ ] Add tests for application fallback paths and complete account-recovery workflows; the current reference fixture only models purpose-bound recovery challenges, not a full recovery channel.
- [ ] Add server-side request forgery and redirect-to-out-of-scope negative tests for future adapters.
- [ ] Define safe rate-limit profiles that avoid triggering lockouts or expensive real biometric processing.
- [ ] Integrate optional audio/model verification only through an explicit test adapter and controlled fixtures.
- [ ] Consider remote authorized targets only after a separate scope, allowlist, redirect/DNS-rebinding, consent and safety review.

A successful local fixture run does not demonstrate that a production voice-authentication system is secure. A deterministic fixture assertion is not a biometric verifier.
