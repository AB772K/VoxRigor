"""Strict, bounded JSON-lines protocol types for an isolated plugin worker.

Messages contain data only. This module deliberately does not transport file
paths, Python objects, callables, arbitrary import paths or executable code.
"""

from __future__ import annotations

import json
import math
from collections.abc import BinaryIO
from typing import Annotated, TypeAlias, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from voxrigor.models import ResultStatus, TestDescriptor
from voxrigor.plugins import PLUGIN_API_VERSION, PluginMetadata

WORKER_PROTOCOL_VERSION = "0.1"
MAX_WORKER_FRAME_BYTES = 1_048_576
MAX_WORKER_INPUTS = 128
MAX_WORKER_TESTS = 256
MAX_WORKER_MEASUREMENTS = 128
_REQUEST_ID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
_PLUGIN_ID_PATTERN = r"^[a-z][a-z0-9_.-]{2,79}$"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_OPAQUE_ID_PATTERN = r"^[a-zA-Z0-9_-]{1,64}$"

MeasurementValue: TypeAlias = str | int | float | bool | None


class WorkerProtocolError(ValueError):
    """Raised when a worker protocol frame is malformed, oversized or invalid."""


class _WorkerModel(BaseModel):
    """Strict base class for all IPC messages."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class WorkerResourceLimits(_WorkerModel):
    """Host-selected hard limits to be enforced by the OS backend."""

    wall_time_seconds: int = Field(ge=1, le=3600)
    cpu_time_seconds: int = Field(ge=1, le=3600)
    memory_bytes: int = Field(ge=134_217_728, le=8_589_934_592)
    process_count: int = Field(ge=1, le=64)
    open_file_count: int = Field(ge=16, le=1024)
    output_bytes: int = Field(ge=0, le=536_870_912)


class StagedInputReference(_WorkerModel):
    """Opaque reference to a host-staged, read-only input; never a host path."""

    input_id: str = Field(pattern=_OPAQUE_ID_PATTERN)
    sha256: str = Field(pattern=_SHA256_PATTERN)
    size_bytes: int = Field(ge=0, le=2_147_483_648)
    media_kind: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,31}$")
    display_name: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def display_name_must_not_be_a_path(self) -> StagedInputReference:
        if "/" in self.display_name or "\\" in self.display_name or self.display_name in {".", ".."}:
            raise ValueError("display_name must be a plain filename, not a path")
        return self


class WorkerHello(_WorkerModel):
    """First worker-to-host frame; proves protocol/API versions, not isolation."""

    kind: LiteralHello = "hello"
    protocol_version: str = Field(pattern=r"^\d+\.\d+$")
    worker_version: str = Field(min_length=1, max_length=64)
    plugin_api_version: str = Field(pattern=r"^\d+\.\d+$")


class WorkerDescribeRequest(_WorkerModel):
    """Host request for plugin metadata and its registered test descriptors."""

    kind: LiteralDescribeRequest = "describe"
    request_id: str = Field(pattern=_REQUEST_ID_PATTERN)
    plugin_id: str = Field(pattern=_PLUGIN_ID_PATTERN)


class WorkerDescribeResponse(_WorkerModel):
    """Worker response containing validated metadata and test descriptors."""

    kind: LiteralDescribeResponse = "description"
    request_id: str = Field(pattern=_REQUEST_ID_PATTERN)
    metadata: PluginMetadata
    tests: tuple[TestDescriptor, ...] = Field(min_length=1, max_length=MAX_WORKER_TESTS)

    @model_validator(mode="after")
    def test_ids_must_be_namespaced_and_unique(self) -> WorkerDescribeResponse:
        prefix = f"{self.metadata.plugin_id}."
        ids = [item.test_id for item in self.tests]
        if len(ids) != len(set(ids)):
            raise ValueError("worker description contains duplicate test IDs")
        if any(not item.startswith(prefix) for item in ids):
            raise ValueError("worker description contains a test outside its plugin namespace")
        return self


class WorkerExecuteRequest(_WorkerModel):
    """Host request to execute one test using only staged-input references."""

    kind: LiteralExecuteRequest = "execute"
    request_id: str = Field(pattern=_REQUEST_ID_PATTERN)
    plugin_id: str = Field(pattern=_PLUGIN_ID_PATTERN)
    test_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,79}$")
    project_name: str = Field(min_length=1, max_length=120)
    staged_inputs: tuple[StagedInputReference, ...] = Field(default=(), max_length=MAX_WORKER_INPUTS)
    limits: WorkerResourceLimits

    @model_validator(mode="after")
    def input_ids_must_be_unique_and_test_must_be_namespaced(self) -> WorkerExecuteRequest:
        ids = [item.input_id for item in self.staged_inputs]
        if len(ids) != len(set(ids)):
            raise ValueError("staged input IDs must be unique")
        if not self.test_id.startswith(f"{self.plugin_id}."):
            raise ValueError("test_id must be inside the requested plugin namespace")
        return self


class WorkerSampleAccounting(_WorkerModel):
    """Sample counts returned as data; reconciliation is checked by the host."""

    input: int = Field(default=0, ge=0)
    evaluated: int = Field(default=0, ge=0)
    excluded: int = Field(default=0, ge=0)

    def is_reconciled(self) -> bool:
        return self.input == self.evaluated + self.excluded


class WorkerExecuteResponse(_WorkerModel):
    """Constrained worker result; all values are untrusted until host validation."""

    kind: LiteralExecuteResponse = "result"
    request_id: str = Field(pattern=_REQUEST_ID_PATTERN)
    plugin_id: str = Field(pattern=_PLUGIN_ID_PATTERN)
    test_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,79}$")
    status: ResultStatus
    measurements: dict[str, MeasurementValue] = Field(default_factory=dict, max_length=MAX_WORKER_MEASUREMENTS)
    limitations: tuple[str, ...] = Field(default=(), max_length=64)
    sample_accounting: WorkerSampleAccounting = Field(default_factory=WorkerSampleAccounting)

    @model_validator(mode="after")
    def result_values_must_be_bounded(self) -> WorkerExecuteResponse:
        if not self.test_id.startswith(f"{self.plugin_id}."):
            raise ValueError("result test_id is outside its plugin namespace")
        for key, value in self.measurements.items():
            if not key or len(key) > 80:
                raise ValueError("measurement keys must contain 1–80 characters")
            if isinstance(value, str) and len(value) > 2048:
                raise ValueError("measurement strings must be at most 2048 characters")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("measurement floats must be finite")
        if any(not item or len(item) > 500 for item in self.limitations):
            raise ValueError("limitations must contain 1–500 characters")
        return self


class WorkerFailure(_WorkerModel):
    """Sanitized worker failure. Tracebacks and local paths are not part of IPC."""

    kind: LiteralFailure = "failure"
    request_id: str = Field(pattern=_REQUEST_ID_PATTERN)
    code: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,47}$")
    message: str = Field(min_length=1, max_length=500)


class WorkerCancelRequest(_WorkerModel):
    """Host cancellation request for the active execution request."""

    kind: LiteralCancelRequest = "cancel"
    request_id: str = Field(pattern=_REQUEST_ID_PATTERN)


class WorkerCancelled(_WorkerModel):
    """Worker acknowledgement of cooperative cancellation."""

    kind: LiteralCancelled = "cancelled"
    request_id: str = Field(pattern=_REQUEST_ID_PATTERN)


class WorkerShutdownRequest(_WorkerModel):
    """Host request to close the worker after the current operation."""

    kind: LiteralShutdownRequest = "shutdown"


class WorkerShutdownResponse(_WorkerModel):
    """Worker acknowledgement that it is ready to exit."""

    kind: LiteralShutdownResponse = "shutdown_ack"


LiteralHello: TypeAlias = str
LiteralDescribeRequest: TypeAlias = str
LiteralDescribeResponse: TypeAlias = str
LiteralExecuteRequest: TypeAlias = str
LiteralExecuteResponse: TypeAlias = str
LiteralFailure: TypeAlias = str
LiteralCancelRequest: TypeAlias = str
LiteralCancelled: TypeAlias = str
LiteralShutdownRequest: TypeAlias = str
LiteralShutdownResponse: TypeAlias = str


WorkerMessage: TypeAlias = Annotated[
    Union[
        WorkerHello,
        WorkerDescribeRequest,
        WorkerDescribeResponse,
        WorkerExecuteRequest,
        WorkerExecuteResponse,
        WorkerFailure,
        WorkerCancelRequest,
        WorkerCancelled,
        WorkerShutdownRequest,
        WorkerShutdownResponse,
    ],
    Field(discriminator="kind"),
]
_WORKER_MESSAGE_ADAPTER = TypeAdapter(WorkerMessage)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise WorkerProtocolError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise WorkerProtocolError(f"non-standard JSON constant is not permitted: {value}")


def decode_worker_frame(frame: bytes, *, max_bytes: int = MAX_WORKER_FRAME_BYTES) -> WorkerMessage:
    """Decode exactly one LF-terminated UTF-8 JSON frame and validate its schema."""

    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    if len(frame) > max_bytes + 1:
        raise WorkerProtocolError(f"worker frame exceeds {max_bytes} bytes")
    if not frame.endswith(b"\n"):
        raise WorkerProtocolError("worker frame must end with LF")
    payload = frame[:-1]
    if payload.endswith(b"\r"):
        raise WorkerProtocolError("CRLF frames are not supported; use LF")
    if len(payload) > max_bytes:
        raise WorkerProtocolError(f"worker frame exceeds {max_bytes} bytes")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise WorkerProtocolError("worker frame is not valid UTF-8") from exc
    try:
        raw = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
        return _WORKER_MESSAGE_ADAPTER.validate_python(raw)
    except WorkerProtocolError:
        raise
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise WorkerProtocolError(f"worker frame failed protocol validation: {type(exc).__name__}") from exc


def encode_worker_frame(message: WorkerMessage, *, max_bytes: int = MAX_WORKER_FRAME_BYTES) -> bytes:
    """Encode one validated message as bounded UTF-8 JSON followed by LF."""

    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    try:
        payload = json.dumps(
            message.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise WorkerProtocolError("worker message could not be encoded as strict JSON") from exc
    if len(payload) > max_bytes:
        raise WorkerProtocolError(f"encoded worker frame exceeds {max_bytes} bytes")
    return payload + b"\n"


def read_worker_message(
    stream: BinaryIO,
    *,
    max_bytes: int = MAX_WORKER_FRAME_BYTES,
) -> WorkerMessage | None:
    """Read one bounded frame; return None only on clean EOF before a frame."""

    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    frame = stream.readline(max_bytes + 2)
    if frame == b"":
        return None
    if len(frame) > max_bytes + 1:
        raise WorkerProtocolError(f"worker frame exceeds {max_bytes} bytes")
    if not frame.endswith(b"\n"):
        raise WorkerProtocolError("truncated worker frame or missing LF terminator")
    return decode_worker_frame(frame, max_bytes=max_bytes)


def write_worker_message(
    stream: BinaryIO,
    message: WorkerMessage,
    *,
    max_bytes: int = MAX_WORKER_FRAME_BYTES,
) -> None:
    """Write one bounded frame and flush it immediately."""

    frame = encode_worker_frame(message, max_bytes=max_bytes)
    stream.write(frame)
    stream.flush()
