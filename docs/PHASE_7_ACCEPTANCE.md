# Phase 7 Acceptance Criteria

## First plugin contract slice

- [x] Define an experimental, versioned plugin API contract and strict metadata model.
- [x] Discover installed voxrigor.plugins entry points without importing their modules.
- [x] Add a separate versioned explicit allow-list; project manifests do not silently enable plugins.
- [x] Validate installed plugin IDs and permission declarations without executing plugin code.
- [x] Require matching installed/configured/metadata plugin IDs and API version.
- [x] Require exact declared/granted permission-set matching, while documenting that labels are not an OS sandbox.
- [x] Restrict contributed test IDs to the plugin's namespace and validate test descriptors.
- [x] Stage all enabled plugins before atomically updating the live test registry.
- [x] Add CLI commands for metadata-only discovery/configuration validation and explicit run-time plugin loading.
- [x] Add synthetic tests for discovery, config/schema validation, permission failures, namespace checks, duplicate IDs, atomicity and CLI integration.
- [x] Document the security boundary: loaded Python plugins execute in-process with the current user's OS privileges.

## Remaining Phase 7 gates

- [x] Add an independently installable example plugin package and test it from a clean wheel install.
- [x] Define experimental/stable plugin API versioning and deprecation rules; add a contract test proving exact API-version acceptance and rejection.
- [x] Implement the versioned, bounded JSONL IPC foundation with strict message discriminators, version handshake, duplicate-key/malformed-frame rejection, opaque staged-input references and namespaced test/result validation.
- [x] Implement a fail-closed isolation-backend preflight contract and tests for missing/unverified backends, identity mismatches, missing controls and unsupported access. Tests use a fake backend and do not claim real OS enforcement.
- [x] Implement an experimental Linux-only rootless-Podman backend with immutable image selection, rootless/seccomp/cgroups-v2 preflight, container inspection, private namespaces, no-network policy, read-only root and staged-input mounts, bounded resources, and an explicit host-side worker supervisor.
- [ ] Pass the dedicated real rootless-Podman integration workflow on a supported Linux runner; externally verify effective identity, seccomp, capabilities, cgroup limits, swap ceiling, host-file denial, host-loopback isolation and cleanup. Mocked tests do not satisfy this gate.
- [ ] Implement a Windows isolation backend (AppContainer plus Job Object or a separately reviewed stronger boundary) and prove restricted identity, ACLs, handles and resource limits with external probes.
- [x] Implement the first host/worker lifecycle slice: staged-input brokering, version handshake, plugin description, one selected test execution, bounded scalar result validation, wall-clock supervision, shutdown acknowledgement and container/process cleanup.
- [ ] Complete output-artifact brokering, cooperative cancellation, comprehensive crash/timeout/OOM recovery probes and auditable execution provenance. The normal CLI must not silently switch away from its in-process path before each supported backend passes its acceptance gates.
- [ ] Add signed plugin/distribution provenance verification if it is required by the project threat model.
- [x] Document a separately isolated plugin-worker design covering the host/worker trust boundary, IPC, capability brokering, Linux/Windows backend requirements, resource limits, fail-closed behavior and adversarial acceptance tests.
- [ ] Complete adversarial validation of the isolated-worker lifecycle, Linux backend and later Windows backend, including resource limits, capability brokering and failure recovery. The design document and synthetic tests alone are not a production sandbox claim.
- [x] Validate the example plugin wheel build/install/discovery/execution path on all six supported OS/Python CI combinations.

Passing contract tests does not make untrusted plugins safe. No sandbox or capability enforcement is included in this version.

The plugin API remains experimental (`0.1`). A stable `1.0` API is a separate release gate; this policy does not imply a current backwards-compatibility guarantee.
