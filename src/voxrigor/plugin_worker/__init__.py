"""Protocol, isolation backends and runtime support for opt-in plugin workers.

The rootless Podman backend is Linux-only. Other platforms remain unsupported
until they have a separately verified operating-system isolation backend.
"""

from voxrigor.plugin_worker.isolation import (
    IsolationBackend,
    IsolationBackendUnavailable,
    IsolationPolicy,
    IsolationReadiness,
    verify_isolation_backend,
)
from voxrigor.plugin_worker.podman import (
    HostStagedInput,
    PodmanBackendError,
    RootlessPodmanBackend,
    WorkerExecutionError,
    WorkerExecutionSpec,
    execute_isolated_plugin_test,
)
from voxrigor.plugin_worker.protocol import (
    MAX_WORKER_FRAME_BYTES,
    WORKER_PROTOCOL_VERSION,
    WorkerProtocolError,
    read_worker_message,
    write_worker_message,
)

__all__ = [
    "HostStagedInput",
    "MAX_WORKER_FRAME_BYTES",
    "PodmanBackendError",
    "RootlessPodmanBackend",
    "WORKER_PROTOCOL_VERSION",
    "IsolationBackend",
    "IsolationBackendUnavailable",
    "IsolationPolicy",
    "IsolationReadiness",
    "WorkerExecutionError",
    "WorkerExecutionSpec",
    "WorkerProtocolError",
    "read_worker_message",
    "execute_isolated_plugin_test",
    "verify_isolation_backend",
    "write_worker_message",
]
