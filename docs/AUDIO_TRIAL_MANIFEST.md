# Audio-Trial Manifest and Model-to-Benchmark Workflow

An audio-trial manifest defines local ASV or PAD trials. It references local audio files using relative paths. Keep it beside an audio folder and do not commit personal recordings or manifests containing personal identifiers.

## ASV example

```json
{
  "schema_version": "0.1",
  "dataset_id": "local-asv-example",
  "dataset_name": "Local speaker verification example",
  "dataset_version": "1.0",
  "task": "asv",
  "protocol_id": "local-asv-v1",
  "model_id": "ecapa-tdnn",
  "evaluation_split": "test",
  "operating_threshold": 0.42,
  "threshold_source": "external",
  "license_name": "research-consented-local",
  "trials": [
    {
      "trial_id": "trial-target-001",
      "label": "target",
      "split": "test",
      "condition": "clean",
      "enrollment_audio": "audio/enroll-001.wav",
      "probe_audio": "audio/probe-001.wav",
      "speaker_id": "speaker-001",
      "source_id": "source-001"
    },
    {
      "trial_id": "trial-nontarget-001",
      "label": "nontarget",
      "split": "test",
      "condition": "clean",
      "enrollment_audio": "audio/enroll-001.wav",
      "probe_audio": "audio/probe-002.wav",
      "speaker_id": "speaker-001",
      "source_id": "source-002"
    }
  ]
}
```

## PAD manifests

For PAD, set task to pad, model_id to aasist-l-onnx, provide one audio path per trial, and use labels bonafide or spoof. Every spoof trial must identify its attack_species. PAD requires an operating threshold declared before evaluating the held-out split.

## Execution

```powershell
voxrigor models score-trials --manifest .\audio-trials.json --output-dir .\runs\inference\asv-example
voxrigor benchmark run .\runs\inference\asv-example\benchmark.json --output .\runs\benchmarks
```

The scorer produces a Phase 2-compatible scores.csv, a schema 0.2 benchmark manifest and an inference-provenance.json sidecar. The sidecar contains pseudonymous trial identifiers, input hashes, model artifact hashes, and preprocessing metadata. It does not contain audio paths, waveforms or embeddings.

The Phase 2 loader verifies both the score CSV hash and sidecar hash before evaluating metrics. Audio paths must be relative and must resolve within the manifest directory, including after symlink resolution.

Use pseudonymous trial, speaker and source identifiers. Avoid names, emails, account IDs or other personal data.

## Interpretation

ECAPA outputs raw cosine similarities; AASIST-L outputs raw bona-fide logits. Neither is a calibrated probability. Use a justified external operating threshold or a separate development split. Never select a threshold using the held-out evaluation split.

## Real-checkpoint smoke tests

The optional real-model-smoke workflow downloads pinned checkpoints and exercises inference on deterministic generated non-biometric audio. It validates runtime execution only, not biometric accuracy, PAD effectiveness or generalization.
