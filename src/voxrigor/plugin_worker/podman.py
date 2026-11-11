"""Rootless Podman backend for Linux plugin-worker isolation.

The backend is intentionally Linux-only. It requires a digest-pinned worker
image and a rootless Podman installation with cgroups v2 and seccomp. It
creates a private user/PID/IPC/network namespace, runs as an unmapped
non-root container UID, and checks the created container configuration plus
kernel-visible process limits before it reports readiness.
"""

from __future__ import annotations

import contextlib
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
    REQUIRED_ISOLATION_CONTROLS,
    IsolationBackendUnavailable,
    IsolationPolicy,
    IsolationReadiness,
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

_PINNED_IMAGE_RE = re.compile(r"^(?:[^\s@]+@sha256:[0-9a-f]{64}|sha256:[0-9a-f]{64})$")
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
        # Only one not-yet-consumed frame may be retained on the host. A
        # compromised worker that floods stdout is back-pressured by this
        # queue instead of growing host memory without bound.
        self._messages: queue.Queue[WorkerMessage | BaseException | None] = queue.Queue(maxsize=1)
        self.container_id: str | None = None
        self._stderr = bytearray()
        self._stderr_lock = threading.Lock()
        self._reader_threads: list[threading.Thread] = []
        self._closed = False

    def start(self) -> None:
        """Create, inspect and start the worker container, attaching only stdio."""

        if self.process is not None:
            raise WorkerExecutionError("Worker session has already been started")
        container_id: str | None = None
        try:
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
            raw_id = self.backend._run_checked(
                command,
                timeout=30,
                operation="create isolated plugin worker",
            )
            container_id = raw_id.strip()
            if not container_id:
                raise WorkerExecutionError("Podman returned no container ID")
            self.container_id = container_id
            expected_binds = tuple(
                (str(path), f"/inputs/{reference.input_id}")
                for reference, path in self.staged_mounts
            )
            self.backend._verify_container(
                container_id,
                self.spec.policy,
                expected_binds=expected_binds,
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
        except BaseException:
            try:
                self.backend._remove_container(container_id or self.container_name)
            finally:
                self.container_id = None
                self.staged_directory.cleanup()
            raise

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

    def _enqueue_message(self, message: WorkerMessage | BaseException | None) -> bool:
        """Queue one frame with backpressure; never buffer an unbounded worker stream."""

        while not self._closed:
            try:
                self._messages.put(message, timeout=0.1)
                return True
            except queue.Full:
                continue
        return False

    def _read_protocol(self, stream: BinaryIO) -> None:
        while True:
            try:
                frame = stream.readline(MAX_WORKER_FRAME_BYTES + 2)
                if not frame:
                    self._enqueue_message(None)
                    return
                message = decode_worker_frame(frame)
                if not self._enqueue_message(message):
                    return
            except BaseException as exc:
                self._enqueue_message(exc)
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
        if self.container_id is None:
            return
        # A worker may already have exited, so a failed "kill" is not itself
        # fatal. The forced removal below is the authoritative cleanup gate.
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                [self.backend.binary, "kill", "--signal", "KILL", self.container_id],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=8,
            )
        self.backend._remove_container(self.container_id)
        self.container_id = None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        process = self.process
        cleanup_error: BaseException | None = None
        try:
            self._kill_container()
        except BaseException as exc:
            cleanup_error = exc
        try:
            if process is not None and process.poll() is None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        process.wait(timeout=5)
            if process is not None:
                for stream in (process.stdin, process.stdout, process.stderr):
                    if stream is not None:
                        with contextlib.suppress(OSError):
                            stream.close()
            for thread in self._reader_threads:
                thread.join(timeout=1)
        finally:
            self.staged_directory.cleanup()
        if cleanup_error is not None:
            raise WorkerExecutionError(
                "Could not confirm removal of the isolated worker container"
            ) from cleanup_error

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
            raise ValueError(
                "worker_image must be an immutable @sha256 reference or local sha256 image ID"
            )
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
            raise PodmanBackendError(
                "Rootless Podman requires at least 4096 bytes of bounded output tmpfs"
            )
        if policy.network_enabled or policy.microphone_enabled or policy.host_filesystem_enabled:
            raise PodmanBackendError(
                "Initial rootless worker backend denies network, microphone and host filesystem"
            )
        uid = str(_CONTAINER_UID)
        gid = str(_CONTAINER_GID)
        temporary_size = max(16 * 1024 * 1024, min(policy.memory_bytes // 4, 64 * 1024 * 1024))
        output_mount = f"/output:ro,noexec,nosuid,nodev,size={policy.output_bytes},mode=0555"
        # Podman accepts the tmpfs mode flag but rejects Docker-style uid/gid
        # mount options. A sticky world-writable /tmp is safe within this
        # private PID/network/user namespace and remains size-bounded.
        temporary_mount = f"/tmp:rw,noexec,nosuid,nodev,size={temporary_size},mode=1777"
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
            # Podman defines --memory-swap as memory plus swap and requires
            # it to exceed --memory. Permit only one byte beyond the RAM cap.
            "--memory-swap",
            str(policy.memory_bytes + 1),
            "--log-driver=none",
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
        expected_binds: tuple[tuple[str, str], ...],
    ) -> None:
        host = document.get("HostConfig")
        config = document.get("Config")
        if not isinstance(host, dict) or not isinstance(config, dict):
            raise PodmanBackendError("Container inspect document omitted HostConfig or Config")

        checks: dict[str, tuple[object, object]] = {
            "read-only root": (host.get("ReadonlyRootfs"), True),
            "network isolation": (host.get("NetworkMode"), "none"),
            "PID namespace": (host.get("PidMode") or "private", "private"),
            "IPC namespace": (host.get("IpcMode") or "private", "private"),
            "memory limit": (host.get("Memory"), policy.memory_bytes),
            "memory plus swap limit": (host.get("MemorySwap"), policy.memory_bytes + 1),
            "process-count limit": (host.get("PidsLimit"), policy.process_count),
            "CPU quota": (host.get("NanoCpus"), 1_000_000_000),
            "container identity": (config.get("User"), f"{_CONTAINER_UID}:{_CONTAINER_GID}"),
        }
        for label, (actual, expected) in checks.items():
            if actual != expected:
                raise PodmanBackendError(f"Podman did not apply the required {label}")
        user_namespace = host.get("UsernsMode")
        # Podman's rootless outer user namespace is created outside libpod and
        # may be reported as an empty mode. Accept that representation only
        # because the in-container uid_map/gid_map probe below must prove the
        # host caller's UID/GID are absent. Explicit host/shared modes fail.
        if not isinstance(user_namespace, str) or (
            user_namespace not in ("", "private") and not user_namespace.startswith("auto")
        ):
            raise PodmanBackendError(
                f"Podman reported an unsupported user namespace mode: {user_namespace!r}"
            )
        id_mappings = host.get("IDMappings")
        if not isinstance(id_mappings, dict):
            raise PodmanBackendError("Podman did not report effective UID/GID mappings")
        for label, key in (("UID", "UidMap"), ("GID", "GidMap")):
            entries = id_mappings.get(key)
            if not isinstance(entries, list) or not entries:
                raise PodmanBackendError(f"Podman did not report effective {label} mappings")
            for entry in entries:
                if not isinstance(entry, str):
                    raise PodmanBackendError(f"Podman returned an invalid {label} mapping")
                fields = entry.split(":")
                if len(fields) != 3:
                    raise PodmanBackendError(f"Podman returned an invalid {label} mapping")
                try:
                    container_start, parent_start, length = map(int, fields)
                except ValueError as exc:
                    raise PodmanBackendError(
                        f"Podman returned a non-numeric {label} mapping"
                    ) from exc
                if container_start < 0 or parent_start < 0 or length <= 0:
                    raise PodmanBackendError(f"Podman returned an invalid {label} mapping")
                # In the rootless parent namespace, podman unshare runs as UID/GID 0.
                # auto/nomap must not map that identity into the worker, even when
                # libpod displays UsernsMode as empty for rootless containers.
                if parent_start == 0:
                    raise PodmanBackendError(
                        f"Podman mapped the rootless parent {label} into the worker"
                    )

        # Podman's inspect capability arrays are configuration summaries, not
        # proof of the capabilities available to a live worker process. The
        # preflight below checks CapInh/Prm/Eff/Bnd/Amb from /proc/self/status
        # inside the constrained container before any plugin code is launched.
        added_capabilities = host.get("CapAdd")
        if not isinstance(added_capabilities, list) or added_capabilities:
            raise PodmanBackendError("Podman unexpectedly added Linux capabilities")
        security_options = host.get("SecurityOpt")
        if not isinstance(security_options, list) or not any(
            "no-new-privileges" in str(value).lower() for value in security_options
        ):
            raise PodmanBackendError("Podman did not enable no-new-privileges")
        if any(str(value).strip().lower() == "seccomp=unconfined" for value in security_options):
            raise PodmanBackendError("Podman explicitly disabled the seccomp profile")

        log_config = host.get("LogConfig")
        if not isinstance(log_config, dict) or log_config.get("Type") != "none":
            raise PodmanBackendError("Podman did not disable persistent container logging")

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
        if (
            not isinstance(environment, list)
            or not set(environment).issubset(allowed_environment)
            or not allowed_environment - {"container=podman"} <= set(environment)
        ):
            raise PodmanBackendError(
                "Worker environment is not limited to the explicit safe allow-list"
            )

        # Podman's HostConfig.Ulimits is a Docker-compatible inspect summary.
        # The live preflight process verifies both RLIMITs with getrlimit below,
        # which is the effective kernel limit seen by a worker process.

        tmpfs = host.get("Tmpfs")
        if not isinstance(tmpfs, dict):
            raise PodmanBackendError("Podman did not configure bounded tmpfs mounts")
        output_settings = set(str(tmpfs.get("/output", "")).lower().split(","))
        required_output_settings = {
            "ro",
            "noexec",
            "nosuid",
            "nodev",
            f"size={policy.output_bytes}",
            "mode=0555",
        }
        if not required_output_settings.issubset(output_settings):
            raise PodmanBackendError(
                "Podman did not apply the bounded read-only output mount policy"
            )
        temporary_size = max(16 * 1024 * 1024, min(policy.memory_bytes // 4, 64 * 1024 * 1024))
        temporary_settings = set(str(tmpfs.get("/tmp", "")).lower().split(","))
        required_temporary_settings = {
            "rw",
            "noexec",
            "nosuid",
            "nodev",
            f"size={temporary_size}",
            "mode=1777",
        }
        if not required_temporary_settings.issubset(temporary_settings):
            raise PodmanBackendError(
                "Podman did not apply the bounded writable temporary-directory policy"
            )

        binds = host.get("Binds") or []
        if not isinstance(binds, list):
            raise PodmanBackendError("Podman returned an invalid bind-mount list")
        actual_binds: set[tuple[str, str]] = set()
        for bind in binds:
            parts = str(bind).split(":")
            if len(parts) < 3:
                raise PodmanBackendError("Podman returned an invalid bind-mount declaration")
            options = {part.lower() for part in ",".join(parts[2:]).split(",")}
            if "ro" not in options or "rw" in options:
                raise PodmanBackendError("Every staged-input bind mount must be read-only")
            actual_binds.add((parts[0], parts[1]))
        if actual_binds != set(expected_binds):
            raise PodmanBackendError("Worker bind mounts differ from the explicitly staged inputs")

        mounts = document.get("Mounts") or []
        if not isinstance(mounts, list):
            raise PodmanBackendError("Podman returned an invalid effective-mount list")
        allowed_host_config_mounts = {
            "/etc/hosts",
            "/etc/hostname",
            "/etc/resolv.conf",
        }
        expected_bind_destinations = {destination for _, destination in expected_binds}
        for mount in mounts:
            if not isinstance(mount, dict):
                raise PodmanBackendError("Podman returned an invalid effective-mount entry")
            mount_type = str(mount.get("Type", "")).lower()
            destination = str(mount.get("Destination", ""))
            if mount_type == "volume":
                raise PodmanBackendError(
                    "Anonymous or named volumes are not permitted for plugin workers"
                )
            if mount_type == "bind":
                if destination in expected_bind_destinations:
                    if mount.get("RW") is not False:
                        raise PodmanBackendError("Staged inputs must be mounted read-only")
                elif destination not in allowed_host_config_mounts:
                    raise PodmanBackendError(
                        "Podman added an unapproved host bind mount to the plugin worker"
                    )

        if host.get("VolumesFrom") not in (None, []):
            raise PodmanBackendError("Worker must not inherit mounts from another container")

    def _verify_container(
        self,
        container_id: str,
        policy: IsolationPolicy,
        *,
        expected_binds: tuple[tuple[str, str], ...],
    ) -> None:
        """Inspect the actual container configuration before it can execute."""

        inspect_raw = self._run_checked(
            [self.binary, "inspect", container_id],
            timeout=15,
            operation="inspect isolated worker container",
        )
        document = self._json_document(inspect_raw, operation="worker container inspect")
        self._verify_container_document(
            document,
            policy,
            expected_binds=expected_binds,
        )

    def _create_and_inspect(
        self,
        policy: IsolationPolicy,
        *,
        command: list[str],
        expected_binds: tuple[tuple[str, str], ...] = (),
    ) -> str:
        raw_id = self._run_checked(
            command, timeout=30, operation="create isolation probe container"
        )
        container_id = raw_id.strip()
        if not container_id:
            raise PodmanBackendError("Podman returned an empty container ID")
        try:
            self._verify_container(
                container_id,
                policy,
                expected_binds=expected_binds,
            )
            return container_id
        except BaseException:
            self._remove_container(container_id)
            raise

    def _remove_container(self, container_id: str) -> None:
        try:
            completed = subprocess.run(
                [self.binary, "rm", "--force", "--volumes", container_id],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PodmanBackendError(
                f"Could not remove isolated worker container ({type(exc).__name__})"
            ) from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip().replace("\n", " ")[:400]
            lowered = detail.lower()
            if any(
                phrase in lowered
                for phrase in ("no such container", "no container with name", "not found")
            ):
                return
            raise PodmanBackendError(
                f"Could not remove isolated worker container (exit {completed.returncode}): "
                f"{detail}"
            )

    def _probe_script(self, policy: IsolationPolicy) -> str:
        """Probe kernel-visible controls from inside the configured container."""

        # /proc/*_map reports IDs relative to the parent user namespace.
        # For rootless Podman that parent is podman unshare, where the
        # invoking host identity is represented by UID/GID 0.
        parent_uid = 0
        parent_gid = 0
        return (
            "\n".join(
                (
                    "import json,os,resource",
                    "status={}",
                    "with open('/proc/self/status',encoding='utf-8') as stream:",
                    "    for line in stream:",
                    "        if ':' in line:",
                    "            key,value=line.split(':',1)",
                    "            status[key]=value.strip()",
                    "assert status.get('NoNewPrivs')=='1'",
                    "assert status.get('Seccomp')=='2'",
                    "capability_keys=('CapInh','CapPrm','CapEff','CapBnd','CapAmb')",
                    "assert all(key in status for key in capability_keys)",
                    "capabilities={key:int(status[key],16) for key in capability_keys}",
                    "assert not any(capabilities.values()), f'Worker capability sets are not empty: {capabilities}'",
                    f"assert os.getuid()=={_CONTAINER_UID}",
                    f"assert os.getuid()!={parent_uid}",
                    f"assert os.getgid()!={parent_gid}",
                    "uid_map=[tuple(map(int,line.split())) for line in open('/proc/self/uid_map',encoding='utf-8')]",
                    "gid_map=[tuple(map(int,line.split())) for line in open('/proc/self/gid_map',encoding='utf-8')]",
                    f"assert all(not parent_start <= {parent_uid} < parent_start + length for _,parent_start,length in uid_map)",
                    f"assert all(not parent_start <= {parent_gid} < parent_start + length for _,parent_start,length in gid_map)",
                    "assert set(os.listdir('/sys/class/net'))<= {'lo'}",
                    "cpu_limit=resource.getrlimit(resource.RLIMIT_CPU)",
                    f"assert cpu_limit==({policy.cpu_time_seconds},{policy.cpu_time_seconds}), 'CPU-time limit mismatch: %r' % (cpu_limit,)",
                    "nofile_limit=resource.getrlimit(resource.RLIMIT_NOFILE)",
                    f"assert nofile_limit==({policy.open_file_count},{policy.open_file_count}), 'open-file limit mismatch: %r' % (nofile_limit,)",
                    "pids=open('/sys/fs/cgroup/pids.max').read().strip()",
                    f"assert pids=={str(policy.process_count)!r}, 'pids.max mismatch: %r' % (pids,)",
                    "mem=open('/sys/fs/cgroup/memory.max').read().strip()",
                    f"assert mem=={str(policy.memory_bytes)!r}, 'memory.max mismatch: %r' % (mem,)",
                    "swap=open('/sys/fs/cgroup/memory.swap.max').read().strip()",
                    "assert swap=='1', f'memory.swap.max mismatch: {swap}'",
                    "cpu=open('/sys/fs/cgroup/cpu.max').read().split()",
                    "assert len(cpu)==2 and cpu[0]!='max' and int(cpu[0])<=int(cpu[1]), f'cpu.max mismatch: {cpu}'",
                    f"probe_path='/etc/.voxrigor-read-only-probe-{uuid4().hex}'",
                    "read_only=False",
                    "try:",
                    "    with open(probe_path,'x'): pass",
                    "except OSError:",
                    "    read_only=True",
                    "assert read_only, 'worker root filesystem remained writable'",
                    "print(json.dumps({'ok':True,'uid':os.getuid(),'seccomp':status['Seccomp']}))",
                )
            )
            + "\n"
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
            raise PodmanBackendError(
                "Rootless Podman security probe returned invalid output"
            ) from exc
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise PodmanBackendError("Rootless Podman security probe did not verify the boundary")

    def preflight(self, policy: IsolationPolicy) -> IsolationReadiness:
        """Actively verify rootless runtime, inspect a constrained container and probe it."""

        if policy.network_enabled or policy.microphone_enabled or policy.host_filesystem_enabled:
            raise PodmanBackendError(
                "Initial worker policy denies network, microphone and host filesystem"
            )
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
                    raise WorkerExecutionError(
                        "Staged input did not match its declared hash and size"
                    )
                os.chmod(destination, 0o444)
                mounts.append((reference, destination))
            os.chmod(root, 0o555)
            return directory, tuple(mounts)
        except BaseException:
            directory.cleanup()
            raise

    @staticmethod
    def _validate_spec_permissions(spec: WorkerExecutionSpec) -> None:
        """Reject capabilities not implemented by this initial Linux worker slice."""

        granted = set(spec.granted_permissions)
        if PluginPermission.NETWORK_LOOPBACK in granted:
            raise PodmanBackendError(
                "network.loopback is not supported by the initial worker backend"
            )
        if PluginPermission.FILESYSTEM_WRITE in granted:
            raise PodmanBackendError(
                "filesystem.write is not supported until a validated artifact-export broker exists"
            )
        for item in spec.staged_inputs:
            media_kind = item.reference.media_kind.lower()
            if media_kind == "audio" or media_kind.startswith("audio_"):
                required = PluginPermission.AUDIO_READ
            elif media_kind == "model" or media_kind.startswith("model_"):
                required = PluginPermission.MODEL_LOAD
            else:
                required = PluginPermission.FILESYSTEM_READ
            if required not in granted:
                raise PodmanBackendError(
                    f"Staged input kind {media_kind!r} requires the {required.value!r} grant"
                )

    def launch(self, spec: WorkerExecutionSpec) -> _WorkerSession:
        """Prepare host-staged inputs and return a not-yet-started worker session."""

        self._validate_spec_permissions(spec)
        if (
            spec.policy.network_enabled
            or spec.policy.microphone_enabled
            or spec.policy.host_filesystem_enabled
        ):
            raise PodmanBackendError(
                "Initial worker policy denies network, microphone and host filesystem"
            )
        staged_directory, staged_mounts = self._copy_staged_inputs(spec.staged_inputs)
        name = f"voxrigor-plugin-{uuid4().hex[:20]}"
        return _WorkerSession(self, name, spec, staged_directory, staged_mounts)


def execute_isolated_plugin_test(
    backend: RootlessPodmanBackend,
    spec: WorkerExecutionSpec,
) -> tuple[WorkerDescribeResponse, WorkerExecuteResponse]:
    """Perform a complete describe/execute/shutdown exchange in a verified worker."""

    backend._validate_spec_permissions(spec)
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
        if (
            description.request_id != describe_id
            or description.metadata.plugin_id != spec.plugin_id
        ):
            raise WorkerExecutionError("Worker description response did not match the request")
        if description.metadata.api_version != hello.plugin_api_version:
            raise WorkerExecutionError("Worker and plugin API versions did not match")
        if set(description.metadata.required_permissions) != set(spec.granted_permissions):
            raise WorkerExecutionError("Worker plugin permissions did not match the host grants")
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
            raise WorkerExecutionError(f"Worker test failed ({result.code}): {result.message}")
        if not isinstance(result, WorkerExecuteResponse):
            raise WorkerExecutionError("Worker returned an unexpected test result")
        if (
            result.request_id != execute_id
            or result.plugin_id != spec.plugin_id
            or result.test_id != spec.test_id
        ):
            raise WorkerExecutionError(
                "Worker result identifiers did not match the execution request"
            )
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
