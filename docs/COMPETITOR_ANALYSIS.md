# Competitor and Related-Work Analysis

**Research snapshot:** 2026-11-07  
**Status:** Initial desk research; not an exhaustive market or patent search.

## 1. Executive finding

VoxRigor should not be positioned as the first voice-biometric testing product. Research platforms already test speaker-recognition adversarial attacks and defenses; benchmark initiatives provide datasets and evaluation protocols; commercial vendors advertise end-to-end voice-biometric vulnerability assessment and voice-authentication workflow QA.

The defensible project strategy is to build an open-source, local-first framework that emphasizes test specification, adapter interoperability, provenance, evidence and separation of biometric, PAD, robustness and application-security results. Whether this combination is sufficiently differentiated must be validated with independent researchers and a deeper literature review.

## 2. Closest research and benchmark projects

### SEC4SR

- Official site: https://sec4sr.github.io/
- Paper: *A Security Analysis Platform for Speaker Recognition* (IEEE Transactions on Dependable and Secure Computing, 2022).
- Focus: speaker-recognition adversarial attacks and defenses, including adaptive and non-adaptive evaluation. The project describes a study of 15 attacks and 23 defenses and provides code/materials for reproduction.
- Overlap: model-level robustness and adversarial evaluation.
- Do not duplicate: its existing attack/defense implementations as a supposed novel contribution.
- Potential relationship: investigate an optional import/adapter or a comparison protocol; do not bundle its code until license, dependency and compatibility conditions are reviewed.

### SpeakerGuard

- Repository: https://github.com/SpeakerGuard
- Paper: *Towards Understanding and Mitigating Audio Adversarial Examples for Speaker Recognition*, IEEE TDSC, 2022.
- Project describes a PyTorch modular library with model, dataset, attack, defense, adaptive-attack and metric components; its README advertises seven attack types, 24 defenses and eight metrics.
- Its README asks commercial users to contact the authors. Do not assume that a public GitHub repository grants permission to redistribute or commercially integrate it. Inspect the repository's actual license files and ask the authors before reuse.
- Overlap: speaker-recognition attack/defense experiments and modular evaluation.
- Potential relationship: learn from its module boundaries; build independent interfaces and tests rather than copying implementation.

### ASVspoof

- Official site: https://www.asvspoof.org/
- ASVspoof 5 organizer baselines: https://github.com/asvspoof-challenge/asvspoof5
- Focus: challenge datasets, protocols, anti-spoofing countermeasures and spoofing-aware speaker verification.
- ASVspoof 5 has two tracks: stand-alone deepfake detection (Track 1) and spoofing-aware automatic speaker verification (Track 2). The official plan specifies minDCF as primary for Track 1 and a-DCF as primary for Track 2, with related secondary metrics.
- Baselines include RawNet2 and AASIST for Track 1, plus SASV baselines for Track 2.
- Overlap: datasets, score protocols, metrics and model baselines.
- Do not duplicate: the challenge itself or claim our metrics replace its official evaluation package.
- Potential relationship: support compatible input/output protocols and compare using official evaluation scripts when permitted.

### Speech Deepfake Arena

- Search/entry point: https://huggingface.co/collections/SpeechAntiSpoofingBenchmarks
- Focus: comparative anti-spoofing model evaluation and benchmark-oriented artifacts.
- Overlap: anti-spoofing model evaluation and cross-dataset performance.
- Potential relationship: import model scores or follow established test protocols rather than build another leaderboard.

## 3. Commercial and product competitors

### PumpCX — Voice Biometrics Vulnerability Testing

- Product page: https://www.pump.cx/voice-biometrics
- Public page advertises automated testing for replay, voice morphing/conversion, man-in-the-middle/injection, synthetic speech and end-to-end workflows from enrollment to high-risk decisions.
- Overlap: direct overlap with voice-biometric vulnerability assessment.
- Evidence caveat: these are vendor-described capabilities; this desk review has not independently validated product performance.
- Differentiation hypothesis: self-hosted open-source framework, public test specifications, researcher plugin SDK, transparent methodology and reproducible artifacts.

### TestMu AI — Voice Biometrics Testing

- Product page: https://www.testmuai.com/voice-biometrics-testing/
- Public page advertises end-to-end enrollment, verification and fallback testing; accents/noise, replay/synthetic audio routing and telephony/experience metrics.
- Overlap: voice authentication workflow testing and QA.
- Evidence caveat: vendor-described features, not independent performance validation.
- Differentiation hypothesis: security-research methodology and evidence-based security findings rather than primarily call-flow/quality-assurance verdicts.

## 4. Adjacent tools and components

| Tool/component | Relevant use | Strategic position |
|---|---|---|
| SpeechBrain ECAPA-TDNN | Speaker-verification baseline | Integrate via optional adapter; retain model card and Apache-2.0 checkpoint terms. |
| AASIST | Audio anti-spoofing baseline | Integrate as an optional baseline; retain upstream MIT notices and exact checkpoint provenance. |
| RawNet2 | Audio anti-spoofing baseline | Candidate optional adapter after code/checkpoint/license review. |
| ASVspoof evaluation package | Protocol-specific metric implementation | Prefer official compatible implementations for challenge reproduction. |
| OWASP API Security Top 10 | Application/API threat taxonomy | Map relevant application test cases to it; do not present it as biometric-specific. |
| OWASP WSTG | Web authentication/session/authorization testing guidance | Use for the application layer only where applicable. |

## 5. Proposed positioning

VoxRigor is not a new anti-spoofing model, a replacement for ASVspoof, or a general-purpose commercial IVR QA clone. It is intended to be the open research harness that connects several distinct evaluations in one reproducible workflow:

- score-level/model evaluation;
- capture-device PAD evaluation;
- audio condition/robustness evaluation;
- controlled application/protocol security testing;
- common result/provenance schema and evidence-linked reporting.

The strongest initial wedge is an offline evaluation runner with strict sample accounting and reproducible report generation. Application testing follows once the target adapter and authorization controls are tested.

## 6. Gaps and validation questions

Before claiming a market gap, conduct:

1. A structured literature review using terms such as speaker verification adversarial robustness, voice biometric presentation attack evaluation, spoofing-aware speaker verification, audio deepfake generalization, biometric authentication API security and voice authentication workflow penetration testing.
2. A GitHub repository search for recent tools, forks and active alternatives.
3. A feature-by-feature evaluation of SEC4SR, SpeakerGuard, current ASVspoof baselines, PumpCX and TestMu.
4. Short interviews with at least five researchers/developers, asking what they currently use, what is difficult to reproduce, and whether they would run an open-source local tool.
5. A technical proof that the common test schema can represent at least one ASV benchmark, one PAD benchmark and one controlled protocol test without flattening their different semantics.

## 7. Research source URLs

- SEC4SR: https://sec4sr.github.io/
- SpeakerGuard: https://github.com/SpeakerGuard
- ASVspoof 5 baselines: https://github.com/asvspoof-challenge/asvspoof5
- ASVspoof 5 evaluation plan: https://www.asvspoof.org/file/ASVspoof5___Evaluation_Plan_Phase2.pdf
- PumpCX: https://www.pump.cx/voice-biometrics
- TestMu AI: https://www.testmuai.com/voice-biometrics-testing/
- SpeechBrain ECAPA model: https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb
- AASIST model card: https://huggingface.co/SpeechAntiSpoofingBenchmarks/AASIST
