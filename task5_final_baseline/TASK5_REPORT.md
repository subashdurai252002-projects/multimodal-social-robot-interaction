# Task 5 — Speech Barge-In Detection

## Status

The laptop development prototype is functionally complete as of 12 October 2026. The same shared barge-in detector was integrated into both the Gemini and local Qwen speech-to-speech pipelines.

The final working baseline is represented by:

- `barge_in_detector.py`
- `speech_gemini_respeaker.py`
- `speech_qwen_respeaker.py`

The files whose names contain `_async_test` are experiments and are not part of the final baseline.

## Objective

The robot must continue monitoring the user while Piper is speaking. Piper must stop only after the complete command "Stop robot" is detected and verified. Incomplete phrases and unrelated speech must not stop playback.

## Final architecture

```text
User speech
    |
    v
ReSpeaker six-channel capture at 16 kHz
    |-- channel 0: microphone mixture
    `-- channel 5: synchronized Piper reference
    |
    v
Streaming DTLN-AEC 512
    |
    v
openWakeWord V4 candidate detector (threshold 0.5)
    |
    v
Faster-Whisper small.en verification
    |-- latest 3-second window
    `-- 5-second fallback window
    |
    v
Phrase rule: stop (the) robot
    |-- verified: terminate Piper playback
    `-- rejected: allow Piper to continue
```

The capture thread continuously drains ReSpeaker audio during synchronous Whisper verification. This prevents the operating-system capture buffer from silently overflowing and retains incoming audio for later processing.

## Integration result

### Gemini

- Six recorded conversations ended with a verified barge-in.
- Seven false V4 candidates were rejected without stopping Piper.
- No false playback stop is present in the saved Gemini log.
- Some final trials required the user to repeat the command. The log does not record individual spoken attempts, so first-attempt recall cannot be calculated reliably.

### Qwen

- Two replies completed normally in the saved logs.
- Three replies were interrupted after successful command verification.
- The confirmation test printed the correct normal-completion and interrupted-playback status messages.
- No false playback stop is present in the saved Qwen logs.

## Observed timing results

These are development observations, not a strict Gemini-versus-Qwen benchmark. Gemini and Qwen produced replies of different lengths, and the sample counts differ.

| Measurement | Gemini | Qwen |
|---|---:|---:|
| Recorded conversations | 6 | 5 |
| Mean LLM response time | 1.210 s | 1.240 s |
| Median LLM response time | 1.185 s | 1.200 s |
| Mean Piper synthesis time | 5.538 s | 3.394 s |
| Median Piper synthesis time | 2.885 s | 2.150 s |
| Mean speech-end-to-playback-start latency | 9.257 s | 6.288 s |
| Median speech-end-to-playback-start latency | 6.140 s | 4.870 s |
| Verified playback interruptions | 6 | 3 |
| Normal playback completions | 0 | 2 |
| Mean successful command-verification time | 2.222 s | 2.047 s |
| Median successful command-verification time | 1.370 s | 1.780 s |

The first Gemini Piper synthesis measurement was 19.02 seconds and materially increased the Gemini mean. The median better represents the typical measurements in this small sample.

## Problems encountered and resolutions

1. **Piper echo generated false wake-word candidates.**
   DTLN-AEC was added using microphone channel 0 and synchronized reference channel 5.

2. **The V4 model alone produced false positives.**
   V4 is now a candidate generator only. Faster-Whisper verifies the complete phrase before playback is terminated.

3. **"Top robot" was sometimes produced by Whisper.**
   The final phrase rule accepts `stop robot` or `stop the robot`; it does not accept `top robot`.

4. **Natural speech before the command was rejected by an overly strict full-transcript rule.**
   Phrase matching now searches for the complete command inside the normalized transcript. For example, "I am talking to my friend, stop robot" is accepted.

5. **Stopping and restarting capture around verification risked stale or lost audio.**
   A continuous capture thread now drains ReSpeaker audio while Whisper verifies.

6. **The Qwen terminal reported that a reply finished even after interruption.**
   Qwen status reporting was corrected to distinguish normal completion from interruption.

## Known limitation

On the development laptop, a false candidate can require an expensive CPU Whisper verification. Rejected Gemini candidates took between 0.22 and 10.98 seconds in the saved run. A valid command spoken during a long verification can therefore be processed late, making the user feel that the first attempt was missed.

An experimental continuous-processing version retained a command spoken once during a 13.15-second false verification and later verified it, but Piper still stopped late. This established that retention and response latency are separate problems. The experimental version was not promoted to the final baseline.

This limitation is attributed to CPU verification latency, not to Gemini or Qwen response generation. It will be reassessed on the final NVIDIA Jetson platform with GPU acceleration.

## Jetson validation still required

After migration, repeat the following without changing the command semantics:

1. Confirm six-channel ReSpeaker and Piper-reference channel mapping.
2. Confirm DTLN model compatibility and real-time throughput.
3. Enable and validate GPU-accelerated Whisper inference.
4. Measure successful and rejected verification latency.
5. Run controlled first-attempt tests with a known count of spoken commands.
6. Report true positives, false negatives, true negatives and false positives.
7. Measure any Piper underrun or stutter during simultaneous inference.

## Evidence files

- `gemini_final_test.txt`
- `qwen_initial_test.txt`
- `qwen_confirmation_test.txt`
- `TASK5_METRICS.csv`
- `SHA256SUMS`

## Conclusion

Task 5 is complete as a CPU-based architectural prototype. Echo-reduced candidate detection, exact command verification and Piper interruption work in both Gemini and Qwen pipelines. The remaining work is deployment validation and latency measurement on Jetson, not redesign of the laptop baseline.
