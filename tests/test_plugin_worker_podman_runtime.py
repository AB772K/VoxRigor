    backend = _backend()
    removed: list[str] = []
    monkeypatch.setattr(backend, "_runtime_preflight", lambda: {})
    monkeypatch.setattr(backend, "_create_and_inspect", lambda *_args, **_kwargs: "probe-id")
    monkeypatch.setattr(
        backend,
        "_run_probe",
        lambda _container: (_ for _ in ()).throw(PodmanBackendError("probe refused")),
    )
    monkeypatch.setattr(
        backend, "_remove_container", lambda container_id: removed.append(container_id)
    )

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
