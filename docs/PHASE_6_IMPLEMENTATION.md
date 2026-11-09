# Phase 6 — Research and Custom-AI Experiments

**Status:** Initial score-only cross-dataset experiment runner implemented. This is research infrastructure, not evidence of a new model or improved biometric performance.

## First slice

Phase 6 begins with a controlled ASV score experiment because the existing Phase 2/3 pipeline already produces versioned score datasets. The first runner links one declared calibration/development dataset to at least two independent evaluation datasets.

The command is:

```powershell
voxrigor research evaluate .\research-experiment.json --output .\runs\research
```

The manifest is versioned by `schemas/research-experiment-0.1.schema.json`. Paths are relative to the experiment-manifest folder and are rejected if they escape that folder.

## Example experiment manifest

```json
{
  "schema_version": "0.1",
  "experiment_id": "ecapa-cross-domain-01",
  "description": "Fit a calibration mapping on development-domain scores and transfer it to held-out domains.",
  "system_id": "ecapa-tdnn-cosine-v1",
  "calibration_dataset_manifest": "calibration/benchmark.json",
  "evaluation_datasets": [
    {
      "domain_id": "in_domain",
      "dataset_manifest": "evaluation-in-domain/benchmark.json"
    },
    {
      "domain_id": "cross_domain",
      "dataset_manifest": "evaluation-cross-domain/benchmark.json"
    }
  ],
  "target_fmr": 0.01,
  "probability_threshold": 0.5,
  "group_columns": ["speaker_id", "source_id"],
  "require_group_disjointness": true,
  "stratify_by_condition": true,
  "cluster_bootstrap": {
    "cluster_column": "speaker_id",
    "replicates": 1000,
    "seed": 2026,
    "confidence_level": 0.95
  }
}
```

Every referenced dataset must be an ASV score-dataset manifest with target and nontarget trials. All datasets must use the same score direction and unique dataset IDs. If model score-producer sidecars are supplied, they must be present for every dataset and agree on model ID, revision, backend, score type and artifact hashes. Inputs declaring already-calibrated scores are rejected to avoid silently calibrating twice.

## Methodology

1. Load each dataset through the existing Phase 2 validator, including score-file SHA-256 and inference/condition provenance checks.
2. Fit regularized Platt logistic calibration on the calibration dataset only. The score mean/scale and logistic coefficients are stored in the report.
3. Select the lowest normalized-score threshold that meets the requested empirical FMR on the calibration data.
4. Freeze the threshold and calibration mapping, then transfer both unchanged to every evaluation dataset.
5. Report raw EER and ROC-AUC, transferred-threshold FMR/FNMR with trial-level Wilson intervals, calibrated Brier score, log loss, expected calibration error (ECE), reliability bins and calibrated-threshold FMR/FNMR.
6. Audit speaker/source identifiers across calibration and evaluation datasets when those columns are configured. Overlap can be a warning or an enforced failure.
7. When `cluster_bootstrap` is configured, resample complete speaker/source clusters with replacement within each held-out evaluation dataset. Report percentile intervals for EER, ROC-AUC and FMR/FNMR at the frozen operating threshold. At least two independent clusters must contribute to each class, and at least 80% of requested replicates must be valid.
8. When `stratify_by_condition` is enabled, group held-out records by the Phase 4 `condition` label. For each condition with both target and nontarget trials, report raw EER/ROC-AUC, the frozen-threshold FMR/FNMR and calibration metrics using the same mapping fitted on the calibration dataset. A condition missing either class is retained with sample counts and marked `not_computable`; no condition-specific threshold is selected.

The probability threshold is an explicit user-declared decision threshold; it is not selected from evaluation labels. The raw operating threshold is selected from the calibration dataset using empirical FMR, then frozen. When the calibration set is small, the target FMR is limited by its impostor trial count: a target of 0.001 cannot be empirically distinguished with a handful of nontarget trials. The report preserves the exact denominator and confidence interval to make this limitation visible.

## Paired multi-system comparison

Use a comparison manifest when two or more systems have produced scores for the same calibration trials and the same held-out evaluation trials. Each system references its own standard research experiment manifest; therefore each system fits its own Platt mapping and selects its own operating threshold using only its own calibration scores.

Run a paired comparison with:

```powershell
voxrigor research compare .\research-comparison.json --output .\runs\research-comparisons
```

The schema is `schemas/research-comparison-0.1.schema.json`.

Example comparison manifest:

```json
{
  "schema_version": "0.1",
  "comparison_id": "ecapa-model-family-study",
  "description": "Compare independently calibrated speaker-verification systems on matched evaluation trials.",
  "reference_system_id": "ecapa-baseline",
  "systems": [
    {
      "system_id": "ecapa-baseline",
      "experiment_manifest": "ecapa/experiment.json"
    },
    {
      "system_id": "alternative-encoder",
      "experiment_manifest": "alternative/experiment.json"
    }
  ],
  "paired_cluster_bootstrap": {
    "cluster_column": "speaker_id",
    "replicates": 1000,
    "seed": 2026,
    "confidence_level": 0.95
  }
}
```

A comparison supports two to eight systems. Each referenced experiment must be a valid score-only ASV experiment and must declare the matching `system_id`. All systems must use the same target FMR, probability threshold and ordered evaluation domains. Calibration datasets must be paired on `trial_id`, label, split, condition, attack-species metadata and configured speaker/source identifiers. The same checks are performed separately for every evaluation domain. Protocol and split metadata must agree.

The scores themselves are expected to differ by system. The runner does not require different model families to share the same score scale or score direction; each model is normalized, calibrated and thresholded under its own score-direction declaration. It does require trial identity and ground-truth/group metadata to match exactly. A missing/extra trial or a label/condition/group mismatch stops the comparison rather than silently comparing different samples.

The report provides per-domain EER, ROC-AUC, FMR/FNMR at each model's own frozen operating threshold, Brier score and ECE; descriptive differences against the declared reference system; and dataset hashes, split/sample counts and score-producer provenance for every system/domain. Negative differences favor the compared system for EER, FMR, FNMR, Brier and ECE; positive ROC-AUC differences favor the compared system.

When `paired_cluster_bootstrap` is configured, each bootstrap replicate samples clusters once and uses the same sampled cluster/trial IDs across every system. It reports percentile intervals for the compared system minus the reference system for EER, ROC-AUC and FMR/FNMR at each model's own fixed threshold. At least two clusters must contribute to each class, and at least 80% of replicates must be valid.

These comparisons are paired descriptions on the supplied trials, not causal proof that one architecture is universally better. The paired bootstrap reflects evaluation-cluster variability only. It does not include model-training variability, calibration-set/threshold-selection uncertainty, hyperparameter-search uncertainty or dataset-sampling bias. Stable pseudonymous IDs must represent the same sampling units across systems. Synthetic CI fixtures demonstrate software behavior only; real model-family claims require approved, licensed, representative data and an independently specified research protocol.

## Interpretation constraints

- Calibration metrics are computed only on held-out evaluation datasets; in-sample calibration fit metrics are not presented as generalization evidence.
- EER and ROC-AUC summarize ranking performance and do not replace the transferred operating point.
- Brier score, log loss and ECE assess probability calibration, not speaker recognition accuracy.
- Wilson intervals are trial-level and do not account for speaker/source clustering. The optional cluster bootstrap provides a separate cluster-resampled interval when stable speaker/source identifiers are available.
- Cluster-bootstrap intervals are conditional on the already-fitted calibration mapping and frozen operating threshold. They quantify held-out evaluation-set cluster sampling variability only; they do not include development/calibration-set uncertainty or threshold-selection variability.
- A cluster bootstrap is only meaningful when the chosen cluster identifiers represent independent sampling units. Trial IDs, random row IDs or per-trial source IDs must not be presented as speaker-level uncertainty.
- Replicates that omit either target or nontarget class are discarded. The run fails rather than reporting an interval when fewer than 80% of requested replicates remain valid.
- Condition-stratified metrics are descriptive held-out slices. They use the single frozen calibration mapping and operating threshold; they do not retune thresholds within conditions.
- A condition named `unspecified` means the CSV lacked a usable condition value. It is surfaced as unspecified rather than interpreted as a clean baseline.
- Group-disjointness checks are only meaningful if pseudonymous identifiers are stable across datasets. Independently re-keyed IDs cannot reveal overlap.
- A score-file experiment cannot validate model preprocessing, audio channel realism or speaker population coverage beyond the supplied provenance and metadata.
- These generic ASV results are not an official ASVspoof result and are not a production authentication-security certification.

No custom neural model is trained in this slice. Fine-tuning is deferred until an explicit research hypothesis, approved dataset access, licensing review, fixed evaluation protocol and leakage-resistant independent test split are available.
