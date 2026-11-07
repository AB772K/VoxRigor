# Third-Party Model and Runtime Notices

This document records third-party model sources used by the optional Phase 3 adapters. The VoxRigor Apache-2.0 license does not relicense third-party model artifacts, source code, datasets or runtimes.

## ECAPA-TDNN

- Hugging Face repository: https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb
- Pinned model revision: `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Model card license: Apache-2.0
- Runtime project: https://github.com/speechbrain/speechbrain
- Runtime interface: `speechbrain.inference.classifiers.EncoderClassifier`
- Runtime package: `speechbrain>=1.1.2,<1.2`
- Runtime license: Apache-2.0
- Model paper: Desplanques, Thienpondt and Demuynck, “ECAPA-TDNN: Emphasized Channel Attention, Propagation and Aggregation in TDNN Based Speaker Verification,” Interspeech 2020.

The model card describes a VoxCeleb-trained speaker embedding model and recommends cosine distance for speaker verification. It explicitly gives no warranty for performance on other datasets. VoxRigor downloads this exact revision to a local snapshot and overrides the upstream `pretrained_path` setting so checkpoint references cannot silently follow `main`.

## AASIST-L

- Hugging Face repository: https://huggingface.co/SpeechAntiSpoofingBenchmarks/AASIST-L
- Pinned ONNX artifact revision: `2bc4bf063f34f081cafa5d51c2e72bbfa5d39715`
- File: `aasist-l.onnx`
- Model card license: MIT (inherited from the upstream implementation)
- Upstream implementation: https://github.com/clovaai/aasist
- Model paper: Jung et al., “AASIST: Audio Anti-Spoofing using Integrated Spectro-Temporal Graph Attention Networks,” ICASSP 2022; https://arxiv.org/abs/2110.01200

AASIST-L is the lightweight variant. Its model card specifies a 16 kHz mono waveform and deterministic 64,600-sample evaluation window. The bona-fide score is class-logit column 1. Reported benchmark results are dataset- and protocol-specific and must not be generalized to arbitrary deployments.

## Runtime dependencies

- PyTorch and TorchAudio: https://pytorch.org/get-started/locally/
- SpeechBrain: https://github.com/speechbrain/speechbrain
- ONNX Runtime: https://github.com/microsoft/onnxruntime
- Hugging Face Hub: https://github.com/huggingface/huggingface_hub
- NumPy: https://github.com/numpy/numpy
- SciPy: https://github.com/scipy/scipy
- SoundFile: https://github.com/bastibe/python-soundfile

## Review and provenance policy

1. Do not commit pretrained model weights to the VoxRigor repository.
2. Fetch only documented repository IDs, file names and pinned revisions.
3. Record the resolved model revision and SHA-256 of every artifact used in an experiment.
4. Review upstream licenses before distributing, modifying or commercially using model artifacts.
5. Keep each third-party license and attribution with any redistributed artifact.
6. Do not use a model card's benchmark number as a performance guarantee.
7. Re-evaluate model artifacts when upstream repositories or runtimes change.

Last reviewed: 2026-11-07.
