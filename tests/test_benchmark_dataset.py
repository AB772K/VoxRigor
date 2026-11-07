import hashlib
import json
from pathlib import Path

import pytest

from voxrigor.benchmarking.dataset import load_score_dataset
from voxrigor.benchmarking.errors import ScoreFileError
from voxrigor.benchmarking.models import DatasetManifest


def _write_dataset(tmp_path: Path, csv_text: str, **overrides):
    score_path = tmp_path / "scores.csv"
    score_path.write_text(csv_text, encoding="utf-8")
    payload = {
        "dataset_id": "test-dataset",
        "dataset_name": "Test dataset",
        "dataset_version": "1",
        "task": "asv",
        "protocol_id": "test-protocol",
        "score_file": "scores.csv",
        "score_file_sha256": hashlib.sha256(score_path.read_bytes()).hexdigest(),
        "evaluation_split": "test",
        "score_direction": "higher_is_genuine",
        "operating_threshold": 0.5,
        "threshold_source": "external",
    }
    payload.update(overrides)
    manifest_path = tmp_path / "benchmark.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return manifest_path


VALID_CSV = (
    "trial_id,label,score,split,condition,speaker_id,source_id\n"
    "d1,target,0.9,dev,clean,a,x\n"
    "d2,nontarget,0.1,dev,clean,b,y\n"
    "t1,target,0.8,test,clean,c,z\n"
    "t2,nontarget,0.2,test,clean,d,w\n"
)


def test_loader_filters_split_and_reconciles_rows(tmp_path: Path) -> None:
    manifest = _write_dataset(tmp_path, VALID_CSV)
    dataset = load_score_dataset(manifest)
    assert len(dataset.records) == 2
    assert dataset.input_rows == 4
    assert dataset.other_split_rows == 2
    assert dataset.label_counts == {"nontarget": 1, "target": 1}
    assert dataset.split_counts == {"dev": 2, "test": 2}


def test_loader_rejects_modified_score_file_hash(tmp_path: Path) -> None:
    manifest = _write_dataset(tmp_path, VALID_CSV)
    (tmp_path / "scores.csv").write_text(
        VALID_CSV + "extra,target,0.7,test,clean,e,f\n", encoding="utf-8"
    )
    with pytest.raises(ScoreFileError, match="SHA-256"):
        load_score_dataset(manifest)


@pytest.mark.parametrize(
    "csv_text,expected",
    [
        ("label,score\ntarget,0.9\n", "missing required columns"),
        ("trial_id,label,score\nx,target,nan\ny,nontarget,0.1\n", "finite"),
        ("trial_id,label,score\nx,unknown,0.9\ny,nontarget,0.1\n", "unsupported label"),
        ("trial_id,label,score\nx,target,0.9\nx,nontarget,0.1\n", "Duplicate trial_id"),
    ],
)
def test_loader_rejects_invalid_score_csv(tmp_path: Path, csv_text: str, expected: str) -> None:
    manifest = _write_dataset(tmp_path, csv_text, evaluation_split="all")
    with pytest.raises(ScoreFileError, match=expected):
        load_score_dataset(manifest)


def test_pad_spoof_rows_require_attack_species(tmp_path: Path) -> None:
    csv_text = "trial_id,label,score,split\nb,bonafide,0.9,test\ns,spoof,0.1,test\n"
    manifest = _write_dataset(
        tmp_path,
        csv_text,
        task="pad",
        operating_threshold=0.5,
        threshold_source="external",
    )
    with pytest.raises(ScoreFileError, match="attack_species"):
        load_score_dataset(manifest)


def test_development_threshold_must_not_use_all_evaluation_splits() -> None:
    with pytest.raises(ValueError, match="named evaluation_split"):
        DatasetManifest(
            dataset_id="test-dataset",
            dataset_name="Test",
            dataset_version="1",
            task="asv",
            protocol_id="p1",
            score_file="scores.csv",
            score_file_sha256="a" * 64,
            evaluation_split="all",
            operating_threshold=0.5,
            threshold_source="development_split",
            threshold_selection_split="dev",
        )


def test_declared_group_disjointness_rejects_overlap(tmp_path: Path) -> None:
    csv_text = (
        "trial_id,label,score,split,speaker_id\n"
        "d1,target,0.9,dev,shared-speaker\n"
        "d2,nontarget,0.1,dev,dev-other\n"
        "t1,target,0.8,test,shared-speaker\n"
        "t2,nontarget,0.2,test,test-other\n"
    )
    manifest = _write_dataset(
        tmp_path,
        csv_text,
        group_columns=["speaker_id"],
        require_group_disjointness=True,
    )
    with pytest.raises(ScoreFileError, match="disjointness policy failed"):
        load_score_dataset(manifest)


def test_unknown_columns_are_reported_not_interpreted(tmp_path: Path) -> None:
    csv_text = (
        "trial_id,label,score,split,private_note\n"
        "t1,target,0.9,test,not-exported\n"
        "t2,nontarget,0.1,test,not-exported\n"
    )
    manifest = _write_dataset(tmp_path, csv_text)
    dataset = load_score_dataset(manifest)
    assert dataset.unknown_columns == ("private_note",)


def test_required_group_audit_needs_group_columns_and_two_splits(tmp_path: Path) -> None:
    csv_text = (
        "trial_id,label,score,split,speaker_id\nt,target,0.9,test,s1\nn,nontarget,0.1,test,s2\n"
    )
    manifest = _write_dataset(
        tmp_path, csv_text, group_columns=["speaker_id"], require_group_disjointness=True
    )
    with pytest.raises(ScoreFileError, match="at least two declared splits"):
        load_score_dataset(manifest)


def test_required_group_audit_rejects_missing_group_values(tmp_path: Path) -> None:
    csv_text = (
        "trial_id,label,score,split,speaker_id\n"
        "d1,target,0.9,dev,\n"
        "d2,nontarget,0.1,dev,s2\n"
        "t1,target,0.8,test,s3\n"
        "t2,nontarget,0.2,test,s4\n"
    )
    manifest = _write_dataset(
        tmp_path, csv_text, group_columns=["speaker_id"], require_group_disjointness=True
    )
    with pytest.raises(ScoreFileError, match="empty .* group value"):
        load_score_dataset(manifest)


def test_development_split_threshold_is_accepted_only_with_distinct_present_split(
    tmp_path: Path,
) -> None:
    manifest = _write_dataset(
        tmp_path,
        VALID_CSV,
        threshold_source="development_split",
        threshold_selection_split="dev",
    )
    dataset = load_score_dataset(manifest)
    assert len(dataset.records) == 2


def test_loader_rejects_absent_evaluation_split(tmp_path: Path) -> None:
    manifest = _write_dataset(tmp_path, VALID_CSV, evaluation_split="production")
    with pytest.raises(ScoreFileError, match="contains no trials"):
        load_score_dataset(manifest)


def test_split_label_counts_are_reported_separately(tmp_path: Path) -> None:
    manifest = _write_dataset(tmp_path, VALID_CSV)
    dataset = load_score_dataset(manifest)

    assert dataset.split_label_counts == {
        "dev": {"nontarget": 1, "target": 1},
        "test": {"nontarget": 1, "target": 1},
    }


def test_declared_group_column_rejects_missing_values_even_without_enforcement(
    tmp_path: Path,
) -> None:
    csv_text = (
        "trial_id,label,score,split,speaker_id\n"
        "d1,target,0.9,dev,\n"
        "d2,nontarget,0.1,dev,s2\n"
        "t1,target,0.8,test,s3\n"
        "t2,nontarget,0.2,test,s4\n"
    )
    manifest = _write_dataset(tmp_path, csv_text, group_columns=["speaker_id"])

    with pytest.raises(ScoreFileError, match="empty configured group value"):
        load_score_dataset(manifest)


def test_development_threshold_split_must_contain_both_classes(tmp_path: Path) -> None:
    csv_text = (
        "trial_id,label,score,split\nd1,target,0.9,dev\nt1,target,0.8,test\nt2,nontarget,0.2,test\n"
    )
    manifest = _write_dataset(
        tmp_path,
        csv_text,
        threshold_source="development_split",
        threshold_selection_split="dev",
    )

    with pytest.raises(ScoreFileError, match="must contain every required class"):
        load_score_dataset(manifest)


def test_blank_threshold_selection_split_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        DatasetManifest(
            dataset_id="test-dataset",
            dataset_name="Test",
            dataset_version="1",
            task="asv",
            protocol_id="p1",
            score_file="scores.csv",
            score_file_sha256="a" * 64,
            evaluation_split="test",
            operating_threshold=0.5,
            threshold_source="development_split",
            threshold_selection_split="   ",
        )


def test_manifest_rejects_windows_absolute_score_paths() -> None:
    with pytest.raises(ValueError, match="relative path"):
        DatasetManifest(
            dataset_id="test-dataset",
            dataset_name="Test",
            dataset_version="1",
            task="asv",
            protocol_id="p1",
            score_file=r"C:\\private\\scores.csv",
            score_file_sha256="a" * 64,
        )


def test_group_overlap_is_reported_when_not_enforced(tmp_path: Path) -> None:
    csv_text = (
        "trial_id,label,score,split,speaker_id\n"
        "d1,target,0.9,dev,shared\n"
        "d2,nontarget,0.1,dev,dev-other\n"
        "t1,target,0.8,test,shared\n"
        "t2,nontarget,0.2,test,test-other\n"
    )
    manifest = _write_dataset(tmp_path, csv_text, group_columns=["speaker_id"])
    dataset = load_score_dataset(manifest)

    assert dataset.group_overlap_counts == {"speaker_id": 1}


def test_manifest_cannot_read_score_file_outside_its_directory(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text(
        "trial_id,label,score\nt,target,0.9\nn,nontarget,0.1\n",
        encoding="utf-8",
    )
    manifest = _write_dataset(
        dataset_dir,
        "trial_id,label,score\nt,target,0.9\nn,nontarget,0.1\n",
        score_file="../outside.csv",
        score_file_sha256=hashlib.sha256(outside.read_bytes()).hexdigest(),
        evaluation_split="all",
    )

    with pytest.raises(ScoreFileError, match="must remain within"):
        load_score_dataset(manifest)


def test_loader_rejects_blank_split_values_instead_of_silently_excluding_rows(
    tmp_path: Path,
) -> None:
    csv_text = (
        "trial_id,label,score,split\nt1,target,0.9,test\nn1,nontarget,0.1,test\nt2,target,0.8,\n"
    )
    manifest = _write_dataset(tmp_path, csv_text)
    with pytest.raises(ScoreFileError, match="empty split"):
        load_score_dataset(manifest)
