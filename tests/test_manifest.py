from pathlib import Path

import pytest

from voxrigor.errors import ManifestError, ProjectExistsError
from voxrigor.manifest import create_manifest, load_manifest


def test_create_and_load_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "voxrigor.json"
    created = create_manifest(manifest_path, "  Research Lab  ", "  test project  ")
    loaded = load_manifest(manifest_path)

    assert loaded.project_id == created.project_id
    assert loaded.name == "Research Lab"
    assert loaded.description == "test project"
    assert loaded.scope.mode == "offline"


def test_create_refuses_to_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "voxrigor.json"
    create_manifest(path, "First")
    original = path.read_bytes()

    with pytest.raises(ProjectExistsError):
        create_manifest(path, "Second")

    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "content",
    ["{not json", '{"schema_version": "9.9", "name": "bad"}', '{"name": "   "}'],
)
def test_invalid_manifest_is_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "voxrigor.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ManifestError):
        load_manifest(path)


def test_manifest_rejects_unknown_fields(tmp_path: Path) -> None:
    path = tmp_path / "voxrigor.json"
    path.write_text('{"name":"lab","unexpected":true}', encoding="utf-8")

    with pytest.raises(ManifestError, match="unexpected"):
        load_manifest(path)


def test_manifest_not_found(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="not found"):
        load_manifest(tmp_path / "missing.json")
