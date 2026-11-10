"""Minimal, non-biometric example plugin for the VoxRigor SDK."""

from __future__ import annotations

from pathlib import Path
import socket

from voxrigor.models import ResultStatus, TestDescriptor
from voxrigor.plugins import PluginMetadata, PluginRegistrationContext
from voxrigor.testing import TestContext, TestOutcome


class PluginContractDiagnostic:
    """A harmless diagnostic proving that the external wheel can register and run a test."""

    descriptor = TestDescriptor(
        test_id="demo.voice.sdk-diagnostic",
        version="0.1.0",
        name="Example plugin SDK diagnostic",
        category="plugin_example",
        description="Confirms that an independently installed plugin can register with VoxRigor.",
    )

    def execute(self, context: TestContext) -> TestOutcome:
        return TestOutcome(
            status=ResultStatus.INCONCLUSIVE,
            measurements={
                "plugin_id": "demo.voice",
                "project_name": context.project.name,
                "sdk_contract": "0.1",
                "result": "plugin test executed",
            },
            limitations=(
                "Example SDK diagnostic only; no audio, biometric model, authentication target "
                "or security control was tested.",
            ),
        )





class WorkerBoundaryProbe:
    """Probe whether the worker can reach one host-only file or host loopback listener."""

    descriptor = TestDescriptor(
        test_id="demo.voice.worker-boundary-probe",
        version="0.1.0",
        name="Worker boundary probe",
        category="worker_isolation",
        description="Checks that one host sentinel and host loopback listener are not reachable.",
    )

    def execute(self, context: TestContext) -> TestOutcome:
        sentinel_path, port_text = context.project.name.split("|", maxsplit=1)
        try:
            Path(sentinel_path).read_bytes()
            sentinel_readable = True
        except OSError:
            sentinel_readable = False

        try:
            with socket.create_connection(("127.0.0.1", int(port_text)), timeout=1):
                host_loopback_reachable = True
        except OSError:
            host_loopback_reachable = False

        return TestOutcome(
            status=ResultStatus.INCONCLUSIVE,
            measurements={
                "host_sentinel_readable": sentinel_readable,
                "host_loopback_reachable": host_loopback_reachable,
            },
            limitations=(
                "Narrow integration probe only; it does not replace a full adversarial sandbox review.",
            ),
        )


class DemoVoicePlugin:
    """Example external plugin exposing diagnostics and a boundary probe, with no permissions."""

    metadata = PluginMetadata(
        plugin_id="demo.voice",
        name="VoxRigor Demo Voice Plugin",
        version="0.1.0",
        api_version="0.1",
        publisher="VoxRigor example package",
        description="A minimal external wheel used to verify the public plugin SDK contract.",
        required_permissions=[],
    )

    def register(self, context: PluginRegistrationContext) -> None:
        context.register(PluginContractDiagnostic())
        context.register(WorkerBoundaryProbe())


def create_plugin() -> DemoVoicePlugin:
    """Entry-point factory required by the VoxRigor plugin contract."""

    return DemoVoicePlugin()
