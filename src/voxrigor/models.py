"""Versioned data models shared by the CLI, runner, and report writers."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MANIFEST_SCHEMA_VERSION = "0.1"
REPORT_SCHEMA_VERSION = "0.1"


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(UTC)


class ResultStatus(StrEnum):
    """A deliberately explicit result vocabulary."""

    VULNERABLE = "vulnerable"
    NO_ISSUE_OBSERVED = "no_issue_observed"
    INCONCLUSIVE = "inconclusive"
    UNSUPPORTED = "unsupported"
    EXECUTION_ERROR = "execution_error"


class ScopeConfig(BaseModel):
    """Phase 1 supports offline projects only; network targets come later."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["offline"] = "offline"
    note: str = "Offline evaluation only; no network target adapter is enabled."


class ProjectManifest(BaseModel):
    """Versioned, intentionally small project configuration."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    schema_version: Literal["0.1"] = MANIFEST_SCHEMA_VERSION
    project_id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    created_at: datetime = Field(default_factory=utc_now)
    scope: ScopeConfig = Field(default_factory=ScopeConfig)

    @field_validator("created_at")
    @classmethod
    def created_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value

    @field_validator("name")
    @classmethod
    def name_must_not_be_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("project name must contain a non-whitespace character")
        return value.strip()

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return value.strip()


class TestDescriptor(BaseModel):
    """Public metadata for a registered test; does not contain executable code."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    test_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,79}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[.-][a-zA-Z0-9.-]+)?$")
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)


class SampleAccounting(BaseModel):
    """Reconciled sample counts for a test that consumes sample records."""

    model_config = ConfigDict(extra="forbid")

    input: int = Field(default=0, ge=0)
    evaluated: int = Field(default=0, ge=0)
    excluded: int = Field(default=0, ge=0)

    def is_reconciled(self) -> bool:
        return self.input == self.evaluated + self.excluded


class TestError(BaseModel):
    """Sanitized exception metadata; tracebacks are not written to reports."""

    model_config = ConfigDict(extra="forbid")

    error_type: str
    message: str


class TestResult(BaseModel):
    """One test execution result in the common report envelope."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = REPORT_SCHEMA_VERSION
    run_id: UUID
    test: TestDescriptor
    status: ResultStatus
    started_at: datetime
    finished_at: datetime
    measurements: dict[str, Any] = Field(default_factory=dict)
    sample_accounting: SampleAccounting = Field(default_factory=SampleAccounting)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    error: TestError | None = None

    @field_validator("started_at", "finished_at")
    @classmethod
    def result_timestamps_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("test timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def finish_must_not_precede_start(self) -> TestResult:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        if self.status is ResultStatus.EXECUTION_ERROR and self.error is None:
            raise ValueError("execution_error results must include sanitized error metadata")
        if self.status is not ResultStatus.EXECUTION_ERROR and self.error is not None:
            raise ValueError("only execution_error results may include error metadata")
        return self


class RunProvenance(BaseModel):
    """Execution metadata intended to make a run auditable and reproducible."""

    model_config = ConfigDict(extra="forbid")

    framework_version: str
    python_version: str
    platform: str
    config_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    random_seed: int | None = None


class RunSummary(BaseModel):
    """Count of results by their explicit status."""

    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=0)
    vulnerable: int = Field(ge=0)
    no_issue_observed: int = Field(ge=0)
    inconclusive: int = Field(ge=0)
    unsupported: int = Field(ge=0)
    execution_error: int = Field(ge=0)

    @model_validator(mode="after")
    def counts_must_equal_total(self) -> RunSummary:
        status_total = (
            self.vulnerable
            + self.no_issue_observed
            + self.inconclusive
            + self.unsupported
            + self.execution_error
        )
        if status_total != self.total:
            raise ValueError("status counts must sum exactly to total")
        return self


class RunReport(BaseModel):
    """Versioned report generated for one local execution."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1"] = REPORT_SCHEMA_VERSION
    run_id: UUID
    project_id: UUID
    project_name: str
    started_at: datetime
    finished_at: datetime
    provenance: RunProvenance
    summary: RunSummary
    results: list[TestResult]

    @field_validator("started_at", "finished_at")
    @classmethod
    def run_timestamps_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("run timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def finish_must_not_precede_start(self) -> RunReport:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        if self.summary.total != len(self.results):
            raise ValueError("summary total must equal the number of result records")
        for result in self.results:
            if result.run_id != self.run_id:
                raise ValueError("every test result must belong to the report run_id")
        actual_counts = {status: 0 for status in ResultStatus}
        for result in self.results:
            actual_counts[result.status] += 1
        expected_counts = {
            ResultStatus.VULNERABLE: self.summary.vulnerable,
            ResultStatus.NO_ISSUE_OBSERVED: self.summary.no_issue_observed,
            ResultStatus.INCONCLUSIVE: self.summary.inconclusive,
            ResultStatus.UNSUPPORTED: self.summary.unsupported,
            ResultStatus.EXECUTION_ERROR: self.summary.execution_error,
        }
        if actual_counts != expected_counts:
            raise ValueError("summary status counts must match the result records")
        return self
