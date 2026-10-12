# Thesis Social Robot — Project Map

## Start here

The actively developed laptop speech-to-speech system consists of three files in the project root:

| Status | File | Purpose |
|---|---|---|
| CURRENT | `speech_gemini_respeaker.py` | Online Gemini conversation pipeline: ReSpeaker input, Whisper transcription, Gemini response, Piper output and barge-in control. |
| CURRENT | `speech_qwen_respeaker.py` | Local Qwen/Ollama version of the same conversation pipeline. |
| CURRENT | `barge_in_detector.py` | Shared DTLN-AEC, openWakeWord V4 and Faster-Whisper command-verification implementation. |

The protected Task 5 snapshot and thesis-ready report are in `task5_final_baseline/`.

## Runtime flow

```text
speech_gemini_respeaker.py OR speech_qwen_respeaker.py
                         |
                         v
               barge_in_detector.py
                         |
          +--------------+--------------+
          |              |              |
       models/       piper_voices/     tools/
```

Do not edit a file in `task5_final_baseline/` during normal development. It is the frozen reference copy.

## Directory guide

| Directory | Classification | Description |
|---|---|---|
| `task5_final_baseline/` | FINAL SNAPSHOT | Working Task 5 scripts, logs, metrics, report and checksums. |
| `docs/` | DOCUMENTATION | Development and meeting notes. |
| `experiments/barge_in/` | EXPERIMENT | Earlier wake-word, AEC, soft-pause, cascade and asynchronous prototypes. |
| `experiments/speech_recognition/` | EXPERIMENT | Earlier live STT, VAD and echo speech scripts. |
| `experiments/echo_cancellation/` | EXPERIMENT | Offline reference-AEC and WebRTC AEC programs. |
| `archive/backups/` | BACKUP | Point-in-time files created before previous edits. Retain until the thesis is complete. |
| `results/logs/` | GENERATED EVIDENCE | Terminal logs from controlled and integration tests. |
| `results/audio/` | GENERATED EVIDENCE | Small standalone Piper test recordings. |
| `test_audio/` | RUNTIME OUTPUT | Audio written by current scripts. The current code expects this exact path. |
| `models/` | REQUIRED DATA | Wake-word, DTLN test and real recording/model data. Do not remove. |
| `piper_voices/` | REQUIRED DATA | Piper voice model and configuration. |
| `tools/` | THIRD-PARTY/RESEARCH TOOLS | DTLN-AEC, openWakeWord training material, ReSpeaker support and WebRTC source. |
| `.venv-stt/` | ENVIRONMENT | Original speech/Piper Python environment. |
| `.venv-dtln-aec/` | ENVIRONMENT | Current integrated DTLN, openWakeWord and Whisper environment. |
| `venvs/` | LEGACY ENVIRONMENT | Earlier Whisper CPU environment. Keep until dependency review. |
| `FORSocialRobots_Architecture/` | RELATED PROJECT | Larger social-marketplace/robot architecture source tree. |
| `llm_based_speech_interaction/` | RELATED PROJECT | Earlier ROS 2 speech-interaction project and logs. |
| `__pycache__/` | GENERATED | Python bytecode cache; not source code. |

## Normal commands

Activate the integrated environment:

```bash
source ~/thesis-social-robot/.venv-dtln-aec/bin/activate
```

Run Gemini:

```bash
python -u ~/thesis-social-robot/speech_gemini_respeaker.py
```

Run Qwen:

```bash
python -u ~/thesis-social-robot/speech_qwen_respeaker.py
```

Check the active code without running it:

```bash
python -m py_compile \
  ~/thesis-social-robot/barge_in_detector.py \
  ~/thesis-social-robot/speech_gemini_respeaker.py \
  ~/thesis-social-robot/speech_qwen_respeaker.py
```

## Recommended learning order

1. Read `task5_final_baseline/TASK5_REPORT.md` for the purpose and architecture.
2. Read `speech_gemini_respeaker.py` to understand the complete conversation loop.
3. Read `barge_in_detector.py` to understand echo cancellation and interruption.
4. Compare `speech_qwen_respeaker.py` with Gemini to see the LLM-specific difference.
5. Consult `experiments/` only when documenting how the final design evolved.

## Safety rules

- Modify the three CURRENT files only after making an explicit backup or using version control.
- Never hard-code API keys in source files or reports.
- Do not delete models, environments, tools, recordings or backups solely because they are large.
- Treat files under `experiments/` as historical prototypes, not production entry points.
- Record future Jetson results separately from laptop results.
