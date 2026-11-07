"""Strict CSV score-trial ingestion, integrity checks and sample accounting."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from voxrigor.benchmarking.errors import DatasetManifestError, ScoreFileError
from voxrigor.benchmarking.models import BenchmarkTask, DatasetManifest

REQUIRED_COLUMNS = {"trial_id", "label", "score"}
SUPPORTED_COLUMNS = REQUIRED_COLUMNS | {
    "split",
    "condition",
    "attack_species",
    "speaker_id",
    "source_id",
}
LABELS = {
    BenchmarkTask.ASV: {"target", "nontarget"},
    BenchmarkTask.PAD: {"bonafide", "spoof"},
}


@dataclass(frozen=True, slots=True)
class ScoreTrial:
    trial_id: str
    label: str
    score: float
    split: str
    condition: str
    attack_species: str | None
    speaker_id: str | None
    source_id: str | None


@dataclass(frozen=True, slots=True)
class ScoreDataset:
    manifest: DatasetManifest
    manifest_path: Path
    score_path: Path
    records: tuple[ScoreTrial, ...]
    input_rows: int
    other_split_rows: int
    split_counts: dict[str, int]
    label_counts: dict[str, int]
    split_label_counts: dict[str, dict[str, int]]
    condition_counts: dict[str, int]
    unknown_columns: tuple[str, ...]
    group_overlap_counts: dict[str, int]
    score_file_sha256: str
    manifest_sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ScoreFileError("Could not read the declared score file") from exc
    return digest.hexdigest()


def load_dataset_manifest(path: Path) -> DatasetManifest:
    if not path.is_file():
        raise DatasetManifestError(f"Dataset manifest not found: {path}")
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        return DatasetManifest.model_validate(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        if isinstance(exc, ValidationError):
            details = "; ".join(
                f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                for item in exc.errors()
            )
            raise DatasetManifestError(f"Dataset manifest validation failed: {details}") from exc
        raise DatasetManifestError("Dataset manifest is not readable UTF-8 JSON") from exc


def _resolve_score_path(manifest_path: Path, score_file: str) -> Path:
    """Resolve a score file without allowing a manifest to escape its dataset folder."""

    base_directory = manifest_path.parent.resolve()
    candidate = (base_directory / score_file).resolve()
    try:
        candidate.relative_to(base_directory)
    except ValueError as exc:
        raise ScoreFileError(
            "The score file path must remain within the dataset manifest directory"
        ) from exc
    if not candidate.is_file():
        raise ScoreFileError("The score file declared by the dataset manifest does not exist")
    return candidate


def load_score_dataset(manifest_path: Path) -> ScoreDataset:
    manifest_path = manifest_path.resolve()
    manifest = load_dataset_manifest(manifest_path)
    score_path = _resolve_score_path(manifest_path, manifest.score_file)
    actual_hash = sha256_file(score_path)
    if actual_hash != manifest.score_file_sha256:
        raise ScoreFileError("Score file SHA-256 does not match the dataset manifest")

    seen_ids: set[str] = set()
    records: list[ScoreTrial] = []
    split_counts: Counter[str] = Counter()
    label_counts: Counter[str] = Counter()
    split_label_counts: dict[str, Counter[str]] = defaultdict(Counter)
    condition_counts: Counter[str] = Counter()
    group_values: dict[str, dict[str, set[str]]] = {
        column: defaultdict(set) for column in manifest.group_columns
    }
    unknown_columns: set[str] = set()
    input_rows = 0

    try:
        with score_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ScoreFileError("Score CSV is empty or has no header")
            headers = reader.fieldnames
            if len(headers) != len(set(headers)):
                raise ScoreFileError("Score CSV contains duplicate column names")
            missing = REQUIRED_COLUMNS - set(headers)
            if missing:
                raise ScoreFileError(
                    "Score CSV is missing required columns: " + ", ".join(sorted(missing))
                )
            unknown_columns = set(headers) - SUPPORTED_COLUMNS
            missing_group_columns = set(manifest.group_columns) - set(headers)
            if missing_group_columns:
                raise ScoreFileError(
                    "Configured group columns are missing: "
                    + ", ".join(sorted(missing_group_columns))
                )
            has_split = "split" in headers
            if not has_split and manifest.evaluation_split != "all":
                raise ScoreFileError("evaluation_split requires a split column in the score CSV")
            if not has_split and manifest.threshold_source.value == "development_split":
                raise ScoreFileError(
                    "development_split threshold provenance requires a split column"
                )
            for row_number, row in enumerate(reader, start=2):
                input_rows += 1
                if None in row:
                    raise ScoreFileError(f"CSV row {row_number} has more values than the header")
                trial_id = (row.get("trial_id") or "").strip()
                if not trial_id:
                    raise ScoreFileError(f"CSV row {row_number} has an empty trial_id")
                if len(trial_id) > 160:
                    raise ScoreFileError(f"CSV row {row_number} trial_id exceeds 160 characters")
                if trial_id in seen_ids:
                    raise ScoreFileError(f"Duplicate trial_id found at CSV row {row_number}")
                seen_ids.add(trial_id)

                label = (row.get("label") or "").strip().lower()
                if label not in LABELS[manifest.task]:
                    accepted = ", ".join(sorted(LABELS[manifest.task]))
                    raise ScoreFileError(
                        f"CSV row {row_number} has an unsupported label; expected one of: {accepted}"
                    )
                raw_score = (row.get("score") or "").strip()
                try:
                    score = float(raw_score)
                except ValueError as exc:
                    raise ScoreFileError(f"CSV row {row_number} has a non-numeric score") from exc
                if not (float("-inf") < score < float("inf")):
                    raise ScoreFileError(f"CSV row {row_number} score must be finite")

                if has_split:
                    split = (row.get("split") or "").strip()
                    if not split:
                        raise ScoreFileError(f"CSV row {row_number} has an empty split")
                else:
                    split = "all"
                split_counts[split] += 1
                split_label_counts[split][label] += 1
                condition = (row.get("condition") or "unspecified").strip() or "unspecified"
                attack_species = (row.get("attack_species") or "").strip() or None
                if manifest.task is BenchmarkTask.PAD and label == "spoof" and not attack_species:
                    raise ScoreFileError(
                        f"CSV row {row_number} is a spoof trial without attack_species"
                    )

                speaker_id = (row.get("speaker_id") or "").strip() or None
                source_id = (row.get("source_id") or "").strip() or None
                for column, value in (("speaker_id", speaker_id), ("source_id", source_id)):
                    if column in group_values:
                        if not value:
                            raise ScoreFileError(
                                f"CSV row {row_number} has an empty configured group value for {column}"
                            )
                        group_values[column][split].add(value)

                selected = manifest.evaluation_split == "all" or split == manifest.evaluation_split
                if selected:
                    records.append(
                        ScoreTrial(
                            trial_id=trial_id,
                            label=label,
                            score=score,
                            split=split,
                            condition=condition,
                            attack_species=attack_species,
                            speaker_id=speaker_id,
                            source_id=source_id,
                        )
                    )
                    label_counts[label] += 1
                    condition_counts[condition] += 1
    except ScoreFileError:
        raise
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise ScoreFileError("Score CSV could not be parsed as UTF-8 CSV") from exc

    if input_rows == 0:
        raise ScoreFileError("Score CSV contains no trial rows")
    if not records:
        raise ScoreFileError("The selected evaluation split contains no trials")
    if manifest.task is BenchmarkTask.ASV:
        required_labels = {"target", "nontarget"}
    else:
        required_labels = {"bonafide", "spoof"}
    missing_labels = required_labels - set(label_counts)
    if missing_labels:
        raise ScoreFileError(
            "Selected evaluation split is missing required classes: "
            + ", ".join(sorted(missing_labels))
        )
    if manifest.threshold_source.value == "development_split":
        selection_split = manifest.threshold_selection_split
        if not selection_split or selection_split not in split_counts:
            raise ScoreFileError("Declared threshold-selection split is absent from the score CSV")
        if not required_labels.issubset(split_label_counts[selection_split]):
            raise ScoreFileError(
                "Declared threshold-selection split must contain every required class"
            )

    overlap_counts: dict[str, int] = {}
    for column, split_map in group_values.items():
        if len(split_map) > 1:
            sets = list(split_map.values())
            shared: set[str] = set()
            for index, first in enumerate(sets):
                for second in sets[index + 1 :]:
                    shared.update(first.intersection(second))
            overlap_counts[column] = len(shared)
        else:
            overlap_counts[column] = 0
    if manifest.require_group_disjointness and len(split_counts) < 2:
        raise ScoreFileError("Group-disjointness enforcement requires at least two declared splits")
    if manifest.require_group_disjointness:
        failures = {key: count for key, count in overlap_counts.items() if count > 0}
        if failures:
            detail = ", ".join(f"{key}={count}" for key, count in sorted(failures.items()))
            raise ScoreFileError(f"Declared split group-disjointness policy failed: {detail}")

    manifest_hash = sha256_file(manifest_path)
    return ScoreDataset(
        manifest=manifest,
        manifest_path=manifest_path,
        score_path=score_path,
        records=tuple(records),
        input_rows=input_rows,
        other_split_rows=input_rows - len(records),
        split_counts=dict(sorted(split_counts.items())),
        label_counts=dict(sorted(label_counts.items())),
        split_label_counts={
            split: dict(sorted(counts.items()))
            for split, counts in sorted(split_label_counts.items())
        },
        condition_counts=dict(sorted(condition_counts.items())),
        unknown_columns=tuple(sorted(unknown_columns)),
        group_overlap_counts=overlap_counts,
        score_file_sha256=actual_hash,
        manifest_sha256=manifest_hash,
    )
