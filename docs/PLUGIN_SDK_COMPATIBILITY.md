# VoxRigor Plugin SDK Versioning and Compatibility Policy

**Current status:** experimental plugin API `0.1`; no stable backwards-compatibility guarantee yet.

## Scope and independent versions

This policy covers the third-party plugin contract: entry-point behavior, `PluginMetadata`, `PluginRegistrationContext`, registered-test requirements, permission labels and the explicit plugin allow-list. It does not promise compatibility for every VoxRigor CLI command, report field, internal module or project manifest.

The VoxRigor distribution version and plugin API version are independent. The package version identifies the installed distribution (currently `0.2.0.dev0`); `voxrigor.plugins.PLUGIN_API_VERSION` identifies the plugin contract (currently `0.1`). A plugin declares the API version it implements in `PluginMetadata.api_version`.

A plugin is loadable only when its declared API version exactly matches the host's supported API version. The loader does not silently accept an unknown, newer or older version. A package-version match alone does not establish plugin API compatibility.

## Experimental 0.x rules

The current `0.1` contract is experimental. Until the plugin API reaches `1.0`, there is no guarantee that a future `0.x` API version will run existing plugin source unchanged. Treat the API version as a strict compatibility identifier, not as a long-term stability promise.

Within one API version (for example, `0.1`), changes must preserve existing plugin behavior and configuration acceptance. Compatible additions may include optional metadata with safe defaults, optional context helpers, documentation clarifications and bug fixes that do not alter the contract.

A change that requires an existing plugin to change source, metadata, configuration or expected behavior must use a new API version. During `0.x`, an incompatible contract uses the next minor label (for example, `0.1` to `0.2`). The host rejects the old version unless it deliberately retains a separately tested compatibility adapter.

Every API-version change must update the API constant and metadata validator, relevant JSON Schemas, example plugin metadata, migration notes and contract tests in the same change. Never change the accepted API version without adding or updating those checks.

## Stable API rules after 1.0

Declaring the plugin API stable requires a separate release gate: documented public exports, an independent example plugin, migration and compatibility tests, supported-environment validation, and a reviewed threat model. Reaching package version `1.0` alone does not automatically make the plugin API stable.

After the plugin API itself reaches `1.0`, it follows semantic-versioning rules independently of the VoxRigor package version:

- **MAJOR:** incompatible plugin-contract change; plugin authors must review migration guidance.
- **MINOR:** backwards-compatible additions; existing plugins using the prior minor API continue to load.
- **PATCH:** compatible bug fixes or clarifications that do not change the contract.

The host must advertise only the compatible API range it actually implements and tests. It must not claim compatibility merely because a plugin declares a lower version.

## Deprecation policy

During experimental `0.x`, deprecated interfaces may be removed in a later API-version increment. VoxRigor will document known migrations when practical, but there is no guaranteed deprecation window. Plugin authors should pin the API version they implement and run integration tests when upgrading the host.

After API `1.0`, deprecating a public plugin symbol or behavior must:

1. identify the affected symbol or behavior and the first release where it is deprecated;
2. document a supported replacement and a migration example;
3. emit a `DeprecationWarning` where a runtime warning is practical, while retaining a documentation notice;
4. retain the deprecated contract for at least one complete subsequent API MINOR release; and
5. remove it only in a later API MAJOR release, with the migration documented in release notes.

Security fixes, vulnerabilities and urgent privacy corrections may require accelerated removal. Such exceptions must explain the risk and migration in release notes; compatibility must not override user safety.

## Supported validation matrix

The current SDK/example integration gate is tested on Windows and Ubuntu with Python 3.11, 3.12 and 3.13. These are the environments exercised by repository CI; they are not a claim that every third-party plugin dependency supports every platform. A plugin publisher is responsible for testing its native libraries, optional dependencies and supported host range.

The clean-wheel integration test builds the core and example plugin distributions, installs them in a fresh virtual environment, checks metadata-only discovery and validation, verifies default-disabled behavior, and runs the registered diagnostic using the installed CLI.

## Plugin publisher guidance

- Pin or constrain the VoxRigor package dependency to a tested host range; do not assume package version and plugin API version are interchangeable.
- Set `PluginMetadata.api_version` to the exact API contract implemented.
- Test wheel installation and real entry-point discovery, not only mocked `EntryPoint` objects.
- Keep permission declarations minimal and accurate. They are operator-consent metadata, not an OS sandbox.
- Publish migration notes when changing the plugin API version.
- Never claim that a plugin is sandboxed or that its declared permissions are technically enforced by the current loader.

## Enforcement in this repository

The plugin SDK contract test asserts the current API identifier and verifies that unsupported API identifiers are rejected by metadata validation. The full CI matrix runs lint, formatting, strict typing, tests and the independently packaged example-wheel integration across all six supported OS/Python combinations.

Passing these checks validates the repository's current SDK contract. It does not certify a third-party plugin's safety or behavior.