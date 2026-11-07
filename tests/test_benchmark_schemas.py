import json
from pathlib import Path

from jsonschema import Draft202012Validator

from voxrigor.benchmarking.dataset import load_score_dataset
from voxrigor.benchmarking.reporting import build_benchmark_report

ROOT = Path(__file__).parents[1]


def test_dataset_manifest_schema_is_valid() -> None:
    schema = json.loads((ROOT / "schemas/score-dataset-manifest-0.1.schema.json").read_text())
    Draft202012Validator.check_schema(schema)


def test_benchmark_report_schema_accepts_generated_report() -> None:
    schema = json.loads((ROOT / "schemas/benchmark-report-0.1.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    manifest = ROOT / "examples/fixtures/asv_benchmark.json"
    dataset = load_score_dataset(manifest)
    report, _ = build_benchmark_report(dataset)
    Draft202012Validator(schema).validate(report.model_dump(mode="json"))


def test_model_generated_score_manifest_schema_is_valid_and_requires_provenance() -> None:
    schema = json.loads((ROOT / "schemas/score-dataset-manifest-0.2.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["schema_version"]["const"] == "0.2"
    assert "score_producer" in schema["required"]
    assert "ScoreProducer" in schema["$defs"]



def test_audio_condition_experiment_schema_is_valid() -> None:
    schema = json.loads(
        (ROOT / "schemas/audio-condition-experiment-0.1.schema.json").read_text()
    )
    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["scenarios"]["maxItems"] == 32


def test_score_producer_schema_supports_condition_provenance() -> None:
    schema = json.loads(
        (ROOT / "schemas/score-dataset-manifest-0.2.schema.json").read_text()
    )
    Draft202012Validator.check_schema(schema)
    producer = schema["$defs"]["ScoreProducer"]["properties"]
    assert "condition_provenance_file" in producer
    assert "condition_provenance_sha256" in producer
