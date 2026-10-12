# Task 5 Meeting Guide — Echo-Robust Speech Barge-In

## One-sentence summary

Task 5 developed a barge-in system that lets a person say **"Stop robot" while the robot is speaking**, suppresses the robot's own Piper voice using a synchronized reference signal, verifies the complete command, and interrupts playback only after verification.

## What problem was solved?

The robot must listen while it is speaking. This is difficult because the ReSpeaker microphone records both:

- the nearby human voice; and
- the robot's much louder Piper playback.

Without echo cancellation, the robot can interpret its own speech as the command. A wake-word model alone also produced high scores for incomplete or unrelated speech. Therefore, Task 5 required both echo handling and command verification.

The safety requirements were:

1. A complete human **"Stop robot"** command should interrupt Piper.
2. Piper's own voice must not stop itself.
3. **"Stop"**, **"Robot"**, **"Top robot"** and unrelated speech must not stop playback.
4. False wake-word candidates should not automatically interrupt the robot.
5. Microphone capture must continue while verification is running.

## Final architecture

```text
Human voice + Piper echo
            |
            v
ReSpeaker six-channel capture, 16 kHz
            |
            |-- channel 0: microphone mixture
            `-- channel 5: synchronized playback reference
            |
            v
Streaming DTLN-AEC 512
            |
            v
Echo-reduced microphone signal
            |
            v
openWakeWord V4, threshold 0.5
            |
       candidate only
            |
            v
Faster-Whisper small.en
   3-second window, then 5-second fallback
            |
            v
Normalized phrase search
   stop robot / stop the robot
            |
      +-----+-----+
      |           |
   verified     rejected
      |           |
terminate       Piper
  Piper        continues
```

The same detector is shared by two speech-to-speech systems:

```text
Gemini pipeline ----+
                    +--> barge_in_detector.py
Qwen pipeline ------+
```

## Active implementation files

### `barge_in_detector.py`

This is the shared barge-in implementation. It contains:

- streaming DTLN-AEC inference;
- six-channel microphone and reference extraction;
- a background thread that continuously drains `arecord`;
- openWakeWord V4 inference;
- a five-second cleaned-audio history buffer;
- Faster-Whisper command verification;
- command normalization and phrase matching;
- Piper playback through `pw-play`;
- playback termination after verification.

### `speech_gemini_respeaker.py`

This pipeline performs:

```text
user recording
→ Faster-Whisper base transcription
→ Gemini API response
→ Piper synthesis
→ monitored playback
```

Gemini requires an internet connection and `GEMINI_API_KEY`.

### `speech_qwen_respeaker.py`

This performs the same speech pipeline but uses local Ollama:

```text
Ollama endpoint: http://127.0.0.1:11434/api/generate
Model: qwen2.5:1.5b
```

## Why each component was selected

### Why ReSpeaker six-channel capture?

The device provides the microphone mixture and a synchronized playback reference in the same recording. Synchronization is critical for acoustic echo cancellation.

### Why DTLN-AEC?

The microphone channel alone contains both human speech and Piper echo. DTLN uses the microphone and playback reference to suppress the playback component while retaining near-end human speech.

Listening tests showed the desired qualitative behavior: the human command remained clear while Piper became quieter and sometimes sounded distorted or underwater. Perfect audio quality was not required; command intelligibility was the objective.

### Why DTLN-512 instead of DTLN-128?

In the controlled comparison:

| Test | DTLN-128 score | DTLN-512 score |
|---|---:|---:|
| Playback only | 0.1128 | 0.4642 |
| Complete Stop robot | 0.3995 | 0.9751 |

At the 0.5 threshold, DTLN-128 missed the valid command, while DTLN-512 detected it. DTLN-512 was therefore selected despite its higher CPU cost.

### Why openWakeWord V4?

V4 provides a lightweight streaming candidate detector. It avoids running full speech recognition continuously on every audio block.

However, V4 is not trusted as the final decision because controlled negative tests produced high scores:

| Negative category | V4 score after DTLN-512 |
|---|---:|
| Stop only | 0.8393 |
| Robot only | 0.9982 |
| Unrelated speech | 0.8712 |

These results demonstrated that a threshold alone could not safely distinguish the full command. V4 was retained only as a candidate generator.

### Why Faster-Whisper verification?

Whisper checks whether the complete phrase actually occurred. On the 45-file real ReSpeaker dataset:

| Verifier | True positives | False negatives | True negatives | False positives | Recall |
|---|---:|---:|---:|---:|---:|
| Faster-Whisper base | 5 | 5 | 35 | 0 | 0.50 |
| Faster-Whisper small.en | 10 | 0 | 35 | 0 | 1.00 |

`small.en` recovered all ten positive recordings in that development test when common command-like transcription variants were tolerated. The final implementation deliberately rejects `Top robot`, so the table must not be presented as proof of perfect recall under the final strict phrase rule. The result is dataset-specific and is not claimed as general population accuracy.

### Why two verification windows?

The latest three seconds usually contain the short command and provide the faster result. If it fails, the five-second history provides additional context for slower or longer speech.

### Why search inside the transcript?

An exact whole-transcript rule rejected natural utterances such as:

```text
Hello, I am talking to my friend, stop robot.
```

The final rule searches for the complete command inside normalized speech. It still requires the words `stop` followed by `robot`, optionally with `the` between them.

Accepted examples:

```text
Stop robot
Please stop robot
Stop the robot
I am talking to my friend, stop robot
```

Rejected examples:

```text
Stop
Robot
Top robot
Unrelated speech
```

## Development path and important failures

### 1. Wake-word-only solution

The initial idea was to stop Piper whenever V4 crossed 0.5. Negative testing showed unacceptable false candidates. The lesson was that wake-word confidence is not equivalent to complete-command verification.

### 2. DTLN-128

DTLN-128 suppressed playback strongly, but the valid command scored only 0.3995 and was missed. It was rejected in favor of DTLN-512.

### 3. Base Whisper verification

Base Whisper had no false positives in the 45-file dataset, but recall was only 0.50. `small.en` improved development-set recall to 1.00.

### 4. Pausing Piper for every candidate

An earlier version paused Piper while Whisper verified. False V4 candidates caused audible pause/resume behavior. The final normal design allows Piper to continue during verification and stops it only after confirmation.

### 5. Stale microphone audio

Synchronous verification initially risked allowing `arecord` data to accumulate without being drained. A background capture thread was introduced so the microphone is continuously read while Whisper runs.

### 6. Strict whole-transcript matching

Whole-transcript matching rejected a real command if other speech appeared before it. Phrase searching solved that requirement while preserving the complete two-word command.

### 7. Accepting `Top robot`

Whisper sometimes transcribed a real command as `Top robot`. Accepting that form improved recall but weakened command specificity. The final safety decision was to reject `Top robot` and accept only `Stop robot` or `Stop the robot`.

### 8. Experimental continuous-processing version

An experimental version continued DTLN/V4 processing while Whisper was checking a previous candidate. In one stress test, a command spoken once during a 13.15-second false verification was retained and later verified in 1.79 seconds.

This proved that command retention could be improved, but Piper still stopped too late because the earlier CPU verification had to finish. The experiment was therefore not promoted to the final baseline.

## Final saved integration results

### Gemini results

- Recorded conversations: 6
- Verified playback interruptions: 6
- False V4 candidates correctly rejected: 7
- False playback stops in the saved log: 0
- Mean Gemini response time: 1.210 seconds
- Median Gemini response time: 1.185 seconds
- Mean successful verification time: 2.222 seconds
- Median successful verification time: 1.370 seconds
- Rejected verification range: 0.22–10.98 seconds

Some final trials required repeated commands. Individual spoken attempts were not logged, so first-attempt recall cannot be calculated from this run.

### Qwen results

- Recorded conversations: 5
- Normal playback completions: 2
- Verified playback interruptions: 3
- False playback stops in the saved logs: 0
- Mean local Qwen response time: 1.240 seconds
- Median local Qwen response time: 1.200 seconds
- Mean successful verification time: 2.047 seconds
- Median successful verification time: 1.780 seconds

The Qwen integration was also corrected so the terminal distinguishes:

```text
Robot reply finished normally.
```

from:

```text
Robot reply interrupted by 'Stop robot'.
```

## How to interpret the timing table

The Gemini and Qwen LLM response times were similar in these small runs. Piper synthesis and total playback-start latency cannot be treated as a strict model comparison because the systems generated responses of different lengths and the sample sizes differed.

The first Gemini Piper synthesis took 19.02 seconds and increased the mean. The median is more representative of the typical development run.

## What is proven

The laptop prototype demonstrates that:

1. synchronized microphone/reference capture works;
2. DTLN-512 can preserve the near-end command while reducing Piper playback;
3. V4 can act as a streaming candidate detector;
4. Whisper can reject false candidates and verify the complete command;
5. verified commands can terminate Piper;
6. the same detector works with both Gemini and Qwen pipelines;
7. microphone capture continues during verification.

## What is not yet proven

Do not claim the following yet:

- population-level command accuracy;
- perfect first-attempt detection;
- real-time GPU performance;
- identical Gemini/Qwen conditions;
- final Jetson latency;
- robustness across many rooms, distances, noise levels and speakers.

The real dataset was small and mainly represented the current development setup.

## Current limitation

On the CPU laptop, a false V4 candidate can trigger an expensive Whisper verification. Continuous capture prevents the operating-system audio stream from being abandoned, but the final synchronous detector may process a later command late and first-attempt detection is not guaranteed. This can make the user feel that the first command was missed.

This is not caused by Gemini. The same shared detector behavior applies to Gemini and Qwen. It is primarily a CPU verification-latency limitation.

The final platform will be an NVIDIA Jetson. GPU-accelerated verification must be measured there before deciding whether the recognition configuration requires further optimization.

## Why the CPU limitation was not hidden

The CPU laptop is the development platform, not the target deployment platform. Weakening the accurate verifier only to make the laptop appear faster could reduce safety. The working baseline was therefore frozen, and the latency limitation was documented honestly for Jetson reassessment.

## Jetson work remaining

1. Confirm that ReSpeaker channels 0 and 5 retain the same meaning.
2. Confirm DTLN-512 real-time throughput.
3. Configure GPU-supported Faster-Whisper/CTranslate2 or the selected Jetson-compatible runtime.
4. Re-measure successful and rejected verification latency.
5. Record the exact number and time of every spoken command attempt.
6. Test multiple speakers, distances, directions and noise conditions.
7. Measure true positives, false negatives, true negatives and false positives.
8. Check Piper playback for stutter under simultaneous GPU/CPU load.

## Suggested live demonstration

Use Qwen if internet reliability is uncertain; use Gemini when internet access and the API key are confirmed.

Demonstration sequence:

1. Start the pipeline.
2. Ask for a multi-sentence explanation.
3. Allow Piper to begin speaking.
4. Say unrelated speech and show that playback continues.
5. Say `Stop` and show that the incomplete command does not intentionally stop playback.
6. Start another response.
7. Say `Stop robot` once and show the verification and interruption messages.
8. Explain that a false V4 candidate is harmless because Whisper is the final decision layer.

Do not depend on a single live demonstration as the only evidence. Keep the saved logs and report available in case room acoustics, internet access or hardware behaves differently during the meeting.

## Three-minute explanation for the professor

> Task 5 addresses barge-in while the robot is speaking. The main difficulty is that the ReSpeaker hears the robot's own Piper output together with the human command. I used a six-channel capture in which channel zero contains the microphone mixture and channel five contains a synchronized playback reference. A streaming DTLN-AEC 512 model uses those signals to suppress the robot's echo while preserving near-end speech. The cleaned signal is passed to an openWakeWord V4 model, but V4 is used only to generate candidates because negative tests showed high scores for partial and unrelated phrases. Each candidate is therefore verified using Faster-Whisper small.en. The verifier accepts the complete phrase Stop robot, optionally Stop the robot, and only then terminates Piper. The same shared detector was integrated into both Gemini and local Qwen speech pipelines. Saved tests show successful interruption and no false playback stops, although slow false verification can delay a later command on the CPU laptop. The architecture is complete as a development prototype, and final performance must be evaluated using GPU acceleration on the target Jetson platform.

## Likely questions and answers

### Why not use only openWakeWord?

Because negative recordings produced scores above the 0.5 threshold. V4 is useful for efficient candidate generation but was not reliable enough to make the final stop decision.

### Why not use only Whisper continuously?

Continuous full ASR is more computationally expensive. The wake-word model reduces how often the heavier verifier is called.

### Why is DTLN needed if Whisper can recognize speech?

Without echo reduction, Piper dominates the microphone and can create false candidates or corrupt human speech. DTLN uses the synchronized reference to separate near-end speech from playback.

### Why was DTLN-512 selected?

DTLN-128 missed the complete command in the controlled test, while DTLN-512 produced a 0.9751 V4 score and retained clearer human speech.

### Why is `Top robot` rejected if Whisper sometimes produces it?

Accepting it would weaken command specificity and could create false stops. The final rule favors safety; improving acoustic recognition is preferable to accepting the wrong phrase.

### Is the system speaker independent?

That has not been proven. Some additional speakers were tested informally, but the final evaluation requires a larger controlled multi-speaker test on Jetson.

### Is Task 5 finished?

The laptop architectural prototype and Gemini/Qwen integration are complete. Final deployment performance and broader reliability evaluation remain Jetson tasks.

### Did the experimental asynchronous version solve latency?

It showed that a command could be retained during a long verification, but it did not make Piper stop promptly because CPU verification remained slow. It was therefore retained as an experiment, not the final baseline.

### What is the main contribution?

The contribution is the integration and evaluation of synchronized reference-based echo cancellation, lightweight candidate detection, exact ASR verification and speech-playback control in a reusable barge-in component for two different conversational backends.

## Files to open during the meeting

1. `PROJECT_MAP.md`
2. `task5_final_baseline/TASK5_REPORT.md`
3. `task5_final_baseline/TASK5_METRICS.csv`
4. `barge_in_detector.py`
5. `speech_gemini_respeaker.py`
6. `speech_qwen_respeaker.py`
7. `results/logs/gemini_final_test.txt`
8. `results/logs/qwen_confirmation_test.txt`

## Final statement

Task 5 should be presented as a successful laptop architecture prototype with honest CPU limitations. The correct next technical activity is Jetson deployment and controlled evaluation, not more uncontrolled laptop model changes.
