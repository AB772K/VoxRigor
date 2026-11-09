# Phase 7 — Isolated Plugin Worker Design

**Status:** architecture decision draft; implementation is not present. The current `voxrigor run --plugin-config ...` path imports and executes plugin code in the VoxRigor process. It is explicitly not a sandbox.

## 1. Security decision

Third-party plugin code must execute outside the trusted VoxRigor host process and inside an operating-system isolation boundary. A Python subprocess by itself is not sufficient: it normally inherits the user's filesystem access, environment, credentials, network access and process privileges.

The host must never import or call a third-party plugin factory when using the isolated execution mode. Plugin discovery may read installed distribution metadata, but all plugin imports, factories, registration callbacks and test execution must occur inside the isolated worker.

**Fail closed:** if the host cannot create and verify a supported isolation boundary, it must refuse isolated plugin execution. It must not silently fall back to an ordinary subprocess or the existing in-process loader.

## 2. Threat model

Assume a plugin may be malicious, compromised, buggy or vulnerable. It may attempt to read host files and secrets, alter project data, access credentials, contact other services, spawn child processes, exhaust memory/CPU/disk, forge results, corrupt IPC, or persist after its test ends.

Assets to protect include the user's home directory and credentials, VoxRigor source and installation, CI secrets, dataset/audio files, model artifacts, project manifests, reports, other processes, network services and the host OS.

Primary goals:

- Keep plugin imports and execution out of the trusted host process.
- Expose only explicitly staged inputs and a per-run output directory.
- Deny host filesystem and network access by default.
- Apply finite wall-clock, CPU, memory, process-count, disk/output and IPC limits.
- Kill the entire worker process tree and remove its ephemeral state after completion, failure or timeout.
- Validate every request and response using versioned schemas; never deserialize Python objects from the worker.
- Preserve auditability: record plugin ID/version, package hash, API version, backend identity, granted capabilities, resource limits and terminal status.

Out of scope for the first isolated-worker implementation: protection from a compromised host kernel/hypervisor, a fully malicious container runtime, CPU side-channel resistance, automatic malware verdicts and cryptographic publisher trust. Those require separate controls and threat-model decisions.

## 3. Host/worker architecture

~~~text
TRUSTED HOST
  CLI / operator allow-list
       |
  metadata-only discovery + package/hash checks
       |
  capability and input broker
       |
  worker supervisor ---- lifecycle / limits / cancellation
       |
       | versioned JSON messages over bounded stdio
======= OS ISOLATION BOUNDARY ====================================
ISOLATED WORKER
  minimal SDK bootstrap
       |
  import plugin entry point
       |
  register namespaced descriptors
       |
  execute selected tests
       |
  bounded JSON results + staged output artifacts
==================================================================
  host validates response, commits result, cleans worker
~~~

### Host responsibilities

The host owns operator consent, allow-list evaluation, package discovery, capability decisions, path resolution, input staging, worker creation, time/resource enforcement, report/provenance writing and result validation. No live `TestRegistry`, Python callback, host file handle, database connection, authentication token, model object or arbitrary Python object crosses into the worker.

Before launch, the host resolves all paths, rejects symlinks/path escapes, verifies package/distribution hashes where available, prepares read-only input mounts, creates a fresh bounded output directory and constructs a minimal environment. It passes only the worker executable, plugin distribution reference, validated allow-list entry, protocol version and staged-file manifest.

### Worker responsibilities

The worker imports the selected plugin, creates the SDK registration context, returns validated test descriptors, accepts execution requests for those descriptors and returns bounded results. It cannot add tests after the registration handshake, change the host registry directly or decide its own permissions.

Use a fresh worker per plugin per run initially. Do not reuse a worker across different plugins, projects or users; process reuse increases state leakage and makes cleanup less reliable.

## 4. IPC contract

Use newline-delimited UTF-8 JSON over the worker's standard input/output pipes. Standard output is reserved for protocol frames; diagnostic logs go to bounded standard error. The host and worker validate every frame against a versioned schema and reject unknown message types, duplicate/invalid request IDs, oversized frames, malformed JSON, unexpected fields, invalid statuses and invalid artifact references.

Minimum message families:

- `hello`: protocol version, worker build and plugin API version.
- `describe`: request plugin metadata and its registered test descriptors.
- `execute`: request ID, selected test ID, a filtered project context, staged input references and output quota.
- `result`: request ID, test descriptor ID, constrained result status, measurements, limitations and worker-generated artifact references.
- `cancel` / `shutdown`: cooperative cancellation followed by host-enforced termination if the worker does not exit.

JSON is data only. Never use `pickle`, `dill`, `cloudpickle`, Python object serialization, arbitrary import paths supplied by the plugin, or executable expressions in IPC. Bound both request and response sizes; cap log output and truncate/redact it before storing.

Worker responses are untrusted claims. The host re-validates result models, IDs, units, measurement types, artifact paths, file sizes and hashes before incorporating them into a report. A plugin cannot self-assert that a security check passed unless the host independently validates the evidence.

## 5. Capability model and data brokering

Permission labels remain declarations and operator-consent metadata until the broker and isolation backend enforce them. A grant alone must never map to broad access to the user's home directory, project root, devices or network.

| Existing label | Initial worker mapping |
|---|---|
| `audio.read` | Read-only staged audio inputs explicitly listed for this test. No microphone, ambient capture or arbitrary audio-device access. |
| `filesystem.read` | Read-only staged files/directories selected by the host. No general host filesystem access. |
| `filesystem.write` | A fresh per-run output directory with a finite quota. No overwrite access to source inputs or host project files. |
| `model.load` | Read-only staged model artifacts explicitly selected by the host. Model format/runtime policy remains separate; loading arbitrary model code is not made safe by this label. |
| `network.loopback` | **Not supported in the first isolated-worker slice.** Default network access is disabled. Add a brokered, destination-allowlisted network capability only after its own design and tests. |

If a plugin requires a permission that the selected backend cannot enforce, the host refuses to run it in isolated mode. Do not silently drop the permission or widen another capability to compensate.

Staged inputs must be content-addressed and read-only inside the worker. Do not mount the user's full project directory, home directory, SSH/config directories, credential stores, runtime sockets or host devices. Output files remain in a quota-limited scratch area and are copied into the report store only after host-side validation.

## 6. Platform isolation backends

The worker protocol is platform-neutral; the isolation enforcement is not. Each backend must be independently implemented, preflighted and adversarially tested. The existence of a backend class or a successful process launch is not evidence that isolation is active.

### Linux candidate: rootless OCI worker

Use a dedicated rootless Podman or Docker-compatible OCI runtime with a pinned worker image digest. Require a non-root user namespace, read-only root filesystem, no Linux capabilities, `no-new-privileges`, a restrictive seccomp profile, a private PID namespace, bounded cgroups, an ephemeral `/tmp`, a bounded writable output mount and `--network none`.

Never use `--privileged`, mount the host root or home directory, mount `/var/run/docker.sock` or another runtime socket into the worker, inherit host credentials, or launch through an unverified rootful daemon. The host must verify that the configured runtime is rootless and that the required namespace, seccomp, cgroup and mount controls are active before executing code.

Rootless OCI containers reduce privileges and provide useful kernel-enforced restrictions, but they still share the host kernel. They are not equivalent to a hypervisor-isolated VM. Higher-risk deployments may require a microVM/VM backend and a separate review.

### Windows candidate: AppContainer plus Job Object

Use a dedicated low-integrity AppContainer identity with explicit capability ACLs, a minimal staged runtime/package directory, a restricted environment and an explicit inherited-handle list containing only IPC pipes. Do not grant network capabilities in the initial backend. Apply a Windows Job Object to the worker tree with kill-on-job-close, active-process limits and CPU/memory limits.

AppContainer setup must establish and verify the worker's AppContainer SID, low integrity, filesystem/registry ACLs, network restrictions and inherited handles. Microsoft documents that Win32 app isolation is based on AppContainer and least-privilege capabilities; packaging and file-access requirements must be tested for the Python runtime and each plugin wheel. If these restrictions cannot be established reliably for the current host, refuse isolated execution rather than running the plugin as a normal user process.

Windows Sandbox or a Hyper-V-isolated worker may be considered as a stronger optional backend, but its availability, input staging, IPC and cleanup semantics require a separate implementation and acceptance test.

### Unsupported platforms

Do not advertise isolated plugin support on macOS or another platform until it has a dedicated backend and the same security acceptance suite. Lack of an isolation backend must not trigger an in-process fallback.

## 7. Resource and lifecycle enforcement

Every backend must enforce finite limits for wall-clock duration, CPU consumption, memory, process count, open files/handles, scratch-disk use, output artifact size, IPC frame size and log volume. Defaults and maxima must be configurable and documented, but unlimited values are not permitted in isolated mode.

Lifecycle:

1. preflight backend and verify enforced controls;
2. create a unique scratch/work directory and stage only approved inputs;
3. start a fresh isolated worker and establish the versioned handshake;
4. validate the plugin metadata and test descriptors;
5. execute only the selected test IDs;
6. validate returned results and copy approved artifacts;
7. terminate the worker and every child process;
8. remove scratch state and emit a final provenance record.

On timeout, cancellation, malformed IPC, crash, OOM, resource-limit breach or backend error, terminate the entire job/container/process tree, clean up and report a non-success execution state. No partial plugin registration or partially validated result is committed. Cleanup failure is itself a visible error and must not be hidden.

## 8. Migration from the current in-process SDK

The current `0.1` SDK loader is opt-in but imports and executes third-party Python code inside the host process. The existing `--plugin-config` option therefore does **not** imply isolation, least privilege or capability enforcement.

Implement the worker under a separately versioned execution contract. Keep the existing in-process path explicitly labeled unsafe for trusted development plugins only; future CLI design should require an unmistakable unsafe opt-in for that path. The isolated mode must be a separate explicit execution selection until each platform backend has passed acceptance. Never change the documentation to call the current in-process loader a sandbox.

## 9. Security acceptance tests

Before isolated execution is considered implemented, CI and backend-specific integration tests must demonstrate:

- the worker process is outside the host process and uses the expected restricted identity;
- a sentinel file outside staged mounts cannot be read or modified;
- read-only input mounts cannot be modified;
- output writes are confined to the quota-limited per-run directory;
- network access is denied, including loopback, for the first backend;
- environment variables and handles containing host secrets are not inherited;
- microphone/audio-device and unrelated host device access are denied;
- process, CPU, memory, wall-time, file-handle and output limits are enforced;
- spawned child processes are terminated with the worker;
- malformed/oversized IPC and forged result IDs are rejected;
- plugin crash, timeout, cancellation, OOM and backend loss leave no partial registry update or unvalidated report result;
- a missing/unhealthy backend fails closed without executing plugin code in the host;
- scratch files, mounts, containers and Job Objects are cleaned up even after failure.

Tests must verify enforcement from outside the worker (host-side probes and OS identity/ACL checks), not merely assert that launch arguments were constructed.

## 10. References and design rationale

- [Python PEP 551 — Security transparency in the Python runtime](https://peps.python.org/pep-0551/) is an informational, withdrawn PEP. Its guidance explicitly cautions against trying to sandbox arbitrary code inside the Python runtime and points toward running Python inside an externally sandboxed environment. This is design guidance, not a current normative standard.
- [Microsoft — Windows 11 application isolation](https://learn.microsoft.com/en-us/windows/security/book/application-security-application-isolation) describes Win32 isolation based on AppContainer, low integrity and explicit resource capabilities.
- [Microsoft — AppContainer isolation](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation) describes file, network and process isolation controls.
- [Docker — Rootless mode](https://docs.docker.com/engine/security/rootless/) describes running both the daemon and containers as a non-root user in a user namespace.
- [Docker — Seccomp security profiles](https://docs.docker.com/engine/security/seccomp) describes syscall filtering as a kernel-enforced container control.

These references inform candidate backends. They do not establish that VoxRigor has implemented or verified any of these controls.