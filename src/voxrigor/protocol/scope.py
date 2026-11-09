"""Strict local-target scope manifest and validation."""

from __future__ import annotations

import ipaddress
import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from voxrigor.protocol.errors import ScopeManifestError


class ProtocolScope(BaseModel):
    """A narrowly-scoped authorization declaration for the current local-only engine."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    schema_version: Literal["0.1"] = "0.1"
    target_url: str = Field(min_length=1, max_length=200)
    target_label: str = Field(default="Local reference service", min_length=1, max_length=100)
    authorized: Literal[True]
    request_budget: int = Field(default=32, ge=1, le=64)
    timeout_seconds: float = Field(default=2.0, gt=0.0, le=3.0, allow_inf_nan=False)
    max_test_wait_seconds: float = Field(default=5.0, ge=0.0, le=10.0, allow_inf_nan=False)

    @field_validator("target_url")
    @classmethod
    def require_loopback_ip_literal(cls, value: str) -> str:
        parsed = urlsplit(value)
        try:
            host = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ValueError("target_url contains an invalid host or port") from exc
        if parsed.scheme != "http" or host is None or port is None:
            raise ValueError("target_url must be an explicit http://loopback-IP:port URL")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("target_url must not contain credentials")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("target_url must identify only an origin; custom paths are not supported")
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError("target_url host must be a loopback IP literal; DNS names are not allowed") from exc
        if not address.is_loopback:
            raise ValueError("protocol testing is restricted to loopback IP addresses")
        if not 1 <= port <= 65535:
            raise ValueError("target_url port must be between 1 and 65535")
        selected_host = f"[{address.compressed}]" if address.version == 6 else address.compressed
        return f"http://{selected_host}:{port}"

    @field_validator("target_label")
    @classmethod
    def normalize_target_label(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("target_label must not be blank")
        return cleaned


def load_scope_manifest(path: Path) -> ProtocolScope:
    """Load a strict JSON scope file."""

    source = Path(path).expanduser()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
        return ProtocolScope.model_validate(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ScopeManifestError("Protocol scope is missing, unreadable or invalid") from exc


def write_scope_example(path: Path, target_url: str, *, authorized: bool) -> Path:
    """Write a local-only scope example after an explicit authorization acknowledgement."""

    if authorized is not True:
        raise ScopeManifestError("Explicit --i-authorize-local-target acknowledgement is required")
    scope = ProtocolScope(target_url=target_url, authorized=True)
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(scope.model_dump_json(indent=2))
        handle.write("\n")
    return destination
