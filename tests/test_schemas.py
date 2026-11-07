import json
from pathlib import Path

from jsonschema import Draft202012Validator

from voxrigor.manifest import create_manifest
from voxrigor.models import ProjectManifest
from voxrigor.testing import TestRunner as Runner, build_default_registry

SCHEMA_DIR = Path(__file__).parents[1] / "schemas"


def _schema(name: str) -> dict:
    schema = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def test_project_manifest_schema_accepts_model_output(tmp_path: Path) -> None:
    manifest_path = tmp_path / "voxrigor.json"
    manifest = create_manifest(manifest_path, "Schema Test")
    Draft202012Validator(_schema("project-manifest-0.1.schema.json")).validate(
        manifest.model_dump(mode="json")
    )


def test_test_result_schema_accepts_model_output(tmp_path: Path) -> None:
    manifest = ProjectManifest(name="Schema Test")
    report = Runner(build_default_registry()).run(manifest)
    result = report.results[0]
    Draft202012Validator(_schema("test-result-0.1.schema.json")).validate(
        result.model_dump(mode="json")
    )


def test_run_report_schema_accepts_model_output() -> None:
    report = Runner(build_default_registry()).run(ProjectManifest(name="Schema Test"))
    Draft202012Validator(_schema("run-report-0.1.schema.json")).validate(
        report.model_dump(mode="json")
    )
