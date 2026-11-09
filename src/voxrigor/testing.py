"""Explicit test registry and deterministic test orchestration."""

from __future__ import annotations

import json
import logging
import platform
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID, uuid4

from voxrigor import __version__
from voxrigor.errors import TestNotFoundError
from voxrigor.models import (
    ProjectManifest,
    ResultStatus,
    RunReport,
    RunSummary,
    SampleAccounting,
    TestDescriptor,
    TestError,
    TestResult,
    utc_now,
)
from voxrigor.provenance import build_provenance

LOGGER = logging.getLogger("voxrigor")


@dataclass(frozen=True)
class TestContext:
    """Minimal context passed to a test implementation."""

    run_id: UUID
    project: ProjectManifest


@dataclass(frozen=True)
class TestOutcome:
    """Data returned by a test implementation."""

    status: ResultStatus
    measurements: dict[str, object]
    limitations: tuple[str, ...] = ()
    sample_accounting: SampleAccounting = field(default_factory=SampleAccounting)


class TestPlugin(Protocol):
    """Contract implemented by a built-in or later external test plugin."""

    descriptor: TestDescriptor

    def execute(self, context: TestContext) -> TestOutcome:
        """Execute one bounded test and return a typed outcome."""


class RuntimeInfoTest:
    """Diagnostic test proving the orchestration path; not a security assessment."""

    descriptor = TestDescriptor(
        test_id="core.runtime-info",
        version="0.1.0",
        name="Runtime information",
        category="framework_diagnostic",
        description="Collect runtime metadata to exercise the Phase 1 runner.",
    )

    def execute(self, context: TestContext) -> TestOutcome:
        return TestOutcome(
            status=ResultStatus.INCONCLUSIVE,
            measurements={
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "project_name": context.project.name,
                "framework_version": __version__,
            },
            limitations=(
                "Diagnostic only: no biometric model, audio sample, authentication target, "
                "or security control was tested.",
            ),
        )


class TestRegistry:
    """An explicit allowlist of test implementations."""

    def __init__(self) -> None:
        self._tests: dict[str, TestPlugin] = {}

    def register(self, plugin: TestPlugin) -> None:
        """Register one implementation without replacing an existing identifier."""

        self.register_many((plugin,))

    def register_many(self, plugins: Iterable[TestPlugin]) -> None:
        """Atomically register multiple implementations after validating all identifiers."""

        pending: dict[str, TestPlugin] = {}
        for plugin in plugins:
            test_id = plugin.descriptor.test_id
            if test_id in self._tests or test_id in pending:
                raise ValueError(f"Duplicate test identifier: {test_id}")
            if not callable(getattr(plugin, "execute", None)):
                raise ValueError(f"Test implementation has no callable execute method: {test_id}")
            pending[test_id] = plugin
        updated = self._tests.copy()
        updated.update(pending)
        self._tests = updated

    def get(self, test_id: str) -> TestPlugin:
        try:
            return self._tests[test_id]
        except KeyError as exc:
            raise TestNotFoundError(f"Unknown test identifier: {test_id}") from exc

    def list(self) -> list[TestDescriptor]:
        return [self._tests[key].descriptor for key in sorted(self._tests)]


class TestRunner:
    """Run explicitly selected registered tests and build a report."""

    def __init__(self, registry: TestRegistry) -> None:
        self.registry = registry

    def run(
        self,
        manifest: ProjectManifest,
        test_ids: list[str] | None = None,
        random_seed: int | None = None,
    ) -> RunReport:
        selected_ids = (
            test_ids
            if test_ids is not None
            else [descriptor.test_id for descriptor in self.registry.list()]
        )
        if not selected_ids:
            raise ValueError("No tests selected")

        # Resolve all IDs before starting; a typo must not produce a partial run.
        plugins = [self.registry.get(test_id) for test_id in selected_ids]
        if len(set(selected_ids)) != len(selected_ids):
            raise ValueError("Duplicate test identifiers are not allowed in one run")

        run_id = uuid4()
        run_started = utc_now()
        results: list[TestResult] = []

        for plugin in plugins:
            started = utc_now()
            try:
                outcome = plugin.execute(TestContext(run_id=run_id, project=manifest))
                # Reject NaN/Infinity and non-JSON objects before they reach report serialization.
                json.dumps(outcome.measurements, allow_nan=False)
                if not outcome.sample_accounting.is_reconciled():
                    raise ValueError("Test sample accounting does not reconcile")
                result = TestResult(
                    run_id=run_id,
                    test=plugin.descriptor,
                    status=outcome.status,
                    started_at=started,
                    finished_at=utc_now(),
                    measurements=outcome.measurements,
                    sample_accounting=outcome.sample_accounting,
                    limitations=list(outcome.limitations),
                )
            except Exception as exc:  # A failed test becomes an explicit result, not success.
                # Do not log exception text or tracebacks: plugins may include secrets or
                # sensitive request/audio metadata in exception messages.
                LOGGER.error(
                    "Test execution failed: %s (%s)",
                    plugin.descriptor.test_id,
                    type(exc).__name__,
                )
                result = TestResult(
                    run_id=run_id,
                    test=plugin.descriptor,
                    status=ResultStatus.EXECUTION_ERROR,
                    started_at=started,
                    finished_at=utc_now(),
                    error=TestError(
                        error_type=type(exc).__name__,
                        message=(
                            "Test raised an exception; exception text was omitted to reduce "
                            "the risk of logging secrets."
                        ),
                    ),
                    limitations=["Execution failed; no security conclusion can be drawn."],
                )
            results.append(result)

        run_finished = utc_now()
        counts = {status.value: 0 for status in ResultStatus}
        for result in results:
            counts[result.status.value] += 1

        return RunReport(
            run_id=run_id,
            project_id=manifest.project_id,
            project_name=manifest.name,
            started_at=run_started,
            finished_at=run_finished,
            provenance=build_provenance(manifest, random_seed=random_seed),
            summary=RunSummary(
                total=len(results),
                vulnerable=counts[ResultStatus.VULNERABLE.value],
                no_issue_observed=counts[ResultStatus.NO_ISSUE_OBSERVED.value],
                inconclusive=counts[ResultStatus.INCONCLUSIVE.value],
                unsupported=counts[ResultStatus.UNSUPPORTED.value],
                execution_error=counts[ResultStatus.EXECUTION_ERROR.value],
            ),
            results=results,
        )


def build_default_registry() -> TestRegistry:
    """Return only the explicitly approved built-in Phase 1 diagnostic test."""

    registry = TestRegistry()
    registry.register(RuntimeInfoTest())
    return registry
