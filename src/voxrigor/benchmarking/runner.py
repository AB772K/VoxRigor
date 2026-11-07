"""Orchestration for offline score-trial benchmark runs."""

from __future__ import annotations

from pathlib import Path

from voxrigor.benchmarking.dataset import load_score_dataset
from voxrigor.benchmarking.errors import BenchmarkError
from voxrigor.benchmarking.reporting import build_benchmark_report, write_benchmark_report


def run_benchmark(manifest_path: Path, output_root: Path) -> Path:
    """Validate a dataset manifest, evaluate its declared split and write a report."""

    dataset = load_score_dataset(manifest_path)
    report, curve = build_benchmark_report(dataset)
    try:
        return write_benchmark_report(report, output_root, curve)
    except BenchmarkError:
        raise
