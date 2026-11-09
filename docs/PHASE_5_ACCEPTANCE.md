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

## Lifecycle extension — implementation added; branch CI pending

- [x] Challenge records include a server-side purpose and mismatched-purpose verification is rejected by the fixed fixture.
- [x] The reference fixture supports an enrollment re-enrollment operation with owner/admin authorization and a monotonically increasing fixture version.
- [x] Session expiry is independently tested; the vulnerable profile deliberately retains expired sessions for detection validation.
- [x] Challenge and session expiry use monotonic time in the reference fixture; runner waiting remains bounded by scope configuration.

## Research and integration gates — still open

- [ ] Define a versioned target-adapter contract for other local reference services.
- [ ] Add a user-configurable API schema without allowing scope expansion or arbitrary request injection.
- [ ] Add account creation/cleanup lifecycle and documented rollback for target state changes.
- [x] Add tests for enrollment/re-enrollment ownership, challenge purpose binding and session expiry.
- [ ] Add tests for application fallback paths and complete account-recovery workflows; the current reference fixture only models purpose-bound recovery challenges, not a full recovery channel.
- [ ] Add server-side request forgery and redirect-to-out-of-scope negative tests for future adapters.
- [ ] Define safe rate-limit profiles that avoid triggering lockouts or expensive real biometric processing.
- [ ] Integrate optional audio/model verification only through an explicit test adapter and controlled fixtures.
- [ ] Consider remote authorized targets only after a separate scope, allowlist, redirect/DNS-rebinding, consent and safety review.

The initial Phase 5 slice passed CI run 42588833761 on Ubuntu and Windows with Python 3.11, 3.12 and 3.13. The lifecycle extension is being validated in a new branch-head CI run; do not treat its gates as passed until that run completes.

A successful local fixture run does not demonstrate that a production voice-authentication system is secure. A deterministic fixture assertion is not a biometric verifier.
