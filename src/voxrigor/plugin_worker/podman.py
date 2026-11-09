"""Rootless Podman backend for Linux plugin-worker isolation.

The backend is intentionally Linux-only. It requires a digest-pinned worker
image and a rootless Podman installation with cgroups v2 and seccomp. It
creates a private user/PID/IPC/network namespace, runs as an unmapped
non-root container UID, and checks the created container configuration plus
kernel-visible process limits before it reports readiness.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from voxrigor.plugin_worker.isolation import (
    IsolationBackendUnavailable,
    IsolationPolicy,
    IsolationReadiness,
    REQUIRED_ISOLATION_CONTROLS,
    verify_isolation_backend,
)
from voxrigor.plugin_worker.protocol import (
    MAX_WORKER_FRAME_BYTES,
    StagedInputReference,
    WorkerDescribeRequest,
    WorkerDescribeResponse,
    WorkerExecuteRequest,
    WorkerExecuteResponse,
    WorkerFailure,
    WorkerHello,
    WorkerMessage,
    WorkerProtocolError,
    WorkerResourceLimits,
    WorkerShutdownRequest,
    WorkerShutdownResponse,
    decode_worker_frame,
    write_worker_message,
)
from voxrigor.plugins import PluginPermission

_PINNED_IMAGE_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
_CONTAINER_UID = 10001
_CONTAINER_GID = 10001
_CPU_RATE = 1.0
_STDERR_CAPTURE_BYTES = 16_384


class PodmanBackendError(IsolationBackendUnavailable):
    """Raised when rootless Podman cannot establish the required boundary."""


@dataclass(frozen=True)
class HostStagedInput:
    """Host-side path and metadata for a file to be copied into the worker."""

    reference: StagedInputReference
    source_path: Path


@dataclass(frozen=True)
class WorkerExecutionSpec:
    """One plugin/test request and the explicitly approved local input files."""

    plugin_id: str
    test_id: str
    project_name: str
    granted_permissions: tuple[PluginPermission, ...] = ()
    staged_inputs: tuple[HostStagedInput, ...] = ()
    policy: IsolationPolicy = field(default_factory=IsolationPolicy)


class WorkerExecutionError(RuntimeError):
    """Raised when a worker fails protocol validation or execution."""


class _WorkerSession:
    """Bounded stdio transport attached to one named Podman container."""

    def __init__(
        self,
        backend: RootlessPodmanBackend,
        container_name: str,
        spec: WorkerExecutionSpec,
        staged_directory: tempfile.TemporaryDirectory[str],
        staged_mounts: tuple[tuple[StagedInputReference, Path], ...],
    ) -> None:
        self.backend = backend
        self.container_name = container_name
        self.spec = spec
        self.staged_directory = staged_directory
        self.staged_mounts = staged_mounts
        self.process: subprocess.Popen[bytes] | None = None
        self._messages: queue.Queue[WorkerMessage | BaseException | None] = queue.Queue()
        self._stderr = bytearray()
        self._stderr_lock = threading.Lock()
        self._reader_threads: list[threading.Thread] = []
        self._closed = False

    def start(self) -> None:
        """Create, inspect and start the worker container, attaching only stdio."""

        if self.process is not None:
            raise WorkerExecutionError("Worker session has already been started")
        command = self.backend._container_command(
            action="create",
            name=self.container_name,
            policy=self.spec.policy,
            image=self.backend.worker_image,
            mounts=self.staged_mounts,
            entrypoint="python",
            worker_command=("-m", "voxrigor.plugin_worker.worker_main"),
            interactive=True,
        )
        container_id = self.backend._run_checked(
            command,
            timeout=30,
            operation="create isolated plugin worker",
        ).strip()
        if not container_id:
            raise WorkerExecutionError("Podman returned no container ID")
        self.backend._verify_container(
            container_id,
            self.spec.policy,
            expected_binds=tuple(str(path) for _, path in self.staged_mounts),
        )
        attach = subprocess.Popen(
            [self.backend.binary, "start", "--attach", "--interactive", container_id],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            start_new_session=True,
        )
        self.process = attach
        self._start_reader_threads()

    def _start_reader_threads(self) -> None:
        process = self.process
        if process is None or process.stdout is None or process.stderr is None:
            raise WorkerExecutionError("Podman worker pipes were not created")
        stdout_thread = threading.Thread(
            target=self._read_protocol,
            args=(process.stdout,),
            name="voxrigor-worker-stdout",
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=self._read_stderr,
            args=(process.stderr,),
            name="voxrigor-worker-stderr",
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()
        self._reader_threads.extend((stdout_thread, stderr_thread))

    def _read_protocol(self, stream: BinaryIO) -> None:
        while True:
            try:
                frame = stream.readline(MAX_WORKER_FRAME_BYTES + 2)
                if not frame:
                    self._messages.put(None)
                    return
                message = decode_worker_frame(frame)
                self._messages.put(message)
            except BaseException as exc:
                self._messages.put(exc)
                return

    def _read_stderr(self, stream: BinaryIO) -> None:
        while True:
            block = stream.read(4096)
            if not block:
                return
            with self._stderr_lock:
                remaining = _STDERR_CAPTURE_BYTES - len(self._stderr)
                if remaining > 0:
                    self._stderr.extend(block[:remaining])

    @property
    def stderr_excerpt(self) -> str:
        with self._stderr_lock:
            return bytes(self._stderr).decode("utf-8", errors="replace")

    def send(self, message: WorkerMessage) -> None:
        process = self.process
        if process is None or process.stdin is None or process.poll() is not None:
            raise WorkerExecutionError("Worker process is not running")
        try:
            write_worker_message(process.stdin, message)
        except (BrokenPipeError, OSError, WorkerProtocolError) as exc:
            raise WorkerExecutionError("Could not send a valid worker protocol frame") from exc

    def receive(self, timeout: float) -> WorkerMessage:
        if timeout <= 0:
            raise TimeoutError("Plugin worker exceeded its wall-clock budget")
        try:
            item = self._messages.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError("Plugin worker exceeded its wall-clock budget") from exc
        if item is None:
            raise WorkerExecutionError("Plugin worker closed its protocol stream unexpectedly")
        if isinstance(item, BaseException):
            raise WorkerExecutionError(
                f"Plugin worker emitted an invalid protocol frame ({type(item).__name__})"
            ) from item
        return item

    def wait(self, timeout: float) -> int:
        process = self.process
        if process is None:
            raise WorkerExecutionError("Worker process was not started")
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("Plugin worker did not exit after shutdown acknowledgement") from exc

    def _kill_container(self) -> None:
        for command in (
            [self.backend.binary, "kill", "--signal", "KILL", self.container_name],
            [self.backend.binary, "rm", "--force", "--volumes", self.container_name],
        ):
            try:
                subprocess.run(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=8,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        process = self.process
        if process is not None and process.poll() is None:
            self._kill_container()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        self._kill_container()
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
        for thread in self._reader_threads:
            thread.join(timeout=1)
        self.staged_directory.cleanup()

    def __enter__(self) -> _WorkerSession:
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


class RootlessPodmanBackend:
    """Linux rootless Podman backend with live preflight and bounded worker launch."""

    backend_id = "podman-rootless-oci"

    def __init__(self, worker_image: str, binary: str = "podman") -> None:
        if not _PINNED_IMAGE_RE.fullmatch(worker_image):
            raise ValueError("worker_image must be pinned by an immutable @sha256 digest")
        if Path(binary).name != binary:
            raise ValueError("binary must be an executable name resolved through PATH")
        self.worker_image = worker_image
        self.binary = binary

    def _run_checked(
        self,
        command: list[str],
        *,
        timeout: int,
        operation: str,
    ) -> str:
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PodmanBackendError(
                f"Podman could not {operation} ({type(exc).__name__})"
            ) from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip().replace("\n", " ")[:400]
            raise PodmanBackendError(
                f"Podman could not {operation} (exit {completed.returncode}): {detail}"
            )
        return completed.stdout

    @staticmethod
    def _json_document(raw: str, *, operation: str) -> dict[str, object]:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PodmanBackendError(f"Podman returned invalid JSON during {operation}") from exc
        if isinstance(parsed, list) and parsed:
            parsed = parsed[0]
        if not isinstance(parsed, dict):
            raise PodmanBackendError(f"Podman returned an unexpected JSON shape during {operation}")
        return parsed

    @staticmethod
    def _nested(document: dict[str, object], *keys: str) -> object:
        value: object = document
        for key in keys:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        return value

    def _runtime_preflight(self) -> dict[str, object]:
        if not sys.platform.startswith("linux") or os.name != "posix":
            raise PodmanBackendError("Rootless Podman isolation is supported only on native Linux")
        get_effective_uid = getattr(os, "geteuid", None)
        if not callable(get_effective_uid) or get_effective_uid() == 0:
            raise PodmanBackendError("Podman must run as a non-root host user in rootless mode")
        if shutil.which(self.binary) is None:
            raise PodmanBackendError("Podman executable was not found on PATH")
        info_raw = self._run_checked(
            [self.binary, "info", "--format", "json"],
            timeout=15,
            operation="inspect runtime security capabilities",
        )
        info = self._json_document(info_raw, operation="runtime info")
        if self._nested(info, "host", "security", "rootless") is not True:
            raise PodmanBackendError("Podman runtime is not rootless")
        if self._nested(info, "host", "security", "seccompEnabled") is not True:
            raise PodmanBackendError("Podman runtime does not report seccomp enabled")
        if self._nested(info, "host", "cgroupVersion") != "v2":
            raise PodmanBackendError("Rootless plugin workers require cgroups v2")
        self._run_checked(
            [self.binary, "image", "exists", self.worker_image],
            timeout=15,
            operation="locate the digest-pinned worker image",
        )
        return info

    def _container_command(
        self,
        *,
        action: str,
        name: str,
        policy: IsolationPolicy,
        image: str,
        mounts: tuple[tuple[StagedInputReference, Path], ...],
        entrypoint: str,
        worker_command: tuple[str, ...],
        interactive: bool,
    ) -> list[str]:
        if policy.output_bytes < 4096:
            raise PodmanBackendError("Rootless Podman requires at least 4096 bytes of bounded output tmpfs")
        if policy.network_enabled or policy.microphone_enabled or policy.host_filesystem_enabled:
            raise PodmanBackendError("Initial rootless worker backend denies network, microphone and host filesystem")
        uid = str(_CONTAINER_UID)
        gid = str(_CONTAINER_GID)
        temporary_size = max(16 * 1024 * 1024, min(policy.memory_bytes // 4, 64 * 1024 * 1024))
        output_mount = (
            f"/output:rw,noexec,nosuid,nodev,size={policy.output_bytes},"
            f"mode=0700,uid={uid},gid={gid}"
        )
        temporary_mount = (
            f"/tmp:rw,noexec,nosuid,nodev,size={temporary_size},"
            f"mode=0700,uid={uid},gid={gid}"
        )
        command = [
            self.binary,
            action,
            "--name",
            name,
            "--pull=never",
            "--network=none",
            "--pid=private",
            "--ipc=private",
            "--userns=auto",
            "--user",
            f"{uid}:{gid}",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit",
            str(policy.process_count),
            "--memory",
            str(policy.memory_bytes),
            "--cpus",
            str(_CPU_RATE),
            "--ulimit",
            f"cpu={policy.cpu_time_seconds}:{policy.cpu_time_seconds}",
            "--ulimit",
            f"nofile={policy.open_file_count}:{policy.open_file_count}",
            "--tmpfs",
            temporary_mount,
            "--tmpfs",
            output_mount,
            "--unsetenv-all",
            "--env",
            "HOME=/tmp/worker-home",
            "--env",
            "PATH=/usr/local/bin:/usr/bin:/bin",
            "--env",
            "PYTHONNOUSERSITE=1",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--no-hosts",
            "--init",
        ]
        if interactive:
            command.append("--interactive")
        for reference, staged_path in mounts:
            command.extend(
                [
                    "--volume",
                    f"{staged_path}:/inputs/{reference.input_id}:ro,Z",
                ]
            )
        command.extend(
            [
                "--entrypoint",
                entrypoint,
                image,
                *worker_command,
            ]
        )
        return command

    @staticmethod
    def _verify_container_document(
        document: dict[str, object],
        policy: IsolationPolicy,
        *,
        expected_binds: tuple[str, ...],
    ) -> None:
        host = document.get("HostConfig")
        config = document.get("Config")
        if not isinstance(host, dict) or not isinstance(config, dict):
            raise PodmanBackendError("Container inspect document omitted HostConfig or Config")

        checks: dict[str, tuple[object, object]] = {
            "read-only root": (host.get("ReadonlyRootfs"), True),
            "network isolation": (host.get("NetworkMode"), "none"),
            "PID namespace": (host.get("PidMode"), "private"),
            "IPC namespace": (host.get("IpcMode"), "private"),
            "memory limit": (host.get("Memory"), policy.memory_bytes),
            "process-count limit": (host.get("PidsLimit"), policy.process_count),
            "CPU quota": (host.get("NanoCpus"), 1_000_000_000),
            "user namespace": (host.get("UsernsMode"), "auto"),
            "container identity": (config.get("User"), f"{_CONTAINER_UID}:{_CONTAINER_GID}"),
        }
        for label, (actual, expected) in checks.items():
            if actual != expected:
                raise PodmanBackendError(f"Podman did not apply the required {label}")

        capabilities = host.get("CapDrop")
        if not isinstance(capabilities, list) or not any(
            str(value).upper() == "ALL" for value in capabilities
        ):
            raise PodmanBackendError("Podman did not drop all Linux capabilities")
        security_options = host.get("SecurityOpt")
        if not isinstance(security_options, list) or not any(
            "no-new-privileges" in str(value).lower() for value in security_options
        ):
            raise PodmanBackendError("Podman did not enable no-new-privileges")

        devices = host.get("Devices")
        if devices not in (None, []):
            raise PodmanBackendError("Podman unexpectedly passed host devices into the worker")

        environment = config.get("Env")
        allowed_environment = {
            "HOME=/tmp/worker-home",
            "PATH=/usr/local/bin:/usr/bin:/bin",
            "PYTHONNOUSERSITE=1",
            "PYTHONDONTWRITEBYTECODE=1",
            "container=podman",
        }
        if not isinstance(environment, list) or not set(environment).issubset(allowed_environment) or not allowed_environment - {"container=podman"} <= set(environment):
            raise PodmanBackendError("Worker environment is not limited to the explicit safe allow-list")

        ulimits = host.get("Ulimits")
        if not isinstance(ulimits, list):
            raise PodmanBackendError("Podman did not expose the configured ulimit settings")
        observed_limits = {
            str(item.get("Name")): (item.get("Soft"), item.get("Hard"))
            for item in ulimits
            if isinstance(item, dict)
        }
        if observed_limits.get("cpu") != (
            policy.cpu_time_seconds,
            policy.cpu_time_seconds,
        ):
            raise PodmanBackendError("Podman did not apply the CPU-time limit")
        if observed_limits.get("nofile") != (
            policy.open_file_count,
            policy.open_file_count,
        ):
            raise PodmanBackendError("Podman did not apply the open-file limit")

        tmpfs = host.get("Tmpfs")
        if not isinstance(tmpfs, dict):
            raise PodmanBackendError("Podman did not configure bounded tmpfs mounts")
        output_settings = str(tmpfs.get("/output", ""))
        if f"size={policy.output_bytes}" not in output_settings:
            raise PodmanBackendError("Podman did not apply the per-worker output quota")
        if "/tmp" not in tmpfs:
            raise PodmanBackendError("Podman did not create an ephemeral bounded temporary directory")

        binds = host.get("Binds") or []
        if not isinstance(binds, list):
            raise PodmanBackendError("Podman returned an invalid bind-mount list")
        actual_sources: list[str] = []
        for bind in binds:
            source = str(bind).split(":", 1)[0]
            actual_sources.append(source)
        if set(actual_sources) != set(expected_binds):
            raise PodmanBackendError("Worker bind mounts differ from the explicitly staged inputs")

        if host.get("VolumesFrom") not in (None, []):
            raise PodmanBackendError("Worker must not inherit mounts from another container")

    def _create_and_inspect(
        self,
        policy: IsolationPolicy,
        *,
        command: list[str],
        expected_binds: tuple[str, ...] = (),
    ) -> str:
        raw_id = self._run_checked(command, timeout=30, operation="create isolation probe container")
        container_id = raw_id.strip()
        if not container_id:
            raise PodmanBackendError("Podman returned an empty container ID")
        try:
            inspect_raw = self._run_checked(
                [self.binary, "inspect", container_id],
                timeout=15,
                operation="inspect isolation probe container",
            )
            document = self._json_document(inspect_raw, operation="container inspect")
            self._verify_container_document(
                document,
                policy,
                expected_binds=expected_binds,
            )
            return container_id
        except BaseException:
            self._remove_container(container_id)
            raise

    def _remove_container(self, container_id: str) -> None:
        try:
            subprocess.run(
                [self.binary, "rm", "--force", "--volumes", container_id],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    def _probe_script(self, policy: IsolationPolicy) -> str:
        """Probe kernel-visible controls from inside the configured container."""

        host_uid = os.getuid()
        return (
            "import json,os,resource\\n"
            "status={}\\n"
            "with open('/proc/self/status',encoding='utf-8') as stream:\\n"
            "    for line in stream:\\n"
            "        if ':' in line:\\n"
            "            key,value=line.split(':',1)\\n"
            "            status[key]=value.strip()\\n"
            "assert status.get('NoNewPrivs')=='1'\\n"
            "assert status.get('Seccomp')=='2'\\n"
            f"assert os.getuid()=={_CONTAINER_UID}\\n"
            f"assert os.getuid()!={host_uid}\\n"
            "assert set(os.listdir('/sys/class/net'))<= {'lo'}\\n"
            "assert resource.getrlimit(resource.RLIMIT_CPU)==("
            f"{policy.cpu_time_seconds},{policy.cpu_time_seconds})\\n"
            "assert resource.getrlimit(resource.RLIMIT_NOFILE)==("
            f"{policy.open_file_count},{policy.open_file_count})\\n"
            "pids=open('/sys/fs/cgroup/pids.max').read().strip()\\n"
            f"assert pids=={str(policy.process_count)!r}\\n"
            "mem=open('/sys/fs/cgroup/memory.max').read().strip()\\n"
            f"assert mem=={str(policy.memory_bytes)!r}\\n"
            "cpu=open('/sys/fs/cgroup/cpu.max').read().split()\\n"
            "assert len(cpu)==2 and cpu[0]!='max' and int(cpu[0])<=int(cpu[1])\\n"
            "read_only=False\\n"
            "try:\\n"
            "    with open('/etc/.voxrigor-read-only-probe','x'): pass\\n"
            "except OSError:\\n"
            "    read_only=True\\n"
            "assert read_only\\n"
            "print(json.dumps({'ok':True,'uid':os.getuid(),'seccomp':status['Seccomp']}))\\n"
        )

    def _run_probe(self, container_id: str) -> None:
        try:
            completed = subprocess.run(
                [self.binary, "start", "--attach", container_id],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PodmanBackendError(
                f"Rootless Podman security probe did not complete ({type(exc).__name__})"
            ) from exc
        if completed.returncode != 0:
            excerpt = completed.stderr.strip().replace("\n", " ")[:400]
            raise PodmanBackendError(
                f"Rootless Podman security probe failed (exit {completed.returncode}): {excerpt}"
            )
        try:
            result = json.loads(completed.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError) as exc:
            raise PodmanBackendError("Rootless Podman security probe returned invalid output") from exc
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise PodmanBackendError("Rootless Podman security probe did not verify the boundary")

    def preflight(self, policy: IsolationPolicy) -> IsolationReadiness:
        """Actively verify rootless runtime, inspect a constrained container and probe it."""

        if policy.network_enabled or policy.microphone_enabled or policy.host_filesystem_enabled:
            raise PodmanBackendError("Initial worker policy denies network, microphone and host filesystem")
        self._runtime_preflight()
        name = f"voxrigor-preflight-{uuid4().hex[:16]}"
        command = self._container_command(
            action="create",
            name=name,
            policy=policy,
            image=self.worker_image,
            mounts=(),
            entrypoint="python",
            worker_command=("-c", self._probe_script(policy)),
            interactive=False,
        )
        container_id = self._create_and_inspect(policy, command=command)
        try:
            self._run_probe(container_id)
        finally:
            self._remove_container(container_id)
        return IsolationReadiness(
            backend_id=self.backend_id,
            runtime_version="rootless-podman-cgroups-v2-seccomp",
            verified=True,
            enforced_controls=tuple(sorted(REQUIRED_ISOLATION_CONTROLS)),
            missing_controls=(),
            detail="Runtime info, container inspect and in-container kernel probes passed.",
        )

    @staticmethod
    def _copy_staged_inputs(
        inputs: tuple[HostStagedInput, ...],
    ) -> tuple[tempfile.TemporaryDirectory[str], tuple[tuple[StagedInputReference, Path], ...]]:
        directory = tempfile.TemporaryDirectory(prefix="voxrigor-worker-inputs-")
        root = Path(directory.name)
        os.chmod(root, 0o700)
        mounts: list[tuple[StagedInputReference, Path]] = []
        seen: set[str] = set()
        try:
            for item in inputs:
                reference = item.reference
                if reference.input_id in seen:
                    raise WorkerExecutionError("Duplicate staged input ID")
                seen.add(reference.input_id)
                source = Path(item.source_path)
                absolute = Path(os.path.abspath(source))
                for component in (absolute, *absolute.parents):
                    if component.is_symlink():
                        raise WorkerExecutionError("Symlinked staged input paths are not permitted")
                resolved = absolute.resolve(strict=True)
                if not resolved.is_file():
                    raise WorkerExecutionError("Staged input must be a regular file")
                if resolved.stat().st_size != reference.size_bytes:
                    raise WorkerExecutionError("Staged input size differs from declared metadata")
                destination = root / reference.input_id
                digest = hashlib.sha256()
                copied = 0
                with resolved.open("rb") as source_stream, destination.open("xb") as target_stream:
                    while block := source_stream.read(1024 * 1024):
                        digest.update(block)
                        target_stream.write(block)
                        copied += len(block)
                if copied != reference.size_bytes or digest.hexdigest() != reference.sha256:
                    raise WorkerExecutionError("Staged input did not match its declared hash and size")
                os.chmod(destination, 0o444)
                mounts.append((reference, destination))
            os.chmod(root, 0o555)
            return directory, tuple(mounts)
        except BaseException:
            directory.cleanup()
            raise

    def launch(self, spec: WorkerExecutionSpec) -> _WorkerSession:
        """Prepare host-staged inputs and return a not-yet-started worker session."""

        if spec.policy.network_enabled or spec.policy.microphone_enabled or spec.policy.host_filesystem_enabled:
            raise PodmanBackendError("Initial worker policy denies network, microphone and host filesystem")
        staged_directory, staged_mounts = self._copy_staged_inputs(spec.staged_inputs)
        name = f"voxrigor-plugin-{uuid4().hex[:20]}"
        return _WorkerSession(self, name, spec, staged_directory, staged_mounts)


def execute_isolated_plugin_test(
    backend: RootlessPodmanBackend,
    spec: WorkerExecutionSpec,
) -> tuple[WorkerDescribeResponse, WorkerExecuteResponse]:
    """Perform a complete describe/execute/shutdown exchange in a verified worker."""

    readiness = verify_isolation_backend(backend, spec.policy)
    if not readiness.verified:
        raise PodmanBackendError("Worker isolation preflight did not verify")
    limits = WorkerResourceLimits(
        wall_time_seconds=spec.policy.wall_time_seconds,
        cpu_time_seconds=spec.policy.cpu_time_seconds,
        memory_bytes=spec.policy.memory_bytes,
        process_count=spec.policy.process_count,
        open_file_count=spec.policy.open_file_count,
        output_bytes=spec.policy.output_bytes,
    )
    describe_id = str(uuid4())
    execute_id = str(uuid4())
    input_references = tuple(item.reference for item in spec.staged_inputs)
    deadline = time.monotonic() + spec.policy.wall_time_seconds

    def remaining() -> float:
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError("Plugin worker exceeded its wall-clock budget")
        return value

    with backend.launch(spec) as session:
        hello = session.receive(remaining())
        if not isinstance(hello, WorkerHello):
            raise WorkerExecutionError("Worker did not send the protocol hello frame")
        if hello.plugin_api_version != "0.1":
            raise WorkerExecutionError("Worker plugin API version is unsupported")
        session.send(
            WorkerDescribeRequest(
                request_id=describe_id,
                plugin_id=spec.plugin_id,
                granted_permissions=spec.granted_permissions,
                limits=limits,
            )
        )
        description = session.receive(remaining())
        if isinstance(description, WorkerFailure):
            raise WorkerExecutionError(
                f"Worker rejected plugin description ({description.code}): {description.message}"
            )
        if not isinstance(description, WorkerDescribeResponse):
            raise WorkerExecutionError("Worker returned an unexpected description response")
        if description.request_id != describe_id or description.metadata.plugin_id != spec.plugin_id:
            raise WorkerExecutionError("Worker description response did not match the request")
        if description.metadata.api_version != hello.plugin_api_version:
            raise WorkerExecutionError("Worker and plugin API versions did not match")
        if spec.test_id not in {item.test_id for item in description.tests}:
            raise WorkerExecutionError("Selected test is not registered by the isolated plugin")

        session.send(
            WorkerExecuteRequest(
                request_id=execute_id,
                plugin_id=spec.plugin_id,
                test_id=spec.test_id,
                project_name=spec.project_name,
                staged_inputs=input_references,
                limits=limits,
            )
        )
        result = session.receive(remaining())
        if isinstance(result, WorkerFailure):
            raise WorkerExecutionError(
                f"Worker test failed ({result.code}): {result.message}"
            )
        if not isinstance(result, WorkerExecuteResponse):
            raise WorkerExecutionError("Worker returned an unexpected test result")
        if (
            result.request_id != execute_id
            or result.plugin_id != spec.plugin_id
            or result.test_id != spec.test_id
        ):
            raise WorkerExecutionError("Worker result identifiers did not match the execution request")
        if not result.sample_accounting.is_reconciled():
            raise WorkerExecutionError("Worker result sample accounting does not reconcile")

        session.send(WorkerShutdownRequest())
        acknowledgement = session.receive(min(5.0, remaining()))
        if not isinstance(acknowledgement, WorkerShutdownResponse):
            raise WorkerExecutionError("Worker did not acknowledge shutdown")
        exit_code = session.wait(min(5.0, remaining()))
        if exit_code != 0:
            raise WorkerExecutionError("Isolated worker exited with a non-zero status")
        return description, result
