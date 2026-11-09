from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from voxrigor.protocol.client import ScopedHttpClient
from voxrigor.protocol.errors import ProtocolError
from voxrigor.protocol.reference import FixtureProfile, ReferenceHTTPServer, create_reference_server
from voxrigor.protocol.runner import CheckStatus, run_protocol_assessment, write_protocol_report
from voxrigor.protocol.scope import ProtocolScope


@contextmanager
def local_fixture(profile: FixtureProfile, ttl: float = 0.1) -> Iterator[ProtocolScope]:
    server = create_reference_server(profile=profile, port=0, challenge_ttl_seconds=ttl)
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
        "PROTOCOL-CHALLENGE-EXPIRY",
        "API-OBJECT-AUTHORIZATION",
        "API-FUNCTION-AUTHORIZATION",
        "PROTOCOL-SESSION-REVOCATION",
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
        "API-OBJECT-AUTHORIZATION",
        "API-FUNCTION-AUTHORIZATION",
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
