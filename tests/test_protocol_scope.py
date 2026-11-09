from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from voxrigor.protocol.scope import ProtocolScope, load_scope_manifest, write_scope_example


@pytest.mark.parametrize(
    "target_url",
    [
        "https://127.0.0.1:8765",
        "http://example.com:8765",
        "http://localhost:8765",
        "http://8.8.8.8:8765",
        "http://127.0.0.1",
        "http://user:pass@127.0.0.1:8765",
        "http://127.0.0.1:8765/private",
        "http://127.0.0.1:8765/?next=http://example.com",
    ],
)
def test_scope_rejects_non_loopback_or_ambiguous_targets(target_url: str) -> None:
    with pytest.raises(ValidationError):
        ProtocolScope(target_url=target_url, authorized=True)


def test_scope_requires_explicit_authorization_acknowledgement() -> None:
    with pytest.raises(ValidationError):
        ProtocolScope.model_validate(
            {"target_url": "http://127.0.0.1:8765", "authorized": False}
        )


def test_scope_enforces_small_request_and_timeout_budgets() -> None:
    with pytest.raises(ValidationError):
        ProtocolScope(
            target_url="http://127.0.0.1:8765",
            authorized=True,
            request_budget=1000,
        )
    with pytest.raises(ValidationError):
        ProtocolScope(
            target_url="http://127.0.0.1:8765",
            authorized=True,
            timeout_seconds=30.0,
        )


def test_scope_example_round_trips_and_does_not_overwrite(tmp_path: Path) -> None:
    path = write_scope_example(tmp_path / "scope.json", "http://127.0.0.1:8765")
    scope = load_scope_manifest(path)
    assert scope.target_url == "http://127.0.0.1:8765"
    assert scope.authorized is True
    with pytest.raises(FileExistsError):
        write_scope_example(path, "http://127.0.0.1:8765")


def test_scope_loader_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "scope.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "target_url": "http://127.0.0.1:8765",
                "authorized": True,
                "remote_override": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="invalid"):
        load_scope_manifest(path)
