# VoxRigor

**Open-source Voice Authentication Security Testing & Evaluation Framework**

VoxRigor is an independent open-source security research project intended to help fellow researchers, biometric engineers and developers evaluate the security and robustness of voice authentication systems.

The project brings together reproducible biometric benchmarking, optional model integrations, presentation-attack evaluation, audio robustness testing and—on the roadmap—authentication protocol and API security assessment.

## Project status

**Current development:** Phase 5 — local protocol and API security engine (development preview, lifecycle extension under validation). Phase 3 model integration work is merged into main. Phase 4 and Phase 5 are carried on the Phase 3 development branch; the Phase 4/5 development line is not yet integrated into main.

Phase 4 added deterministic local audio-condition generation and provenance verification. Its initial CI matrix passed on Ubuntu and Windows with Python 3.11–3.13. Physical replay hardware and approved-dataset accuracy studies remain open.

Implemented capabilities currently include offline evaluation of precomputed ASV/PAD scores, dataset integrity checks, benchmark reporting, optional ECAPA-TDNN and AASIST-L model adapters, and deterministic local audio-condition generation.

Both pinned pretrained model checkpoints passed runtime smoke tests using generated non-human audio. This validates checkpoint loading and adapter execution, not biometric accuracy. Approved-dataset evaluation and physical presentation rig testing remain open research tasks.

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

```powershell
voxrigor models list
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

## Mission

I am developing VoxRigor as an independent security researcher to help fellow security researchers and developers systematically investigate how voice authentication systems behave under biometric, audio and application-level security tests.

**Research openly. Test rigorously. Report honestly.**

## Responsible use

Only test audio and systems you own or are explicitly authorized to assess. VoxRigor is a research and evaluation framework, not a certification authority or a guarantee that a tested system is secure. Scores from pretrained models must not be treated as calibrated probabilities or universal authentication decisions.

## License

VoxRigor's original code is distributed under Apache-2.0. Third-party model artifacts, datasets and dependencies retain their respective licenses and usage restrictions.
