from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from voxrigor.protocol.client import ScopedHttpClient
from voxrigor.protocol.errors import ProtocolError
from voxrigor.protocol.reference import (
    FixtureProfile,
    ReferenceHTTPServer,
    create_reference_server,
    fixture_proof,
)
from voxrigor.protocol.runner import CheckStatus, run_protocol_assessment, write_protocol_report
from voxrigor.protocol.scope import ProtocolScope


@contextmanager
def local_fixture(profile: FixtureProfile, ttl: float = 0.1) -> Iterator[ProtocolScope]:
    server = create_reference_server(
        profile=profile,
        port=0,
        challenge_ttl_seconds=ttl,
        session_ttl_seconds=0.1,
    )
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        daemon=True,
    )
    thread.start()
    port = int(server.server_address[1])
    scope = ProtocolScope(
        target_url=f"http://127.0.0.1:{port}",
        target_label=f"local-{profile}",
        authorized=True,
        request_budget=32,
        timeout_seconds=1.0,
        max_test_wait_seconds=1.0,
    )
    try:
        yield scope
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def finding_map(report: object) -> dict[str, CheckStatus]:
    return {item.check_id: item.status for item in report.findings}  # type: ignore[attr-defined]


def test_fixed_reference_fixture_rejects_protocol_and_api_abuse() -> None:
    with local_fixture("fixed") as scope:
        report = run_protocol_assessment(scope, framework_version="test")
    statuses = finding_map(report)
    expected_checks = {
        "PROTOCOL-HEALTH",
        "PROTOCOL-CHALLENGE-REPLAY",
        "PROTOCOL-CHALLENGE-SUBJECT-BINDING",
        "PROTOCOL-CHALLENGE-PURPOSE-BINDING",
        "PROTOCOL-CHALLENGE-EXPIRY",
        "API-OBJECT-AUTHORIZATION",
        "API-REENROLLMENT-OWNERSHIP",
        "API-FUNCTION-AUTHORIZATION",
        "PROTOCOL-SESSION-REVOCATION",
        "PROTOCOL-SESSION-EXPIRY",
        "API-RESOURCE-CONSUMPTION",
    }
    assert set(statuses) == expected_checks
    assert set(statuses.values()) == {CheckStatus.NO_ISSUE_OBSERVED}
    assert report.request_count <= 32


def test_vulnerable_fixture_demonstrates_known_control_failures() -> None:
    with local_fixture("vulnerable") as scope:
        report = run_protocol_assessment(scope, framework_version="test")
    statuses = finding_map(report)
    for check_id in (
        "PROTOCOL-CHALLENGE-REPLAY",
        "PROTOCOL-CHALLENGE-SUBJECT-BINDING",
        "PROTOCOL-CHALLENGE-EXPIRY",
        "PROTOCOL-CHALLENGE-PURPOSE-BINDING",
        "API-OBJECT-AUTHORIZATION",
        "API-REENROLLMENT-OWNERSHIP",
        "API-FUNCTION-AUTHORIZATION",
        "PROTOCOL-SESSION-EXPIRY",
        "API-RESOURCE-CONSUMPTION",
    ):
        assert statuses[check_id] is CheckStatus.VULNERABLE
    assert statuses["PROTOCOL-SESSION-REVOCATION"] is CheckStatus.NO_ISSUE_OBSERVED


def test_report_does_not_contain_fixture_proofs_or_session_tokens(tmp_path: Path) -> None:
    with local_fixture("vulnerable") as scope:
        report = run_protocol_assessment(scope, framework_version="test")
    serialized = report.model_dump_json()
    assert "access_token" not in serialized
    assert "fixture-proof" not in serialized
    assert "Authorization" not in serialized
    saved = write_protocol_report(report, tmp_path / "protocol-report")
    json_report = (saved / "report.json").read_text(encoding="utf-8")
    markdown_report = (saved / "report.md").read_text(encoding="utf-8")
    assert "access_token" not in json_report
    assert "fixture-proof" not in json_report
    assert "Authorization" not in markdown_report


def test_scoped_client_enforces_request_budget() -> None:
    with local_fixture("fixed") as scope:
        limited = scope.model_copy(update={"request_budget": 1})
        client = ScopedHttpClient(limited)
        result = client.request("GET", "/health")
        assert result.status_code == 200
        with pytest.raises(ProtocolError, match="budget"):
            client.request("GET", "/health")


def test_client_rejects_unapproved_routes_without_network_request() -> None:
    with local_fixture("fixed") as scope:
        client = ScopedHttpClient(scope)
        with pytest.raises(ProtocolError, match="allowlist"):
            client.request("POST", "http://127.0.0.1/evil")
        assert client.requests_made == 0


def test_reference_server_refuses_non_loopback_bind() -> None:
    with pytest.raises(ValueError, match="127.0.0.1"):
        from voxrigor.protocol.reference import ReferenceApplication

        ReferenceHTTPServer(
            ("0.0.0.0", 0),
            ReferenceApplication(profile="fixed", challenge_ttl_seconds=1.0),
        )

def test_fixed_fixture_binds_challenge_to_recovery_purpose() -> None:
    with local_fixture("fixed") as scope:
        client = ScopedHttpClient(scope)
        created = client.request(
            "POST",
            "/v1/challenges",
            payload={"subject_id": "alice", "purpose": "recovery"},
        )
        assert created.status_code == 201
        challenge_id = str(created.payload["challenge_id"])
        nonce = str(created.payload["nonce"])

        wrong_purpose = client.request(
            "POST",
            "/v1/verify",
            payload={
                "challenge_id": challenge_id,
                "subject_id": "alice",
                "purpose": "authentication",
                "proof": fixture_proof("alice", nonce),
            },
        )
        assert wrong_purpose.status_code == 403
        right_purpose = client.request(
            "POST",
            "/v1/verify",
            payload={
                "challenge_id": challenge_id,
                "subject_id": "alice",
                "purpose": "recovery",
                "proof": __import__(
                    "voxrigor.protocol.reference",
                    fromlist=["fixture_proof"],
                ).fixture_proof("alice", nonce),
            },
        )
        assert right_purpose.status_code == 200


def test_reenrollment_is_owner_authorized_and_increments_version() -> None:
    from voxrigor.protocol.runner import _session

    with local_fixture("fixed") as scope:
        client = ScopedHttpClient(scope)
        alice_token, _ = _session(client, "alice")
        before = client.request(
            "GET",
            "/v1/enrollments/enroll-bob",
            bearer_token=alice_token,
        )
        denied = client.request(
            "POST",
            "/v1/enrollments/enroll-bob",
            payload={"template_sha256": "a" * 64},
            bearer_token=alice_token,
        )
        assert before.status_code == 403
        assert denied.status_code == 403

        bob_token, _ = _session(client, "bob")
        updated = client.request(
            "POST",
            "/v1/enrollments/enroll-bob",
            payload={"template_sha256": "b" * 64},
            bearer_token=bob_token,
        )
        after = client.request(
            "GET",
            "/v1/enrollments/enroll-bob",
            bearer_token=bob_token,
        )
        assert updated.status_code == 200
        assert updated.payload["version"] == "2"
        assert after.status_code == 200
        assert after.payload["version"] == "2"
        assert after.payload["template_sha256"] == "b" * 64


def test_expired_fixed_session_is_rejected() -> None:
    with local_fixture("fixed") as scope:
        client = ScopedHttpClient(scope)
        challenge = client.request(
            "POST",
            "/v1/challenges",
            payload={"subject_id": "alice"},
        )
        verified = client.request(
            "POST",
            "/v1/verify",
            payload={
                "challenge_id": challenge.payload["challenge_id"],
                "subject_id": "alice",
                "purpose": "authentication",
                "proof": fixture_proof("alice", str(challenge.payload["nonce"])),
            },
        )
        assert verified.status_code == 200
        time.sleep(0.12)
        result = client.request(
            "GET",
            "/v1/me",
            bearer_token=str(verified.payload["access_token"]),
        )
        assert result.status_code == 401
