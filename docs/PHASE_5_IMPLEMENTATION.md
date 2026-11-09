# Phase 5 — Local Reference Application and Protocol/API Security Engine

**Status:** Initial local-only protocol engine and lifecycle extension validated in the six-environment CI matrix. General target adapters, complete fallback paths and account-recovery workflows remain future work.

## Objective

Assess security properties around a voice-authentication application's protocol and API workflow without requiring a production identity provider, customer account, cloud service, microphone or real biometric model.

The first slice is a deliberately small HTTP reference service plus a bounded assessment client. The lifecycle extension additionally checks challenge-purpose binding, re-enrollment ownership and server-side session expiry. It exercises challenge state, session lifecycle, object authorization, function authorization and resource limits. The reference service uses a deterministic synthetic test assertion to stand in for a biometric verifier. It is not speaker recognition, presentation-attack detection, liveness verification or evidence of biometric accuracy.

## Safety boundary

- The scope manifest requires explicit authorization acknowledgement.
- The target must be an explicit loopback IP literal and port, such as http://127.0.0.1:8765. DNS names, hostnames, public IPs, proxies, custom URL paths and remote targets are not supported by this first release.
- HTTP proxy discovery is disabled. Redirects are never followed.
- Only the fixed set of protocol routes and GET/POST methods used by the checks is allowed.
- Each assessment is capped at 64 requests; each request has a timeout no greater than three seconds; request bodies are capped at 16 KiB; response bodies are capped at 32 KiB.
- Challenge-expiry waiting is bounded by the explicit scope budget (at most ten seconds).
- The reference service always binds to 127.0.0.1. Its accounts, challenges, sessions and enrollment fixtures are in-memory and disappear on shutdown.
- The intentionally vulnerable profile exists only for local scanner validation. Never expose it to a network interface.
- No arbitrary payload fuzzing, brute-force behavior, destructive operations, external telephony, microphone capture or raw audio upload is included.

## Commands

Start a fixed local reference service:

```powershell
voxrigor protocol serve --fixture-profile fixed --port 8765 --challenge-ttl-seconds 3
```

Create a local scope file:

```powershell
voxrigor protocol init-scope --target-url http://127.0.0.1:8765 --i-authorize-local-target --output .\protocol-scope.json
```

Run the bounded checks:

```powershell
voxrigor protocol run --scope .\protocol-scope.json --output .\runs\protocol-fixed
```

Demonstrate known failures using a self-starting ephemeral fixture:

```powershell
voxrigor protocol demo --fixture-profile vulnerable --output .\runs\protocol-vulnerable
```

The demo command starts a temporary reference service on an OS-assigned loopback port, executes the checks and shuts the service down.

## Initial checks

| Check ID | Control tested | Expected fixed behavior |
|---|---|---|
| PROTOCOL-CHALLENGE-REPLAY | One-time challenge consumption | Reuse of a successful challenge is rejected |
| PROTOCOL-CHALLENGE-SUBJECT-BINDING | Challenge bound to subject | A challenge issued for Alice cannot verify Bob |
| PROTOCOL-CHALLENGE-PURPOSE-BINDING | Challenge purpose binding | An enrollment/recovery challenge cannot be reused for authentication |
| PROTOCOL-CHALLENGE-EXPIRY | Challenge expiry | Expired challenge is rejected, subject to the scope's bounded wait budget |
| API-OBJECT-AUTHORIZATION | Enrollment object-level authorization | Alice cannot read Bob's enrollment |
| API-REENROLLMENT-OWNERSHIP | Re-enrollment object ownership | Alice cannot replace Bob's enrollment |
| API-FUNCTION-AUTHORIZATION | Administrative function-level authorization | Regular user cannot access admin audit function |
| PROTOCOL-SESSION-REVOCATION | Logout and session invalidation | A logged-out token is rejected by protected endpoints |
| PROTOCOL-SESSION-EXPIRY | Session expiry | An expired session token is rejected by protected endpoints |
| API-RESOURCE-CONSUMPTION | Challenge creation rate limit | Repeated challenge creation is rate-limited |

The vulnerable reference profile deliberately omits challenge single-use/subject/purpose/expiry enforcement, enrollment ownership checks, admin role checks, session expiry enforcement and challenge rate limiting. It retains session revocation so the suite also demonstrates a control that remains effective in both profiles.

Challenge expiry and session expiry use monotonic process clocks in the reference fixture. Runner waits never exceed the scope's explicit test-wait budget. If the service declares a lifetime longer than that budget, the finding is Inconclusive rather than waiting longer.

The enrollment fixture supports a narrowly-scoped re-enrollment operation for the Bob test record. A normal user can update only their own record; an administrator can update another record. The scanner attempts a cross-subject update as Alice and records only the HTTP result metadata. It does not capture or upload real biometric templates.

## Scope manifest

The scope file contains no account password or bearer token. It is strict JSON, rejects unknown fields, and must include the authorization acknowledgement:

```json
{
  "schema_version": "0.1",
  "target_url": "http://127.0.0.1:8765",
  "target_label": "Local voice-auth reference",
  "authorized": true,
  "request_budget": 32,
  "timeout_seconds": 2.0,
  "max_test_wait_seconds": 5.0
}
```

## Evidence and findings

Reports include a run identifier, target label, UTC timestamp, request count, check status, HTTP status, elapsed time and response size. They do not include request or response payloads, Authorization headers, bearer tokens, fixture proofs, raw audio or embeddings.

Findings use the framework result states:
- vulnerable
- no_issue_observed
- inconclusive
- unsupported
- execution_error

no_issue_observed means only that a particular check did not demonstrate the condition. It is not proof that the endpoint, service or overall voice-authentication system is secure.

## Standards mapping

The first test catalogue is informed by:
- [OWASP API Security Top 10:2023](https://api-security.owasp.org/editions/2023/en/0x11-t10/), especially Broken Object Level Authorization, Broken Authentication, Unrestricted Resource Consumption and Broken Function Level Authorization.
- [OWASP Web Security Testing Guide](https://wstg.owasp.org/latest/), especially Authentication, Authorization, Session Management and API Testing.
- [OWASP ASVS 5.0.0](https://asvs.owasp.org/), as a technical-control verification reference.

This is a mapping for test design, not an assertion of OWASP verification or compliance.

## Validation status

The initial Phase 5 implementation passed CI run 42588833761. The lifecycle extension passed CI run 42592810707 on Ubuntu and Windows with Python 3.11, 3.12 and 3.13. All six jobs passed Ruff lint, Ruff formatting, strict Mypy and the full test suite. Each Linux job completed 201 tests and 85.58% coverage against the 85% gate. The new regression tests cover challenge-purpose binding, enrollment re-enrollment ownership/versioning and session expiry in fixed and intentionally vulnerable fixtures. These results validate the local protocol fixture; they do not establish production biometric or system security.

## Current limitations

- Only the bundled reference API contract is tested; a general-purpose third-party application adapter is not yet implemented.
- All targets must be loopback IP literals; remote authorized-target testing is deferred.
- The deterministic fixture assertion does not verify voice, speaker identity, liveness, PAD or deepfake resistance.
- Enrollment is represented by in-memory fixture records, not real biometric templates.
- The suite does not test password storage, MFA provider integrations, account recovery channels, OAuth/OIDC, WebAuthn, telephony or distributed session stores.
- Challenge expiry testing becomes inconclusive when the target's declared expiry exceeds the operator's wait budget.
- The fixed and vulnerable fixtures are small examples, not complete implementations of a production authentication service.
