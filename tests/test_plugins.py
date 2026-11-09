from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from typer.testing import CliRunner

from voxrigor.cli import app
from voxrigor.models import ProjectManifest, ResultStatus, TestDescriptor
from voxrigor.plugins import (
    PLUGIN_API_VERSION,
    PLUGIN_ENTRY_POINT_GROUP,
    EnabledPluginConfig,
    PluginConfig,
    PluginLoadError,
    PluginMetadata,
    PluginPermission,
    PluginRegistrationContext,
    discover_installed_plugins,
    load_enabled_plugins,
    validate_plugin_config,
)
from voxrigor.testing import (
    TestContext,
    TestOutcome,
    TestRegistry,
    build_default_registry,
)

runner = CliRunner()
SCHEMA_DIR = Path(__file__).parents[1] / "schemas"


@dataclass
class FakeEntryPoint:
    name: str
    factory: Callable[[], object]
    value: str = "fake_plugin:factory"
    dist: object | None = None
    load_calls: int = 0

    def load(self) -> Callable[[], object]:
        self.load_calls += 1
        return self.factory


class ExampleTest:
    def __init__(self, test_id: str) -> None:
        self.descriptor = TestDescriptor(
            test_id=test_id,
            version="0.1.0",
            name="Example plugin check",
            category="plugin_example",
            description="A synthetic plugin test used by the SDK contract tests.",
        )

    def execute(self, context: TestContext) -> TestOutcome:
        return TestOutcome(
            status=ResultStatus.INCONCLUSIVE,
            measurements={"project": context.project.name, "plugin_check": "executed"},
            limitations=("Synthetic test fixture; no target or biometric model was assessed.",),
        )


class ExamplePlugin:
    def __init__(
        self,
        plugin_id: str,
        *,
        permissions: list[PluginPermission] | None = None,
        test_id: str | None = None,
    ) -> None:
        self.metadata = PluginMetadata(
            plugin_id=plugin_id,
            name="Example plugin",
            version="0.1.0",
            publisher="VoxRigor SDK tests",
            description="Synthetic plugin used to test the plugin contract.",
            required_permissions=permissions or [],
        )
        self.test_id = test_id or f"{plugin_id}.health"

    def register(self, context: PluginRegistrationContext) -> None:
        context.register(ExampleTest(self.test_id))


class InvalidNamespacePlugin(ExamplePlugin):
    def register(self, context: PluginRegistrationContext) -> None:
        context.register(ExampleTest("other-plugin.health"))


def _write_config(
    path: Path,
    enabled: list[dict[str, object]],
) -> Path:
    path.write_text(
        json.dumps({"schema_version": "0.1", "enabled_plugins": enabled}, indent=2),
        encoding="utf-8",
    )
    return path


def _enabled(plugin_id: str, grants: list[str] | None = None) -> dict[str, object]:
    return {"plugin_id": plugin_id, "granted_permissions": grants or []}


def _entry_point(
    plugin_id: str,
    factory: Callable[[], object],
) -> FakeEntryPoint:
    return FakeEntryPoint(
        name=plugin_id,
        factory=factory,
        dist=type("Distribution", (), {"name": "example-plugin-distribution"})(),
    )


def _schema() -> dict[str, Any]:
    schema = json.loads((SCHEMA_DIR / "plugin-config-0.1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def test_plugin_api_version_is_explicit_and_rejects_unsupported_versions() -> None:
    assert PLUGIN_API_VERSION == "0.1"
    assert ExamplePlugin("demo.voice").metadata.api_version == PLUGIN_API_VERSION

    with pytest.raises(ValueError):
        PluginMetadata(
            plugin_id="demo.voice",
            name="Example plugin",
            version="0.1.0",
            api_version="0.2",
            publisher="tests",
            description="Unsupported API versions must not be silently accepted.",
        )


def test_plugin_config_schema_and_pydantic_contract_agree() -> None:
    valid = {
        "schema_version": "0.1",
        "enabled_plugins": [
            {
                "plugin_id": "demo.voice",
                "granted_permissions": ["audio.read", "model.load"],
            }
        ],
    }
    Draft202012Validator(_schema()).validate(valid)
    assert PluginConfig.model_validate(valid).enabled_plugins[0].plugin_id == "demo.voice"

    invalid = {
        "schema_version": "0.1",
        "enabled_plugins": [{"plugin_id": "demo.voice", "granted_permissions": ["network.remote"]}],
    }
    with pytest.raises(JSONSchemaValidationError):
        Draft202012Validator(_schema()).validate(invalid)
    with pytest.raises(ValueError):
        PluginConfig.model_validate(invalid)


def test_plugin_config_rejects_duplicate_ids_and_permissions(tmp_path: Path) -> None:
    duplicate_plugins = _write_config(
        tmp_path / "duplicate-plugins.json",
        [_enabled("demo.voice"), _enabled("demo.voice")],
    )
    with pytest.raises(PluginLoadError, match="validation failed"):
        validate_plugin_config(
            duplicate_plugins,
            installed_entry_points=[cast(Any, _entry_point("demo.voice", lambda: None))],
        )

    with pytest.raises(ValueError, match="duplicate"):
        EnabledPluginConfig(
            plugin_id="demo.voice",
            granted_permissions=[PluginPermission.AUDIO_READ, PluginPermission.AUDIO_READ],
        )


def test_discovery_lists_metadata_without_importing_plugins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    entry = _entry_point("demo.voice", lambda: calls.append("loaded"))
    monkeypatch.setattr(
        "voxrigor.plugins.entry_points",
        lambda **kwargs: [entry] if kwargs.get("group") == PLUGIN_ENTRY_POINT_GROUP else [],
    )

    discovered = discover_installed_plugins()

    assert [item.plugin_id for item in discovered] == ["demo.voice"]
    assert discovered[0].distribution == "example-plugin-distribution"
    assert calls == []
    assert entry.load_calls == 0


def test_validate_config_checks_installed_id_without_importing_plugin_code(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    entry = _entry_point("demo.voice", lambda: calls.append("loaded"))
    config = _write_config(tmp_path / "plugins.json", [_enabled("demo.voice")])

    validated = validate_plugin_config(config, installed_entry_points=[cast(Any, entry)])

    assert validated.enabled_plugins[0].plugin_id == "demo.voice"
    assert calls == []
    assert entry.load_calls == 0


def test_valid_plugin_loads_only_after_explicit_allow_list_and_registers_namespace(
    tmp_path: Path,
) -> None:
    entry = _entry_point(
        "demo.voice",
        lambda: ExamplePlugin("demo.voice", permissions=[PluginPermission.AUDIO_READ]),
    )
    config = _write_config(
        tmp_path / "plugins.json",
        [_enabled("demo.voice", ["audio.read"])],
    )
    registry = build_default_registry()

    result = load_enabled_plugins(config, registry, installed_entry_points=[cast(Any, entry)])

    assert result.loaded_plugin_ids == ("demo.voice",)
    assert result.registered_test_ids == ("demo.voice.health",)
    assert "demo.voice.health" in [item.test_id for item in registry.list()]
    assert entry.load_calls == 1


def test_plugin_requires_exact_explicit_permission_grants(tmp_path: Path) -> None:
    entry = _entry_point(
        "demo.voice",
        lambda: ExamplePlugin("demo.voice", permissions=[PluginPermission.AUDIO_READ]),
    )
    missing = _write_config(tmp_path / "missing.json", [_enabled("demo.voice")])
    registry = build_default_registry()
    with pytest.raises(PluginLoadError, match="requires explicit grants"):
        load_enabled_plugins(missing, registry, installed_entry_points=[cast(Any, entry)])
    assert "demo.voice.health" not in [item.test_id for item in registry.list()]

    extra = _write_config(
        tmp_path / "extra.json",
        [_enabled("demo.voice", ["audio.read", "model.load"])],
    )
    with pytest.raises(PluginLoadError, match="unnecessary permission grants"):
        load_enabled_plugins(extra, registry, installed_entry_points=[cast(Any, entry)])
    assert "demo.voice.health" not in [item.test_id for item in registry.list()]


def test_plugin_id_and_test_namespace_must_match_allow_list(tmp_path: Path) -> None:
    mismatch = _entry_point("demo.voice", lambda: ExamplePlugin("other.plugin"))
    config = _write_config(tmp_path / "mismatch.json", [_enabled("demo.voice")])
    with pytest.raises(PluginLoadError, match="metadata ID"):
        load_enabled_plugins(
            config, build_default_registry(), installed_entry_points=[cast(Any, mismatch)]
        )

    wrong_namespace = _entry_point("demo.voice", lambda: InvalidNamespacePlugin("demo.voice"))
    with pytest.raises(PluginLoadError, match="test IDs beginning"):
        load_enabled_plugins(
            config, build_default_registry(), installed_entry_points=[cast(Any, wrong_namespace)]
        )


def test_plugin_loader_stages_every_plugin_before_atomic_registry_update(tmp_path: Path) -> None:
    alpha = _entry_point("alpha.plugin", lambda: ExamplePlugin("alpha.plugin"))
    beta = _entry_point("beta.plugin", lambda: InvalidNamespacePlugin("beta.plugin"))
    config = _write_config(
        tmp_path / "plugins.json",
        [_enabled("alpha.plugin"), _enabled("beta.plugin")],
    )
    registry = build_default_registry()
    before = [item.test_id for item in registry.list()]

    with pytest.raises(PluginLoadError, match="test IDs beginning"):
        load_enabled_plugins(
            config,
            registry,
            installed_entry_points=[cast(Any, alpha), cast(Any, beta)],
        )

    assert [item.test_id for item in registry.list()] == before
    assert alpha.load_calls == 1
    assert beta.load_calls == 1


def test_loader_rejects_existing_test_id_without_mutating_registry(tmp_path: Path) -> None:
    core = _entry_point(
        "core",
        lambda: ExamplePlugin("core", test_id="core.runtime-info"),
    )
    config = _write_config(tmp_path / "plugins.json", [_enabled("core")])
    registry = build_default_registry()

    with pytest.raises(PluginLoadError, match="conflicts"):
        load_enabled_plugins(config, registry, installed_entry_points=[cast(Any, core)])

    assert [item.test_id for item in registry.list()] == ["core.runtime-info"]


def test_registration_context_rejects_invalid_descriptor_and_duplicate_test_ids() -> None:
    context = PluginRegistrationContext(
        PluginMetadata(
            plugin_id="demo.voice",
            name="Example plugin",
            version="0.1.0",
            publisher="tests",
            description="tests",
        ),
        frozenset(),
    )
    with pytest.raises(PluginLoadError, match="valid TestDescriptor"):
        context.register(type("NoDescriptor", (), {"execute": lambda self, value: None})())
    context.register(ExampleTest("demo.voice.health"))
    with pytest.raises(PluginLoadError, match="duplicate test ID"):
        context.register(ExampleTest("demo.voice.health"))


def test_registry_register_many_is_atomic_on_duplicate(tmp_path: Path) -> None:
    registry = TestRegistry()
    registry.register(ExampleTest("alpha.plugin.first"))
    with pytest.raises(ValueError, match="Duplicate"):
        registry.register_many(
            [ExampleTest("beta.plugin.second"), ExampleTest("alpha.plugin.first")]
        )
    assert [item.test_id for item in registry.list()] == ["alpha.plugin.first"]


def test_plugin_cli_discovery_and_validation_do_not_import_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    entry = _entry_point("demo.voice", lambda: calls.append("loaded"))
    monkeypatch.setattr(
        "voxrigor.plugins.entry_points",
        lambda **kwargs: [entry] if kwargs.get("group") == PLUGIN_ENTRY_POINT_GROUP else [],
    )
    config = _write_config(tmp_path / "plugins.json", [_enabled("demo.voice")])

    list_result = runner.invoke(app, ["plugins", "list"])
    assert list_result.exit_code == 0, list_result.output
    assert "demo.voice" in list_result.output

    validate_result = runner.invoke(app, ["plugins", "validate", str(config)])
    assert validate_result.exit_code == 0, validate_result.output
    assert "no plugin code was imported" in validate_result.output.lower()
    assert calls == []
    assert entry.load_calls == 0


def test_cli_requires_explicit_plugin_config_before_plugin_code_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _entry_point("demo.voice", lambda: ExamplePlugin("demo.voice"))
    monkeypatch.setattr(
        "voxrigor.plugins.entry_points",
        lambda **kwargs: [entry] if kwargs.get("group") == PLUGIN_ENTRY_POINT_GROUP else [],
    )
    project_path = tmp_path / "voxrigor.json"
    project_path.write_text(
        ProjectManifest(name="Plugin CLI test").model_dump_json(), encoding="utf-8"
    )
    config = _write_config(tmp_path / "plugins.json", [_enabled("demo.voice")])

    result = runner.invoke(
        app,
        [
            "run",
            "--project",
            str(project_path),
            "--output",
            str(tmp_path / "runs"),
            "--test-id",
            "demo.voice.health",
            "--plugin-config",
            str(config),
        ],
    )

    assert result.exit_code == 0, result.output
    assert entry.load_calls == 1
    assert "no sandbox is provided" in result.output.lower()


def test_disabled_plugins_are_not_loaded_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    entry = _entry_point("demo.voice", lambda: calls.append("loaded"))
    monkeypatch.setattr(
        "voxrigor.plugins.entry_points",
        lambda **kwargs: [entry] if kwargs.get("group") == PLUGIN_ENTRY_POINT_GROUP else [],
    )

    registry = build_default_registry()

    assert [item.test_id for item in registry.list()] == ["core.runtime-info"]
    assert calls == []
    assert entry.load_calls == 0
