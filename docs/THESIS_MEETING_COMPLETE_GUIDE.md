# Professor Meeting Guide — Tasks 1–5

## Overall objective

The project developed a speech-interaction pipeline for a social robot, beginning with microphone capture and transcription and progressing to local/cloud conversations and echo-robust barge-in.

```text
Task 1: ReSpeaker speech input and transcription
Task 2: Piper speech output
Task 3: Offline Qwen speech-to-speech interaction
Task 4: Online Gemini interaction and comparison
Task 5: Echo-robust "Stop robot" barge-in
```

The detailed Task 5 technical explanation is in `docs/TASK5_MEETING_GUIDE.md`. This document gives the complete meeting sequence, with Tasks 1–4 intentionally shorter.

# Task 1 — ReSpeaker and live speech recognition

## Objective

Capture human speech through the ReSpeaker array, detect when an utterance starts and ends, and transcribe it using Faster-Whisper.

## Configuration

- Ubuntu 24.04 laptop
- ROS 2 Jazzy available, although the final laptop speech scripts are standalone Python programs
- ReSpeaker capture device: `hw:1,0`
- Sampling rate: 16,000 Hz
- Six channels, signed 16-bit PCM
- Channel 0 selected for normal user transcription
- Faster-Whisper `base`, CPU, `int8`

## Endpoint detection

- one-second background calibration before each turn;
- wait up to 15 seconds for speech;
- preserve approximately 0.5 seconds of pre-roll;
- finish after approximately 0.8 seconds of silence;
- maximum utterance length of 20 seconds;
- return to listening when no speech is detected.

## Result

Live ReSpeaker speech was transcribed successfully. In the initial three-run STT/Piper baseline:

- mean Whisper inference time: 0.47 seconds;
- mean speech-end-to-text latency: 1.36 seconds;
- a longer utterance of approximately 16.37 seconds was also transcribed without being cut off.

## Limitation discovered

STT errors propagate to later components. For example, Whisper changed `states` to `stairs`, after which Qwen answered the incorrect question. This demonstrated that downstream LLM quality cannot repair every transcription error.

# Task 2 — Piper text-to-speech and speech echo

## Objective

Convert text into audible robot speech and connect transcription directly to spoken output.

## Configuration

- Piper 1.7.0
- Voice: `en_US-lessac-medium`
- Output: mono, signed 16-bit WAV at 22,050 Hz
- Piper executable retained in `.venv-stt/bin/piper`

## Development sequence

```text
typed text
→ Piper WAV
→ speaker

then

ReSpeaker
→ Faster-Whisper
→ Piper repeats the transcription
→ speaker
```

## Three-run baseline result

- mean Piper synthesis time: 1.53 seconds;
- mean speech-end-to-speaker-start latency: 2.89 seconds;
- mean playback duration: 3.82 seconds.

Two runs reproduced the reference sentence correctly. One transcription omitted the word `the`, showing that spoken output reflects upstream STT results.

## Important design fact

Piper synthesizes the complete WAV file before playback begins. It is not streamed, so response length affects synthesis and speaker-start latency.

# Task 3 — Offline Qwen speech-to-speech pipeline

## Objective

Create a complete offline conversational loop:

```text
ReSpeaker
→ Faster-Whisper
→ local Qwen
→ Piper
→ speaker
→ listen again
```

## Configuration

- Ollama 0.32.15
- Qwen2.5 1.5B
- local REST endpoint: `http://127.0.0.1:11434/api/generate`
- model keep-alive: 10 minutes
- CPU AVX2 selected on the development laptop

## CPU versus Vulkan investigation

The mixed Vulkan configuration generated approximately 0.60 tokens per second in the controlled request. Warm CPU AVX2 generated approximately 22.65 tokens per second. CPU AVX2 was therefore around 38 times faster for that laptop test and was selected.

This result applies to the development laptop and is not a general statement that CPUs are always faster than GPUs.

## Cold-start problem and solution

A cold Qwen request took 7.45 seconds for the model response in an early pipeline test, and other cold model-loading observations were approximately 16–26 seconds.

The program now sends an automatic warm-up request before displaying `SPEAK NOW`. This moves model loading to startup.

After automatic warm-up, the two-test result was:

- average Qwen response: 0.53 seconds;
- average speech-end-to-speaker-start latency: 3.07 seconds.

In a later four-turn continuous test:

- average warm Qwen response: 0.56 seconds;
- average speech-end-to-speaker-start latency: 3.38 seconds.

## Continuous conversation

Whisper and Qwen are prepared once, after which the system repeatedly listens, transcribes, generates, speaks and listens again.

Supported spoken exit phrases include:

- `Goodbye`
- `Good bye`
- `Stop conversation`
- `Exit`
- `Quit`

Both forms of goodbye are supported because Whisper produced both transcriptions.

## Advantages and limitations

Advantages:

- works offline;
- no cloud API key or quota;
- user transcription stays local;
- fast responses after warm-up.

Limitations:

- local CPU/RAM consumption;
- significant cold startup;
- response quality can be weaker;
- internal model knowledge can be outdated;
- STT errors can produce confidently incorrect answers.

# Task 4 — Gemini cloud pipeline and Qwen comparison

## Objective

Implement the same continuous speech interaction using Gemini and compare local and cloud model operation.

```text
ReSpeaker
→ Faster-Whisper
→ Gemini REST API
→ Piper
→ speaker
→ listen again
```

## Configuration

- Gemini model configured in the program: `gemini-3.5-flash-lite`
- REST `generateContent` request
- API key supplied through `GEMINI_API_KEY`
- internet connection required
- key not stored in source code
- Google Search grounding not enabled

## Independent API validation

The API was first tested with `What is the capital of Germany?`. A valid answer and API metadata confirmed:

- key validity;
- network access;
- model availability;
- correct REST request structure.

## Continuous Gemini result

Seven question-and-answer turns were completed, followed by a successful spoken exit.

- average Gemini response: 0.69 seconds;
- average speech-end-to-text latency: 1.33 seconds;
- average speech-end-to-speaker-start latency: 3.82 seconds;
- average Piper synthesis time: 1.80 seconds.

## Preliminary Qwen versus Gemini comparison

| Property | Qwen | Gemini |
|---|---|---|
| Execution | Local | Google cloud |
| Internet | Not required | Required |
| API key | No | Yes |
| Local warm-up | Required | No local LLM loading |
| Observed warm model response | 0.56 s | 0.69 s |
| Observed speech end to speaker start | 3.38 s | 3.82 s |
| Privacy | Text remains local | Transcribed text sent to Google |
| Quota | No API quota | API/free-tier limits |

The questions and answer lengths were not identical, so this was an operational comparison rather than a controlled benchmark.

## Current-information limitation

Internet access does not mean that Gemini automatically searches the web. Because Search grounding was not enabled, some time-sensitive answers were outdated. Current or political information must be verified using authoritative sources or a grounded/search-enabled design.

## Main conclusion from Task 4

Both pipelines worked. Qwen offered offline privacy and fast warm responses. Gemini avoided local model loading and handled some incomplete inputs better, but depended on internet access, an API key and cloud quotas.

# Task 5 — Echo-robust speech barge-in

## Objective

Allow a user to interrupt Piper by saying **"Stop robot" while the robot is speaking**, without allowing Piper's own voice, partial phrases or unrelated speech to stop playback.

## Why Task 5 was difficult

During playback, the ReSpeaker records both the human and the robot. The system must separate near-end speech from Piper echo, detect a possible command, verify the complete phrase and control playback—all while audio continues arriving.

## Final architecture

```text
Human speech + Piper playback
            |
ReSpeaker, six channels, 16 kHz
            |
channel 0 microphone + channel 5 playback reference
            |
streaming DTLN-AEC 512
            |
openWakeWord V4 candidate detector, threshold 0.5
            |
Faster-Whisper small.en verification
            |
3-second window, then 5-second fallback
            |
search for: stop robot / stop the robot
            |
verified → terminate Piper
rejected → Piper continues
```

## Why DTLN-512 was selected

| Test | DTLN-128 | DTLN-512 |
|---|---:|---:|
| Playback-only V4 score | 0.1128 | 0.4642 |
| Complete-command V4 score | 0.3995 | 0.9751 |

DTLN-128 missed the valid command at threshold 0.5. DTLN-512 preserved it and was selected despite greater CPU cost.

## Why V4 is not the final decision

After DTLN-512, development negatives still produced high V4 scores:

- `Stop` only: 0.8393
- `Robot` only: 0.9982
- unrelated speech: 0.8712

Therefore, V4 generates candidates but cannot stop Piper by itself.

## Why Whisper small.en was selected

On the 45-file real ReSpeaker development dataset:

- base: 5 true positives, 5 false negatives, 35 true negatives and 0 false positives;
- small.en: 10 true positives, 0 false negatives, 35 true negatives and 0 false positives when common command-like variants were tolerated.

The final strict implementation rejects `Top robot`, so the small.en development result is not proof of perfect recall under the final rule.

## Final command rule

Accepted:

- `Stop robot`
- `Stop the robot`
- longer speech that contains the complete phrase

Rejected:

- `Stop`
- `Robot`
- `Top robot`
- unrelated speech

Phrase search is used because people may talk before issuing the command.

## Main problems solved

1. Piper echo was reduced using synchronized microphone/reference DTLN processing.
2. V4 false candidates were protected by Whisper verification.
3. DTLN-128 was replaced with DTLN-512 after the valid-command miss.
4. Faster-Whisper base was replaced with small.en for better development recall.
5. False candidates no longer automatically stop Piper.
6. Whole-transcript matching was replaced with complete-phrase search.
7. `Top robot` acceptance was removed to preserve command specificity.
8. `arecord` is continuously drained during verification to reduce stale-buffer risk.
9. The detector was shared by both Gemini and Qwen.
10. Qwen status reporting now distinguishes normal completion from interruption.

## Saved Gemini barge-in results

- six recorded conversations;
- six verified interruptions;
- seven false candidates rejected;
- no false playback stop in the saved log;
- median successful verification: 1.370 seconds;
- rejected verification range: 0.22–10.98 seconds.

Some commands were repeated. The exact number and timing of spoken attempts were not logged, so first-attempt recall cannot be calculated.

## Saved Qwen barge-in results

- five recorded conversations;
- two normal completions;
- three verified interruptions;
- no false playback stop in the saved logs;
- median successful verification: 1.780 seconds.

## Current limitation

A false candidate can start a long CPU Whisper verification. Continuous capture keeps draining audio, but the synchronous final detector can process a later command late and first-attempt detection is not guaranteed.

An experimental continuous-processing version retained one command spoken during a 13.15-second false verification, but playback still stopped late. It was not promoted to the final baseline.

## Task 5 status

The laptop architectural prototype is complete. The final Jetson platform must still be used to measure GPU verification latency and multi-speaker reliability.

For the complete development history, safety reasoning, detailed limitations, demonstration sequence and professor questions, open `docs/TASK5_MEETING_GUIDE.md`.

# Combined conclusion

Tasks 1–4 created and evaluated the basic speech-interaction pipeline. Task 5 extended it so the robot can monitor a verified safety command while speaking. The current laptop implementation demonstrates the complete architecture for both online Gemini and offline Qwen. The next engineering phase is Jetson deployment and controlled evaluation rather than further uncontrolled laptop changes.

# Recommended meeting order

1. Explain the overall five-task progression.
2. Spend approximately one minute each on Tasks 1–4.
3. Spend most of the meeting on Task 5 architecture and evidence.
4. Demonstrate Qwen if network reliability is uncertain.
5. Show the saved logs if a live acoustic test behaves differently.
6. End with the Jetson evaluation plan and ask the professor to confirm the required test population and acceptance criteria.

# Three-minute Task 5 explanation

> Task 5 addresses barge-in while the robot is speaking. The main difficulty is that the ReSpeaker hears the robot's own Piper output together with the human command. I used a six-channel capture in which channel zero contains the microphone mixture and channel five contains a synchronized playback reference. A streaming DTLN-AEC 512 model uses those signals to suppress the robot's echo while preserving near-end speech. The cleaned signal is passed to an openWakeWord V4 model, but V4 is used only to generate candidates because negative tests showed high scores for partial and unrelated phrases. Each candidate is therefore verified using Faster-Whisper small.en. The verifier accepts the complete phrase Stop robot, optionally Stop the robot, and only then terminates Piper. The same shared detector was integrated into both Gemini and local Qwen speech pipelines. Saved tests show successful interruption and no false playback stops, although slow false verification can delay a later command on the CPU laptop. The architecture is complete as a development prototype, and final performance must be evaluated using GPU acceleration on the target Jetson platform.

# Suggested live demonstration

Use Qwen if internet reliability is uncertain. Use Gemini only when the internet connection and API key are confirmed.

1. Activate `.venv-dtln-aec`.
2. Start the selected pipeline.
3. Ask for a multi-sentence explanation.
4. Allow Piper to begin speaking.
5. Say unrelated speech and show that this alone does not stop playback.
6. Say `Stop` or `Robot` separately and explain that incomplete commands must be rejected.
7. Start another response if required.
8. Say `Stop robot` once.
9. Show the V4 score, Whisper transcript and playback-interruption messages.
10. Explain that V4 proposes a candidate, but Whisper makes the final decision.

Qwen demonstration command:

```bash
source ~/thesis-social-robot/.venv-dtln-aec/bin/activate
python -u ~/thesis-social-robot/src/speech_qwen_respeaker.py
```

Gemini demonstration command:

```bash
source ~/thesis-social-robot/.venv-dtln-aec/bin/activate
read -s -p "Gemini API key: " GEMINI_API_KEY
echo
export GEMINI_API_KEY
python -u ~/thesis-social-robot/src/speech_gemini_respeaker.py
```

Do not depend only on the live demonstration. Room acoustics, network access and CPU load can affect a single run. Keep the saved logs and metrics available as supporting evidence.

# Likely professor questions and answers

## Why not use only openWakeWord?

Negative recordings produced V4 scores above the 0.5 threshold. V4 is efficient for candidate generation but was not sufficiently reliable for the final stop decision.

## Why not run Whisper continuously without V4?

Continuous full ASR is computationally heavier. V4 reduces how often the more expensive verifier is invoked.

## Why is DTLN needed?

Piper playback dominates the microphone mixture and can corrupt the human command or generate false candidates. DTLN uses the synchronized playback reference to reduce that echo.

## Why was DTLN-512 selected instead of DTLN-128?

In the controlled comparison, DTLN-128 produced a complete-command score of 0.3995 and missed the 0.5 threshold. DTLN-512 produced 0.9751 and retained clearer near-end speech.

## Why reject `Top robot` if Whisper sometimes produces it?

Accepting it would weaken command specificity and could increase false stops. The final design favors safety. Future acoustic/model improvement is preferable to treating the wrong phrase as correct.

## Why use a 3-second window and a 5-second fallback?

The three-second window usually contains the short command and can finish faster. The five-second history helps when speech is slower or additional words precede the command.

## Why is the command accepted inside a longer transcript?

People may speak to another person before issuing the command. Requiring the entire transcript to equal `Stop robot` incorrectly rejected natural examples. The final rule still requires the complete phrase in the correct order.

## Is the system speaker independent?

That has not been demonstrated scientifically. Additional voices were tested informally, but a controlled multi-speaker evaluation remains necessary on Jetson.

## Why were the Gemini and Qwen timings different?

They use different execution locations and produced responses of different lengths. The recorded measurements are operational observations, not a strict controlled benchmark.

## Why can false verification take a long time?

The CPU laptop runs Faster-Whisper `small.en`, sometimes over both 3-second and 5-second windows. Difficult echo-reduced audio can require substantially more processing than a clear command.

## Did the asynchronous experiment solve the delay?

It demonstrated that a command spoken once during a 13.15-second false verification could be retained and later verified. It did not make Piper stop promptly because the earlier CPU verification remained expensive. Therefore, it was not promoted to the final baseline.

## Is Task 5 finished?

The laptop architectural prototype and Gemini/Qwen integration are complete. GPU latency, first-attempt reliability and broader multi-speaker evaluation remain Jetson deployment work.

## What is the main Task 5 contribution?

The main contribution is the integration and evaluation of synchronized reference-based echo cancellation, lightweight streaming candidate detection, exact ASR verification and Piper playback control in a shared component that works with two conversational backends.

## Why use both Qwen and Gemini?

Qwen demonstrates offline local operation and privacy. Gemini demonstrates a cloud alternative without local LLM loading. Supporting both separates the speech/barge-in architecture from a particular language-model provider.

## What happens when Gemini internet access fails?

The Gemini request fails because it depends on the cloud endpoint. Qwen remains the offline alternative. Robust production software should catch the network error and either retry or fall back to the local model.

## Does Gemini automatically provide current information?

No. Internet connectivity to the Gemini API is not the same as Search grounding. The tested request did not enable grounding, so time-sensitive answers can be outdated and require authoritative verification.

## What should happen next?

Deploy the frozen architecture on Jetson, configure the supported GPU inference runtime, repeat controlled multi-speaker testing, record every command attempt and calculate true-positive, false-negative, true-negative and false-positive rates.

# Claims to avoid during the meeting

Do not claim:

- perfect accuracy;
- guaranteed first-attempt detection;
- general speaker independence;
- final Jetson latency;
- a controlled Gemini-versus-Qwen benchmark;
- that Gemini automatically searches the current web;
- that the experimental asynchronous detector is the final system.

# Final meeting conclusion

> Tasks 1–4 established live transcription, speech synthesis and continuous local/cloud conversation. Task 5 added a reusable echo-robust barge-in component that verifies the complete Stop robot command before interrupting playback. The laptop prototype is functionally complete for both Gemini and Qwen. The remaining work is controlled Jetson deployment and evaluation, especially GPU verification latency and first-attempt multi-speaker reliability.
