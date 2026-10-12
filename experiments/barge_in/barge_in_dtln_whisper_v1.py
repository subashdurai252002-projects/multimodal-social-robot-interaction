#!/usr/bin/env python3

import re
import signal
import subprocess
import time
import wave
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
from ai_edge_litert.interpreter import Interpreter
from faster_whisper import WhisperModel
from openwakeword.model import Model


ROOT = Path("/home/subash/thesis-social-robot")

WAKEWORD_MODEL = (
    ROOT
    / "models/stop_robot/"
    / "stop_robot_v4.onnx"
)

DTLN_MODEL_PREFIX = (
    ROOT
    / "tools/DTLN-aec/pretrained_models/"
    / "dtln_aec_512"
)

PLAYBACK_FILE = (
    ROOT
    / "test_audio/barge_in_long_reply.wav"
)

CAPTURE_DEVICE = "hw:1,0"

PLAYBACK_TARGET = (
    "alsa_output.usb-SEEED_ReSpeaker_4_Mic_Array__"
    "UAC1.0_-00.analog-stereo"
)


SAMPLE_RATE = 16000
CHANNELS = 6
SAMPLE_WIDTH = 2

# DTLN processes 128 samples at a time.
DTLN_BLOCK_LENGTH = 512
DTLN_BLOCK_SHIFT = 128

CAPTURE_FRAME_BYTES = (
    DTLN_BLOCK_SHIFT
    * CHANNELS
    * SAMPLE_WIDTH
)

# openWakeWord expects 1280 samples per prediction.
WAKEWORD_FRAME_SAMPLES = 1280
WAKEWORD_THRESHOLD = 0.5

# Whisper receives five seconds ending one second
# after the V4 candidate.
HISTORY_SECONDS = 5.0
TRAILING_SECONDS = 1.0

HISTORY_BLOCKS = int(
    HISTORY_SECONDS
    * SAMPLE_RATE
    / DTLN_BLOCK_SHIFT
)

TRAILING_BLOCKS = int(
    TRAILING_SECONDS
    * SAMPLE_RATE
    / DTLN_BLOCK_SHIFT
)

WARMUP_BLOCKS = int(
    1.0
    * SAMPLE_RATE
    / DTLN_BLOCK_SHIFT
)

PROMPT_AFTER_SECONDS = 3.0
REJECTED_CANDIDATE_COOLDOWN = 0.75


COMMAND_PATTERN = re.compile(
    r"^(?:(?:hey|okay|please)\s+)?"
    r"stop\s+(?:the\s+)?robot$"
)


def read_exact(stream, size):
    data = b""

    while len(data) < size:
        part = stream.read(
            size - len(data)
        )

        if not part:
            return None

        data += part

    return data


def stop_process(process):
    if process is None:
        return

    if process.poll() is None:
        try:
            process.send_signal(signal.SIGCONT)
        except ProcessLookupError:
            pass

        process.terminate()

        try:
            process.wait(timeout=2)

        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


class StreamingDTLNAEC:
    def __init__(self, model_prefix):
        self.interpreter_1 = Interpreter(
            model_path=str(model_prefix) + "_1.tflite"
        )
        self.interpreter_1.allocate_tensors()

        self.interpreter_2 = Interpreter(
            model_path=str(model_prefix) + "_2.tflite"
        )
        self.interpreter_2.allocate_tensors()

        self.input_details_1 = (
            self.interpreter_1.get_input_details()
        )
        self.output_details_1 = (
            self.interpreter_1.get_output_details()
        )

        self.input_details_2 = (
            self.interpreter_2.get_input_details()
        )
        self.output_details_2 = (
            self.interpreter_2.get_output_details()
        )

        self.states_1 = np.zeros(
            self.input_details_1[1]["shape"],
            dtype=np.float32,
        )

        self.states_2 = np.zeros(
            self.input_details_2[1]["shape"],
            dtype=np.float32,
        )

        self.microphone_buffer = np.zeros(
            DTLN_BLOCK_LENGTH,
            dtype=np.float32,
        )

        self.reference_buffer = np.zeros(
            DTLN_BLOCK_LENGTH,
            dtype=np.float32,
        )

        self.output_buffer = np.zeros(
            DTLN_BLOCK_LENGTH,
            dtype=np.float32,
        )

    def process(self, microphone, reference):
        if len(microphone) != DTLN_BLOCK_SHIFT:
            raise ValueError(
                "Incorrect microphone block length"
            )

        if len(reference) != DTLN_BLOCK_SHIFT:
            raise ValueError(
                "Incorrect reference block length"
            )

        self.microphone_buffer[
            :-DTLN_BLOCK_SHIFT
        ] = self.microphone_buffer[
            DTLN_BLOCK_SHIFT:
        ]

        self.microphone_buffer[
            -DTLN_BLOCK_SHIFT:
        ] = microphone

        self.reference_buffer[
            :-DTLN_BLOCK_SHIFT
        ] = self.reference_buffer[
            DTLN_BLOCK_SHIFT:
        ]

        self.reference_buffer[
            -DTLN_BLOCK_SHIFT:
        ] = reference

        microphone_fft = np.fft.rfft(
            self.microphone_buffer
        ).astype(np.complex64)

        microphone_magnitude = np.abs(
            microphone_fft
        ).reshape(
            1,
            1,
            -1,
        ).astype(np.float32)

        reference_magnitude = np.abs(
            np.fft.rfft(
                self.reference_buffer
            )
        ).reshape(
            1,
            1,
            -1,
        ).astype(np.float32)

        self.interpreter_1.set_tensor(
            self.input_details_1[0]["index"],
            microphone_magnitude,
        )

        self.interpreter_1.set_tensor(
            self.input_details_1[2]["index"],
            reference_magnitude,
        )

        self.interpreter_1.set_tensor(
            self.input_details_1[1]["index"],
            self.states_1,
        )

        self.interpreter_1.invoke()

        output_mask = self.interpreter_1.get_tensor(
            self.output_details_1[0]["index"]
        )

        self.states_1 = self.interpreter_1.get_tensor(
            self.output_details_1[1]["index"]
        )

        estimated_block = np.fft.irfft(
            microphone_fft
            * np.squeeze(output_mask)
        ).reshape(
            1,
            1,
            -1,
        ).astype(np.float32)

        reference_block = self.reference_buffer.reshape(
            1,
            1,
            -1,
        ).astype(np.float32)

        self.interpreter_2.set_tensor(
            self.input_details_2[1]["index"],
            self.states_2,
        )

        self.interpreter_2.set_tensor(
            self.input_details_2[0]["index"],
            estimated_block,
        )

        self.interpreter_2.set_tensor(
            self.input_details_2[2]["index"],
            reference_block,
        )

        self.interpreter_2.invoke()

        output_block = np.squeeze(
            self.interpreter_2.get_tensor(
                self.output_details_2[0]["index"]
            )
        ).astype(np.float32)

        self.states_2 = self.interpreter_2.get_tensor(
            self.output_details_2[1]["index"]
        )

        self.output_buffer[
            :-DTLN_BLOCK_SHIFT
        ] = self.output_buffer[
            DTLN_BLOCK_SHIFT:
        ]

        self.output_buffer[
            -DTLN_BLOCK_SHIFT:
        ] = 0.0

        self.output_buffer += output_block

        cleaned = self.output_buffer[
            :DTLN_BLOCK_SHIFT
        ].copy()

        return np.clip(
            cleaned,
            -1.0,
            1.0,
        )


def verify_command(whisper, audio):
    started = time.perf_counter()

    segments, _ = whisper.transcribe(
        audio,
        language="en",
        beam_size=5,
        condition_on_previous_text=False,
        vad_filter=True,
    )

    transcript = " ".join(
        segment.text.strip()
        for segment in segments
    ).strip()

    normalized = re.sub(
        r"[^a-z]+",
        " ",
        transcript.lower(),
    ).strip()

    verified = bool(
        COMMAND_PATTERN.search(normalized)
    )

    elapsed = time.perf_counter() - started

    return transcript, verified, elapsed


print("Loading DTLN-512...")

dtln = StreamingDTLNAEC(
    DTLN_MODEL_PREFIX
)

print("Loading openWakeWord V4...")

wakeword = Model(
    wakeword_models=[
        str(WAKEWORD_MODEL)
    ],
    inference_framework="onnx",
    enable_speex_noise_suppression=False,
)

print("Loading Faster-Whisper small.en...")

whisper = WhisperModel(
    "small.en",
    device="cpu",
    compute_type="int8",
)

print("All models ready.")


def start_recorder():
    return subprocess.Popen(
        [
            "arecord",
            "-D",
            CAPTURE_DEVICE,
            "-f",
            "S16_LE",
            "-r",
            str(SAMPLE_RATE),
            "-c",
            str(CHANNELS),
            "--buffer-time=1000000",
            "-t",
            "raw",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )


recorder = start_recorder()


playback = None

raw_capture = []
cleaned_capture = []

history = deque(
    maxlen=HISTORY_BLOCKS
)

wakeword_buffer = np.zeros(
    WAKEWORD_FRAME_SAMPLES,
    dtype=np.int16,
)

wakeword_fill = 0

candidate_active = False
candidate_trailing_blocks = 0
candidate_score = 0.0
candidate_time = 0.0

verification_future = None
verification_count = 0
cooldown_until = 0.0

command_verified = False
false_stop_before_prompt = False

prompt_time = None
verification_time = None
verified_transcript = ""

executor = ThreadPoolExecutor(
    max_workers=1
)


def process_capture_block(raw):
    global wakeword_fill

    raw_capture.append(raw)

    six_channel = np.frombuffer(
        raw,
        dtype=np.int16,
    ).reshape(
        -1,
        CHANNELS,
    )

    microphone = (
        six_channel[:, 0].astype(np.float32)
        / 32768.0
    )

    reference = (
        six_channel[:, 5].astype(np.float32)
        / 32768.0
    )

    cleaned = dtln.process(
        microphone,
        reference,
    )

    cleaned_capture.append(
        cleaned.copy()
    )

    history.append(
        cleaned.copy()
    )

    cleaned_int16 = np.clip(
        cleaned * 32768.0,
        -32768,
        32767,
    ).astype(np.int16)

    available = len(cleaned_int16)
    source_position = 0
    scores = []

    while source_position < available:
        remaining = (
            WAKEWORD_FRAME_SAMPLES
            - wakeword_fill
        )

        amount = min(
            remaining,
            available - source_position,
        )

        wakeword_buffer[
            wakeword_fill:
            wakeword_fill + amount
        ] = cleaned_int16[
            source_position:
            source_position + amount
        ]

        wakeword_fill += amount
        source_position += amount

        if wakeword_fill == WAKEWORD_FRAME_SAMPLES:
            prediction = wakeword.predict(
                wakeword_buffer
            )

            score = float(
                next(iter(prediction.values()))
            )

            scores.append(score)
            wakeword_fill = 0

    return scores


print("Warming live DTLN and microphone buffers...")

for _ in range(WARMUP_BLOCKS):
    raw = read_exact(
        recorder.stdout,
        CAPTURE_FRAME_BYTES,
    )

    if raw is None:
        raise RuntimeError(
            "Microphone ended during warm-up"
        )

    process_capture_block(raw)

print("Warm-up complete.")


playback = subprocess.Popen(
    [
        "pw-play",
        "--target",
        PLAYBACK_TARGET,
        str(PLAYBACK_FILE),
    ],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

playback_started = time.perf_counter()

print("Playback started.")
print("Wait for the SAY NOW message.")


try:
    while (
        playback.poll() is None
        or candidate_active
    ):
        raw = read_exact(
            recorder.stdout,
            CAPTURE_FRAME_BYTES,
        )

        if raw is None:
            print("Microphone stream ended.")
            break

        scores = process_capture_block(raw)

        now = time.perf_counter()
        playback_elapsed = (
            now - playback_started
        )

        if (
            prompt_time is None
            and playback_elapsed
            >= PROMPT_AFTER_SECONDS
        ):
            prompt_time = now

            print()
            print(
                ">>> SAY ONCE NOW: Stop robot",
                flush=True,
            )

        if candidate_active:
            candidate_trailing_blocks -= 1

            if candidate_trailing_blocks <= 0:
                verification_audio = np.concatenate(
                    list(history)
                ).astype(np.float32)

                verification_count += 1

                print(
                    "Piper continues during verification."
                )

                print(
                    "Stopping capture to prevent stale "
                    "audio from accumulating."
                )

                stop_process(recorder)

                print(
                    "Running Whisper verification "
                    f"{verification_count}..."
                )

                (
                    transcript,
                    verified,
                    elapsed,
                ) = verify_command(
                    whisper,
                    verification_audio,
                )

                candidate_active = False

                print(
                    "Whisper verification:",
                    repr(transcript),
                )

                print(
                    "Verification inference:",
                    round(elapsed, 2),
                    "seconds",
                )

                if verified:
                    command_verified = True
                    verified_transcript = transcript
                    verification_time = (
                        time.perf_counter()
                    )

                    print(
                        "COMPLETE COMMAND VERIFIED."
                    )

                    if prompt_time is None:
                        false_stop_before_prompt = True

                        print(
                            "FALSE STOP: verified before "
                            "the user prompt."
                        )

                    else:
                        print(
                            "Prompt-to-verification time:",
                            round(
                                verification_time
                                - prompt_time,
                                2,
                            ),
                            "seconds",
                        )

                    stop_process(playback)
                    print("Playback interrupted.")
                    break

                print(
                    "Candidate rejected."
                )

                if playback.poll() is None:
                    print(
                        "Restarting fresh microphone "
                        "monitoring..."
                    )

                    recorder = start_recorder()

                    dtln = StreamingDTLNAEC(
                        DTLN_MODEL_PREFIX
                    )

                    wakeword = Model(
                        wakeword_models=[
                            str(WAKEWORD_MODEL)
                        ],
                        inference_framework="onnx",
                        enable_speex_noise_suppression=False,
                    )

                    history.clear()

                    wakeword_buffer.fill(0)
                    wakeword_fill = 0

                    for _ in range(WARMUP_BLOCKS):
                        fresh_raw = read_exact(
                            recorder.stdout,
                            CAPTURE_FRAME_BYTES,
                        )

                        if fresh_raw is None:
                            raise RuntimeError(
                                "Microphone ended during "
                                "fresh warm-up"
                            )

                        process_capture_block(
                            fresh_raw
                        )

                    print(
                        "Fresh monitoring restarted; "
                        "Piper was not paused."
                    )

                else:
                    print(
                        "Playback finished during "
                        "verification."
                    )

                cooldown_until = (
                    time.perf_counter()
                    + REJECTED_CANDIDATE_COOLDOWN
                )

        for score in scores:
            if (
                score < WAKEWORD_THRESHOLD
                or candidate_active
                or now < cooldown_until
            ):
                continue

            candidate_active = True
            candidate_trailing_blocks = (
                TRAILING_BLOCKS
            )

            candidate_score = score
            candidate_time = playback_elapsed

            print()
            print(
                "V4 candidate:",
                round(score, 4),
                "at",
                round(playback_elapsed, 2),
                "seconds",
            )

            print(
                "Collecting one trailing second..."
            )

            break

    if not command_verified:
        print()
        print(
            "Complete 'Stop robot' command "
            "was not verified."
        )


except KeyboardInterrupt:
    print()
    print("Interrupted by user.")


finally:
    stop_process(playback)
    stop_process(recorder)

    executor.shutdown(
        wait=True
    )


timestamp = datetime.now().strftime(
    "%Y%m%d_%H%M%S"
)

raw_capture_file = (
    ROOT
    / "test_audio"
    / f"barge_in_dtln_whisper_v1_{timestamp}_6ch.wav"
)

cleaned_capture_file = (
    ROOT
    / "test_audio"
    / f"barge_in_dtln_whisper_v1_{timestamp}_cleaned.wav"
)


with wave.open(
    str(raw_capture_file),
    "wb",
) as wav:
    wav.setnchannels(CHANNELS)
    wav.setsampwidth(SAMPLE_WIDTH)
    wav.setframerate(SAMPLE_RATE)
    wav.writeframes(
        b"".join(raw_capture)
    )


if cleaned_capture:
    cleaned_audio = np.concatenate(
        cleaned_capture
    )

else:
    cleaned_audio = np.zeros(
        0,
        dtype=np.float32,
    )

cleaned_int16 = np.clip(
    cleaned_audio * 32768.0,
    -32768,
    32767,
).astype(np.int16)


with wave.open(
    str(cleaned_capture_file),
    "wb",
) as wav:
    wav.setnchannels(1)
    wav.setsampwidth(SAMPLE_WIDTH)
    wav.setframerate(SAMPLE_RATE)
    wav.writeframes(
        cleaned_int16.tobytes()
    )


print()
print("V4 threshold:", WAKEWORD_THRESHOLD)
print("Whisper verifications:", verification_count)

if candidate_time > 0:
    print(
        "Last candidate score:",
        round(candidate_score, 4),
    )

    print(
        "Last candidate time:",
        round(candidate_time, 2),
        "seconds",
    )

if verified_transcript:
    print(
        "Verified transcript:",
        repr(verified_transcript),
    )

print(
    "Result:",
    (
        "FALSE STOP"
        if false_stop_before_prompt
        else "SUCCESS"
        if command_verified
        else "NO VERIFIED COMMAND"
    ),
)

print(
    "Saved six-channel capture:",
    raw_capture_file,
)

print(
    "Saved DTLN-cleaned capture:",
    cleaned_capture_file,
)
