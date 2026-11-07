# Phase 4 — Audio Condition and Presentation Evaluation

**Status:** Initial deterministic audio-condition generator validated by the six-environment CI matrix. Physical presentation rig integration is not implemented.

## Purpose

Phase 4 generates controlled local audio variants so researchers can compare a clean baseline with explicitly declared capture-channel or signal conditions. It does not silently normalize, clip, or change the sample rate. Each operation and its order are recorded.

## Supported transformations

| Operation | Behavior | Important limitation |
|---|---|---|
| Resample | Polyphase resampling to a declared 8–192 kHz rate | This is a sample-rate conversion, not a microphone/channel model. |
| Gaussian noise | Add seeded white Gaussian noise at a declared measured-input SNR | Noise is generated per trial and endpoint from a reproducibly derived seed. Silent inputs are rejected. |
| μ-law | G.711-style μ-law companding and quantization at 8 kHz | This is a narrowband codec approximation. It does not simulate RTP, packet loss, jitter, echo cancellation or a complete VoIP stack. |
| Reverberation | Convolve with a supplied local impulse response | The IR must be mono, no longer than two seconds, and at the current signal's sample rate. |

Transformations execute in manifest order. For ASV trials, a scenario targets `probe`, `enrollment`, or `both`. For PAD, each scenario targets `audio`. A clean scenario with no operations is mandatory and generated for every source trial.

## Command

Install the audio extra and generate condition files:

```powershell
python -m pip install -e ".[audio]"
voxrigor audio conditions generate --manifest .\condition-experiment.json --output-dir .\runs\conditions\experiment-01
```

Then use the generated audio-trial manifest with the Phase 3 model-to-benchmark pipeline:

```powershell
voxrigor models score-trials --manifest .\runs\conditions\experiment-01\audio-trials.json --output-dir .\runs\inference\experiment-01
voxrigor benchmark run .\runs\inference\experiment-01\benchmark.json --output .\runs\benchmarks
```

## Example experiment manifest

```json
{
  "schema_version": "0.1",
  "source_manifest": "audio-trials.json",
  "scenarios": [
    {
      "scenario_id": "clean",
      "target": "probe",
      "transforms": []
    },
    {
      "scenario_id": "noise-20db",
      "target": "probe",
      "transforms": [
        {"kind": "gaussian_noise", "snr_db": 20, "seed": 1729}
      ]
    },
    {
      "scenario_id": "telephony-mulaw",
      "target": "probe",
      "transforms": [
        {"kind": "mulaw"}
      ]
    },
    {
      "scenario_id": "room-ir",
      "target": "probe",
      "transforms": [
        {
          "kind": "reverberation",
          "impulse_response": "impulse-responses/room.wav",
          "wet_mix": 0.35
        }
      ]
    }
  ]
}
```

For PAD, set the target to audio in every scenario, including clean. The referenced source audio-trial manifest and all audio/IR paths must resolve inside their respective manifest directories. See the audio-condition experiment schema for the JSON shape; runtime validation also enforces the clean-baseline rule.

## Reproducibility and integrity

The output directory contains:
- `audio-trials.json`: a new manifest with unique pseudonymous trial IDs and condition labels;
- `audio/`: FLOAT WAV files for every generated endpoint;
- `conditions-provenance.json`: source and output audio hashes, transform order, parameters, effective per-trial seeds, sample rates, durations and amplitude summaries.

The condition provenance sidecar excludes input paths, raw waveforms and embeddings. Its SHA-256 is copied into the generated audio-trial manifest, then into the Phase 3 score-producer record. Phase 2 verifies the sidecar hash before calculating metrics. Editing the condition history after scoring invalidates the dataset manifest.

FLOAT WAV preserves samples outside [-1, 1] instead of silently clipping. Such outputs may not be suitable for every player or physical playback chain; inspect peak amplitude and apply an explicitly declared gain operation in a future extension rather than relying on implicit normalization.

Hard safety limits: 120-second input files, 2-second impulse responses, 2,000 expanded trials, and 1 GiB of generated audio per run. All processing is local. No microphone, speaker, network target or telephony interface is invoked.

## Digital versus physical presentation

A transformed file remains a **digital condition**. It must not be labelled as a physical replay or acoustic presentation attack. A physical presentation experiment requires an explicit speaker/room/microphone/capture path, calibration and repeatable hardware metadata. That optional rig is design-only at this stage.

## Validation status

The automated Phase 4 implementation gates passed in CI run 42413468715 on Ubuntu and Windows with Python 3.11, 3.12 and 3.13. The Linux jobs each completed 172 tests at 86.65% coverage. The Windows jobs completed successfully as well. These tests verify deterministic transformations, file integrity, provenance handoff and tamper detection. They do not validate biometric accuracy or real-world channel fidelity.

## Limitations

- No automatic ambient microphone recording.
- No speaker playback, telephony or RTP integration.
- No packet-loss/jitter simulation.
- No codec quality claim or standards conformance claim.
- No guarantee that a transformed condition matches a real deployment channel.
- Condition-dependent metric changes are not automatically security vulnerabilities.
