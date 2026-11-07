# VoxRigor Phase 2 Upload Guide

This archive contains the current repository snapshot: Phase 0 documentation, Phase 1 core framework, Phase 2 offline ASV/PAD score evaluation, synthetic fixtures, JSON schemas, tests, and GitHub Actions configuration.

## Before uploading

- Keep the existing repository `LICENSE` file. This archive intentionally does not replace it.
- Keep `.gitignore`. It excludes Python caches, virtual environments, secrets, local benchmark outputs, audio recordings, and model checkpoints. It is intentionally project-specific.
- Do not upload real voice recordings, biometric templates, credentials, `.env` files, personal identifiers, restricted datasets, model checkpoints, or generated run directories.

## Upload to the review branch

1. Open `https://github.com/AB772K/VoxRigor`.
2. Select branch `phase-2-offline-benchmark` in the branch selector.
3. Choose **Add file → Upload files**.
4. Extract this archive on your computer.
5. Upload the extracted files and folders while preserving their directory structure (`src/`, `tests/`, `docs/`, `schemas/`, `examples/`, `.github/`).
6. When GitHub asks how to handle existing files, replace the existing `README.md`, `.gitignore`, `CHANGELOG.md`, `pyproject.toml`, and Phase 1/Phase 2 docs with the versions in this snapshot. Do not replace `LICENSE`.
7. Commit with: `Implement Phase 2 offline ASV and PAD score evaluation`.

## Validate on Windows PowerShell

Run these commands from the extracted repository directory:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -q --cov=voxrigor --cov-report=term-missing
voxrigor --help
voxrigor benchmark --help
```

## Phase 2 commands

The evaluator consumes precomputed scores. It does not yet read audio or perform model inference.

```powershell
voxrigor benchmark validate .\examples\fixtures\asv_benchmark.json
voxrigor benchmark run .\examples\fixtures\asv_benchmark.json --output .\runs\asv
voxrigor benchmark validate .\examples\fixtures\pad_benchmark.json
voxrigor benchmark run .\examples\fixtures\pad_benchmark.json --output .\runs\pad
```

The ASV/PAD score fixtures contain fabricated numeric values solely for parser, metric, and report tests. They are not real model results and must not be presented as such.
