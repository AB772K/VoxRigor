"""Fail-closed contract for future operating-system plugin isolation backends.

No concrete production backend is registered by this module. An ordinary
subprocess is deliberately not considered an isolation backend.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

REQUIRED_ISOLATION_CONTROLS = frozenset(
    {
        "separate_process",
        "restricted_identity",
        "read_only_root",
        "staged_inputs_only",
        "bounded_output_directory",
        "no_network",
        "no_host_credentials",
        "no_host_devices",
        "cpu_limit",
        "memory_limit",
        "process_limit",
        "open_file_limit",
        "wall_time_limit",
        "child_process_cleanup",
    }
)


class IsolationBackendUnavailable(RuntimeError):
    """Raised when no verified backend can enforce the required policy."""


class IsolationPolicy(BaseModel):
    """Finite resource ceilings and default-deny policy for a future worker."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    wall_time_seconds: int = Field(default=300, ge=1, le=3600)
    cpu_time_seconds: int = Field(default=300, ge=1, le=3600)
    memory_bytes: int = Field(default=1_073_741_824, ge=134_217_728, le=8_589_934_592)
    process_count: int = Field(default=8, ge=1, le=64)
    open_file_count: int = Field(default=128, ge=16, le=1024)
    output_bytes: int = Field(default=67_108_864, ge=0, le=536_870_912)
    network_enabled: bool = False
    microphone_enabled: bool = False
    host_filesystem_enabled: bool = False


class IsolationReadiness(BaseModel):
    """Backend preflight result. Controls must be actively verified, not assumed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    backend_id: str = Field(min_length=1, max_length=80)
    runtime_version: str = Field(min_length=1, max_length=80)
    verified: bool
    enforced_controls: list[str] = Field(default_factory=list, max_length=64)
    missing_controls: list[str] = Field(default_factory=list, max_length=64)
    detail: str = Field(default="", max_length=500)


class IsolationBackend(Protocol):
    """Future platform backend must prove controls before it may launch a worker."""

    @property
    def backend_id(self) -> str:
        """Stable, implementation-defined backend identifier."""

    def preflight(self, policy: IsolationPolicy) -> IsolationReadiness:
        """Actively inspect runtime capabilities and return verified controls."""


def missing_required_controls(readiness: IsolationReadiness) -> tuple[str, ...]:
    """Return required controls not explicitly verified by the backend."""

    enforced = set(readiness.enforced_controls)
    reported_missing = set(readiness.missing_controls)
    return tuple(sorted((REQUIRED_ISOLATION_CONTROLS - enforced) | reported_missing))


def verify_isolation_backend(
    backend: IsolationBackend | None,
    policy: IsolationPolicy | None = None,
) -> IsolationReadiness:
    """Fail closed unless a backend actively reports every mandatory control."""

    if backend is None:
        raise IsolationBackendUnavailable(
            "No production plugin isolation backend is installed; refusing to launch plugin code"
        )
    selected_policy = policy or IsolationPolicy()
    if (
        selected_policy.network_enabled
        or selected_policy.microphone_enabled
        or selected_policy.host_filesystem_enabled
    ):
        raise IsolationBackendUnavailable(
            "Network, microphone and general host-filesystem access are not supported by the initial worker policy"
        )
    try:
        declared_backend_id = backend.backend_id
        readiness = backend.preflight(selected_policy)
    except IsolationBackendUnavailable:
        raise
    except Exception as exc:
        raise IsolationBackendUnavailable(
            f"Isolation backend preflight failed ({type(exc).__name__}); refusing execution"
        ) from exc

    if readiness.backend_id != declared_backend_id:
        raise IsolationBackendUnavailable(
            "Isolation backend identity did not match its preflight result"
        )
    unknown_controls = set(readiness.enforced_controls) - REQUIRED_ISOLATION_CONTROLS
    if unknown_controls:
        raise IsolationBackendUnavailable(
            "Isolation backend reported unknown security controls: "
            + ", ".join(sorted(unknown_controls))
        )
    if not readiness.verified:
        raise IsolationBackendUnavailable(
            f"Isolation backend {readiness.backend_id!r} did not verify its security boundary"
        )
    missing = missing_required_controls(readiness)
    if missing:
        raise IsolationBackendUnavailable(
            f"Isolation backend {readiness.backend_id!r} does not enforce required controls: "
            + ", ".join(missing)
        )
    return readiness
