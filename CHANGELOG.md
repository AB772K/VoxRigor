# Changelog

All notable VoxRigor changes are documented here.

## 0.2.0.dev0 — Phase 3 biometric model integrations

- Added optional ECAPA-TDNN speaker embedding and cosine-similarity adapter.
- Added AASIST-L ONNX anti-spoofing adapter using a pinned model artifact revision.
- Added local audio decoding, duration limits, mono conversion, resampling and source hashing.
- Added model discovery, fetch and single-file scoring CLI commands.
- Kept heavyweight ML runtimes out of the base installation.
- Added model provenance notices, optional dependency groups and Phase 3 acceptance gates.
- Added deterministic adapter tests with fake runtimes and synthetic audio.

Real pretrained-checkpoint inference validation remains pending.
