# Dataset, Model and Artifact Policy

**Status:** Draft 0.1 — Phase 0  
**Policy owner:** VoxRigor maintainers

## 1. Core rule

VoxRigor distributes framework code and adapters, not third-party voice datasets or pretrained weights by default. A dataset or model being publicly downloadable does not automatically grant redistribution, commercial use, modification or all research uses.

Every integration must have a recorded provenance and license review before it is recommended as a default dependency or included in release automation.

## 2. Candidate datasets

| Dataset | Potential use | Initial decision | License/provenance caution |
|---|---|---|---|
| ASVspoof 5 | Stand-alone deepfake detection and spoofing-aware ASV | High-priority benchmark adapter | Follow official registration/download instructions and evaluation rules. Do not redistribute the data. Verify current dataset terms directly with organizers before use. |
| ASVspoof 2019 LA/PA | Historical logical/physical access anti-spoofing benchmark | Compatibility adapter after ASVspoof 5 path | Official database page directs users to a license process for at least some data. Do not assume a third-party mirror's helper-code license applies to the audio. |
| ASVspoof 2021 LA/DF/PA | Cross-dataset/generalization testing | Candidate external evaluation | Verify original source terms and exact protocol; any third-party repackaging may have a separate license only for the repackaging code or derived files. |
| In-The-Wild | Realistic audio-deepfake generalization | Candidate external evaluation | Official Fraunhofer page states the dataset and documentation are Apache-2.0; verify current source package and attribution requirements. Public-figure audio still requires ethical handling. |
| MLAAD | Multilingual audio anti-spoofing | Optional research-only adapter | Dataset card states CC BY-NC 4.0 and non-commercial academic research only. Do not bundle it or use it in commercial tests without permission/appropriate legal review. |
| VoxCeleb 1/2 | Speaker verification training/evaluation | Candidate only after terms review | Check dataset and source-video licensing, redistribution and research restrictions separately. |
| Consented local recordings | Reference app/test fixtures | Preferred for local functional tests | Obtain informed consent, document purpose/retention, avoid recording bystanders and support deletion. |

## 3. ASVspoof-specific cautions

ASVspoof 5's evaluation plan defines separate Track 1 (stand-alone deepfake detection) and Track 2 (spoofing-aware speaker verification) protocols and sets restrictions on data use, including speaker/utterance overlap restrictions for the open condition. A model trained on data that overlaps with ASVspoof 5 speakers or utterances may invalidate a claimed open-condition evaluation.

VoxRigor must preserve the benchmark's official split/trial files and protocol metadata. It must not merge training and development partitions to create an undocumented split or use evaluation data for threshold selection. If a user's selected external data cannot be shown not to overlap, the report must flag the limitation and must not label the result as valid under the official open condition.

## 4. Dataset adapter contract requirements

Each dataset adapter must declare:

- dataset identifier and release/version;
- official source URL and access date;
- license/terms URL and reviewed status;
- citation/BibTeX where provided;
- file format, sample rate, channels and encoding expectations;
- label schema and label provenance;
- speaker/source/generator/attack metadata fields, if available;
- official split names and trial protocol;
- whether the data may be used for commercial, academic or research-only purposes;
- required user action (download, account, click-through or signed agreement).

The adapter must not silently convert labels, discard samples or alter audio. Any normalization/transformation must be recorded and, where possible, produce a derived artifact hash.

## 5. Candidate model integrations

### SpeechBrain ECAPA-TDNN

- Model card: https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb
- The model card declares Apache-2.0.
- Purpose: speaker-verification embedding/scoring baseline.
- It is not a PAD/anti-spoofing model.
- Record model revision, weight hash, preprocessing, sample-rate/channel assumptions and upstream code version.

### AASIST

- Upstream: https://github.com/clovaai/aasist
- Model card: https://huggingface.co/SpeechAntiSpoofingBenchmarks/AASIST
- The AASIST model card declares MIT for its package/checkpoint; upstream repository notices identify third-party subcomponents and their terms. Re-check the exact source files and artifacts used.
- Purpose: audio anti-spoofing countermeasure baseline.
- It is not a speaker-identity verifier.
- Record checkpoint hash, expected waveform length/sample rate, score direction and inference preprocessing.

### RawNet2 and others

Candidate only after a separate review of source license, checkpoint license, training data, dependencies, preprocessing and evaluation compatibility.

## 6. Model supply-chain requirements

- Do not load arbitrary checkpoint URLs automatically.
- Require a source, immutable revision and SHA-256 for model artifacts.
- Pin inference dependencies for reproducible environments.
- Review official model cards and repository license files; a model card label may not cover all dependencies or source code.
- Never assume source-code license automatically covers training data or weights.
- Treat checkpoint deserialization as a security-sensitive operation. Consult current upstream advisories before selecting PyTorch versions and loading APIs.
- A user-supplied checkpoint is untrusted input. Document this clearly; later releases may isolate model execution in a separate process/container.

## 7. Artifact and privacy rules

- Dataset/audio files are not committed to the repository.
- CI uses tiny synthetic fixtures, not restricted benchmark recordings or real user biometrics.
- Raw audio is excluded from reports by default.
- Every retained artifact records hash, media type, size, origin and retention policy.
- Reports redact tokens, API keys, email addresses and configured identifiers.
- Users control where artifacts are stored and when they are deleted.

## 8. Dataset/model inventory

Maintain a machine-readable inventory in a later phase with fields such as:

```yaml
id: example-model
kind: speaker_verification
source_url: https://example.invalid/model
revision: immutable-revision
sha256: required-for-local-checkpoint
license: Apache-2.0
license_url: https://example.invalid/license
commercial_use: unknown
redistribution: not_assumed
preprocessing:
  sample_rate_hz: 16000
  channels: 1
score_semantics:
  direction: higher_is_more_target_like
  output: similarity_score
```

The example URL is deliberately invalid and is a schema illustration only.

## 9. Public references

- ASVspoof 5: https://www.asvspoof.org/ and https://github.com/asvspoof-challenge/asvspoof5
- ASVspoof 2019 databases/license route: https://www.asvspoof.org/database
- ASVspoof 5 evaluation plan: https://www.asvspoof.org/file/ASVspoof5___Evaluation_Plan_Phase2.pdf
- In-The-Wild dataset: https://deepfake-demo.aisec.fraunhofer.de/in_the_wild
- MLAAD: https://huggingface.co/datasets/mueller91/MLAAD
- SpeechBrain ECAPA: https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb
- AASIST: https://github.com/clovaai/aasist
- PyTorch 2026 checkpoint security advisory: https://github.com/pytorch/pytorch/security/advisories/GHSA-63cw-57p8-fm3p
