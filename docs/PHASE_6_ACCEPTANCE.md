# Phase 6 Acceptance Criteria

## Initial score-only experiment runner

- [x] Versioned experiment manifest separates one calibration dataset from at least two evaluation datasets.
- [x] Dataset paths are relative, constrained to the experiment folder and validated through Phase 2 score/provenance checks.
- [x] Experiment refuses non-ASV inputs, duplicate dataset IDs, inconsistent score directions and mismatched score-producer lineage.
- [x] Platt calibration is fitted only on the calibration dataset.
- [x] Raw operating threshold is selected only on calibration data and transferred unchanged to every evaluation dataset.
- [x] Evaluation reports raw EER/ROC-AUC and transferred-threshold FMR/FNMR with denominators and Wilson intervals.
- [x] Held-out calibration reports Brier score, log loss, ECE, reliability bins and probability-threshold FMR/FNMR.
- [x] Optional speaker/source overlap audit reports pairwise counts and can enforce disjointness.
- [x] JSON and HTML reports preserve dataset hashes, sample accounting, model lineage when supplied and methodological limitations.
- [x] CI validates the new manifest, calibration functions, transfer behavior, overlap policy, CLI and reporting on all six supported environments.

## Research gates — still open

- [ ] Evaluate approved, representative datasets and publish reproducible experiment cards.
- [ ] Compare calibration and operating-point transfer across more than one speaker-verification model family.
- [ ] Add speaker-clustered bootstrap confidence intervals or another justified cluster-aware uncertainty method.
- [ ] Add protocol-specific cost metrics only with a matching official protocol and independently validated implementation.
- [ ] Add condition-stratified cross-dataset analysis using Phase 4 audio-condition provenance.
- [ ] Add a separately specified PAD calibration/evaluation protocol; ASV logistic calibration must not be reused for PAD without methodological justification.
- [ ] Train or fine-tune a custom model only after a falsifiable hypothesis, data licensing/consent review, leakage-resistant split and independent evaluation protocol are approved.

Passing automated tests demonstrates implementation behavior on synthetic fixtures, not biometric generalization or a model improvement.
