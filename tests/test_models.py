import pytest
from pydantic import ValidationError

from voxrigor.models import ResultStatus, RunSummary, SampleAccounting
from voxrigor.models import TestDescriptor as Descriptor
from voxrigor.models import TestError as Error
from voxrigor.models import TestResult as Result


def test_status_vocabulary_is_complete() -> None:
    assert {status.value for status in ResultStatus} == {
        "vulnerable",
        "no_issue_observed",
        "inconclusive",
        "unsupported",
        "execution_error",
    }


def test_sample_accounting_reconciles() -> None:
    assert SampleAccounting(input=10, evaluated=8, excluded=2).is_reconciled()
    assert not SampleAccounting(input=10, evaluated=8, excluded=1).is_reconciled()


def test_descriptor_rejects_bad_identifier() -> None:
    with pytest.raises(ValidationError):
        Descriptor(
            test_id="BAD ID",
            version="0.1.0",
            name="Bad",
            category="test",
            description="Bad identifier",
        )


def test_run_summary_counts_are_nonnegative() -> None:
    with pytest.raises(ValidationError):
        RunSummary(
            total=-1,
            vulnerable=0,
            no_issue_observed=0,
            inconclusive=0,
            unsupported=0,
            execution_error=0,
        )


def test_run_summary_rejects_inconsistent_counts() -> None:
    with pytest.raises(ValidationError, match="sum exactly"):
        RunSummary(
            total=2,
            vulnerable=0,
            no_issue_observed=0,
            inconclusive=1,
            unsupported=0,
            execution_error=0,
        )


def test_execution_error_requires_error_metadata() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="must include sanitized error"):
        Result(
            run_id=uuid4(),
            test=Descriptor(
                test_id="test.sample",
                version="0.1.0",
                name="Sample",
                category="test",
                description="Sample result.",
            ),
            status=ResultStatus.EXECUTION_ERROR,
            started_at=now,
            finished_at=now,
        )


def test_non_execution_error_cannot_carry_error_metadata() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="only execution_error"):
        Result(
            run_id=uuid4(),
            test=Descriptor(
                test_id="test.sample",
                version="0.1.0",
                name="Sample",
                category="test",
                description="Sample result.",
            ),
            status=ResultStatus.INCONCLUSIVE,
            started_at=now,
            finished_at=now,
            error=Error(error_type="RuntimeError", message="redacted"),
        )
