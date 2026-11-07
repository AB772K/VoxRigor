from pathlib import Path

from voxrigor.models import ProjectManifest
from voxrigor.provenance import build_provenance, canonical_json_bytes, sha256_bytes, sha256_file


def test_canonical_json_ignores_dictionary_insertion_order() -> None:
    assert canonical_json_bytes({"a": 1, "b": 2}) == canonical_json_bytes({"b": 2, "a": 1})


def test_sha256_bytes_known_value() -> None:
    expected = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert sha256_bytes(b"abc") == expected


def test_sha256_file_streams_content(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(b"abc")
    assert sha256_file(str(path)) == sha256_bytes(b"abc")


def test_provenance_has_config_hash() -> None:
    manifest = ProjectManifest(name="lab")
    provenance = build_provenance(manifest, random_seed=17)
    assert len(provenance.config_sha256) == 64
    assert provenance.random_seed == 17
    assert provenance.python_version
    assert provenance.framework_version
