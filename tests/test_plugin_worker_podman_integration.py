from __future__ import annotations

import os
import socket
import tempfile

import pytest

from voxrigor.plugin_worker.podman import (
    RootlessPodmanBackend,
    WorkerExecutionSpec,
    execute_isolated_plugin_test,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("VOXRIGOR_PODMAN_WORKER_IMAGE"),
    reason="Requires the opt-in real rootless Podman integration environment",
)


def test_real_rootless_worker_denies_host_file_and_host_loopback_access() -> None:
    image = os.environ["VOXRIGOR_PODMAN_WORKER_IMAGE"]
    backend = RootlessPodmanBackend(worker_image=image)

    with tempfile.NamedTemporaryFile(prefix="voxrigor-host-sentinel-", mode="w") as sentinel:
        sentinel.write("host-only-secret-sentinel")
        sentinel.flush()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            host_port = listener.getsockname()[1]

            spec = WorkerExecutionSpec(
                plugin_id="demo.voice",
                test_id="demo.voice.worker-boundary-probe",
                project_name=f"{sentinel.name}|{host_port}",
            )
            description, result = execute_isolated_plugin_test(backend, spec)

    assert description.metadata.plugin_id == "demo.voice"
    assert result.plugin_id == "demo.voice"
    assert result.test_id == "demo.voice.worker-boundary-probe"
    assert result.measurements["host_sentinel_readable"] is False
    assert result.measurements["host_loopback_reachable"] is False
    assert result.status.value == "inconclusive"
