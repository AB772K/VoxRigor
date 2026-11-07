# VoxRigor Score-Trial CSV Format (0.1)

## Purpose and boundary

Phase 2 evaluates **precomputed scores** produced by a user-supplied biometric system or research pipeline. VoxRigor does not load audio, generate embeddings, run a model, or verify the correctness of the upstream score-generation process in Phase 2.

A CSV is paired with a JSON dataset manifest. The manifest records task, protocol, score direction, selected split, score-file SHA-256, license/source metadata and optional operating-threshold provenance.

## Required CSV columns

| Column | Type | Meaning |
|---|---|---|
| `trial_id` | string | Unique trial identifier across the entire CSV, including non-evaluation splits. Do not put names, emails or other personal data here. |
| `label` | string | `target`/`nontarget` for ASV; `bonafide`/`spoof` for PAD. |
| `score` | finite decimal | Upstream comparison or countermeasure score. NaN and infinity are rejected. |

## Optional columns

| Column | Meaning |
|---|---|
| `split` | Split identifier, e.g. `train`, `dev`, `test`. When absent, `evaluation_split` must be `all`. |
| `condition` | Recording/channel or other declared condition. Missing values become `unspecified`. |
| `attack_species` | Required for every PAD `spoof` row; identifies the attack species/category used by the dataset protocol. |
| `speaker_id` | Optional pseudonymous speaker grouping key. It is never copied into the report. |
| `source_id` | Optional pseudonymous source-recording grouping key. It is never copied into the report. |

Unknown columns are accepted for interoperability but are not interpreted; their names are disclosed in the report. Do not place personal or sensitive values in unknown columns if the CSV may be shared.

## ASV semantics

- `target`: mated/genuine comparison trial.
- `nontarget`: non-mated/impostor comparison trial.
- A normalized score greater than or equal to the operating threshold is accepted as genuine.
- Higher-is-genuine and lower-is-genuine score conventions are supported.
- FMR is the proportion of nontarget comparison trials accepted as genuine.
- FNMR is the proportion of target comparison trials rejected.
- These comparison-trial measures must not be relabelled as operational end-to-end FAR/FRR without a separately defined transaction protocol.

The empirical ROC is built from all unique observed scores, with tied scores processed as a group. AUC is trapezoidal area under that empirical ROC. EER is linearly interpolated between adjacent ROC points. The interpolated EER is descriptive and is not a deployment threshold.

FMR/FNMR at an operating threshold are only computed when a threshold is provided. A threshold source must be declared as `external` or `development_split`. A development threshold requires a named selection split distinct from the evaluation split. VoxRigor verifies that the split exists and differs; it cannot prove how the threshold was selected.

## PAD semantics

- `bonafide`: bona-fide presentation.
- `spoof`: attack presentation.
- Every spoof row must have an `attack_species` value.
- A normalized score greater than or equal to the threshold is classified as bona fide.
- APCER is computed separately for each attack species: spoof presentations of that species classified as bona fide divided by all spoof presentations of that species.
- BPCER is the proportion of bona-fide presentations classified as spoof.
- The report also contains a sample-weighted pooled APCER for convenience, but it is not a substitute for per-species APCER.

PAD requires a predeclared operating threshold. PAD results are not inferred from the ASV EER threshold.

## Dataset manifest

Create a manifest using the CLI, which hashes the score file and validates the selected split:

```bash
voxrigor benchmark init ./scores.csv \
  --manifest ./benchmark.json \
  --task asv \
  --dataset-id my-asv-test \
  --dataset-name "My ASV evaluation" \
  --dataset-version "1.0" \
  --protocol-id "my-protocol-v1" \
  --evaluation-split test \
  --score-direction higher_is_genuine \
  --threshold 0.42 \
  --threshold-source external
```

For PAD, use `--task pad`, provide an operating threshold and declare its source. Use `--threshold-source development_split --threshold-selection-split dev` only when the threshold was selected on that development split and the evaluation split is a separate named split.

## Validation rules

- CSV must be UTF-8 (UTF-8 BOM is accepted) and comma-delimited.
- Required headers must exist and be unique.
- Trial IDs must be non-empty and unique across the whole file.
- Scores must be finite numeric values.
- Labels must match the task vocabulary exactly after lowercase/whitespace normalization.
- Both required classes must be present in the selected evaluation split.
- Rows from other splits are counted as not selected; they are not silently mixed into evaluation.
- A changed score file fails SHA-256 verification.
- If `group_columns` are declared, their values must be present in every row so the overlap audit is not silently incomplete.
- If group-disjointness is explicitly required, configured pseudonymous group identifiers must not overlap across splits.
- A development threshold-selection split must exist and contain all task-required classes; the tool still cannot verify how the user derived the threshold.
- Invalid rows cause validation to fail. Phase 2 does not silently discard malformed records.

## Limitations

- Wilson confidence intervals are trial-level and do not adjust for speaker/source clustering.
- If speaker/source identifiers are not supplied, cross-split subject/source leakage cannot be assessed by VoxRigor.
- EER and AUC do not establish security or real-world operational error rates.
- No official ASVspoof minDCF, a-DCF, t-DCF or Cllr compatibility claim is made by the generic Phase 2 evaluator.
- Dataset protocol, labels, class balance, source provenance and score-generation procedure remain the researcher's responsibility.
