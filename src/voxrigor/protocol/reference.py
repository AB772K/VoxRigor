"""In-memory local reference voice-authentication protocol service.

The fixture verifier is deliberately synthetic. It exercises protocol state, not speaker
recognition, presentation-attack detection, voice liveness or any biometric accuracy claim.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
import time
from typing import Any, Literal, cast


FixtureProfile = Literal["fixed", "vulnerable"]
_FIXTURE_PROOF_KEY = b"VoxRigor-local-fixture-only-not-a-credential"


def fixture_proof(subject_id: str, nonce: str) -> str:
    """Build the deterministic test-only assertion understood by the reference fixture."""
    message = f"{subject_id}:{nonce}".encode()
    return hmac.new(_FIXTURE_PROOF_KEY, message, hashlib.sha256).hexdigest()


@dataclass
class Challenge:
    challenge_id: str
    subject_id: str
    nonce: str
    expires_at: float
    used: bool = False


@dataclass
class Session:
    subject_id: str
    role: str
    expires_at: float


@dataclass
class ReferenceApplication:
    profile: FixtureProfile
    challenge_ttl_seconds: float
    session_ttl_seconds: float = 60.0
    challenges: dict[str, Challenge] = field(default_factory=dict)
    sessions: dict[str, Session] = field(default_factory=dict)
    challenge_times: dict[str, deque[float]] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)

    accounts: dict[str, str] = field(
        default_factory=lambda: {
            "alice": "user",
            "bob": "user",
            "charlie": "user",
            "rate-probe": "user",
            "admin": "admin",
        }
    )
    enrollments: dict[str, dict[str, str]] = field(
        default_factory=lambda: {
            "enroll-alice": {
                "subject_id": "alice",
                "template_sha256": hashlib.sha256(b"fixture-alice-template").hexdigest(),
            },
            "enroll-bob": {
                "subject_id": "bob",
                "template_sha256": hashlib.sha256(b"fixture-bob-template").hexdigest(),
            },
        }
    )

    def create_challenge(self, subject_id: str) -> tuple[int, dict[str, object]]:
        now = time.time()
        if subject_id not in self.accounts:
            return 404, {"error": "unknown_test_subject"}
        with self.lock:
            if self.profile == "fixed":
                history = self.challenge_times.setdefault(subject_id, deque())
                while history and now - history[0] > 60.0:
                    history.popleft()
                if len(history) >= 5:
                    return 429, {"error": "challenge_rate_limit"}
                history.append(now)
            challenge_id = secrets.token_urlsafe(18)
            nonce = secrets.token_hex(32)
            self.challenges[challenge_id] = Challenge(
                challenge_id=challenge_id,
                subject_id=subject_id,
                nonce=nonce,
                expires_at=now + self.challenge_ttl_seconds,
            )
            return 201, {
                "challenge_id": challenge_id,
                "nonce": nonce,
                "expires_in": self.challenge_ttl_seconds,
            }

    def verify(self, challenge_id: str, subject_id: str, proof: str) -> tuple[int, dict[str, object]]:
        with self.lock:
            challenge = self.challenges.get(challenge_id)
            if challenge is None:
                return 404, {"error": "challenge_not_found"}
            if self.profile == "fixed":
                if challenge.subject_id != subject_id:
                    return 403, {"error": "challenge_subject_mismatch"}
                if challenge.used:
                    return 409, {"error": "challenge_already_used"}
                if time.time() > challenge.expires_at:
                    challenge.used = True
                    return 410, {"error": "challenge_expired"}
                # Consume before validating the assertion so a failed proof cannot be replayed.
                challenge.used = True
            expected = fixture_proof(subject_id, challenge.nonce)
            if subject_id not in self.accounts or not hmac.compare_digest(proof, expected):
                return 401, {"error": "fixture_assertion_rejected"}
            token = secrets.token_urlsafe(32)
            self.sessions[token] = Session(
                subject_id=subject_id,
                role=self.accounts[subject_id],
                expires_at=time.time() + self.session_ttl_seconds,
            )
            return 200, {
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": self.session_ttl_seconds,
            }

    def get_session(self, authorization: str | None) -> tuple[str | None, Session | None]:
        if authorization is None or not authorization.startswith("Bearer "):
            return None, None
        token = authorization[7:]
        with self.lock:
            session = self.sessions.get(token)
            if session is not None and time.time() > session.expires_at:
                self.sessions.pop(token, None)
                session = None
            return token, session


class ReferenceHTTPServer(ThreadingHTTPServer):
    """Threaded HTTP server pinned to IPv4 loopback."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        app: ReferenceApplication,
    ) -> None:
        if server_address[0] != "127.0.0.1":
            raise ValueError("Reference service may bind only to 127.0.0.1")
        self.app = app
        super().__init__(server_address, ReferenceRequestHandler)


class ReferenceRequestHandler(BaseHTTPRequestHandler):
    """Minimal JSON handler with no external dependencies or request logging."""

    server_version = "VoxRigorReference/0.1"
    sys_version = ""

    @property
    def app(self) -> ReferenceApplication:
        return cast(ReferenceHTTPServer, self.server).app

    def log_message(self, _format: str, *_args: object) -> None:
        # Do not log request bodies, headers, tokens, or test identities.
        return

    def _send(self, status: int, payload: dict[str, object] | None = None) -> None:
        body = b"" if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _read_json(self) -> dict[str, Any] | None:
        length_text = self.headers.get("Content-Length")
        try:
            length = int(length_text or "0")
        except ValueError:
            self._send(400, {"error": "invalid_content_length"})
            return None
        if length <= 0 or length > 16 * 1024:
            self._send(413 if length > 16 * 1024 else 400, {"error": "invalid_request_size"})
            return None
        content_type = self.headers.get("Content-Type", "").split(";", maxsplit=1)[0].strip().lower()
        if content_type != "application/json":
            self._send(415, {"error": "application_json_required"})
            return None
        try:
            raw = self.rfile.read(length)
            value = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, {"error": "invalid_json"})
            return None
        if not isinstance(value, dict):
            self._send(400, {"error": "json_object_required"})
            return None
        return value

    def _session(self) -> tuple[str | None, Session | None]:
        return self.app.get_session(self.headers.get("Authorization"))

    def do_GET(self) -> None:
        path = self.path
        if "?" in path or "#" in path:
            self._send(400, {"error": "query_and_fragment_not_supported"})
            return
        if path == "/health":
            self._send(200, {"service": "voxrigor-reference", "protocol": "0.1"})
            return
        if path == "/v1/me":
            _, session = self._session()
            if session is None:
                self._send(401, {"error": "authentication_required"})
            else:
                self._send(200, {"subject_id": session.subject_id, "role": session.role})
            return
        if path == "/v1/enrollments/enroll-bob":
            _, session = self._session()
            if session is None:
                self._send(401, {"error": "authentication_required"})
                return
            record = self.app.enrollments["enroll-bob"]
            if (
                self.app.profile == "fixed"
                and session.subject_id != record["subject_id"]
                and session.role != "admin"
            ):
                self._send(403, {"error": "object_access_denied"})
                return
            self._send(
                200,
                {
                    "enrollment_id": "enroll-bob",
                    "subject_id": record["subject_id"],
                    "template_sha256": record["template_sha256"],
                },
            )
            return
        if path == "/v1/admin/audit":
            _, session = self._session()
            if session is None:
                self._send(401, {"error": "authentication_required"})
                return
            if self.app.profile == "fixed" and session.role != "admin":
                self._send(403, {"error": "admin_role_required"})
                return
            self._send(200, {"events": 0, "fixture": True})
            return
        self._send(404, {"error": "route_not_found"})

    def do_POST(self) -> None:
        path = self.path
        if "?" in path or "#" in path:
            self._send(400, {"error": "query_and_fragment_not_supported"})
            return
        payload = self._read_json()
        if payload is None:
            return
        if path == "/v1/challenges":
            subject = payload.get("subject_id")
            if not isinstance(subject, str):
                self._send(400, {"error": "subject_id_required"})
                return
            status, response = self.app.create_challenge(subject)
            self._send(status, response)
            return
        if path == "/v1/verify":
            challenge_id = payload.get("challenge_id")
            subject_id = payload.get("subject_id")
            proof = payload.get("proof")
            if not all(isinstance(item, str) for item in (challenge_id, subject_id, proof)):
                self._send(400, {"error": "challenge_id_subject_id_and_proof_required"})
                return
            status, response = self.app.verify(
                cast(str, challenge_id),
                cast(str, subject_id),
                cast(str, proof),
            )
            self._send(status, response)
            return
        if path == "/v1/logout":
            token, session = self._session()
            if token is None or session is None:
                self._send(401, {"error": "authentication_required"})
                return
            with self.app.lock:
                self.app.sessions.pop(token, None)
            self._send(204)
            return
        self._send(404, {"error": "route_not_found"})

    def do_PUT(self) -> None:
        self._send(405, {"error": "method_not_allowed"})

    def do_DELETE(self) -> None:
        self._send(405, {"error": "method_not_allowed"})


def create_reference_server(
    *,
    profile: FixtureProfile = "fixed",
    port: int = 8765,
    challenge_ttl_seconds: float = 3.0,
) -> ReferenceHTTPServer:
    """Create an in-memory local fixture server. It never binds to a non-loopback address."""

    if not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")
    if not 0.1 <= challenge_ttl_seconds <= 120.0:
        raise ValueError("challenge_ttl_seconds must be between 0.1 and 120 seconds")
    app = ReferenceApplication(profile=profile, challenge_ttl_seconds=challenge_ttl_seconds)
    return ReferenceHTTPServer(("127.0.0.1", port), app)
