# Contributing to VoxRigor

Thank you for considering a contribution. VoxRigor is currently a pre-alpha research framework; interfaces and schemas may change before the first stable release.

## Before opening a pull request

1. Open or comment on an issue for substantial changes so the objective and methodology can be discussed.
2. Do not include real voice recordings, biometric templates, credentials, customer data, model checkpoints, or private assessment evidence.
3. Confirm that any code, dataset metadata, model integration, fixture, or documentation you contribute can legally be distributed under the project's applicable terms. Third-party material keeps its own license.
4. For security-sensitive changes, explain the threat model and how the change avoids expanding target scope or introducing unsafe defaults.

## Development setup

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
python -m pytest --cov=voxrigor --cov-report=term-missing
ruff check .
ruff format --check .
mypy src/voxrigor
```

## Contribution expectations

- Add tests for new behavior and regression tests for fixed defects.
- Keep the core independent of optional machine-learning packages.
- Preserve explicit result statuses and sample-accounting rules.
- Document metric semantics, score direction, thresholds and denominators.
- Do not silently drop samples or rewrite official dataset splits.
- Keep biometric and personal data local; test fixtures should be synthetic or appropriately authorized.
- Do not claim a plugin is sandboxed unless an actual, tested isolation boundary exists.
- Keep documentation aligned with implemented behavior. Planned capabilities must be labelled as planned.

## Pull request checklist

- [ ] The change has a clear purpose and issue/context.
- [ ] Tests cover the change and relevant edge cases.
- [ ] Lint, formatting and type checks pass.
- [ ] Public interfaces and report schemas are updated where needed.
- [ ] Security, privacy, licensing and reproducibility impacts are documented.
- [ ] No secrets or sensitive biometric material are included.
