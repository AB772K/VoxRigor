# VoxRigor Benchmark Data Format (0.1)

Phase 2 evaluates precomputed decision scores in CSV files. It does not load waveforms or run biometric models. Model inference is planned for Phase 3.

Required columns: `trial_id`, `label`, and finite numeric `score`.

ASV labels are `target` and `nontarget`. PAD labels are `bonafide` and `spoof`; every PAD spoof row needs an `attack_species` value. Optional fields include `split`, `condition`, `speaker_id`, and `source_id`.

The manifest records the dataset and protocol identity, evaluation split, score direction, score-file SHA-256, license/source information, and threshold provenance. Thresholds may be externally supplied or declared as selected on a development split distinct from the evaluation split. VoxRigor verifies the split exists and contains the required classes; it does not validate the researcher's threshold-selection procedure.

ASV metrics: FMR and FNMR at a declared operating threshold, 95% trial-level Wilson intervals, empirical ROC, trapezoidal ROC-AUC, and linearly interpolated EER. FMR/FNMR are comparison-trial measures, not automatically transaction-level FAR/FRR. EER is descriptive, not a deployment threshold.

PAD metrics: BPCER and APCER for each attack species, with trial-level Wilson intervals. Pooled APCER is sample-weighted and must not replace per-species results.

The loader rejects duplicate trial IDs, missing classes, invalid labels, NaN/Infinity, score-file hash mismatches, and score paths resolving outside the manifest directory. Declared group columns must be populated. Optional group-disjointness enforcement checks speaker/source overlap between splits.

Limitations: confidence intervals do not adjust for speaker/source clustering; metrics are only as valid as the supplied scores, labels, split design and protocol. No official ASVspoof minDCF, a-DCF, t-DCF or Cllr compatibility claim is made.