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
- [x] Add paired multi-system comparison for 2–8 independently calibrated ASV systems with exact trial/label/split/condition/group alignment and optional paired cluster-bootstrap deltas.
- [ ] Compare calibration and operating-point transfer empirically across multiple speaker-verification model families using approved representative datasets; the comparison tool alone is not an empirical result.
- [x] Add optional deterministic cluster-bootstrap intervals for held-out EER, ROC-AUC and frozen-threshold FMR/FNMR, with class/cluster and valid-replicate safeguards.
- [x] Add optional two-stage nested cluster bootstrap that independently resamples calibration and evaluation clusters, re-fits Platt calibration and re-selects the target-FMR threshold per replicate, with cluster-disjointness and valid-replicate safeguards.
- [ ] Extend uncertainty to include model-training, hyperparameter-search and independent dataset-acquisition variability through separately justified experiments.
- [ ] Add protocol-specific cost metrics only with a matching official protocol and independently validated implementation.
- [x] Add optional condition-stratified held-out ASV analysis using Phase 4 condition labels, with frozen calibration/threshold transfer and not-computable handling for one-class conditions.
- [ ] Add a separately specified PAD calibration/evaluation protocol; ASV logistic calibration must not be reused for PAD without methodological justification.
- [ ] Train or fine-tune a custom model only after a falsifiable hypothesis, data licensing/consent review, leakage-resistant split and independent evaluation protocol are approved.

Passing automated tests demonstrates implementation behavior on synthetic fixtures, not biometric generalization or a model improvement.
