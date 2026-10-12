# Multimodal Social Robot Interaction

A ROS 2-based research and development project investigating natural,
speech-based human-robot interaction for social robots.

## Overview

This project explores multimodal communication for social robots by
combining speech recognition, conversational AI, speech synthesis,
and audio processing.

The work is being developed as part of a Master's thesis at
Friedrich-Alexander-Universität Erlangen-Nürnberg (FAU).

## Technologies

- Ubuntu 24.04
- ROS 2 Jazzy
- Python
- ReSpeaker Microphone Array
- Whisper Speech Recognition
- Gemini and Qwen Language Models
- Piper Text-to-Speech
- Voice Activity Detection
- Acoustic Echo Cancellation

## Speech Interaction Pipeline

User Speech
    |
    v
ReSpeaker Microphone
    |
    v
Voice Activity Detection
    |
    v
Whisper Speech Recognition
    |
    v
Gemini / Qwen
    |
    v
Piper Text-to-Speech
    |
    v
Speaker Output

## Development Areas

- Live speech recognition
- Conversational AI integration
- Text-to-speech synthesis
- Speech interruption (barge-in)
- Acoustic echo cancellation
- Interaction latency evaluation
- Multimodal human-robot interaction

## Project Structure

- `speech_gemini_respeaker.py` - Gemini-based speech interaction
- `speech_qwen_respeaker.py` - Qwen-based speech interaction
- `barge_in_detector.py` - Speech interruption detection
- `experiments/` - Experimental implementations
- `results/` - Experimental results
- `docs/` - Technical documentation
- `task5_final_baseline/` - Experimental baseline and metrics
- `PROJECT_MAP.md` - Detailed project overview

## Current Development Status

The project currently focuses on speech interaction,
acoustic echo cancellation, interruption detection,
and performance evaluation.

Integration with the complete social robot architecture
and physical robot platforms is part of the broader
development roadmap.

## Research Context

The project investigates natural human-robot interaction
using multimodal sensing and adaptive communication.

Target platforms include Unitree and Pepper social robots.

## License

No license has been assigned to this repository.
All rights reserved unless otherwise specified.
