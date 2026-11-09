"""Protocol/API security checks with bounded scope and redacted evidence."""

from __future__ import annotations

import tempfile
import time
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from voxrigor.protocol.client import HttpResult, ScopedHttpClient
from voxrigor.protocol.errors import ProtocolError
from voxrigor.protocol.reference import fixture_proof
from voxrigor.protocol.scope import ProtocolScope


class CheckStatus(StrEnum):
    VULNERABLE = "vulnerable"
    NO_ISSUE_OBSERVED = "no_issue_observed"
    INCONCLUSIVE = "inconclusive"
    UNSUPPORTED = "unsupported"
    EXECUTION_ERROR = "execution_error"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProtocolFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    check_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    status: CheckStatus
    severity: Severity
    summary: str = Field(min_length=1, max_length=600)
    recommendation: str = Field(min_length=1, max_length=600)
    evidence: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ProtocolReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "0.1"
    run_id: str
    generated_at: datetime
    framework_version: str
    target_label: str
    target_url: str
    mode: str = "loopback_only"
    request_count: int = Field(ge=0)
    findings: list[ProtocolFinding]
    warnings: list[str] = Field(default_factory=list)


def _evidence(route: str, result: HttpResult) -> dict[str, str | int | float | bool | None]:
    """Keep only response metadata; never include tokens, request bodies or response payloads."""
    return {
        "route": route,
        "http_status": result.status_code,
        "elapsed_ms": round(result.elapsed_ms, 3),
        "response_bytes": result.response_bytes,
    }


def _challenge(client: ScopedHttpClient, subject_id: str) -> tuple[HttpResult, str, str]:
    result = client.request("POST", "/v1/challenges", payload={"subject_id": subject_id})
    challenge_id = result.payload.get("challenge_id")
    nonce = result.payload.get("nonce")
    if result.status_code != 201 or not isinstance(challenge_id, str) or not isinstance(nonce, str):
        raise ProtocolError("Target did not issue a usable protocol challenge")
    return result, challenge_id, nonce


def _verify(
    client: ScopedHttpClient,
    challenge_id: str,
    subject_id: str,
    nonce: str,
) -> HttpResult:
    return client.request(
        "POST",
        "/v1/verify",
        payload={
            "challenge_id": challenge_id,
            "subject_id": subject_id,
            "proof": fixture_proof(subject_id, nonce),
        },
    )


def _session(client: ScopedHttpClient, subject_id: str) -> str:
    _, challenge_id, nonce = _challenge(client, subject_id)
    result = _verify(client, challenge_id, subject_id, nonce)
    token = result.payload.get("access_token")
    if result.status_code != 200 or not isinstance(token, str):
        raise ProtocolError("Target did not issue a disposable reference-test session")
    return token


def _finding(
    check_id: str,
    title: str,
    status: CheckStatus,
    severity: Severity,
    summary: str,
    recommendation: str,
    evidence: dict[str, str | int | float | bool | None] | None = None,
) -> ProtocolFinding:
    return ProtocolFinding(
        check_id=check_id,
        title=title,
        status=status,
        severity=severity,
        summary=summary,
        recommendation=recommendation,
        evidence=evidence or {},
    )


def run_protocol_assessment(scope: ProtocolScope, *, framework_version: str) -> ProtocolReport:
    """Run non-destructive protocol checks against the declared loopback target only."""

    client = ScopedHttpClient(scope)
    findings: list[ProtocolFinding] = []
    warnings = [
        "This profile accepts a deterministic fixture assertion. It tests protocol state and API controls, not speaker recognition or presentation-attack detection.",
        "The target is restricted to a loopback IP literal. Remote targets and DNS names are unsupported.",
        "no_issue_observed means only that this test did not demonstrate the condition; it is not a security guarantee.",
    ]

    try:
        health = client.request("GET", "/health")
        if health.status_code != 200 or health.payload.get("service") != "voxrigor-reference":
            raise ProtocolError("Target is not the expected VoxRigor reference protocol service")
        findings.append(
            _finding(
                "PROTOCOL-HEALTH",
                "Reference service identity",
                CheckStatus.NO_ISSUE_OBSERVED,
                Severity.INFO,
                "The target returned the expected local reference-service identity.",
                "Keep the reference endpoint isolated and use disposable test accounts.",
                _evidence("/health", health),
            )
        )

        # A challenge that has been consumed must not issue another session.
        _, challenge_id, nonce = _challenge(client, "alice")
        first = _verify(client, challenge_id, "alice", nonce)
        if first.status_code != 200:
            raise ProtocolError(
                "Could not establish the first disposable session for replay testing"
            )
        replay = _verify(client, challenge_id, "alice", nonce)
        if replay.status_code == 200:
            replay_status = CheckStatus.VULNERABLE
            replay_summary = "The same challenge response was accepted more than once."
        elif replay.status_code in {409, 410}:
            replay_status = CheckStatus.NO_ISSUE_OBSERVED
            replay_summary = "The repeated challenge response was rejected."
        else:
            replay_status = CheckStatus.INCONCLUSIVE
            replay_summary = "The target returned an unexpected response to the repeated challenge."
        findings.append(
            _finding(
                "PROTOCOL-CHALLENGE-REPLAY",
                "One-time challenge enforcement",
                replay_status,
                Severity.HIGH,
                replay_summary,
                "Bind challenges to one subject, expire them, and consume them atomically after a verification attempt.",
                _evidence("/v1/verify", replay),
            )
        )

        # A challenge created for Alice must not authorize Bob.
        _, binding_id, binding_nonce = _challenge(client, "alice")
        binding = _verify(client, binding_id, "bob", binding_nonce)
        if binding.status_code == 200:
            binding_status = CheckStatus.VULNERABLE
            binding_summary = (
                "A challenge issued for one subject was accepted for a different subject."
            )
        elif binding.status_code in {403, 404, 409, 410}:
            binding_status = CheckStatus.NO_ISSUE_OBSERVED
            binding_summary = "The cross-subject challenge use was rejected."
        else:
            binding_status = CheckStatus.INCONCLUSIVE
            binding_summary = (
                "The target returned an unexpected response to cross-subject challenge use."
            )
        findings.append(
            _finding(
                "PROTOCOL-CHALLENGE-SUBJECT-BINDING",
                "Challenge-to-subject binding",
                binding_status,
                Severity.HIGH,
                binding_summary,
                "Bind the challenge identifier and nonce to the intended subject and authentication purpose on the server.",
                _evidence("/v1/verify", binding),
            )
        )

        # Do not exceed the operator's explicit time budget waiting for expiry.
        expiry_challenge, expiry_id, expiry_nonce = _challenge(client, "charlie")
        ttl_value = expiry_challenge.payload.get("expires_in")
        wait_seconds = float(ttl_value) + 0.05 if isinstance(ttl_value, (int, float)) else None
        if wait_seconds is not None and 0 <= wait_seconds <= scope.max_test_wait_seconds:
            time.sleep(wait_seconds)
            expired = _verify(client, expiry_id, "charlie", expiry_nonce)
            if expired.status_code == 200:
                expiry_status = CheckStatus.VULNERABLE
                expiry_summary = "A challenge was accepted after its declared expiry interval."
            elif expired.status_code in {409, 410}:
                expiry_status = CheckStatus.NO_ISSUE_OBSERVED
                expiry_summary = "The expired challenge was rejected."
            else:
                expiry_status = CheckStatus.INCONCLUSIVE
                expiry_summary = (
                    "The target returned an unexpected response for an expired challenge."
                )
            findings.append(
                _finding(
                    "PROTOCOL-CHALLENGE-EXPIRY",
                    "Challenge expiration",
                    expiry_status,
                    Severity.HIGH,
                    expiry_summary,
                    "Enforce server-side challenge expiry using a trusted server clock.",
                    _evidence("/v1/verify", expired),
                )
            )
        else:
            findings.append(
                _finding(
                    "PROTOCOL-CHALLENGE-EXPIRY",
                    "Challenge expiration",
                    CheckStatus.INCONCLUSIVE,
                    Severity.MEDIUM,
                    "The target-reported challenge lifetime exceeds the configured test wait budget; the runner did not wait for expiry.",
                    "Perform an approved expiry test with a declared test window rather than weakening the time budget.",
                    {
                        "route": "/v1/challenges",
                        "reported_expires_in": (
                            float(ttl_value) if isinstance(ttl_value, (int, float)) else None
                        ),
                        "max_wait_seconds": scope.max_test_wait_seconds,
                    },
                )
            )

        alice_token = _session(client, "alice")
        enrollment = client.request(
            "GET",
            "/v1/enrollments/enroll-bob",
            bearer_token=alice_token,
        )
        if enrollment.status_code == 200:
            bola_status = CheckStatus.VULNERABLE
            bola_summary = "Alice could read Bob's enrollment object."
        elif enrollment.status_code in {403, 404}:
            bola_status = CheckStatus.NO_ISSUE_OBSERVED
            bola_summary = "Cross-subject access to Bob's enrollment object was denied."
        else:
            bola_status = CheckStatus.INCONCLUSIVE
            bola_summary = (
                "The target returned an unexpected response to the enrollment authorization test."
            )
        findings.append(
            _finding(
                "API-OBJECT-AUTHORIZATION",
                "Enrollment object-level authorization",
                bola_status,
                Severity.HIGH,
                bola_summary,
                "Derive the owner from the authenticated session and authorize every object lookup server-side.",
                _evidence("/v1/enrollments/{enrollment_id}", enrollment),
            )
        )

        admin = client.request("GET", "/v1/admin/audit", bearer_token=alice_token)
        if admin.status_code == 200:
            admin_status = CheckStatus.VULNERABLE
            admin_summary = "A regular user could call the administrative audit endpoint."
        elif admin.status_code in {403, 404}:
            admin_status = CheckStatus.NO_ISSUE_OBSERVED
            admin_summary = "The administrative function was denied to a regular user."
        else:
            admin_status = CheckStatus.INCONCLUSIVE
            admin_summary = (
                "The target returned an unexpected response to the function authorization test."
            )
        findings.append(
            _finding(
                "API-FUNCTION-AUTHORIZATION",
                "Administrative function-level authorization",
                admin_status,
                Severity.HIGH,
                admin_summary,
                "Enforce role and privilege checks on every administrative function, not only in the client.",
                _evidence("/v1/admin/audit", admin),
            )
        )

        logout = client.request("POST", "/v1/logout", bearer_token=alice_token)
        after_logout = client.request("GET", "/v1/me", bearer_token=alice_token)
        if logout.status_code not in {200, 204}:
            session_status = CheckStatus.INCONCLUSIVE
            session_summary = "The target did not complete the disposable session logout operation."
        elif after_logout.status_code == 200:
            session_status = CheckStatus.VULNERABLE
            session_summary = "The session remained usable after a successful logout response."
        elif after_logout.status_code in {401, 403}:
            session_status = CheckStatus.NO_ISSUE_OBSERVED
            session_summary = "The session was rejected after logout."
        else:
            session_status = CheckStatus.INCONCLUSIVE
            session_summary = "The target returned an unexpected response after logout."
        findings.append(
            _finding(
                "PROTOCOL-SESSION-REVOCATION",
                "Session revocation after logout",
                session_status,
                Severity.HIGH,
                session_summary,
                "Revoke the server-side session and ensure protected endpoints reject the token immediately.",
                _evidence("/v1/me", after_logout),
            )
        )

        # A separate subject isolates the small fixed-profile rate limit from earlier checks.
        rate_results = [
            client.request("POST", "/v1/challenges", payload={"subject_id": "rate-probe"})
            for _ in range(6)
        ]
        rate_limited = any(result.status_code == 429 for result in rate_results)
        accepted = sum(result.status_code == 201 for result in rate_results)
        if rate_limited:
            rate_status = CheckStatus.NO_ISSUE_OBSERVED
            rate_summary = (
                "The target rejected at least one request after its challenge-rate threshold."
            )
        elif accepted == len(rate_results):
            rate_status = CheckStatus.VULNERABLE
            rate_summary = (
                "All repeated challenge requests were accepted without an observed rate limit."
            )
        else:
            rate_status = CheckStatus.INCONCLUSIVE
            rate_summary = "The target returned a mixed response pattern that did not demonstrate the expected rate-limit behavior."
        findings.append(
            _finding(
                "API-RESOURCE-CONSUMPTION",
                "Challenge endpoint rate limiting",
                rate_status,
                Severity.MEDIUM,
                rate_summary,
                "Apply per-subject and per-client rate limits, resource budgets and monitoring to costly authentication operations.",
                {
                    "route": "/v1/challenges",
                    "requests_sent": len(rate_results),
                    "accepted_requests": accepted,
                    "rate_limited": rate_limited,
                    "last_http_status": rate_results[-1].status_code,
                },
            )
        )
    except ProtocolError as exc:
        findings.append(
            _finding(
                "PROTOCOL-RUN-EXECUTION",
                "Protocol assessment execution",
                CheckStatus.EXECUTION_ERROR,
                Severity.INFO,
                str(exc),
                "Check that the local reference service is running, the scope is correct and the configured limits are sufficient.",
            )
        )

    return ProtocolReport(
        run_id=str(uuid4()),
        generated_at=datetime.now(UTC),
        framework_version=framework_version,
        target_label=scope.target_label,
        target_url=scope.target_url,
        request_count=client.requests_made,
        findings=findings,
        warnings=warnings,
    )


def write_protocol_report(report: ProtocolReport, output_dir: Path) -> Path:
    """Write a redacted JSON and Markdown report into a new directory."""

    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise ProtocolError("Refusing to overwrite an existing protocol report directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        with (temporary / "report.json").open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(report.model_dump_json(indent=2))
            handle.write("\n")
        with (temporary / "report.md").open("x", encoding="utf-8", newline="\n") as handle:
            handle.write("# VoxRigor Protocol Assessment\n\n")
            handle.write(f"- Run ID: {report.run_id}\n")
            handle.write(f"- Target: {report.target_label} ({report.target_url})\n")
            handle.write(f"- Generated: {report.generated_at.isoformat()}\n")
            handle.write(f"- HTTP requests: {report.request_count}\n\n")
            handle.write(
                "> no_issue_observed is not a security guarantee. This local profile does not perform biometric inference.\n\n"
            )
            handle.write("| Check | Status | Severity | Summary |\n")
            handle.write("|---|---|---|---|\n")
            for finding in report.findings:
                summary = finding.summary.replace("|", "\\|").replace("\n", " ")
                handle.write(
                    f"| {finding.title} | {finding.status.value} | {finding.severity.value} | {summary} |\n"
                )
            handle.write("\n## Warnings\n\n")
            for warning in report.warnings:
                handle.write(f"- {warning}\n")
            handle.write(
                "\nEvidence excludes request bodies, response payloads, tokens and fixture proofs.\n"
            )
        temporary.rename(destination)
        return destination
    except Exception:
        import shutil

        shutil.rmtree(temporary, ignore_errors=True)
        raise
