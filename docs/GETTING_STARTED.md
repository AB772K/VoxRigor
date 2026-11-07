# Getting Started (Phase 1)

> Phase 1 is a core-framework prototype. The only bundled test is a runtime diagnostic. It does not evaluate voice biometrics, audio, authentication protocols, or a target system.

## Requirements

- Python 3.11 or newer.
- No GPU or machine-learning framework is required.

## Install from a clone

```bash
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

## Create and validate a local project

```bash
voxrigor init ./my-voice-research --name "My Voice Research"
voxrigor validate ./my-voice-research/voxrigor.json
```

## Discover and execute the diagnostic test

```bash
voxrigor tests
voxrigor run --project ./my-voice-research/voxrigor.json --output ./my-voice-research/runs
```

The run writes `report.json` and `report.html` to a UUID-named directory. The built-in `core.runtime-info` test intentionally returns `inconclusive`, because it only verifies that the framework can run a test and collect provenance. It is not a security test.

## Validate an existing report

```bash
voxrigor report ./my-voice-research/runs/<run-id>/report.json
```

## Safety and privacy

This Phase 1 build has no network target adapter and performs no network testing. Do not add audio recordings, biometric templates, access tokens, or other sensitive material to source control. Run artifacts may contain project metadata; review them before sharing.
