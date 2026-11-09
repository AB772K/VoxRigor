# VoxRigor Demo Voice Plugin

This is a separately packaged, intentionally harmless example of the VoxRigor plugin SDK.

It publishes the `demo.voice` entry point and registers one diagnostic test:

- Test ID: `demo.voice.sdk-diagnostic`
- Required permissions: none
- Result: `inconclusive`
- Scope: SDK wiring only; no audio, biometric model, authentication target or security control is tested.

## Build and install

From the repository root, after installing VoxRigor's development dependencies:

```powershell
python -m pip wheel --no-deps --no-build-isolation --wheel-dir .\dist\demo-voice .\examples\plugins\demo-voice
python -m pip install .\dist\demo-voice\voxrigor_demo_voice_plugin-0.1.0-py3-none-any.whl
```

The plugin declares a dependency on `voxrigor==0.2.0.dev0`; install a compatible VoxRigor release first.

## Discover, validate and run

Create `voxrigor.plugins.json`:

```json
{
  "schema_version": "0.1",
  "enabled_plugins": [
    {
      "plugin_id": "demo.voice",
      "granted_permissions": []
    }
  ]
}
```

Then run:

```powershell
voxrigor plugins list
voxrigor plugins validate .\voxrigor.plugins.json
voxrigor tests --plugin-config .\voxrigor.plugins.json
voxrigor run --project .\voxrigor.json --plugin-config .\voxrigor.plugins.json --test-id demo.voice.sdk-diagnostic
```

**Security note:** this example has no requested permissions and performs no external actions. The VoxRigor plugin loader is not a sandbox; installing/loading other plugins executes their Python code with the current process' operating-system privileges.
