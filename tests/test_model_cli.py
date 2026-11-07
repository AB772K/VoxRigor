from typer.testing import CliRunner

from voxrigor.biometrics.catalog import list_builtin_models
from voxrigor.biometrics.cli import models_app


def test_model_catalog_exposes_two_explicit_baselines() -> None:
    descriptors = list_builtin_models()
    assert {item.model_id for item in descriptors} == {"ecapa-tdnn", "aasist-l-onnx"}
    assert all(not item.calibrated for item in descriptors)


def test_models_list_command_does_not_require_ml_backends() -> None:
    result = CliRunner().invoke(models_app, ["list"])
    assert result.exit_code == 0, result.output
    assert "ecapa-tdnn" in result.output
    assert "aasist-l-onnx" in result.output
    assert "not universal authentication decisions" in result.output
