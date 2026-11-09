from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from voxrigor.models import ResultStatus
from voxrigor.models import TestDescriptor as Descriptor
from voxrigor.plugin_worker import podman as podman_module
from voxrigor.plugin_worker.isolation import (
    REQUIRED_ISOLATION_CONTROLS,
    IsolationPolicy,
    IsolationReadiness,
)
from voxrigor.plugin_worker.podman import (
    HostStagedInput,
    PodmanBackendError,
    RootlessPodmanBackend,
    WorkerExecutionError,
    WorkerExecutionSpec,
    _WorkerSession,
    execute_isolated_plugin_test,
)
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
)
from voxrigor.plugins import PLUGIN_API_VERSION, PluginMetadata

IMAGE = "registry.example.invalid/voxrigor-worker@sha256:" + "a" * 64
REQUEST_ID = "123e4567-e89b-42d3-a456-426614174000"


def _backend() -> RootlessPodmanBackend:
    return RootlessPodmanBackend(worker_image=IMAGE)


def _metadata() -> PluginMetadata:
    return PluginMetadata(
        plugin_id="demo.voice",
        name="Demo voice plugin",
        version="0.1.0",
        api_version=PLUGIN_API_VERSION,
        publisher="VoxRigor worker tests",
        description="Metadata used by host supervisor tests.",
        required_permissions=[],
    )


def _descriptor() -> Descriptor:
    return Descriptor(
        test_id="demo.voice.diagnostic",
        version="0.1.0",
        name="Worker diagnostic",
        category="worker_test",
        description="A fake worker test descriptor.",
    )


def _limits(policy: IsolationPolicy | None = None) -> WorkerResourceLimits:
    selected = policy or IsolationPolicy()
    return WorkerResourceLimits(
        wall_time_seconds=selected.wall_time_seconds,
        cpu_time_seconds=selected.cpu_time_seconds,
        memory_bytes=selected.memory_bytes,
        process_count=selected.process_count,
        open_file_count=selected.open_file_count,
        output_bytes=selected.output_bytes,
    )


def _container_document(policy: IsolationPolicy | None = None) -> dict[str, object]:
    selected = policy or IsolationPolicy()
    return {
        "HostConfig": {
            "ReadonlyRootfs": True,
            "NetworkMode": "none",
            "PidMode": "private",
            "IpcMode": "private",
            "Memory": selected.memory_bytes,
            "PidsLimit": selected.process_count,
            "NanoCpus": 1_000_000_000,
            "UsernsMode": "auto",
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
            "Devices": [],
            "Ulimits": [
                {
                    "Name": "cpu",
                    "Soft": selected.cpu_time_seconds,
                    "Hard": selected.cpu_time_seconds,
                },
                {
                    "Name": "nofile",
                    "Soft": selected.open_file_count,
                    "Hard": selected.open_file_count,
                },
            ],
            "Tmpfs": {
                "/tmp": "rw,noexec,nosuid,nodev,size=16777216",
                "/output": f"ro,noexec,nosuid,nodev,size={selected.output_bytes}",
            },
            "Binds": [],
            "VolumesFrom": [],
        },
        "Config": {
            "User": "10001:10001",
            "Env": [
                "HOME=/tmp/worker-home",
                "PATH=/usr/local/bin:/usr/bin:/bin",
                "PYTHONNOUSERSITE=1",
                "PYTHONDONTWRITEBYTECODE=1",
            ],
        },
    }


def _spec(policy: IsolationPolicy | None = None) -> WorkerExecutionSpec:
    return WorkerExecutionSpec(
        plugin_id="demo.voice",
        test_id="demo.voice.diagnostic",
        project_name="Worker supervisor tests",
        policy=policy or IsolationPolicy(),
    )


class _FakeSession:
    def __init__(
        self,
        *,
        hello: object | None = None,
        description: object | None = None,
        result: object | None = None,
        shutdown: object | None = None,
    ) -> None:
        self.responses = [
            hello
            or WorkerHello(
                protocol_version=WORKER_PROTOCOL_VERSION,
                worker_version="0.2.0",
                plugin_api_version=PLUGIN_API_VERSION,
            )
        ]
        self.description = description
        self.result = result
        self.shutdown = shutdown or WorkerShutdownResponse()
        self.sent: list[object] = []
        self.closed = False

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *_args: object) -> None:
        self.closed = True

    def send(self, message: object) -> None:
        self.sent.append(message)
        if isinstance(message, WorkerDescribeRequest):
            response = self.description
            if response is None:
                response = WorkerDescribeResponse(
                    request_id=message.request_id,
                    metadata=_metadata(),
                    tests=[_descriptor()],
                )
            self.responses.append(response)
        elif isinstance(message, WorkerExecuteRequest):
            response = self.result
            if response is None:
                response = WorkerExecuteResponse(
                    request_id=message.request_id,
                    plugin_id=message.plugin_id,
                    test_id=message.test_id,
                    status=ResultStatus.NO_ISSUE_OBSERVED,
                    measurements={"passed": True},
                    sample_accounting=WorkerSampleAccounting(),
                )
            self.responses.append(response)
        elif isinstance(message, WorkerShutdownRequest):
            self.responses.append(self.shutdown)

    def receive(self, _timeout: float) -> object:
        if not self.responses:
            raise AssertionError("The host requested more worker messages than the fake supplied")
        return self.responses.pop(0)

    def wait(self, _timeout: float) -> int:
        return 0


def test_run_checked_returns_stdout_and_rejects_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend()
    monkeypatch.setattr(
        podman_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="ok\n", stderr=""),
    )
    assert (
        backend._run_checked(["podman", "version"], timeout=3, operation="read version")
        == "ok\n"
    )

    monkeypatch.setattr(
        podman_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=125, stdout="", stderr="runtime denied"
        ),
    )
    with pytest.raises(PodmanBackendError, match="runtime denied"):
        backend._run_checked(["podman", "info"], timeout=3, operation="inspect runtime")


@pytest.mark.parametrize(
    "error", [OSError("missing podman"), subprocess.TimeoutExpired("podman", 1)]
)
def test_run_checked_wraps_host_process_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    backend = _backend()

    def fail(*_args: object, **_kwargs: object) -> object:
        raise error

    monkeypatch.setattr(podman_module.subprocess, "run", fail)
    with pytest.raises(PodmanBackendError, match="could not inspect runtime"):
        backend._run_checked(["podman", "info"], timeout=1, operation="inspect runtime")


def test_json_document_accepts_object_or_singleton_list_and_rejects_bad_shapes() -> None:
    assert _backend()._json_document('{"ok": true}', operation="test") == {"ok": True}
    assert _backend()._json_document('[{"id": "abc"}]', operation="test") == {"id": "abc"}
    with pytest.raises(PodmanBackendError, match="invalid JSON"):
        _backend()._json_document("{bad", operation="test")
    with pytest.raises(PodmanBackendError, match="unexpected JSON shape"):
        _backend()._json_document("[]", operation="test")


def test_nested_json_helper_stops_at_non_mapping_values() -> None:
    assert (
        _backend()._nested(
            {"host": {"security": {"rootless": True}}}, "host", "security", "rootless"
        )
        is True
    )
    assert _backend()._nested({"host": None}, "host", "security") is None


def test_runtime_preflight_checks_rootless_seccomp_cgroups_and_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend()
    monkeypatch.setattr(podman_module.sys, "platform", "linux")
    monkeypatch.setattr(podman_module.os, "name", "posix")
    monkeypatch.setattr(podman_module.os, "geteuid", lambda: 1000, raising=False)
    monkeypatch.setattr(podman_module.shutil, "which", lambda _binary: "/usr/bin/podman")
    calls: list[list[str]] = []

    def checked(command: list[str], **_kwargs: object) -> str:
        calls.append(command)
        if "info" in command:
            return json.dumps(
                {
                    "host": {
                        "security": {"rootless": True, "seccompEnabled": True},
                        "cgroupVersion": "v2",
                    }
                }
            )
        return ""

    monkeypatch.setattr(backend, "_run_checked", checked)
    info = backend._runtime_preflight()
    assert backend._nested(info, "host", "security", "rootless") is True
    assert len(calls) == 2
    assert calls[1][:3] == ["podman", "image", "exists"]


@pytest.mark.parametrize(
    ("runtime", "expected"),
    [
        (
            {
                "host": {
                    "security": {"rootless": False, "seccompEnabled": True},
                    "cgroupVersion": "v2",
                }
            },
            "not rootless",
        ),
        (
            {
                "host": {
                    "security": {"rootless": True, "seccompEnabled": False},
                    "cgroupVersion": "v2",
                }
            },
            "seccomp",
        ),
        (
            {
                "host": {
                    "security": {"rootless": True, "seccompEnabled": True},
                    "cgroupVersion": "v1",
                }
            },
            "cgroups v2",
        ),
    ],
)
def test_runtime_preflight_fails_closed_for_weak_runtime(
    monkeypatch: pytest.MonkeyPatch,
    runtime: dict[str, object],
    expected: str,
) -> None:
    backend = _backend()
    monkeypatch.setattr(podman_module.sys, "platform", "linux")
    monkeypatch.setattr(podman_module.os, "name", "posix")
    monkeypatch.setattr(podman_module.os, "geteuid", lambda: 1000, raising=False)
    monkeypatch.setattr(podman_module.shutil, "which", lambda _binary: "/usr/bin/podman")
    monkeypatch.setattr(backend, "_run_checked", lambda *_args, **_kwargs: json.dumps(runtime))
    with pytest.raises(PodmanBackendError, match=expected):
        backend._runtime_preflight()


def test_verify_container_accepts_inspected_policy_and_rejects_missing_host_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend()
    document = _container_document()
    monkeypatch.setattr(backend, "_run_checked", lambda *_args, **_kwargs: json.dumps(document))
    backend._verify_container("container-id", IsolationPolicy(), expected_binds=())

    monkeypatch.setattr(
        backend, "_run_checked", lambda *_args, **_kwargs: json.dumps({"Config": {}})
    )
    with pytest.raises(PodmanBackendError, match="HostConfig"):
        backend._verify_container("container-id", IsolationPolicy(), expected_binds=())


def test_verify_container_document_rejects_unapproved_mount_type_and_rw_staged_input() -> None:
    document = _container_document()
    document["Mounts"] = [{"Type": "volume", "Destination": "/unexpected"}]
    with pytest.raises(PodmanBackendError, match="volumes"):
        RootlessPodmanBackend._verify_container_document(
            document,
            IsolationPolicy(),
            expected_binds=(),
        )

    document = _container_document()
    document["HostConfig"]["Binds"] = ["/tmp/staged:/inputs/input-audio-1:rw"]
    document["Mounts"] = [{"Type": "bind", "Destination": "/inputs/input-audio-1", "RW": True}]
    with pytest.raises(PodmanBackendError, match="read-only"):
        RootlessPodmanBackend._verify_container_document(
            document,
            IsolationPolicy(),
            expected_binds=(("/tmp/staged", "/inputs/input-audio-1"),),
        )


def test_create_and_inspect_removes_container_when_verification_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend()
    removed: list[str] = []
    monkeypatch.setattr(backend, "_run_checked", lambda *_args, **_kwargs: "container-id\n")
    monkeypatch.setattr(
        backend,
        "_verify_container",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PodmanBackendError("bad config")),
    )
    monkeypatch.setattr(
        backend, "_remove_container", lambda container_id: removed.append(container_id)
    )

    with pytest.raises(PodmanBackendError, match="bad config"):
        backend._create_and_inspect(IsolationPolicy(), command=["podman", "create"])
    assert removed == ["container-id"]


def test_remove_container_swallows_cleanup_process_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> object:
        raise OSError("podman already gone")

    monkeypatch.setattr(podman_module.subprocess, "run", fail)
    _backend()._remove_container("container-id")


def test_run_probe_accepts_verified_json_and_rejects_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend()
    monkeypatch.setattr(
        podman_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=0,
            stdout='{"ok": true, "uid": 10001}\n',
            stderr="",
        ),
    )
    backend._run_probe("container-id")

    monkeypatch.setattr(
        podman_module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="", stderr="probe failed"),
    )
    with pytest.raises(PodmanBackendError, match="probe failed"):
        backend._run_probe("container-id")


def test_preflight_runs_the_container_probe_and_always_removes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend()
    removed: list[str] = []
    monkeypatch.setattr(backend, "_runtime_preflight", lambda: {})
    monkeypatch.setattr(backend, "_create_and_inspect", lambda *_args, **_kwargs: "probe-id")
    monkeypatch.setattr(backend, "_run_probe", lambda _container: None)
    monkeypatch.setattr(backend, "_remove_container", lambda container_id: removed.append(container_id))

    readiness = backend.preflight(IsolationPolicy())

    assert readiness.verified is True
    assert readiness.backend_id == backend.backend_id
    assert set(readiness.enforced_controls) == REQUIRED_ISOLATION_CONTROLS
    assert removed == ["probe-id"]


def test_preflight_removes_probe_container_even_when_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend()
    removed: list[str] = []
    monkeypatch.setattr(backend, "_runtime_preflight", lambda: {})
    monkeypatch.setattr(backend, "_create_and_inspect", lambda *_args, **_kwargs: "probe-id")
    monkeypatch.setattr(
        backend,
        "_run_probe",
        lambda _container: (_ for _ in ()).throw(PodmanBackendError("probe refused")),
    )
    monkeypatch.setattr(backend, "_remove_container", lambda container_id: removed.append(container_id))

    with pytest.raises(PodmanBackendError, match="probe refused"):
        backend.preflight(IsolationPolicy())
    assert removed == ["probe-id"]


def test_copy_staged_inputs_rejects_symlinks_and_size_mismatches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "sample.wav"
    source.write_bytes(b"abc")
    reference = StagedInputReference(
        input_id="input-audio-1",
        sha256=hashlib.sha256(b"abc").hexdigest(),
        size_bytes=3,
        media_kind="audio",
        display_name="sample.wav",
    )
    original_is_symlink = Path.is_symlink

    def fake_symlink_check(path: Path) -> bool:
        return path == source.absolute() or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", fake_symlink_check)
    with pytest.raises(WorkerExecutionError, match="Symlinked"):
        RootlessPodmanBackend._copy_staged_inputs(
            (HostStagedInput(reference=reference, source_path=source),)
        )
    monkeypatch.setattr(Path, "is_symlink", original_is_symlink)

    wrong_size = reference.model_copy(update={"size_bytes": 4})
    with pytest.raises(WorkerExecutionError, match="size"):
        RootlessPodmanBackend._copy_staged_inputs(
            (HostStagedInput(reference=wrong_size, source_path=source),)
        )


def test_launch_returns_a_not_yet_started_session_and_cleans_on_policy_failure() -> None:
    backend = _backend()
    session = backend.launch(_spec())
    assert isinstance(session, _WorkerSession)
    assert session.process is None
    session.close()

    with pytest.raises(PodmanBackendError, match="Initial worker policy denies"):
        backend.launch(_spec(IsolationPolicy(network_enabled=True)))


class _FakeProcess:
    def __init__(self, *, return_code: int | None = None) -> None:
        self.stdin = io.BytesIO()
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()
        self.return_code = return_code
        self.wait_calls = 0
        self.killed = False

    def poll(self) -> int | None:
        return self.return_code

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls += 1
        if self.return_code is not None:
            return self.return_code
        self.return_code = 0
        return 0

    def kill(self) -> None:
        self.killed = True
        self.return_code = -9


def test_worker_session_protocol_reader_stderr_and_send_receive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tempfile.TemporaryDirectory()
    session = _WorkerSession(_backend(), "worker-name", _spec(), directory, ())
    process = _FakeProcess()
    session.process = cast(subprocess.Popen[bytes], process)
    hello = WorkerHello(
        protocol_version=WORKER_PROTOCOL_VERSION,
        worker_version="0.2.0",
        plugin_api_version=PLUGIN_API_VERSION,
    )
    session._read_protocol(io.BytesIO(encode_worker_frame(hello)))
    assert session.receive(0.2) == hello
    with pytest.raises(WorkerExecutionError, match="closed"):
        session.receive(0.2)

    session._read_stderr(io.BytesIO(b"diagnostic output"))
    assert "diagnostic output" in session.stderr_excerpt
    session.send(WorkerShutdownRequest())
    process.stdin.seek(0)
    from voxrigor.plugin_worker.protocol import read_worker_message

    assert isinstance(read_worker_message(process.stdin), WorkerShutdownRequest)
    session._kill_container = lambda: None
    session.close()
    session.close()
    assert not Path(directory.name).exists()


def test_worker_session_reader_surfaces_invalid_frames_and_send_requires_live_process() -> None:
    directory = tempfile.TemporaryDirectory()
    session = _WorkerSession(_backend(), "worker-name", _spec(), directory, ())
    with pytest.raises(WorkerExecutionError, match="not running"):
        session.send(WorkerShutdownRequest())

    session._read_protocol(io.BytesIO(b"bad frame\n"))
    with pytest.raises(WorkerExecutionError, match="invalid protocol"):
        session.receive(0.2)

    session._kill_container = lambda: None
    session.close()


def test_worker_session_close_kills_process_after_wait_timeout() -> None:
    directory = tempfile.TemporaryDirectory()
    session = _WorkerSession(_backend(), "worker-name", _spec(), directory, ())
    process = _FakeProcess()

    def timeout_then_finish(timeout: float | None = None) -> int:
        process.wait_calls += 1
        if process.wait_calls == 1:
            raise subprocess.TimeoutExpired("podman", timeout)
        process.return_code = -9
        return -9

    process.wait = timeout_then_finish  # type: ignore[method-assign]
    session.process = cast(subprocess.Popen[bytes], process)
    session._kill_container = lambda: None
    session.close()
    assert process.killed is True
    assert process.wait_calls == 2


def test_worker_session_start_cleans_container_if_creation_returns_no_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend()
    directory = tempfile.TemporaryDirectory()
    session = _WorkerSession(backend, "worker-name", _spec(), directory, ())
    removed: list[str] = []
    monkeypatch.setattr(backend, "_run_checked", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(backend, "_remove_container", lambda name: removed.append(name))

    with pytest.raises(WorkerExecutionError, match="no container ID"):
        session.start()
    assert removed == ["worker-name"]
    assert not Path(directory.name).exists()


def test_worker_session_start_inspects_before_attaching_and_close_cleans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend()
    directory = tempfile.TemporaryDirectory()
    session = _WorkerSession(backend, "worker-name", _spec(), directory, ())
    inspected: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    monkeypatch.setattr(backend, "_run_checked", lambda *_args, **_kwargs: "container-id")
    monkeypatch.setattr(
        backend,
        "_verify_container",
        lambda container, _policy, *, expected_binds: inspected.append((container, expected_binds)),
    )
    process = _FakeProcess()
    monkeypatch.setattr(podman_module.subprocess, "Popen", lambda *_args, **_kwargs: process)
    session.start()
    assert inspected == [("container-id", ())]
    session._kill_container = lambda: None
    session.close()


def test_worker_session_wait_reports_timeout() -> None:
    directory = tempfile.TemporaryDirectory()
    session = _WorkerSession(_backend(), "worker-name", _spec(), directory, ())

    class TimeoutProcess(_FakeProcess):
        def wait(self, timeout: float | None = None) -> int:
            raise subprocess.TimeoutExpired("podman", timeout)

    session.process = cast(subprocess.Popen[bytes], TimeoutProcess())
    with pytest.raises(TimeoutError, match="shutdown acknowledgement"):
        session.wait(0.01)
    session._kill_container = lambda: None
    session.close()


def test_execute_isolated_plugin_test_completes_host_worker_exchange(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend()
    fake = _FakeSession()
    monkeypatch.setattr(
        podman_module,
        "verify_isolation_backend",
        lambda *_args: IsolationReadiness(
            backend_id=backend.backend_id,
            runtime_version="test",
            verified=True,
            enforced_controls=tuple(sorted(REQUIRED_ISOLATION_CONTROLS)),
        ),
    )
    monkeypatch.setattr(backend, "launch", lambda _spec: fake)

    description, result = execute_isolated_plugin_test(backend, _spec())

    assert description.metadata.plugin_id == "demo.voice"
    assert result.status is ResultStatus.NO_ISSUE_OBSERVED
    assert result.measurements == {"passed": True}
    assert [type(item) for item in fake.sent] == [
        WorkerDescribeRequest,
        WorkerExecuteRequest,
        WorkerShutdownRequest,
    ]
    assert fake.closed is True


def test_execute_isolated_plugin_test_rejects_worker_description_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend()
    failure = WorkerFailure(request_id=REQUEST_ID, code="plugin_load_error", message="failed")
    fake = _FakeSession(description=failure)
    monkeypatch.setattr(
        podman_module,
        "verify_isolation_backend",
        lambda *_args: IsolationReadiness(
            backend_id=backend.backend_id,
            runtime_version="test",
            verified=True,
            enforced_controls=tuple(sorted(REQUIRED_ISOLATION_CONTROLS)),
        ),
    )
    monkeypatch.setattr(backend, "launch", lambda _spec: fake)

    with pytest.raises(WorkerExecutionError, match="plugin_load_error"):
        execute_isolated_plugin_test(backend, _spec())
    assert fake.closed is True


def test_execute_isolated_plugin_test_rejects_unverified_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend()
    monkeypatch.setattr(
        podman_module,
        "verify_isolation_backend",
        lambda *_args: IsolationReadiness(
            backend_id=backend.backend_id,
            runtime_version="test",
            verified=False,
            enforced_controls=(),
        ),
    )
    with pytest.raises(PodmanBackendError, match="did not verify"):
        execute_isolated_plugin_test(backend, _spec())


def test_execute_isolated_plugin_test_rejects_bad_worker_response_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend()

    class BadSession(_FakeSession):
        def send(self, message: object) -> None:
            super().send(message)
            if isinstance(message, WorkerDescribeRequest):
                self.responses[-1] = WorkerDescribeResponse(
                    request_id=REQUEST_ID,
                    metadata=_metadata(),
                    tests=[_descriptor()],
                )

    fake = BadSession()
    monkeypatch.setattr(
        podman_module,
        "verify_isolation_backend",
        lambda *_args: IsolationReadiness(
            backend_id=backend.backend_id,
            runtime_version="test",
            verified=True,
            enforced_controls=tuple(sorted(REQUIRED_ISOLATION_CONTROLS)),
        ),
    )
    monkeypatch.setattr(backend, "launch", lambda _spec: fake)
    with pytest.raises(WorkerExecutionError, match="description response"):
        execute_isolated_plugin_test(backend, _spec())
