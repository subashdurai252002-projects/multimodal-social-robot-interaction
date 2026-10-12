#include <algorithm>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "modules/audio_processing/include/audio_processing.h"

constexpr int SAMPLE_RATE = 16000;
constexpr int INPUT_CHANNELS = 6;
constexpr int MICROPHONE_CHANNEL = 0;
constexpr int REFERENCE_CHANNEL = 5;

// WebRTC processes audio in 10-millisecond frames.
constexpr int FRAME_SAMPLES = 160;

// Previously measured reference-to-microphone acoustic delay.
constexpr int STREAM_DELAY_MS = 66;

const std::string INPUT_FILE =
    "/home/subash/thesis-social-robot/"
    "test_audio/reference_aec_new_6ch.wav";

const std::string OUTPUT_FILE =
    "/home/subash/thesis-social-robot/"
    "test_audio/webrtc_direct_aec_cleaned.wav";

#pragma pack(push, 1)

struct WavHeader {
    char riff[4];
    uint32_t file_size;
    char wave[4];

    char fmt[4];
    uint32_t fmt_size;
    uint16_t audio_format;
    uint16_t channels;
    uint32_t sample_rate;
    uint32_t byte_rate;
    uint16_t block_align;
    uint16_t bits_per_sample;

    char data[4];
    uint32_t data_size;
};

#pragma pack(pop)

void check_webrtc(
    int result,
    const std::string& operation
) {
    if (result != 0) {
        throw std::runtime_error(
            operation
            + " failed with WebRTC error "
            + std::to_string(result)
        );
    }
}

void write_mono_wav(
    const std::string& path,
    const std::vector<int16_t>& samples
) {
    WavHeader header{};

    std::memcpy(
        header.riff,
        "RIFF",
        4
    );

    std::memcpy(
        header.wave,
        "WAVE",
        4
    );

    std::memcpy(
        header.fmt,
        "fmt ",
        4
    );

    std::memcpy(
        header.data,
        "data",
        4
    );

    header.fmt_size = 16;
    header.audio_format = 1;
    header.channels = 1;
    header.sample_rate = SAMPLE_RATE;
    header.bits_per_sample = 16;
    header.block_align = 2;
    header.byte_rate =
        SAMPLE_RATE * header.block_align;

    header.data_size =
        static_cast<uint32_t>(
            samples.size() * sizeof(int16_t)
        );

    header.file_size =
        36 + header.data_size;

    std::ofstream output(
        path,
        std::ios::binary
    );

    if (!output) {
        throw std::runtime_error(
            "Could not create output WAV"
        );
    }

    output.write(
        reinterpret_cast<const char*>(
            &header
        ),
        sizeof(header)
    );

    output.write(
        reinterpret_cast<const char*>(
            samples.data()
        ),
        header.data_size
    );
}

int main(
    int argc,
    char* argv[]
) {
    try {
        if (argc != 3) {
            std::cerr
                << "Usage: "
                << argv[0]
                << " INPUT_6CH.wav OUTPUT_MONO.wav\n";

            return 1;
        }

        const std::string input_file =
            argv[1];

        const std::string output_file =
            argv[2];

        std::ifstream input(
            input_file,
            std::ios::binary
        );

        if (!input) {
            throw std::runtime_error(
                "Could not open input WAV"
            );
        }

        WavHeader header{};

        input.read(
            reinterpret_cast<char*>(
                &header
            ),
            sizeof(header)
        );

        if (!input) {
            throw std::runtime_error(
                "Could not read WAV header"
            );
        }

        if (
            std::memcmp(
                header.riff,
                "RIFF",
                4
            ) != 0
            ||
            std::memcmp(
                header.wave,
                "WAVE",
                4
            ) != 0
            ||
            std::memcmp(
                header.fmt,
                "fmt ",
                4
            ) != 0
            ||
            std::memcmp(
                header.data,
                "data",
                4
            ) != 0
        ) {
            throw std::runtime_error(
                "Expected a standard 44-byte PCM WAV"
            );
        }

        if (
            header.audio_format != 1
            || header.channels != INPUT_CHANNELS
            || header.sample_rate != SAMPLE_RATE
            || header.bits_per_sample != 16
        ) {
            throw std::runtime_error(
                "Input must be six-channel, "
                "16 kHz, 16-bit PCM"
            );
        }

        std::vector<int16_t> interleaved(
            header.data_size / sizeof(int16_t)
        );

        input.read(
            reinterpret_cast<char*>(
                interleaved.data()
            ),
            header.data_size
        );

        if (!input) {
            throw std::runtime_error(
                "Could not read WAV audio"
            );
        }

        const size_t total_frames =
            interleaved.size() / INPUT_CHANNELS;

        std::cout
            << "Input frames: "
            << total_frames
            << "\n";

        std::cout
            << "Duration: "
            << static_cast<double>(
                total_frames
            ) / SAMPLE_RATE
            << " seconds\n";

        std::cout
            << "Stream delay: "
            << STREAM_DELAY_MS
            << " ms\n";

        webrtc::AudioProcessing* apm =
            webrtc::AudioProcessingBuilder()
                .Create();

        if (apm == nullptr) {
            throw std::runtime_error(
                "Could not create WebRTC "
                "AudioProcessing 1.3"
            );
        }

        webrtc::AudioProcessing::Config config;

        config.echo_canceller.enabled = true;
        config.echo_canceller.mobile_mode = false;
        config.echo_canceller
            .export_linear_aec_output = false;
        config.echo_canceller
            .enforce_high_pass_filtering = true;

        // Keep NS and AGC disabled so this experiment
        // measures AEC3 rather than additional processing.
        config.noise_suppression.enabled = false;
        config.gain_controller1.enabled = false;
        config.gain_controller2.enabled = false;

        apm->ApplyConfig(config);

        const webrtc::StreamConfig stream_config(
            SAMPLE_RATE,
            1
        );

        std::vector<int16_t> output;
        output.reserve(total_frames);

        std::vector<int16_t> microphone(
            FRAME_SAMPLES,
            0
        );

        std::vector<int16_t> reference(
            FRAME_SAMPLES,
            0
        );

        for (
            size_t start = 0;
            start < total_frames;
            start += FRAME_SAMPLES
        ) {
            const size_t remaining =
                total_frames - start;

            const size_t valid_samples =
                std::min(
                    static_cast<size_t>(
                        FRAME_SAMPLES
                    ),
                    remaining
                );

            std::fill(
                microphone.begin(),
                microphone.end(),
                0
            );

            std::fill(
                reference.begin(),
                reference.end(),
                0
            );

            for (
                size_t index = 0;
                index < valid_samples;
                ++index
            ) {
                const size_t base =
                    (start + index)
                    * INPUT_CHANNELS;

                microphone[index] =
                    interleaved[
                        base
                        + MICROPHONE_CHANNEL
                    ];

                reference[index] =
                    interleaved[
                        base
                        + REFERENCE_CHANNEL
                    ];
            }

            check_webrtc(
                apm->ProcessReverseStream(
                    reference.data(),
                    stream_config,
                    stream_config,
                    reference.data()
                ),
                "AEC3 process reverse stream"
            );

            check_webrtc(
                apm->set_stream_delay_ms(
                    STREAM_DELAY_MS
                ),
                "AEC3 set stream delay"
            );

            check_webrtc(
                apm->ProcessStream(
                    microphone.data(),
                    stream_config,
                    stream_config,
                    microphone.data()
                ),
                "AEC3 process capture stream"
            );

            output.insert(
                output.end(),
                microphone.begin(),
                microphone.begin()
                    + valid_samples
            );

        }

        delete apm;

        write_mono_wav(
            output_file,
            output
        );

        std::cout
            << "Output frames: "
            << output.size()
            << "\n";

        std::cout
            << "Saved: "
            << output_file
            << "\n";

        std::cout
            << "WebRTC AEC3 offline processing complete\n";

        return 0;
    }
    catch (
        const std::exception& error
    ) {
        std::cerr
            << "ERROR: "
            << error.what()
            << "\n";

        return 1;
    }
}
