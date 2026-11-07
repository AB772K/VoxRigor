# Changelog

All notable changes to VoxRigor will be documented here.

## Unreleased — Phase 2 offline benchmark engine

- Added strict score-trial CSV ingestion and dataset manifests with SHA-256 integrity checks.
- Added ASV FMR/FNMR, trial-level Wilson intervals, empirical ROC/AUC and interpolated EER.
- Added PAD BPCER and per-attack-species APCER reporting.
- Added split/condition accounting, optional explicit group-overlap checks and synthetic fixtures.
- Added JSON, HTML, ROC CSV and PAD species CSV benchmark artifacts.
- Added CI workflow to the repository integration branch.

## Phase 1 core prototype

- Added a lightweight Python package and Typer CLI.
- Added strict offline project manifest validation.
- Added explicit built-in test registration and orchestration.
- Added run IDs, UTC timestamps, result statuses and configuration provenance.
- Added JSON and HTML report generation and machine-readable schemas.
