"""Bounded HTTP client that cannot leave an explicit loopback origin."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from voxrigor.protocol.errors import ProtocolError
from voxrigor.protocol.scope import ProtocolScope


MAX_REQUEST_BODY_BYTES = 16 * 1024
MAX_RESPONSE_BODY_BYTES = 32 * 1024

_ALLOWED_ROUTES = frozenset(
    {
        "/health",
        "/v1/challenges",
        "/v1/verify",
        "/v1/me",
        "/v1/logout",
        "/v1/enrollments/enroll-bob",
        "/v1/admin/audit",
    }
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        """Never follow redirects, even to another loopback address."""
        return None


@dataclass(frozen=True)
class HttpResult:
    """Small response envelope. Callers must not copy body data into report evidence."""

    status_code: int
    payload: dict[str, Any]
    elapsed_ms: float
    response_bytes: int


class ScopedHttpClient:
    """Sequential, bounded HTTP client for a fixed set of protocol routes."""

    def __init__(self, scope: ProtocolScope) -> None:
        self._scope = scope
        self._requests_made = 0
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirect(),
        )

    @property
    def requests_made(self) -> int:
        return self._requests_made

    def request(
        self,
        method: str,
        route: str,
        *,
        payload: dict[str, object] | None = None,
        bearer_token: str | None = None,
    ) -> HttpResult:
        """Send one request after enforcing method, route, body, budget and response limits."""

        selected_method = method.upper()
        if selected_method not in {"GET", "POST"}:
            raise ProtocolError("Only GET and POST are supported by the non-destructive protocol profile")
        if route not in _ALLOWED_ROUTES:
            raise ProtocolError("Requested route is not in the protocol test allowlist")
        self._requests_made += 1
        if self._requests_made > self._scope.request_budget:
            raise ProtocolError("Protocol request budget was exhausted")

        body: bytes | None = None
        headers = {"Accept": "application/json", "User-Agent": "VoxRigor-LocalProtocol/0.1"}
        if payload is not None:
            try:
                body = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise ProtocolError("Protocol request payload is not valid JSON data") from exc
            if len(body) > MAX_REQUEST_BODY_BYTES:
                raise ProtocolError("Protocol request body exceeds the 16 KiB limit")
            headers["Content-Type"] = "application/json"
        if bearer_token is not None:
            if not bearer_token or len(bearer_token) > 512 or "\r" in bearer_token or "\n" in bearer_token:
                raise ProtocolError("Invalid in-memory bearer token")
            headers["Authorization"] = f"Bearer {bearer_token}"

        request = urllib.request.Request(
            f"{self._scope.target_url}{route}",
            data=body,
            headers=headers,
            method=selected_method,
        )
        started = time.monotonic()
        try:
            response = self._opener.open(request, timeout=self._scope.timeout_seconds)
        except urllib.error.HTTPError as exc:
            response = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProtocolError("Local target did not return a bounded HTTP response") from exc

        try:
            raw = response.read(MAX_RESPONSE_BODY_BYTES + 1)
            status = int(getattr(response, "status", getattr(response, "code", 0)))
        except (OSError, ValueError) as exc:
            raise ProtocolError("Could not read the bounded local target response") from exc
        finally:
            response.close()
        elapsed_ms = (time.monotonic() - started) * 1000.0
        if len(raw) > MAX_RESPONSE_BODY_BYTES:
            raise ProtocolError("Local target response exceeded the 32 KiB limit")
        if not raw:
            decoded: dict[str, Any] = {}
        else:
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProtocolError("Local target returned a non-JSON response") from exc
            if not isinstance(value, dict):
                raise ProtocolError("Local target response must be a JSON object")
            decoded = value
        return HttpResult(
            status_code=status,
            payload=decoded,
            elapsed_ms=elapsed_ms,
            response_bytes=len(raw),
        )
