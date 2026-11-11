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
    WorkerExecutionError,
    WorkerExecutionSpec,
)
from voxrigor.plugin_worker.protocol import StagedInputReference
from voxrigor.plugins import PluginPermission

IMAGE = "registry.example.invalid/voxrigor-worker@sha256:" + "a" * 64


def _backend() -> RootlessPodmanBackend:
    return RootlessPodmanBackend(worker_image=IMAGE)


def _container_document(policy: IsolationPolicy) -> dict[str, object]:
    return {
        "EffectiveCaps": [],
        "BoundingCaps": [],
        "HostConfig": {
            "ReadonlyRootfs": True,
            "NetworkMode": "none",
            "PidMode": "private",
            "IpcMode": "private",
            "Memory": policy.memory_bytes,
            "MemorySwap": policy.memory_bytes + 1,
            "PidsLimit": policy.process_count,
            "NanoCpus": 1_000_000_000,
            "UsernsMode": "",
            "IDMappings": {
                "UidMap": ["0:1:65536"],
                "GidMap": ["0:1:65536"],
            },
            "CapAdd": [],
            "SecurityOpt": ["no-new-privileges"],
            "LogConfig": {"Type": "none"},
            "Devices": [],
            "Ulimits": [
                {"Name": "cpu", "Soft": policy.cpu_time_seconds, "Hard": policy.cpu_time_seconds},
                {"Name": "nofile", "Soft": policy.open_file_count, "Hard": policy.open_file_count},
            ],
            "Tmpfs": {
                "/tmp": "rw,noexec,nosuid,nodev,size=16777216,mode=1777",
                "/output": f"ro,noexec,nosuid,nodev,size={policy.output_bytes},mode=0555",
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
    local_image = RootlessPodmanBackend("sha256:" + "b" * 64)
    assert local_image.worker_image == "sha256:" + "b" * 64
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
        "--memory-swap",
        "--log-driver=none",
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
        ("MemorySwap", -1, "memory plus swap"),
        ("LogConfig", {"Type": "json-file"}, "persistent container logging"),
        ("PidsLimit", -1, "process-count limit"),
        ("NanoCpus", 0, "CPU quota"),
        ("UsernsMode", "host", "user namespace"),
        (
            "IDMappings",
            {"UidMap": ["0:0:65536"], "GidMap": ["0:1:65536"]},
            "rootless parent UID",
        ),
        ("CapAdd", ["CAP_SYS_ADMIN"], "added Linux capabilities"),
        ("Devices", [{"PathOnHost": "/dev/snd"}], "host devices"),
        (
            "SecurityOpt",
            ["no-new-privileges", "seccomp=unconfined"],
            "seccomp profile",
        ),
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


def test_container_inspect_summaries_are_not_treated_as_kernel_proof() -> None:
    policy = IsolationPolicy()
    document = _container_document(policy)
    document["EffectiveCaps"] = ["CAP_CHOWN", "CAP_SETUID"]
    document["BoundingCaps"] = ["CAP_SYS_ADMIN"]
    host = document["HostConfig"]
    assert isinstance(host, dict)
    host["Ulimits"] = []

    # Podman's inspect summaries are not authoritative for a running process.
    # The real preflight separately verifies the kernel-visible capability
    # sets and effective CPU/open-file limits before plugin code is launched.
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
    assert "/proc/self/uid_map" in script
    assert "/proc/self/gid_map" in script
    assert "parent_uid=0" in script
    assert "parent_gid=0" in script
    assert "parent_start + length" in script
    assert all(
        capability in script for capability in ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
    )


def test_preflight_refuses_non_linux_before_invoking_podman(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    with pytest.raises(WorkerExecutionError, match="declared hash"):
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
    with pytest.raises(WorkerExecutionError, match="Duplicate staged input ID"):
        RootlessPodmanBackend._copy_staged_inputs(inputs)


def test_container_output_mount_is_read_only_by_default() -> None:
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
    tmpfs_args = [
        command[index + 1] for index, option in enumerate(command[:-1]) if option == "--tmpfs"
    ]
    output_spec = next(item for item in tmpfs_args if item.startswith("/output:"))
    assert output_spec.startswith("/output:ro,")
    assert "rw" not in output_spec.split(",")


def test_backend_refuses_unimplemented_network_and_write_capabilities() -> None:
    network_spec = WorkerExecutionSpec(
        plugin_id="demo.voice",
        test_id="demo.voice.diagnostic",
        project_name="Worker security",
        granted_permissions=(PluginPermission.NETWORK_LOOPBACK,),
    )
    with pytest.raises(PodmanBackendError, match="network.loopback"):
        _backend().launch(network_spec)

    write_spec = WorkerExecutionSpec(
        plugin_id="demo.voice",
        test_id="demo.voice.diagnostic",
        project_name="Worker security",
        granted_permissions=(PluginPermission.FILESYSTEM_WRITE,),
    )
    with pytest.raises(PodmanBackendError, match="filesystem.write"):
        _backend().launch(write_spec)


@pytest.mark.parametrize(
    ("media_kind", "permissions", "expected"),
    [
        ("audio", (), "audio.read"),
        ("model", (), "model.load"),
        ("dataset", (), "filesystem.read"),
    ],
)
def test_staged_input_kinds_require_matching_permission_grants(
    media_kind: str,
    permissions: tuple[PluginPermission, ...],
    expected: str,
) -> None:
    reference = StagedInputReference(
        input_id="input-data-1",
        sha256="a" * 64,
        size_bytes=1,
        media_kind=media_kind,
        display_name="sample.bin",
    )
    spec = WorkerExecutionSpec(
        plugin_id="demo.voice",
        test_id="demo.voice.diagnostic",
        project_name="Worker security",
        staged_inputs=(HostStagedInput(reference=reference, source_path=Path("sample.bin")),),
        granted_permissions=permissions,
    )
    with pytest.raises(PodmanBackendError, match=expected):
        _backend()._validate_spec_permissions(spec)


def test_staged_input_with_matching_grant_is_permitted_by_host_policy(tmp_path: Path) -> None:
    source = tmp_path / "sample.wav"
    source.write_bytes(b"audio")
    reference = StagedInputReference(
        input_id="input-audio-1",
        sha256=hashlib.sha256(b"audio").hexdigest(),
        size_bytes=5,
        media_kind="audio",
        display_name="sample.wav",
    )
    spec = WorkerExecutionSpec(
        plugin_id="demo.voice",
        test_id="demo.voice.diagnostic",
        project_name="Worker security",
        granted_permissions=(PluginPermission.AUDIO_READ,),
        staged_inputs=(HostStagedInput(reference=reference, source_path=source),),
    )
    _backend()._validate_spec_permissions(spec)
