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

- [ ] Publish an independently installable example plugin package and test it from a clean wheel install.
- [ ] Define and test a backwards-compatibility/deprecation policy for the public SDK.
- [ ] Add signed plugin/distribution provenance verification if it is required by the project threat model.
- [ ] Design a separately isolated plugin worker before claiming permission enforcement or sandboxing.
- [ ] Add optional worker lifecycle, resource limits and failure-recovery integration only after the isolation boundary is designed.
- [ ] Validate plugin packaging and compatibility on all supported operating systems and Python versions from an independently built wheel.

Passing contract tests does not make untrusted plugins safe. No sandbox or capability enforcement is included in this version.