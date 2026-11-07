# Minimal offline project example

From the repository root, run:

```bash
voxrigor validate examples/minimal-project/voxrigor.json
voxrigor run --project examples/minimal-project/voxrigor.json --output ./example-runs
```

The runtime diagnostic returns `inconclusive` because it does not evaluate a biometric model or security control. This fixture exists to verify manifest parsing, test orchestration and report generation.
