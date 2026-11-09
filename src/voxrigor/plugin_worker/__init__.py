"""Foundation for the future OS-isolated plugin worker.

The protocol and backend contracts in this package do not themselves provide
process or operating-system isolation. No production backend is registered yet.
"""

from voxrigor.plugin_worker.isolation import (
    IsolationBackend,
    IsolationBackendUnavailable,
    IsolationPolicy,
    IsolationReadiness,
    verify_isolation_backend,
)
from voxrigor.plugin_worker.protocol import (
    MAX_WORKER_FRAME_BYTES,
    WORKER_PROTOCOL_VERSION,
    WorkerProtocolError,
    read_worker_message,
    write_worker_message,
)

__all__ = [
    "MAX_WORKER_FRAME_BYTES",
    "WORKER_PROTOCOL_VERSION",
    "IsolationBackend",
    "IsolationBackendUnavailable",
    "IsolationPolicy",
    "IsolationReadiness",
    "WorkerProtocolError",
    "read_worker_message",
    "verify_isolation_backend",
    "write_worker_message",
]
