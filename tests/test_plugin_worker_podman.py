from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from voxrigor.plugin_worker.isolation import IsolationPolicy
from voxrigor.plugin_worker.podman import (
    HostStagedInput,
    PodmanBackendError,
    RootlessPodmanBackend,
)
from voxrigor.plugin_worker.protocol import StagedInputReference

IMAGE = "registry.example.invalid/voxrigor-worker@sha256:" + "a" * 64


def _backend() -> RootlessPodmanBackend:
    return RootlessPodmanBackend(worker_image=IMAGE)


def _container_document(policy: IsolationPolicy) -> dict[str, object]:
    return {
        "HostConfig": {
            "ReadonlyRootfs": True,
            "NetworkMode": "none",
            "PidMode": "private",
            "IpcMode": "private",
            "Memory": policy.memory_bytes,
            "PidsLimit": policy.process_count,
            "NanoCpus": 1_000_000_000,
            "UsernsMode": "auto",
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
            "Devices": [],
            "Ulimits": [
                {"Name": "cpu", "Soft": policy.cpu_time_seconds, "Hard": policy.cpu_time_seconds},
                {"Name": "nofile", "Soft": policy.open_file_count, "Hard": policy.open_file_count},
            ],
            "Tmpfs": {
                "/tmp": "rw,noexec,nosuid,nodev,size=16777216",
                "/output": f"rw,noexec,nosuid,nodev,size={policy.output_bytes}",
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


def test_worker_image_must_be_pinned_by_sha256_digest() -> None:
    with pytest.raises(ValueError, match="immutable"):
        RootlessPodmanBackend("registry.example.invalid/voxrigor-worker:latest")

    backend = _backend()
    assert backend.backend_id == "podman-rootless-oci"


def test_container_command_has_default_deny_security_flags() -> None:
    policy = IsolationPolicy()
    command = _backend()._container_command(
        action="create",
        name="voxrigor-test-worker",
        policy=policy,
        image=IMAGE,
        mounts=(),
        entrypoint="python",
        worker_command=("-m", "voxrigor.plugin_worker.worker_main"),
        interactive=True,
    )

    joined = " ".join(command)
    for expected in (
        "--network=none",
        "--pid=private",
        "--ipc=private",
        "--userns=auto",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit",
        "--memory",
        "--cpus",
        "--ulimit",
        "--tmpfs",
        "--unsetenv-all",
        "--no-hosts",
        "--init",
    ):
        assert expected in command or expected in joined
    assert "--privileged" not in command
    assert "--publish" not in command
    assert "/var/run/docker.sock" not in joined


def test_container_command_rejects_permissions_outside_the_initial_worker_policy() -> None:
    policy = IsolationPolicy(network_enabled=True)
    with pytest.raises(PodmanBackendError, match="denies network"):
        _backend()._container_command(
            action="create",
            name="voxrigor-test-worker",
            policy=policy,
            image=IMAGE,
            mounts=(),
            entrypoint="python",
            worker_command=("-m", "voxrigor.plugin_worker.worker_main"),
            interactive=True,
        )


def test_container_inspect_verification_accepts_the_complete_policy() -> None:
    policy = IsolationPolicy()
    RootlessPodmanBackend._verify_container_document(
        _container_document(policy),
        policy,
        expected_binds=(),
    )


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("ReadonlyRootfs", False, "read-only root"),
        ("NetworkMode", "bridge", "network isolation"),
        ("PidMode", "host", "PID namespace"),
        ("Memory", 0, "memory limit"),
        ("PidsLimit", -1, "process-count limit"),
        ("NanoCpus", 0, "CPU quota"),
        ("UsernsMode", "host", "user namespace"),
        ("CapDrop", [], "drop all Linux capabilities"),
        ("Devices", [{"PathOnHost": "/dev/snd"}], "host devices"),
        ("SecurityOpt", ["seccomp=unconfined"], "no-new-privileges"),
    ],
)
def test_container_inspect_verification_rejects_weakened_controls(
    key: str,
    value: object,
    message: str,
) -> None:
    policy = IsolationPolicy()
    document = _container_document(policy)
    host = document["HostConfig"]
    assert isinstance(host, dict)
    host[key] = value

    with pytest.raises(PodmanBackendError, match=message):
        RootlessPodmanBackend._verify_container_document(
            document,
            policy,
            expected_binds=(),
        )


def test_container_inspect_verification_requires_exactly_the_staged_bind_list(
    tmp_path: Path,
) -> None:
    policy = IsolationPolicy()
    document = _container_document(policy)
    host = document["HostConfig"]
    assert isinstance(host, dict)
    host["Binds"] = ["/home/user/.ssh:/inputs/a:ro"]

    with pytest.raises(PodmanBackendError, match="staged inputs"):
        RootlessPodmanBackend._verify_container_document(
            document,
            policy,
            expected_binds=(),
        )


@pytest.mark.skipif(sys.platform != "linux", reason="The runtime probe is Linux/Podman specific")
def test_in_container_probe_script_is_valid_python() -> None:
    script = _backend()._probe_script(IsolationPolicy())
    compile(script, "<voxrigor-podman-probe>", "exec")


def test_preflight_refuses_non_linux_before_invoking_podman(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(PodmanBackendError, match="native Linux"):
        _backend().preflight(IsolationPolicy())


def test_staged_input_is_copied_verified_and_not_exposed_by_host_path(tmp_path: Path) -> None:
    source = tmp_path / "sample.wav"
    source.write_bytes(b"voxrigor staged fixture")
    payload = source.read_bytes()
    reference = StagedInputReference(
        input_id="input-audio-1",
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        media_kind="audio",
        display_name="sample.wav",
    )
    temporary, mounts = RootlessPodmanBackend._copy_staged_inputs(
        (HostStagedInput(reference=reference, source_path=source),)
    )
    try:
        assert len(mounts) == 1
        staged_reference, staged_path = mounts[0]
        assert staged_reference == reference
        assert staged_path.read_bytes() == payload
        assert staged_path != source
        assert staged_path.stat().st_mode & 0o222 == 0
    finally:
        temporary.cleanup()


def test_staged_input_hash_mismatch_fails_before_container_creation(tmp_path: Path) -> None:
    source = tmp_path / "sample.wav"
    source.write_bytes(b"actual bytes")
    reference = StagedInputReference(
        input_id="input-audio-1",
        sha256="b" * 64,
        size_bytes=len(b"actual bytes"),
        media_kind="audio",
        display_name="sample.wav",
    )
    with pytest.raises(Exception, match="declared hash"):
        RootlessPodmanBackend._copy_staged_inputs(
            (HostStagedInput(reference=reference, source_path=source),)
        )


def test_duplicate_staged_input_ids_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "sample.wav"
    source.write_bytes(b"same")
    reference = StagedInputReference(
        input_id="input-audio-1",
        sha256=hashlib.sha256(b"same").hexdigest(),
        size_bytes=4,
        media_kind="audio",
        display_name="sample.wav",
    )
    inputs = (
        HostStagedInput(reference=reference, source_path=source),
        HostStagedInput(reference=reference, source_path=source),
    )
    with pytest.raises(Exception, match="Duplicate staged input ID"):
        RootlessPodmanBackend._copy_staged_inputs(inputs)
