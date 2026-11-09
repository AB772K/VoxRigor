# Phase 5 — Local Reference Application and Protocol/API Security Engine

**Status:** Initial local-only protocol engine implemented on the Phase 5 branch. Cross-platform CI and full acceptance review are in progress.

## Objective

Assess security properties around a voice-authentication application's protocol and API workflow without requiring a production identity provider, customer account, cloud service, microphone or real biometric model.

The first slice is a deliberately small HTTP reference service plus a bounded assessment client. It exercises challenge state, session lifecycle, object authorization, function authorization and resource limits. The reference service uses a deterministic synthetic test assertion to stand in for a biometric verifier. It is not speaker recognition, presentation-attack detection, liveness verification or evidence of biometric accuracy.

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
voxrigor protocol init-scope --target-url http://127.0.0.1:8765 --output .\protocol-scope.json
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
| PROTOCOL-CHALLENGE-EXPIRY | Challenge expiry | Expired challenge is rejected, subject to the scope's bounded wait budget |
| API-OBJECT-AUTHORIZATION | Enrollment object-level authorization | Alice cannot read Bob's enrollment |
| API-FUNCTION-AUTHORIZATION | Administrative function-level authorization | Regular user cannot access admin audit function |
| PROTOCOL-SESSION-REVOCATION | Logout and session invalidation | A logged-out token is rejected by protected endpoints |
| API-RESOURCE-CONSUMPTION | Challenge creation rate limit | Repeated challenge creation is rate-limited |

The vulnerable reference profile deliberately omits challenge single-use/subject-binding/expiry enforcement, enrollment ownership checks, admin role checks and challenge rate limiting. It retains session revocation so the suite also demonstrates a control that remains effective in both profiles.

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

## Current limitations

- Only the bundled reference API contract is tested; a general-purpose third-party application adapter is not yet implemented.
- All targets must be loopback IP literals; remote authorized-target testing is deferred.
- The deterministic fixture assertion does not verify voice, speaker identity, liveness, PAD or deepfake resistance.
- Enrollment is represented by in-memory fixture records, not real biometric templates.
- The suite does not test password storage, MFA provider integrations, account recovery channels, OAuth/OIDC, WebAuthn, telephony or distributed session stores.
- Challenge expiry testing becomes inconclusive when the target's declared expiry exceeds the operator's wait budget.
- The fixed and vulnerable fixtures are small examples, not complete implementations of a production authentication service.
