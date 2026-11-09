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
- [ ] Add signed plugin/distribution provenance verification if it is required by the project threat model.
- [x] Document a separately isolated plugin-worker design covering the host/worker trust boundary, IPC, capability brokering, Linux/Windows backend requirements, resource limits, fail-closed behavior and adversarial acceptance tests.
- [ ] Implement and adversarially validate the isolated worker lifecycle, platform backends, resource limits, capability brokering and failure recovery. The design document is not an implementation or a sandbox claim.
- [x] Validate the example plugin wheel build/install/discovery/execution path on all six supported OS/Python CI combinations.

Passing contract tests does not make untrusted plugins safe. No sandbox or capability enforcement is included in this version.

The plugin API remains experimental (`0.1`). A stable `1.0` API is a separate release gate; this policy does not imply a current backwards-compatibility guarantee.
