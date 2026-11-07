# VoxRigor Repository Integration Status

**The repository bundle has already been integrated into the review branch. Do not upload it again.**

The active branch is `phase-2-offline-benchmark`, and its implementation is proposed for merging through [Pull Request #2](https://github.com/AB772K/VoxRigor/pull/2).

## Validation results

- 78 automated tests passed locally; 86.75% coverage.
- ASV and PAD synthetic CLI workflows validated.
- GitHub Actions passed on Ubuntu and Windows with Python 3.11, 3.12 and 3.13.
- Ruff lint, Ruff formatting, strict Mypy and pytest all passed in each matrix job.

## Important repository files

- `.gitignore` is project-specific and should remain. It excludes caches, virtual environments, secrets, local datasets/output, audio recordings and model checkpoints.
- `.gitattributes` keeps CSV line endings stable across Windows and POSIX so the recorded score-file SHA-256 hashes remain reproducible.
- Keep the existing `LICENSE`; it was not replaced.

## Phase 2 scope

The benchmark engine evaluates **precomputed ASV/PAD scores**. It does not load audio or run biometric models. Supplied fixtures are fabricated numeric test data, not real performance evidence.

## Manual validation on Windows PowerShell

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest -q --cov=voxrigor --cov-report=term-missing
voxrigor benchmark validate .\examples\fixtures\asv_benchmark.json
voxrigor benchmark run .\examples\fixtures\asv_benchmark.json --output .\runs\asv
voxrigor benchmark validate .\examples\fixtures\pad_benchmark.json
voxrigor benchmark run .\examples\fixtures\pad_benchmark.json --output .\runs\pad
```
