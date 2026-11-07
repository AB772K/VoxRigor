# VoxRigor

**Open-source Voice Authentication Security Testing & Evaluation Framework**

VoxRigor is an independent open-source security research project intended to help fellow researchers, biometric engineers and developers evaluate the security and robustness of voice authentication systems.

The project brings together reproducible biometric benchmarking, optional model integrations, presentation-attack evaluation, audio robustness testing and—on the roadmap—authentication protocol and API security assessment.

## Project status

**Current development:** Phase 3 — optional biometric model adapters (development preview).

Implemented capabilities currently include offline evaluation of precomputed ASV/PAD scores, dataset integrity checks, benchmark reporting, and optional ECAPA-TDNN and AASIST-L model adapters.

Real pretrained-checkpoint inference validation is still pending. Consult the phase documentation before relying on the adapters in research or production.

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
- [Third-party model notices](docs/THIRD_PARTY_MODELS.md)
- [Phase 3 acceptance gates](docs/PHASE_3_ACCEPTANCE.md)

## Mission

I am developing VoxRigor as an independent security researcher to help fellow security researchers and developers systematically investigate how voice authentication systems behave under biometric, audio and application-level security tests.

**Research openly. Test rigorously. Report honestly.**

## Responsible use

Only test audio and systems you own or are explicitly authorized to assess. VoxRigor is a research and evaluation framework, not a certification authority or a guarantee that a tested system is secure. Scores from pretrained models must not be treated as calibrated probabilities or universal authentication decisions.

## License

VoxRigor's original code is distributed under Apache-2.0. Third-party model artifacts, datasets and dependencies retain their respective licenses and usage restrictions.
