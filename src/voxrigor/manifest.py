"""Project manifest creation and validation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from voxrigor.errors import ManifestError, ProjectExistsError
from voxrigor.models import ProjectManifest

DEFAULT_MANIFEST = "voxrigor.json"


def create_manifest(path: Path, name: str, description: str = "") -> ProjectManifest:
    """Create a new manifest without overwriting an existing file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = ProjectManifest(name=name, description=description)
    content = manifest.model_dump_json(indent=2) + "\n"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    except FileExistsError as exc:
        raise ProjectExistsError(f"Refusing to overwrite existing file: {path}") from exc

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return manifest


def load_manifest(path: Path) -> ProjectManifest:
    """Load and validate a JSON project manifest."""

    if not path.is_file():
        raise ManifestError(f"Project manifest not found: {path}")
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        return ProjectManifest.model_validate(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ManifestError(f"Manifest is not valid UTF-8 JSON: {path}") from exc
    except OSError as exc:
        raise ManifestError(f"Could not read manifest {path}: {exc}") from exc
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in exc.errors()
        )
        raise ManifestError(f"Manifest validation failed: {details}") from exc