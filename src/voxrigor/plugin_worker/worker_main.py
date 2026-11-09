"""Worker-side bootstrap. This module must be executed inside an OS sandbox.

Plugin entry points are imported only after the host has established the
worker boundary and sent the first describe request. Stdout is reserved for
bounded protocol frames; plugin print/log output is redirected to stderr.
"""

from __future__ import annotations

import contextlib
import hashlib
import math
import os
import sys
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import NoReturn
from uuid import uuid4

from voxrigor import __version__
from voxrigor.models import ProjectManifest, ResultStatus, TestDescriptor
from voxrigor.plugin_worker.protocol import (
    WorkerCancelRequest,
    WorkerCancelled,
    WorkerDescribeRequest,
    WorkerDescribeResponse,
    WorkerExecuteRequest,
    WorkerExecuteResponse,
    WorkerFailure,
    WorkerHello,
    WorkerMessage,
    WorkerProtocolError,
    WorkerShutdownRequest,
    WorkerShutdownResponse,
    WorkerSampleAccounting,
    read_worker_message,
    write_worker_message,
)
from voxrigor.plugins import (
    PLUGIN_API_VERSION,
    PLUGIN_ENTRY_POINT_GROUP,
    PluginMetadata,
    PluginPermission,
    PluginRegistrationContext,
    VoxRigorExternalPlugin,
)
from voxrigor.testing import StagedTestInput, TestOutcome, TestPlugin, TestRegistry, TestContext


class WorkerBootstrapError(RuntimeError):
    """Raised when the host request or installed plugin violates the worker contract."""


def _apply_process_limits(cpu_seconds: int, open_file_count: int) -> None:
    """Apply irreversible per-process limits before importing third-party code."""

    if os.name != "posix":
        raise WorkerBootstrapError("This worker build requires a POSIX resource-limit API")
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    current_soft, current_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    selected = open_file_count
    if current_hard != resource.RLIM_INFINITY:
        selected = min(selected, current_hard)
    if selected < 16:
        raise WorkerBootstrapError("The runtime cannot provide the minimum open-file limit")
    resource.setrlimit(resource.RLIMIT_NOFILE, (selected, selected))


def _entry_point_for(plugin_id: str) -> EntryPoint:
    matches = [
        item
        for item in entry_points(group=PLUGIN_ENTRY_POINT_GROUP)
        if item.name == plugin_id
    ]
    if len(matches) != 1:
        raise WorkerBootstrapError("Expected exactly one installed entry point for this plugin ID")
    return matches[0]


def _load_plugin(
    plugin_id: str,
    granted_permissions: tuple[PluginPermission, ...],
) -> tuple[PluginMetadata, TestRegistry]:
    """Import and register one plugin inside the isolated worker only."""

    entry_point = _entry_point_for(plugin_id)
    factory = entry_point.load()
    if not callable(factory):
        raise WorkerBootstrapError("Plugin entry point did not resolve to a callable factory")
    plugin_object = factory()
    metadata = getattr(plugin_object, "metadata", None)
    if not isinstance(metadata, PluginMetadata):
        raise WorkerBootstrapError("Plugin factory returned invalid metadata")
    if metadata.plugin_id != plugin_id:
        raise WorkerBootstrapError("Plugin metadata ID does not match the requested ID")
    if metadata.api_version != PLUGIN_API_VERSION:
        raise WorkerBootstrapError("Plugin API version is not supported by this worker")
    if set(metadata.required_permissions) != set(granted_permissions):
        raise WorkerBootstrapError("Granted permissions do not match the plugin declaration")
    register = getattr(plugin_object, "register", None)
    if not callable(register):
        raise WorkerBootstrapError("Plugin object has no callable register method")

    context = PluginRegistrationContext(metadata, frozenset(granted_permissions))
    register(context)
    if not context.pending_tests:
        raise WorkerBootstrapError("Plugin registered no tests")
    registry = TestRegistry()
    registry.register_many(context.pending_tests)
    return metadata, registry


def _staged_test_inputs(request: WorkerExecuteRequest) -> tuple[StagedTestInput, ...]:
    staged: list[StagedTestInput] = []
    for reference in request.staged_inputs:
        path = Path("/inputs") / reference.input_id
        if not path.is_file() or path.is_symlink():
            raise WorkerBootstrapError("A declared staged input is not available as a regular file")
        stat = path.stat()
        if stat.st_size != reference.size_bytes:
            raise WorkerBootstrapError("A staged input size differs from its host-verified metadata")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != reference.sha256:
            raise WorkerBootstrapError("A staged input hash differs from its host-verified metadata")
        staged.append(
            StagedTestInput(
                input_id=reference.input_id,
                path=path,
                display_name=reference.display_name,
                media_kind=reference.media_kind,
                sha256=reference.sha256,
                size_bytes=reference.size_bytes,
            )
        )
    return tuple(staged)


def _scalar_measurements(values: dict[str, object]) -> dict[str, str | int | float | bool | None]:
    output: dict[str, str | int | float | bool | None] = {}
    for key, value in values.items():
        if not isinstance(key, str) or not key or len(key) > 80:
            raise WorkerBootstrapError("Test result contains an invalid measurement key")
        if value is None or isinstance(value, (str, bool, int)):
            if isinstance(value, str) and len(value) > 2048:
                raise WorkerBootstrapError("Test result contains an oversized measurement string")
            output[key] = value
        elif isinstance(value, float) and math.isfinite(value):
            output[key] = value
        else:
            raise WorkerBootstrapError(
                "Worker protocol v0.1 accepts only finite scalar measurement values"
            )
    return output


def _send_failure(request_id: str, code: str, message: str) -> None:
    write_worker_message(
        sys.stdout.buffer,
        WorkerFailure(request_id=request_id, code=code, message=message),
    )


def serve() -> int:
    """Serve one plugin session over stdin/stdout JSONL."""

    write_worker_message(
        sys.stdout.buffer,
        WorkerHello(
            protocol_version="0.1",
            worker_version=__version__,
            plugin_api_version=PLUGIN_API_VERSION,
        ),
    )
    metadata: PluginMetadata | None = None
    registry: TestRegistry | None = None
    active_plugin_id: str | None = None
    active_limits: dict[str, int] | None = None

    while True:
        try:
            message = read_worker_message(sys.stdin.buffer)
        except WorkerProtocolError:
            return 2
        if message is None:
            return 0

        if isinstance(message, WorkerShutdownRequest):
            write_worker_message(sys.stdout.buffer, WorkerShutdownResponse())
            return 0

        if isinstance(message, WorkerCancelRequest):
            write_worker_message(
                sys.stdout.buffer,
                WorkerCancelled(request_id=message.request_id),
            )
            continue

        if isinstance(message, WorkerDescribeRequest):
            if metadata is not None:
                _send_failure(
                    message.request_id,
                    "session_already_described",
                    "This worker accepts only one plugin per session.",
                )
                return 2
            try:
                _apply_process_limits(
                    message.limits.cpu_time_seconds,
                    message.limits.open_file_count,
                )
                with contextlib.redirect_stdout(sys.stderr):
                    metadata, registry = _load_plugin(
                        message.plugin_id,
                        message.granted_permissions,
                    )
                active_plugin_id = message.plugin_id
                active_limits = message.limits.model_dump()
                write_worker_message(
                    sys.stdout.buffer,
                    WorkerDescribeResponse(
                        request_id=message.request_id,
                        metadata=metadata,
                        tests=tuple(registry.list()),
                    ),
                )
            except Exception as exc:
                _send_failure(
                    message.request_id,
                    "plugin_load_error",
                    f"Plugin could not be loaded or registered ({type(exc).__name__}).",
                )
                return 2
            continue

        if isinstance(message, WorkerExecuteRequest):
            if registry is None or metadata is None or active_plugin_id is None:
                _send_failure(
                    message.request_id,
                    "plugin_not_described",
                    "The plugin must complete the describe handshake before execution.",
                )
                return 2
            if message.plugin_id != active_plugin_id:
                _send_failure(
                    message.request_id,
                    "plugin_id_mismatch",
                    "Execution request does not match this worker session.",
                )
                return 2
            if message.limits.model_dump() != active_limits:
                _send_failure(
                    message.request_id,
                    "resource_policy_mismatch",
                    "Execution limits differ from the limits applied during worker startup.",
                )
                return 2
            try:
                plugin_test = registry.get(message.test_id)
                staged_inputs = _staged_test_inputs(message)
                context = TestContext(
                    run_id=uuid4(),
                    project=ProjectManifest(name=message.project_name),
                    staged_inputs=staged_inputs,
                )
                with contextlib.redirect_stdout(sys.stderr):
                    outcome = plugin_test.execute(context)
                if not isinstance(outcome, TestOutcome):
                    raise WorkerBootstrapError("Plugin test returned an invalid outcome object")
                if not outcome.sample_accounting.is_reconciled():
                    raise WorkerBootstrapError("Plugin sample accounting does not reconcile")
                write_worker_message(
                    sys.stdout.buffer,
                    WorkerExecuteResponse(
                        request_id=message.request_id,
                        plugin_id=message.plugin_id,
                        test_id=message.test_id,
                        status=outcome.status,
                        measurements=_scalar_measurements(outcome.measurements),
                        limitations=tuple(outcome.limitations),
                        sample_accounting=WorkerSampleAccounting(
                            input=outcome.sample_accounting.input,
                            evaluated=outcome.sample_accounting.evaluated,
                            excluded=outcome.sample_accounting.excluded,
                        ),
                    ),
                )
            except Exception as exc:
                _send_failure(
                    message.request_id,
                    "plugin_execution_error",
                    f"Plugin test failed ({type(exc).__name__}); details were not returned over IPC.",
                )
                continue
            continue

        _send_failure(
            message.request_id,
            "unexpected_message",
            "This message is not valid in the current worker state.",
        )
        return 2


def main() -> NoReturn:
    """Process entry point; never write diagnostics to the protocol stream."""

    try:
        exit_code = serve()
    except BaseException:
        exit_code = 2
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
