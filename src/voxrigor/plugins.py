"""Explicit, opt-in discovery and loading for third-party test plugins.

Entry-point discovery reads installed package metadata only. Loading a plugin imports
and executes third-party Python code in the current process; it is not a sandbox.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from voxrigor.models import TestDescriptor
from voxrigor.testing import TestPlugin, TestRegistry

PLUGIN_ENTRY_POINT_GROUP = "voxrigor.plugins"
PLUGIN_API_VERSION: Literal["0.1"] = "0.1"


class PluginPermission(StrEnum):
    """Permission labels declared by a plugin and granted by the operator.

    These labels are an auditable contract, not an operating-system security boundary.
    """

    AUDIO_READ = "audio.read"
    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"
    MODEL_LOAD = "model.load"
    NETWORK_LOOPBACK = "network.loopback"


class PluginLoadError(ValueError):
    """Raised when an explicitly enabled plugin fails its declared contract."""


class PluginMetadata(BaseModel):
    """Metadata returned by a plugin factory before test registration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plugin_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,79}$")
    name: str = Field(min_length=1, max_length=120)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[.-][a-zA-Z0-9.-]+)?$")
    api_version: Literal["0.1"] = PLUGIN_API_VERSION
    publisher: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    required_permissions: list[PluginPermission] = Field(default_factory=list, max_length=16)

    @field_validator("required_permissions")
    @classmethod
    def permissions_must_be_unique(cls, values: list[PluginPermission]) -> list[PluginPermission]:
        if len(set(values)) != len(values):
            raise ValueError("required_permissions must not contain duplicates")
        return values


class EnabledPluginConfig(BaseModel):
    """One explicitly enabled plugin and the permissions granted to it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plugin_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,79}$")
    granted_permissions: list[PluginPermission] = Field(default_factory=list, max_length=16)

    @field_validator("granted_permissions")
    @classmethod
    def grants_must_be_unique(cls, values: list[PluginPermission]) -> list[PluginPermission]:
        if len(set(values)) != len(values):
            raise ValueError("granted_permissions must not contain duplicates")
        return values


class PluginConfig(BaseModel):
    """Separate allow-list file; project manifests do not implicitly enable plugins."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1"] = "0.1"
    enabled_plugins: list[EnabledPluginConfig] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def enabled_plugin_ids_must_be_unique(self) -> PluginConfig:
        ids = [plugin.plugin_id for plugin in self.enabled_plugins]
        if len(ids) != len(set(ids)):
            raise ValueError("enabled plugin_id values must be unique")
        return self


class PluginRegistrationContext:
    """Collects plugin tests before atomically adding them to the live registry."""

    def __init__(
        self,
        metadata: PluginMetadata,
        granted_permissions: frozenset[PluginPermission],
    ) -> None:
        self.plugin_id = metadata.plugin_id
        self.metadata = metadata
        self.granted_permissions = granted_permissions
        self._pending: list[TestPlugin] = []

    @property
    def pending_tests(self) -> tuple[TestPlugin, ...]:
        return tuple(self._pending)

    def register(self, plugin_test: TestPlugin) -> None:
        """Register a test under this plugin's namespace."""

        descriptor = getattr(plugin_test, "descriptor", None)
        if not isinstance(descriptor, TestDescriptor):
            raise PluginLoadError(
                f"Plugin {self.plugin_id!r} registered a test without a valid TestDescriptor"
            )
        required_prefix = f"{self.plugin_id}."
        if not descriptor.test_id.startswith(required_prefix):
            raise PluginLoadError(
                f"Plugin {self.plugin_id!r} may only register test IDs beginning with "
                f"{required_prefix!r}"
            )
        if not callable(getattr(plugin_test, "execute", None)):
            raise PluginLoadError(
                f"Plugin {self.plugin_id!r} registered a test without an execute method"
            )
        if any(item.descriptor.test_id == descriptor.test_id for item in self._pending):
            raise PluginLoadError(
                f"Plugin {self.plugin_id!r} registered duplicate test ID {descriptor.test_id!r}"
            )
        self._pending.append(plugin_test)


class VoxRigorExternalPlugin(Protocol):
    """Factory-created external plugin object implemented by third-party packages."""

    metadata: PluginMetadata

    def register(self, context: PluginRegistrationContext) -> None:
        """Register namespaced TestPlugin implementations."""


class PluginFactory(Protocol):
    """Factory exported by the voxrigor.plugins Python entry-point group."""

    def __call__(self) -> VoxRigorExternalPlugin:
        """Create one plugin instance."""


@dataclass(frozen=True)
class InstalledPluginInfo:
    """Non-executable information returned by installed entry-point discovery."""

    plugin_id: str
    entry_point: str
    distribution: str


@dataclass(frozen=True)
class PluginLoadResult:
    """Result of explicitly loading enabled plugins into a test registry."""

    loaded_plugin_ids: tuple[str, ...]
    registered_test_ids: tuple[str, ...]


def load_plugin_config(path: Path) -> PluginConfig:
    """Read the strict, separate plugin allow-list without importing plugin code."""

    if not path.is_file():
        raise PluginLoadError(f"Plugin configuration file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return PluginConfig.model_validate(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PluginLoadError("Plugin configuration is not readable UTF-8 JSON") from exc
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in exc.errors()
        )
        raise PluginLoadError(f"Plugin configuration validation failed: {details}") from exc


def discover_installed_plugins() -> list[InstalledPluginInfo]:
    """List installed plugin entry points without importing or executing them."""

    try:
        installed = entry_points(group=PLUGIN_ENTRY_POINT_GROUP)
    except Exception as exc:
        raise PluginLoadError(
            f"Could not inspect installed plugin entry points ({type(exc).__name__})"
        ) from exc

    results: list[InstalledPluginInfo] = []
    for entry_point in installed:
        distribution = "unknown"
        dist = getattr(entry_point, "dist", None)
        if dist is not None:
            distribution = getattr(dist, "name", None) or "unknown"
        results.append(
            InstalledPluginInfo(
                plugin_id=entry_point.name,
                entry_point=entry_point.value,
                distribution=distribution,
            )
        )
    return sorted(results, key=lambda item: (item.plugin_id, item.distribution))


def _resolve_entry_points(
    installed_entry_points: Sequence[EntryPoint] | None,
) -> list[EntryPoint]:
    try:
        return list(
            installed_entry_points
            if installed_entry_points is not None
            else entry_points(group=PLUGIN_ENTRY_POINT_GROUP)
        )
    except Exception as exc:
        raise PluginLoadError(
            f"Could not inspect installed plugin entry points ({type(exc).__name__})"
        ) from exc


def _validate_enabled_entries(
    config: PluginConfig,
    available: Sequence[EntryPoint],
) -> dict[str, EntryPoint]:
    by_name: dict[str, list[EntryPoint]] = {}
    for item in available:
        by_name.setdefault(item.name, []).append(item)

    selected: dict[str, EntryPoint] = {}
    for enabled in config.enabled_plugins:
        candidates = by_name.get(enabled.plugin_id, [])
        if not candidates:
            raise PluginLoadError(
                f"Enabled plugin {enabled.plugin_id!r} is not installed in entry-point group "
                f"{PLUGIN_ENTRY_POINT_GROUP!r}"
            )
        if len(candidates) != 1:
            raise PluginLoadError(
                f"Plugin ID {enabled.plugin_id!r} is ambiguous: "
                f"{len(candidates)} matching entry points are installed"
            )
        selected[enabled.plugin_id] = candidates[0]
    return selected


def validate_plugin_config(
    path: Path,
    *,
    installed_entry_points: Sequence[EntryPoint] | None = None,
) -> PluginConfig:
    """Validate the explicit allow-list against installed entry points without importing code."""

    config = load_plugin_config(path)
    available = _resolve_entry_points(installed_entry_points)
    _validate_enabled_entries(config, available)
    return config


def load_enabled_plugins(
    config_path: Path,
    registry: TestRegistry,
    *,
    installed_entry_points: Sequence[EntryPoint] | None = None,
) -> PluginLoadResult:
    """Load only plugins named by the allow-list and add their tests atomically.

    This imports third-party Python code with the current process' operating-system
    permissions. Declared permissions are an audit and consent contract only; this
    loader does not sandbox or technically restrict plugin code. All enabled plugins
    are staged before any test is added to the registry, so a later plugin failure
    cannot leave an earlier plugin partially enabled.
    """

    config = load_plugin_config(config_path)
    if not config.enabled_plugins:
        return PluginLoadResult(loaded_plugin_ids=(), registered_test_ids=())

    available = _resolve_entry_points(installed_entry_points)
    selected_entries = _validate_enabled_entries(config, available)
    loaded_plugin_ids: list[str] = []
    registered_test_ids: list[str] = []
    staged_plugins: list[TestPlugin] = []
    staged_test_ids: set[str] = set()
    existing_test_ids = {descriptor.test_id for descriptor in registry.list()}

    for enabled in config.enabled_plugins:
        entry_point = selected_entries[enabled.plugin_id]
        try:
            factory = entry_point.load()
            if not callable(factory):
                raise PluginLoadError(
                    f"Plugin {enabled.plugin_id!r} entry point must resolve to a zero-argument factory"
                )
            plugin_object = factory()
        except PluginLoadError:
            raise
        except Exception as exc:
            raise PluginLoadError(
                f"Plugin {enabled.plugin_id!r} failed during import or initialization "
                f"({type(exc).__name__}); exception text was omitted"
            ) from exc

        try:
            metadata_value = getattr(plugin_object, "metadata", None)
            metadata = PluginMetadata.model_validate(metadata_value)
        except Exception as exc:
            raise PluginLoadError(
                f"Plugin {enabled.plugin_id!r} returned invalid PluginMetadata"
            ) from exc

        if metadata.plugin_id != enabled.plugin_id or metadata.plugin_id != entry_point.name:
            raise PluginLoadError(
                f"Plugin metadata ID {metadata.plugin_id!r} does not match its configured "
                f"and installed entry-point ID {enabled.plugin_id!r}"
            )
        if metadata.api_version != PLUGIN_API_VERSION:
            raise PluginLoadError(
                f"Plugin {enabled.plugin_id!r} requires SDK API {metadata.api_version!r}; "
                f"this installation supports {PLUGIN_API_VERSION!r}"
            )

        required = set(metadata.required_permissions)
        granted = set(enabled.granted_permissions)
        missing = sorted(item.value for item in required - granted)
        undeclared = sorted(item.value for item in granted - required)
        if missing:
            raise PluginLoadError(
                f"Plugin {enabled.plugin_id!r} requires explicit grants for: {', '.join(missing)}"
            )
        if undeclared:
            raise PluginLoadError(
                f"Plugin {enabled.plugin_id!r} has unnecessary permission grants: "
                f"{', '.join(undeclared)}"
            )

        register = getattr(plugin_object, "register", None)
        if not callable(register):
            raise PluginLoadError(
                f"Plugin {enabled.plugin_id!r} does not implement register(context)"
            )
        context = PluginRegistrationContext(metadata, frozenset(granted))
        try:
            register(context)
        except PluginLoadError:
            raise
        except Exception as exc:
            raise PluginLoadError(
                f"Plugin {enabled.plugin_id!r} failed while registering tests "
                f"({type(exc).__name__}); exception text was omitted"
            ) from exc

        pending = context.pending_tests
        if not pending:
            raise PluginLoadError(f"Plugin {enabled.plugin_id!r} did not register any tests")

        new_ids = [plugin_test.descriptor.test_id for plugin_test in pending]
        duplicates = sorted((set(new_ids) | staged_test_ids) & existing_test_ids)
        duplicate_staged = sorted(set(new_ids) & staged_test_ids)
        duplicates = sorted(set(duplicates) | set(duplicate_staged))
        if duplicates:
            raise PluginLoadError(
                f"Plugin {enabled.plugin_id!r} conflicts with registered or staged test IDs: "
                + ", ".join(duplicates)
            )

        staged_plugins.extend(pending)
        staged_test_ids.update(new_ids)
        loaded_plugin_ids.append(enabled.plugin_id)
        registered_test_ids.extend(new_ids)

    try:
        registry.register_many(staged_plugins)
    except ValueError as exc:
        raise PluginLoadError(
            "Could not atomically add enabled plugin tests to the registry"
        ) from exc

    return PluginLoadResult(
        loaded_plugin_ids=tuple(loaded_plugin_ids),
        registered_test_ids=tuple(registered_test_ids),
    )
