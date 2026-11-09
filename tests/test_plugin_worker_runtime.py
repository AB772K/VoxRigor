from __future__ import annotations

import io
import sys
from types import SimpleNamespace
from typing import cast

import pytest

from voxrigor.models import ResultStatus, SampleAccounting
from voxrigor.models import TestDescriptor as Descriptor
from voxrigor.plugin_worker import worker_main
from voxrigor.plugin_worker.protocol import (
    WORKER_PROTOCOL_VERSION,
    StagedInputReference,
    WorkerDescribeRequest,
    WorkerDescribeResponse,
    WorkerExecuteRequest,
    WorkerExecuteResponse,
    WorkerFailure,
    WorkerHello,
    WorkerResourceLimits,
    WorkerSampleAccounting,
    WorkerShutdownRequest,
    WorkerShutdownResponse,
    encode_worker_frame,
    read_worker_message,
)
from voxrigor.plugins import PLUGIN_API_VERSION, PluginMetadata
from voxrigor.testing import TestContext as Context
from voxrigor.testing import TestOutcome as Outcome
from voxrigor.testing import TestRegistry as Registry

REQUEST_ID = "123e4567-e89b-42d3-a456-426614174000"
EXECUTE_ID = "123e4567-e89b-42d3-a456-426614174001"


def _limits(wall_time: int = 30) -> WorkerResourceLimits:
    return WorkerResourceLimits(
        wall_time_seconds=wall_time,
        cpu_time_seconds=30,
        memory_bytes=268_435_456,
        process_count=4,
        open_file_count=64,
        output_bytes=1_048_576,
    )


def _metadata() -> PluginMetadata:
    return PluginMetadata(
        plugin_id="demo.voice",
        name="Demo voice plugin",
        version="0.1.0",
        api_version=PLUGIN_API_VERSION,
        publisher="VoxRigor worker tests",
        description="A plugin fixture for exercising the worker protocol loop.",
        required_permissions=[],
    )


def _descriptor() -> Descriptor:
    return Descriptor(
        test_id="demo.voice.diagnostic",
        version="0.1.0",
        name="Worker diagnostic",
        category="worker_test",
        description="Exercises the isolated worker bootstrap contract.",
    )


class _TestImplementation:
    descriptor = _descriptor()

    def __init__(self, outcome: Outcome | None = None, error: Exception | None = None) -> None:
        self.outcome = outcome or Outcome(
            status=ResultStatus.NO_ISSUE_OBSERVED,
            measurements={"passed": True, "score": 0.75},
            limitations=("Worker test fixture only.",),
            sample_accounting=SampleAccounting(),
        )
        self.error = error
        self.context: Context | None = None

    def execute(self, context: Context) -> Outcome:
        self.context = context
        if self.error is not None:
            raise self.error
        return self.outcome


def _registry(test: _TestImplementation | None = None) -> Registry:
    registry = Registry()
    registry.register(test or _TestImplementation())
    return registry


def _describe(limits: WorkerResourceLimits | None = None) -> WorkerDescribeRequest:
    return WorkerDescribeRequest(
        request_id=REQUEST_ID,
        plugin_id="demo.voice",
        limits=limits or _limits(),
    )


def _execute(
    *,
    limits: WorkerResourceLimits | None = None,
    plugin_id: str = "demo.voice",
    test_id: str = "demo.voice.diagnostic",
) -> WorkerExecuteRequest:
    return WorkerExecuteRequest(
        request_id=EXECUTE_ID,
        plugin_id=plugin_id,
        test_id=test_id,
        project_name="Worker test project",
        limits=limits or _limits(),
    )


def _serve(
    monkeypatch: pytest.MonkeyPatch,
    messages: list[bytes],
    metadata: PluginMetadata | None = None,
    registry: Registry | None = None,
) -> tuple[int, list[object]]:
    input_stream = io.BytesIO(b"".join(messages))
    output_stream = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=input_stream))
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=output_stream))
    monkeypatch.setattr(worker_main, "_apply_process_limits", lambda *_args: None)
    if metadata is not None and registry is not None:
        monkeypatch.setattr(
            worker_main,
            "_load_plugin",
            lambda *_args: (metadata, registry),
        )
    result = worker_main.serve()
    output_stream.seek(0)
    decoded: list[object] = []
    while (message := read_worker_message(output_stream)) is not None:
        decoded.append(message)
    return result, decoded


def test_worker_serve_completes_describe_execute_shutdown_handshake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    implementation = _TestImplementation()
    result, messages = _serve(
        monkeypatch,
        [
            encode_worker_frame(_describe()),
            encode_worker_frame(_execute()),
            encode_worker_frame(WorkerShutdownRequest()),
        ],
        metadata=_metadata(),
        registry=_registry(implementation),
    )

    assert result == 0
    assert isinstance(messages[0], WorkerHello)
    assert messages[0].protocol_version == WORKER_PROTOCOL_VERSION
    assert isinstance(messages[1], WorkerDescribeResponse)
    assert messages[1].request_id == REQUEST_ID
    assert messages[1].tests[0].test_id == "demo.voice.diagnostic"
    assert isinstance(messages[2], WorkerExecuteResponse)
    assert messages[2].request_id == EXECUTE_ID
    assert messages[2].measurements == {"passed": True, "score": 0.75}
    assert messages[2].sample_accounting == WorkerSampleAccounting()
    assert isinstance(messages[3], WorkerShutdownResponse)
    assert implementation.context is not None
    assert implementation.context.project.name == "Worker test project"


def test_worker_serve_rejects_execution_before_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, messages = _serve(monkeypatch, [encode_worker_frame(_execute())])

    assert result == 2
    assert isinstance(messages[0], WorkerHello)
    assert isinstance(messages[1], WorkerFailure)
    assert messages[1].code == "plugin_not_described"


def test_worker_serve_rejects_malformed_input_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    result, messages = _serve(monkeypatch, [b"{malformed json}\n"])

    assert result == 2
    assert len(messages) == 1
    assert isinstance(messages[0], WorkerHello)


def test_worker_serve_rejects_worker_to_host_message_from_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, messages = _serve(
        monkeypatch,
        [
            encode_worker_frame(
                WorkerHello(
                    protocol_version=WORKER_PROTOCOL_VERSION,
                    worker_version="host-fixture",
                    plugin_api_version=PLUGIN_API_VERSION,
                )
            )
        ],
    )

    assert result == 2
    assert len(messages) == 1
    assert isinstance(messages[0], WorkerHello)


def test_worker_serve_sanitizes_plugin_load_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    input_stream = io.BytesIO(encode_worker_frame(_describe()))
    output_stream = io.BytesIO()
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=input_stream))
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(buffer=output_stream))
    monkeypatch.setattr(worker_main, "_apply_process_limits", lambda *_args: None)

    def fail_load(*_args: object) -> tuple[PluginMetadata, Registry]:
        raise RuntimeError("private path and secret should never be sent")

    monkeypatch.setattr(worker_main, "_load_plugin", fail_load)
    assert worker_main.serve() == 2
    output_stream.seek(0)
    hello = read_worker_message(output_stream)
    failure = read_worker_message(output_stream)
    assert isinstance(hello, WorkerHello)
    assert isinstance(failure, WorkerFailure)
    assert failure.code == "plugin_load_error"
    assert "private path" not in failure.message


def test_worker_serve_rejects_second_plugin_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, messages = _serve(
        monkeypatch,
        [encode_worker_frame(_describe()), encode_worker_frame(_describe())],
        metadata=_metadata(),
        registry=_registry(),
    )

    assert result == 2
    assert isinstance(messages[1], WorkerDescribeResponse)
    assert isinstance(messages[2], WorkerFailure)
    assert messages[2].code == "session_already_described"


@pytest.mark.parametrize(
    ("plugin_id", "test_id", "limits", "expected_code"),
    [
        ("other.voice", "other.voice.diagnostic", None, "plugin_id_mismatch"),
        ("demo.voice", "demo.voice.diagnostic", _limits(wall_time=31), "resource_policy_mismatch"),
    ],
)
def test_worker_serve_rejects_mismatched_execution_identity_or_limits(
    monkeypatch: pytest.MonkeyPatch,
    plugin_id: str,
    test_id: str,
    limits: WorkerResourceLimits | None,
    expected_code: str,
) -> None:
    result, messages = _serve(
        monkeypatch,
        [
            encode_worker_frame(_describe()),
            encode_worker_frame(
                _execute(
                    plugin_id=plugin_id,
                    test_id=test_id,
                    limits=limits,
                )
            ),
        ],
        metadata=_metadata(),
        registry=_registry(),
    )

    assert result == 2
    assert isinstance(messages[-1], WorkerFailure)
    assert messages[-1].code == expected_code


def test_worker_serve_reports_plugin_execution_failure_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    implementation = _TestImplementation(error=RuntimeError("secret file /home/user/key"))
    result, messages = _serve(
        monkeypatch,
        [encode_worker_frame(_describe()), encode_worker_frame(_execute())],
        metadata=_metadata(),
        registry=_registry(implementation),
    )

    assert result == 0
    failure = messages[-1]
    assert isinstance(failure, WorkerFailure)
    assert failure.code == "plugin_execution_error"
    assert "/home/user/key" not in failure.message


def test_worker_serve_rejects_unreconciled_sample_accounting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    implementation = _TestImplementation(
        outcome=Outcome(
            status=ResultStatus.INCONCLUSIVE,
            measurements={},
            sample_accounting=SampleAccounting(input=2, evaluated=1, excluded=0),
        )
    )
    result, messages = _serve(
        monkeypatch,
        [encode_worker_frame(_describe()), encode_worker_frame(_execute())],
        metadata=_metadata(),
        registry=_registry(implementation),
    )

    assert result == 0
    assert isinstance(messages[-1], WorkerFailure)
    assert messages[-1].code == "plugin_execution_error"


def test_scalar_measurements_accept_only_bounded_finite_scalars() -> None:
    values = {"none": None, "text": "value", "flag": True, "count": 3, "ratio": 0.5}
    assert worker_main._scalar_measurements(values) == values

    with pytest.raises(worker_main.WorkerBootstrapError, match="invalid measurement key"):
        worker_main._scalar_measurements({"": "bad"})
    with pytest.raises(worker_main.WorkerBootstrapError, match="oversized"):
        worker_main._scalar_measurements({"text": "x" * 2049})
    with pytest.raises(worker_main.WorkerBootstrapError, match="finite"):
        worker_main._scalar_measurements({"score": float("nan")})
    with pytest.raises(worker_main.WorkerBootstrapError, match="only finite scalar"):
        worker_main._scalar_measurements({"nested": {"value": 1}})


def test_worker_rejects_staged_input_missing_from_container_mounts() -> None:
    request = _execute().model_copy(
        update={
            "staged_inputs": (
                StagedInputReference(
                    input_id="input-audio-1",
                    sha256="a" * 64,
                    size_bytes=1,
                    media_kind="audio",
                    display_name="sample.wav",
                ),
            )
        }
    )
    with pytest.raises(worker_main.WorkerBootstrapError, match="not available"):
        worker_main._staged_test_inputs(request)


def test_worker_requires_posix_resource_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker_main.os, "name", "nt")
    with pytest.raises(worker_main.WorkerBootstrapError, match="POSIX"):
        worker_main._apply_process_limits(30, 64)


def test_worker_entry_point_lookup_requires_exactly_one_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Entry:
        name = "demo.voice"

    monkeypatch.setattr(worker_main, "entry_points", lambda **_kwargs: [Entry()])
    assert worker_main._entry_point_for("demo.voice").name == "demo.voice"

    monkeypatch.setattr(worker_main, "entry_points", lambda **_kwargs: [])
    with pytest.raises(worker_main.WorkerBootstrapError, match="exactly one"):
        worker_main._entry_point_for("demo.voice")


def test_worker_load_plugin_imports_and_registers_inside_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Entry:
        name = "demo.voice"

        def load(self) -> object:
            class Plugin:
                metadata = _metadata()

                def register(self, context: object) -> None:
                    cast(worker_main.PluginRegistrationContext, context).register(
                        _TestImplementation()
                    )

            return Plugin

    monkeypatch.setattr(worker_main, "entry_points", lambda **_kwargs: [Entry()])
    metadata, registry = worker_main._load_plugin("demo.voice", ())
    assert metadata.plugin_id == "demo.voice"
    assert [item.test_id for item in registry.list()] == ["demo.voice.diagnostic"]


def test_worker_load_plugin_rejects_grants_that_do_not_match_plugin_declaration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Entry:
        name = "demo.voice"

        def load(self) -> object:
            class Plugin:
                metadata = _metadata()

                def register(self, context: object) -> None:
                    cast(worker_main.PluginRegistrationContext, context).register(
                        _TestImplementation()
                    )

            return Plugin

    monkeypatch.setattr(worker_main, "entry_points", lambda **_kwargs: [Entry()])
    with pytest.raises(worker_main.WorkerBootstrapError, match="permissions"):
        worker_main._load_plugin(
            "demo.voice",
            (worker_main.PluginPermission.AUDIO_READ,),
        )


def test_worker_main_converts_unhandled_bootstrap_error_to_exit_code_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker_main, "serve", lambda: 0)
    with pytest.raises(SystemExit) as exit_info:
        worker_main.main()
    assert exit_info.value.code == 0

    def interrupted() -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(worker_main, "serve", interrupted)
    with pytest.raises(SystemExit) as exit_info:
        worker_main.main()
    assert exit_info.value.code == 2
