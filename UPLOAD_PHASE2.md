# VoxRigor Phase 2 Upload Guide

This branch contains the reviewed Phase 0/Phase 1 documentation updates, a project-specific `.gitignore`, and a GitHub Actions workflow. The Phase 2 Python implementation is supplied separately in the repository bundle and must be uploaded to this branch before the Phase 2 pull request is considered complete.

## Upload the implementation bundle

1. Download and extract the VoxRigor Phase 2 repository bundle supplied with this project.
2. Open https://github.com/AB772K/VoxRigor/tree/phase-2-offline-benchmark.
3. Choose **Add file → Upload files**.
4. Upload the extracted files and folders, preserving `src/`, `tests/`, `schemas/`, `examples/`, `docs/` and `.github/`.
5. Keep the existing repository `LICENSE`. Do not upload a replacement license.
6. Keep `.gitignore`; it prevents local caches, virtual environments, secrets, benchmark outputs, audio files and model checkpoints from being committed.
7. Commit with: `Implement Phase 2 offline ASV and PAD score evaluation`.

## Validate on Windows PowerShell

From the extracted repository directory:

```powershell
py -3.13 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -q --cov=voxrigor --cov-report=term-missing
voxrigor --help
voxrigor benchmark --help
```

## Phase 2 boundaries

Phase 2 evaluates user-supplied **precomputed scores**. It does not load waveform audio, run biometric models, or test a live authentication application. ASV/PAD sample fixtures in the bundle are fabricated test data and are not genuine model-performance evidence.
