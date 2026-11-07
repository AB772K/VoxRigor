from uuid import UUID

import pytest

from voxrigor.errors import TestNotFoundError as UnknownTestError
from voxrigor.models import (
    ProjectManifest,
    ResultStatus,
    SampleAccounting,
    TestDescriptor as Descriptor,
)
from voxrigor.testing import (
    TestOutcome as Outcome,
    TestRegistry as Registry,
    TestRunner as Runner,
    build_default_registry,
)


class BrokenTest:
    descriptor = Descriptor(
        test_id="test.broken",
        version="0.1.0",
        name="Broken test",
        category="test",
        description="Raises on purpose for an error-path test.",
    )

    def execute(self, context):
        raise RuntimeError("expected test failure")


class BadAccountingTest:
    descriptor = Descriptor(
        test_id="test.bad-accounting",
        version="0.1.0",
        name="Bad accounting",
        category="test",
        description="Returns inconsistent sample counts.",
    )

    def execute(self, context):
        return Outcome(
            status=ResultStatus.NO_ISSUE_OBSERVED,
            measurements={},
            sample_accounting=SampleAccounting(input=3, evaluated=1, excluded=1),
        )


def test_builtin_test_runs_as_inconclusive() -> None:
    report = Runner(build_default_registry()).run(ProjectManifest(name="lab"))
    assert isinstance(report.run_id, UUID)
    assert report.summary.total == 1
    assert report.summary.inconclusive == 1
    assert report.results[0].status is ResultStatus.INCONCLUSIVE
    assert "no biometric model" in report.results[0].limitations[0]


def test_unknown_test_is_rejected_before_execution() -> None:
    with pytest.raises(UnknownTestError):
        Runner(build_default_registry()).run(ProjectManifest(name="lab"), ["missing.test"])


def test_duplicate_test_ids_are_rejected() -> None:
    registry = build_default_registry()
    with pytest.raises(ValueError, match="Duplicate"):
        Runner(registry).run(
            ProjectManifest(name="lab"),
            ["core.runtime-info", "core.runtime-info"],
        )


def test_test_exception_becomes_execution_error() -> None:
    registry = Registry()
    registry.register(BrokenTest())
    report = Runner(registry).run(ProjectManifest(name="lab"))
    result = report.results[0]
    assert result.status is ResultStatus.EXECUTION_ERROR
    assert result.error is not None
    assert result.error.error_type == "RuntimeError"
    assert "exception text was omitted" in result.error.message


def test_sample_accounting_mismatch_becomes_execution_error() -> None:
    registry = Registry()
    registry.register(BadAccountingTest())
    report = Runner(registry).run(ProjectManifest(name="lab"))
    assert report.results[0].status is ResultStatus.EXECUTION_ERROR
    assert "exception text was omitted" in report.results[0].error.message


class NonJsonTest:
    descriptor = Descriptor(
        test_id="test.non-json",
        version="0.1.0",
        name="Non-JSON output",
        category="test",
        description="Returns an unsupported measurement type.",
    )

    def execute(self, context):
        return Outcome(
            status=ResultStatus.NO_ISSUE_OBSERVED,
            measurements={"bad": object()},
        )


def test_non_json_measurements_become_execution_error() -> None:
    registry = Registry()
    registry.register(NonJsonTest())
    report = Runner(registry).run(ProjectManifest(name="lab"))
    assert report.results[0].status is ResultStatus.EXECUTION_ERROR
    assert report.summary.execution_error == 1


class SensitiveErrorTest:
    descriptor = Descriptor(
        test_id="test.sensitive-error",
        version="0.1.0",
        name="Sensitive error",
        category="test",
        description="Raises an exception containing a sentinel secret.",
    )

    def execute(self, context):
        raise RuntimeError("token=DO_NOT_DISCLOSE")


def test_exception_text_is_not_disclosed_in_result() -> None:
    registry = Registry()
    registry.register(SensitiveErrorTest())
    report = Runner(registry).run(ProjectManifest(name="lab"))
    serialized = report.model_dump_json()
    assert "DO_NOT_DISCLOSE" not in serialized
    assert report.results[0].status is ResultStatus.EXECUTION_ERROR
