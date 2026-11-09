# Phase 7 — Plugin SDK, integrations and usability

**Status:** First plugin-contract slice implemented. The API is experimental (0.1) and is not yet a stable compatibility guarantee.

## Design boundary

VoxRigor plugins are Python distributions that publish entry points in the voxrigor.plugins group. A plugin factory returns an object with validated PluginMetadata and a register(context) method. The context accepts test implementations whose IDs are namespaced under the plugin ID.

The loader does not import plugins during discovery or allow-list validation. It loads only IDs in a separate, explicit configuration file. All enabled plugins are staged before their tests are atomically added to the in-memory registry. If a later plugin fails validation or registration, none of the staged tests are added.

**This is not a sandbox.** Calling an entry point imports and executes third-party Python code in the VoxRigor process. Factory construction and plugin registration can execute arbitrary code before its declared permissions are checked. Permission labels are an auditable consent/metadata contract only; they do not restrict filesystem, audio, model or network access. Loaded plugins have the same operating-system permissions as the current user. A plugin can also perform side effects before registration fails; registry atomicity does not roll back arbitrary plugin behavior. Install and enable only plugins whose source and publisher you trust. Strong isolation requires a separate worker/process/container security design and is not implemented in this slice.

## Discover and validate without importing code

List installed entry-point metadata:

~~~powershell
voxrigor plugins list
~~~

This reads installed package metadata and does not import the plugin module.

Create an explicit allow-list such as voxrigor.plugins.json:

~~~json
{
  "schema_version": "0.1",
  "enabled_plugins": [
    {
      "plugin_id": "demo.voice",
      "granted_permissions": ["audio.read"]
    }
  ]
}
~~~

Validate that the enabled IDs are installed and that the configuration follows the schema:

~~~powershell
voxrigor plugins validate .\\voxrigor.plugins.json
~~~

Validation checks entry-point names and configuration metadata only. It does not import plugin modules, execute factories or prove that a plugin is benign.

## Plugin packaging contract

A complete, independently installable example package is maintained at `examples/plugins/demo-voice`. It includes a standalone `pyproject.toml`, source module, package README and a real `voxrigor.plugins` entry point. The integration test builds the VoxRigor core wheel and this example wheel, installs both into a fresh virtual environment, confirms metadata-only discovery/validation, checks that plugins remain disabled by default, and runs the example test through the installed `voxrigor` console command. CI exercises that clean-wheel path on Windows and Ubuntu with Python 3.11–3.13.

A third-party package declares an entry point in its own pyproject.toml:

~~~toml
[project.entry-points."voxrigor.plugins"]
"demo.voice" = "demo_voice.plugin:create_plugin"
~~~

A plugin factory returns an object with PluginMetadata and register(context). The plugin ID in metadata must match the entry-point and allow-list ID. The plugin can register only test IDs beginning with its own plugin ID followed by a period. Duplicate IDs, missing methods, invalid descriptors, API-version mismatches and permission mismatches are rejected.

The current permission vocabulary is:

- audio.read
- filesystem.read
- filesystem.write
- model.load
- network.loopback

A configured grant must match the plugin's declared required-permission set exactly. These values are declarations and operator intent records, not enforced capabilities. In particular, network.loopback does not create a network sandbox or limit Python sockets.

## Explicitly load and execute enabled plugins

List built-in tests and the explicitly enabled plugin tests:

~~~powershell
voxrigor tests --plugin-config .\\voxrigor.plugins.json
~~~

Run a selected plugin test:

~~~powershell
voxrigor run --project .\\voxrigor.json --plugin-config .\\voxrigor.plugins.json --test-id demo.voice.diagnostic
~~~

Omitting --plugin-config leaves third-party plugins disabled. The loader stages all enabled plugin registrations first and commits them to the registry as one batch. This protects the registry from partial registration, but it does not undo side effects performed by imported plugin code.

## Validation

CI uses synthetic plugin fixtures to exercise metadata discovery and allow-list validation without code import; explicit loading and namespaced test registration; API, metadata and permission mismatches; invalid plugin registrations; duplicate IDs and all-or-nothing registry updates; and CLI listing, validation and explicit run-time loading. A separate integration test builds and installs the example plugin as a wheel in a fresh virtual environment and runs it through the public CLI.

Passing these tests validates the SDK contract and registry behavior only. It does not certify third-party plugins, isolate their code or prove their security. The first slice does not include containerized workers, permission enforcement, plugin signing or cryptographic publisher verification.

## SDK versioning and deprecation

The plugin API is currently experimental at `0.1`; its version is independent of the VoxRigor package version. The loader requires an exact API-version match and does not silently accept unknown versions. The repository's compatibility, migration and deprecation rules are documented in [Plugin SDK Versioning and Compatibility Policy](PLUGIN_SDK_COMPATIBILITY.md). That policy distinguishes experimental `0.x` behavior from compatibility promises that will apply only after a separately approved stable `1.0` plugin API gate.


## Isolated plugin worker — design only

A platform-specific worker architecture has been documented in [Isolated Plugin Worker Design](PLUGIN_WORKER_ISOLATION_DESIGN.md). It covers process isolation, bounded JSON IPC, staged-file capabilities, Linux rootless OCI and Windows AppContainer candidate backends, resource controls, fail-closed behavior and adversarial acceptance tests. **This design is not implemented.** The current `--plugin-config` loader still executes third-party code in-process with the current user's OS permissions; it is not a sandbox.
