# VoxRigor

**Open-source Voice Authentication Security Testing & Evaluation Framework**

VoxRigor is an independent open-source security research project intended to help fellow researchers, biometric engineers and developers evaluate the security and robustness of voice authentication systems.

The project brings together reproducible biometric benchmarking, optional model integrations, presentation-attack evaluation, audio robustness testing and authentication protocol/API security assessment.

## Project status

**Current development:** Phase 7 — experimental plugin SDK and integrations. Phase 1–3 implementation and Phase 5 local protocol/lifecycle work are integrated into `main`. Phase 4 audio-condition generation is implemented and validated on the development line; the digital-condition generator and provenance chain are available in the current codebase, while physical presentation hardware remains unimplemented.

The latest Phase 5 lifecycle extension passed the six-job GitHub Actions matrix on Ubuntu and Windows with Python 3.11, 3.12 and 3.13 (run [42593363565](https://github.com/AB772K/VoxRigor/actions/runs/42593363565)). The validation includes Ruff lint, Ruff formatting, strict Mypy, and the complete test suite. The Linux jobs completed 201 tests at 85.58% coverage against the configured 85% gate.

Implemented capabilities include offline evaluation of precomputed ASV/PAD scores, dataset integrity checks, benchmark reporting, optional ECAPA-TDNN and AASIST-L model adapters, deterministic local audio-condition generation, a bounded loopback-only protocol/API security engine, and the initial score-only cross-dataset research runner, optional cluster-bootstrap uncertainty for held-out ASV evaluation, condition-stratified ASV analysis using frozen calibration and operating thresholds, paired comparison of independently calibrated ASV systems on identical trial sets, optional nested cluster-bootstrap uncertainty that re-fits calibration and re-selects thresholds, an experimental opt-in third-party plugin contract with metadata-only discovery and explicit allow-list loading, plus a versioned bounded worker IPC foundation and fail-closed isolation-backend contract. No production isolation backend or worker launcher is implemented.

Both pinned pretrained model checkpoints passed runtime smoke tests using generated non-human audio. This validates checkpoint loading and adapter execution, not biometric accuracy. Approved-dataset evaluation, cross-dataset generalization studies, calibration research and physical presentation-rig validation remain research tasks.

The Phase 5 reference protocol service uses a deterministic synthetic assertion; it does not implement speaker recognition, PAD or liveness detection. Its results validate the scanner against controlled fixtures and must not be interpreted as production-system security evidence. Phase 6's automated research fixtures are synthetic score data, not biometric-performance evidence.

## Installation

The core package does not require machine-learning runtimes:

```powershell
python -m pip install -e .
```

Install only the adapter you need:

```powershell
# ECAPA-TDNN speaker verification
python -m pip install -e ".[speaker]"

# AASIST-L ONNX anti-spoofing
python -m pip install -e ".[pad-onnx]"

# Audio condition generation (resampling, seeded noise, mu-law, reverberation)
python -m pip install -e ".[audio]"
```

## Discover models

~~~powershell
voxrigor models list
~~~

## Third-party plugins (experimental)

~~~powershell
# Metadata-only discovery; does not import plugin code
voxrigor plugins list

# Validate an explicit allow-list; does not import plugin code
voxrigor plugins validate .\\voxrigor.plugins.json

# Load only plugins named in the allow-list when running tests
voxrigor run --project .\\voxrigor.json --plugin-config .\\voxrigor.plugins.json
~~~

**Plugin security boundary:** loading a Python plugin executes third-party code in-process with the current user's OS permissions. Permission labels are declarations only; this version does not sandbox plugins or enforce filesystem/network capabilities. Enable only packages whose source and publisher you trust. See the Phase 7 plugin SDK documentation for the contract and limitations.

## Run a research experiment

See [Phase 6 implementation](docs/PHASE_6_IMPLEMENTATION.md) for the manifest format and methodology.

```powershell
voxrigor research evaluate .\research-experiment.json --output .\runs\research

# Compare independently calibrated systems on identical ASV trials
voxrigor research compare .\research-comparison.json --output .\runs\research-comparisons
```

## Documentation

- [Getting started](docs/GETTING_STARTED.md)
- [Project charter](docs/PROJECT_CHARTER.md)
- [Requirements](docs/REQUIREMENTS.md)
- [Threat model](docs/THREAT_MODEL.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Phase 2 benchmark format](docs/BENCHMARK_DATA_FORMAT.md)
- [Phase 3 implementation](docs/PHASE_3_IMPLEMENTATION.md)
- [Audio-trial manifest and model-to-benchmark workflow](docs/AUDIO_TRIAL_MANIFEST.md)
- [Third-party model notices](docs/THIRD_PARTY_MODELS.md)
- [Phase 3 acceptance gates](docs/PHASE_3_ACCEPTANCE.md)
- [Phase 4 audio-condition implementation](docs/PHASE_4_IMPLEMENTATION.md)
- [Phase 4 acceptance gates](docs/PHASE_4_ACCEPTANCE.md)
- [Phase 5 protocol and API engine](docs/PHASE_5_IMPLEMENTATION.md)
- [Phase 5 acceptance gates](docs/PHASE_5_ACCEPTANCE.md)
- [Phase 6 research experiments](docs/PHASE_6_IMPLEMENTATION.md)
- [Phase 6 acceptance gates](docs/PHASE_6_ACCEPTANCE.md)
- [Phase 7 plugin SDK](docs/PHASE_7_IMPLEMENTATION.md)
- [Plugin SDK versioning and compatibility policy](docs/PLUGIN_SDK_COMPATIBILITY.md)
- [Isolated plugin worker design and protocol foundation (OS backend not yet implemented)](docs/PLUGIN_WORKER_ISOLATION_DESIGN.md)
- [Phase 7 acceptance gates](docs/PHASE_7_ACCEPTANCE.md)
- [Development roadmap](docs/ROADMAP.md)

## Mission

I am developing VoxRigor as an independent security researcher to help fellow security researchers and developers systematically investigate how voice authentication systems behave under biometric, audio and application-level security tests.

**Research openly. Test rigorously. Report honestly.**

## Responsible use

Only test audio and systems you own or are explicitly authorized to assess. VoxRigor is a research and evaluation framework, not a certification authority or a guarantee that a tested system is secure. Scores from pretrained models must not be treated as calibrated probabilities or universal authentication decisions.

## License

VoxRigor's original code is distributed under Apache-2.0. Third-party model artifacts, datasets and dependencies retain their respective licenses and usage restrictions.
