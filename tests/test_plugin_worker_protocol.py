from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import pytest
from pydantic import ValidationError

from voxrigor.models import ResultStatus, TestDescriptor
from voxrigor.plugin_worker.isolation import (
    REQUIRED_ISOLATION_CONTROLS,
    IsolationBackendUnavailable,
    IsolationPolicy,
    IsolationReadiness,
    verify_isolation_backend,
)
from voxrigor.plugin_worker.protocol import (
    MAX_WORKER_FRAME_BYTES,
    WORKER_PROTOCOL_VERSION,
    StagedInputReference,
    WorkerDescribeResponse,
    WorkerExecuteRequest,
    WorkerExecuteResponse,
    WorkerHello,
    WorkerProtocolError,
    WorkerResourceLimits,
    decode_worker_frame,
    encode_worker_frame,
    read_worker_message,
    write_worker_message,
)
from voxrigor.plugins import PLUGIN_API_VERSION, PluginMetadata

REQUEST_ID = "123e4567-e89b-42d3-a456-426614174000"


def _hello() -> WorkerHello:
    return WorkerHello(
        protocol_version=WORKER_PROTOCOL_VERSION,
        worker_version="0.2.0.dev0",
        plugin_api_version=PLUGIN_API_VERSION,
    )


def _limits() -> WorkerResourceLimits:
    return WorkerResourceLimits(
        wall_time_seconds=30,
        cpu_time_seconds=30,
        memory_bytes=268_435_456,
        process_count=4,
        open_file_count=64,
        output_bytes=1_048_576,
    )


def _plugin_metadata() -> PluginMetadata:
    return PluginMetadata(
        plugin_id="demo.voice",
        name="Demo voice plugin",
        version="0.1.0",
        api_version=PLUGIN_API_VERSION,
        publisher="VoxRigor tests",
        description="Contract test fixture.",
        required_permissions=[],
    )


def _descriptor(test_id: str = "demo.voice.diagnostic") -> TestDescriptor:
    return TestDescriptor(
        test_id=test_id,
        version="0.1.0",
        name="Diagnostic",
        category="plugin_example",
        description="A harmless protocol contract test.",
    )


def test_worker_hello_round_trips_over_bounded_jsonl() -> None:
    message = _hello()
    stream = BytesIO()
    write_worker_message(stream, message)
    stream.seek(0)

    decoded = read_worker_message(stream)

    assert decoded == message
    assert read_worker_message(stream) is None


def test_worker_hello_rejects_unknown_or_mismatched_versions() -> None:
    with pytest.raises(ValidationError):
        WorkerHello(
            protocol_version="0.2",
            worker_version="0.2.0",
            plugin_api_version=PLUGIN_API_VERSION,
        )

    with pytest.raises(ValidationError):
        WorkerHello(
            protocol_version=WORKER_PROTOCOL_VERSION,
            worker_version="0.2.0",
            plugin_api_version="0.2",
        )


def test_decoder_rejects_duplicate_keys_and_unknown_message_types() -> None:
    duplicate = (
        b'{"kind":"hello","kind":"hello","protocol_version":"0.1",'
        b'"worker_version":"0.2.0","plugin_api_version":"0.1"}\n'
    )
    with pytest.raises(WorkerProtocolError, match="duplicate"):
        decode_worker_frame(duplicate)

    unknown = b'{"kind":"run-shell","command":"whoami"}\n'
    with pytest.raises(WorkerProtocolError, match="protocol validation"):
        decode_worker_frame(unknown)


def test_decoder_rejects_invalid_utf8_nonstandard_numbers_and_crlf() -> None:
    with pytest.raises(WorkerProtocolError, match="UTF-8"):
        decode_worker_frame(b"\xff\n")

    with pytest.raises(WorkerProtocolError, match="non-standard JSON"):
        decode_worker_frame(b'{"kind":"failure","request_id":"' + REQUEST_ID.encode() + b'","code":"test","message":"x","extra":NaN}\n')

    with pytest.raises(WorkerProtocolError, match="CRLF"):
        decode_worker_frame(encode_worker_frame(_hello())[:-1] + b"\r\n")


def test_reader_rejects_truncated_and_oversized_frames() -> None:
    with pytest.raises(WorkerProtocolError, match="truncated"):
        read_worker_message(BytesIO(b'{"kind":"hello"}'))

    with pytest.raises(WorkerProtocolError, match="exceeds"):
        read_worker_message(BytesIO(b"x" * (MAX_WORKER_FRAME_BYTES + 2) + b"\n"))


def test_encoder_enforces_caller_supplied_frame_limit() -> None:
    with pytest.raises(WorkerProtocolError, match="exceeds"):
        encode_worker_frame(_hello(), max_bytes=8)


def test_description_rejects_tests_outside_plugin_namespace_and_duplicates() -> None:
    metadata = _plugin_metadata()
    with pytest.raises(ValidationError, match="outside its plugin namespace"):
        WorkerDescribeResponse(
            request_id=REQUEST_ID,
            metadata=metadata,
            tests=[_descriptor("other.plugin.test")],
        )

    with pytest.raises(ValidationError, match="duplicate"):
        WorkerDescribeResponse(
            request_id=REQUEST_ID,
            metadata=metadata,
            tests=[_descriptor(), _descriptor()],
        )


def test_staged_input_reference_does_not_accept_host_paths() -> None:
    with pytest.raises(ValidationError, match="plain filename"):
        StagedInputReference(
            input_id="input-1",
            sha256="a" * 64,
            size_bytes=100,
            media_kind="audio",
            display_name="../secret.wav",
        )

    with pytest.raises(ValidationError, match="plain filename"):
        StagedInputReference(
            input_id="input-1",
            sha256="a" * 64,
            size_bytes=100,
            media_kind="audio",
            display_name=r"C:\Users\user\secret.wav",
        )


def test_execute_request_only_accepts_namespaced_test_and_opaque_input_refs() -> None:
    staged = StagedInputReference(
        input_id="input-audio-1",
        sha256="b" * 64,
        size_bytes=1024,
        media_kind="audio",
        display_name="sample.wav",
    )
    request = WorkerExecuteRequest(
        request_id=REQUEST_ID,
        plugin_id="demo.voice",
        test_id="demo.voice.diagnostic",
        project_name="Worker contract",
        staged_inputs=[staged],
        limits=_limits(),
    )
    assert request.staged_inputs[0].input_id == "input-audio-1"

    with pytest.raises(ValidationError, match="namespace"):
        WorkerExecuteRequest(
            request_id=REQUEST_ID,
            plugin_id="demo.voice",
            test_id="core.runtime-info",
            project_name="Worker contract",
            limits=_limits(),
        )

    with pytest.raises(ValidationError, match="extra"):
        WorkerExecuteRequest.model_validate(
            {
                "request_id": REQUEST_ID,
                "plugin_id": "demo.voice",
                "test_id": "demo.voice.diagnostic",
                "project_name": "Worker contract",
                "staged_inputs": [],
                "limits": _limits().model_dump(),
                "path": "C:/Users/secret",
            }
        )


def test_worker_result_rejects_non_finite_and_nested_measurements() -> None:
    with pytest.raises(ValidationError, match="finite"):
        WorkerExecuteResponse(
            request_id=REQUEST_ID,
            plugin_id="demo.voice",
            test_id="demo.voice.diagnostic",
            status=ResultStatus.INCONCLUSIVE,
            measurements={"score": float("nan")},
        )

    with pytest.raises(ValidationError):
        WorkerExecuteResponse.model_validate(
            {
                "kind": "result",
                "request_id": REQUEST_ID,
                "plugin_id": "demo.voice",
                "test_id": "demo.voice.diagnostic",
                "status": "inconclusive",
                "measurements": {"nested": {"secret": "value"}},
                "limitations": [],
                "sample_accounting": {"input": 0, "evaluated": 0, "excluded": 0},
            }
        )


@dataclass
class FakeIsolationBackend:
    readiness: IsolationReadiness
    calls: int = 0
    backend_id_value: str = "fake-test-backend"

    @property
    def backend_id(self) -> str:
        return self.backend_id_value

    def preflight(self, policy: IsolationPolicy) -> IsolationReadiness:
        self.calls += 1
        return self.readiness


def _readiness(
    controls: tuple[str, ...] | None = None,
    *,
    verified: bool = True,
    backend_id: str = "fake-test-backend",
) -> IsolationReadiness:
    return IsolationReadiness(
        backend_id=backend_id,
        runtime_version="test-runtime-1",
        verified=verified,
        enforced_controls=list(controls or sorted(REQUIRED_ISOLATION_CONTROLS)),
    )


def test_isolation_backend_contract_fails_closed_when_none_is_registered() -> None:
    with pytest.raises(IsolationBackendUnavailable, match="No production"):
        verify_isolation_backend(None)


def test_isolation_backend_contract_requires_every_control() -> None:
    missing = set(REQUIRED_ISOLATION_CONTROLS)
    missing.remove("no_network")
    backend = FakeIsolationBackend(_readiness(tuple(sorted(missing))))

    with pytest.raises(IsolationBackendUnavailable, match="no_network"):
        verify_isolation_backend(backend)

    assert backend.calls == 1


def test_isolation_backend_contract_requires_verified_identity() -> None:
    unverified = FakeIsolationBackend(_readiness(verified=False))
    with pytest.raises(IsolationBackendUnavailable, match="did not verify"):
        verify_isolation_backend(unverified)

    wrong_identity = FakeIsolationBackend(_readiness(backend_id="another-backend"))
    with pytest.raises(IsolationBackendUnavailable, match="identity"):
        verify_isolation_backend(wrong_identity)


def test_unsupported_permissions_are_refused_before_backend_preflight() -> None:
    backend = FakeIsolationBackend(_readiness())
    policy = IsolationPolicy(network_enabled=True)

    with pytest.raises(IsolationBackendUnavailable, match="not supported"):
        verify_isolation_backend(backend, policy)

    assert backend.calls == 0


def test_complete_fake_preflight_contract_is_accepted_but_is_not_a_real_sandbox() -> None:
    backend = FakeIsolationBackend(_readiness())

    readiness = verify_isolation_backend(backend)

    assert readiness.verified is True
    assert readiness.backend_id == backend.backend_id
    assert backend.calls == 1
