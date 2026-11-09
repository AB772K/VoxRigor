"""Minimal, non-biometric example plugin for the VoxRigor SDK."""

from __future__ import annotations

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


class DemoVoicePlugin:
    """Example external plugin exposing one diagnostic test and no permissions."""

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


def create_plugin() -> DemoVoicePlugin:
    """Entry-point factory required by the VoxRigor plugin contract."""

    return DemoVoicePlugin()
