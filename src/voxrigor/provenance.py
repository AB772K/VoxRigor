"""Stable configuration hashing and run provenance helpers."""

from __future__ import annotations

import hashlib
import json
import platform
from typing import Any

from voxrigor import __version__
from voxrigor.models import ProjectManifest, RunProvenance


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON-compatible data deterministically."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def sha256_bytes(content: bytes) -> str:
    """Return a lowercase SHA-256 hexadecimal digest."""

    return hashlib.sha256(content).hexdigest()


def sha256_file(path: str) -> str:
    """Hash a file incrementally without loading it fully into memory."""

    digest = hashlib.sha256()
    with open(path, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_provenance(manifest: ProjectManifest, random_seed: int | None = None) -> RunProvenance:
    """Capture runtime details and a hash of the validated manifest."""

    config_hash = sha256_bytes(canonical_json_bytes(manifest.model_dump(mode="json")))
    return RunProvenance(
        framework_version=__version__,
        python_version=platform.python_version(),
        platform=platform.platform(),
        config_sha256=config_hash,
        random_seed=random_seed,
    )
