# Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import argparse
import os
import sys
import grpc
import time
import soundfile as sf
import numpy as np
from tqdm import tqdm
from typing import Iterator, Optional

sys.path.append(os.path.join(os.getcwd(), "../interfaces/bnr"))
# Importing gRPC compiler auto-generated maxine bnr library
import bnr_pb2  # noqa: E402
import bnr_pb2_grpc  # noqa: E402

# Sample rate constants
CONST_SAMPLE_48KHZ = 48000
CONST_SAMPLE_16KHZ = 16000


def read_file_content(file_path: os.PathLike) -> None:
    """Function to read file content as bytes.

    Args:
      file_path: Path to input file
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"The file '{file_path}' does not exist. Exiting.")

    with open(file_path, "rb") as file:
        return file.read()


def generate_request_for_inference(
    input_filepath: os.PathLike,
    sample_rate: int,
    streaming: bool,
    intensity_ratio: float = None,
    progress_bar: Optional[tqdm] = None,
) -> None:
    """Generator to produce the request data stream

    Args:
      input_filepath: Path to input file
      sample_rate: Input audio sample rate
      streaming: Enables grpc streaming mode
      intensity_ratio: Controls denoising intensity (0.0 to 1.0), only works with v1 models
      progress_bar: (Optional) Progress bar instance (streaming mode only)
    """
    # First send the config if intensity_ratio is specified for v1 models
    if intensity_ratio is not None:
        config_request = bnr_pb2.EnhanceAudioRequest(
            config=bnr_pb2.EnhanceAudioConfig(intensity_ratio=intensity_ratio)
        )
        config_request.config.intensity_ratio = intensity_ratio
        yield config_request

    if streaming:
        """
        Input audio chunk is generated based on sample rate and input size 10ms,
        """
        input_audio, sample_rate_file = sf.read(input_filepath)
        input_audio = input_audio.astype(np.float32)  # Convert to float32
        input_size_in_ms = 10
        samples_per_ms = sample_rate // 1000
        input_float_size = int(input_size_in_ms * samples_per_ms)

        pad_length = input_float_size - len(input_audio) % input_float_size
        input_audio = np.pad(input_audio, (0, pad_length), "constant")

        if progress_bar is not None:
            progress_bar.total = len(input_audio) // input_float_size

        print(
            f"Len {len(input_audio)}, chunk_size {input_float_size}, audio {input_audio}, "
            f"type {input_audio.dtype}"
        )

        print(
            f"Will process {len(input_audio)//sample_rate} seconds of input audio in "
            f"{input_size_in_ms} ms chunks"
        )
        for i in range(0, len(input_audio), input_float_size):
            data = input_audio[i : i + input_float_size]
            yield bnr_pb2.EnhanceAudioRequest(audio_stream_data=data.tobytes())
    else:
        DATA_CHUNKS = 64 * 1024  # bytes, we send the wav file in 64KB chunks
        with open(input_filepath, "rb") as fd:
            while True:
                buffer = fd.read(DATA_CHUNKS)
                if buffer == b"":
                    break
                yield bnr_pb2.EnhanceAudioRequest(audio_stream_data=buffer)


def write_output_file_from_response(
    response_iter: Iterator[bnr_pb2.EnhanceAudioResponse],
    output_filepath: os.PathLike,
    sample_rate: int,
    streaming: bool,
    progress_bar: Optional[tqdm],
) -> None:
    """Function to write the output file from the incoming gRPC data stream.

    Args:
      response_iter: Responses from the server to write into output file
      output_filepath: Path to output file
      sample_rate: Input audio sample rate
      streaming: Enables grpc streaming mode
      progress_bar: (Optional) Progress bar instance (streaming mode only)
    """
    if streaming:
        output_audio = []
        response_count = 0
        for response in response_iter:
            if response.HasField("audio_stream_data"):
                response_count += 1
                if progress_bar is not None:
                    progress_bar.update(1)
                output_audio.append(np.frombuffer(response.audio_stream_data, np.float32))

        sf.write(output_filepath, np.hstack(output_audio), sample_rate)
        if progress_bar:
            progress_bar.close()
        return response_count
    else:
        with open(output_filepath, "wb") as fd:
            for response in response_iter:
                if response.HasField("audio_stream_data"):
                    fd.write(response.audio_stream_data)


def parse_args() -> None:
    """
    Parse command-line arguments using argparse.
    """
    # Set up argument parsing
    parser = argparse.ArgumentParser(
        description="Process wav audio files using gRPC and apply bnr."
    )
    parser.add_argument(
        "--preview-mode",
        action="store_true",
        help="Flag to send request to preview NVCF NIM server on "
        "https://build.nvidia.com/nvidia/bnr/api",
    )
    parser.add_argument(
        "--ssl-mode",
        type=str,
        help="Flag to set SSL mode, default is None",
        default=None,
        choices=["MTLS", "TLS"],
    )
    parser.add_argument(
        "--ssl-key",
        type=str,
        default=None,
        help="The path to ssl private key.",
    )
    parser.add_argument(
        "--ssl-cert",
        type=str,
        default=None,
        help="The path to ssl certificate chain.",
    )
    parser.add_argument(
        "--ssl-root-cert",
        type=str,
        default=None,
        help="The path to ssl root certificate.",
    )
    parser.add_argument(
        "--target",
        type=str,
        default="127.0.0.1:8001",
        help="IP:port of gRPC service, when hosted locally. "
        "Use grpc.nvcf.nvidia.com:443 when hosted on NVCF.",
    )
    parser.add_argument(
        "--input",
        type=str,
        default="../assets/bnr_48k_input.wav",
        help="The path to the input audio file.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="bnr_48k_output.wav",
        help="The path for the output audio file.",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="NGC API key required for authentication, "
        "utilized when using TRY API ignored otherwise",
    )
    parser.add_argument(
        "--function-id",
        type=str,
        help="NVCF function ID for the service, utilized when using TRY API ignored otherwise",
    )
    parser.add_argument(
        "--streaming",
        action="store_true",
        help="Flag to enable grpc streaming mode. ",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        help="Sample rate of input audio file in Hz, default is 48000.",
        default=CONST_SAMPLE_48KHZ,
        choices=[CONST_SAMPLE_48KHZ, CONST_SAMPLE_16KHZ],
    )

    parser.add_argument(
        "--intensity-ratio",
        type=float,
        help=(
            "Intensity ratio value between 0 and 1 to control denoising intensity. "
            "Default is 1.0 (maximum denoising)."
        ),
        default=None,
    )
    args = parser.parse_args()

    # Validate intensity_ratio value
    if args.intensity_ratio is not None and (
        args.intensity_ratio < 0.0 or args.intensity_ratio > 1.0
    ):
        parser.error("Intensity ratio value must be between 0.0 and 1.0")

    return args


def process_request(
    channel: any,
    input_filepath: os.PathLike,
    output_filepath: os.PathLike,
    sample_rate: int,
    streaming: bool,
    request_metadata: dict = None,
    intensity_ratio: float = None,
) -> None:
    """Function to process gRPC request

    Args:
      channel: gRPC channel for server client communication
      input_filepath: Path to input file
      output_filepath: Path to output file
      sample_rate: Input audio sample rate
      streaming: Enables grpc streaming mode
      request_metadata: Credentials to process request
      intensity_ratio: Controls denoising intensity (0.0 to 1.0)
    """
    try:
        stub = bnr_pb2_grpc.MaxineBNRStub(channel)
        start_time = time.time()

        progress_bar = None
        if streaming:
            progress_bar = tqdm()

        responses = stub.EnhanceAudio(
            generate_request_for_inference(
                input_filepath=input_filepath,
                sample_rate=sample_rate,
                streaming=streaming,
                intensity_ratio=intensity_ratio,
                progress_bar=progress_bar,
            ),
            metadata=request_metadata,
        )

        response_count = write_output_file_from_response(
            response_iter=responses,
            output_filepath=output_filepath,
            sample_rate=sample_rate,
            streaming=streaming,
            progress_bar=progress_bar,
        )

        end_time = time.time()
        if streaming:
            avg_latency = (end_time - start_time) / response_count
            print(f"Average latency per request: {avg_latency*1000:.2f}ms")
            print(f"Processed {response_count} chunks.")

        print(
            f"Function invocation completed in {end_time-start_time:.2f}s, "
            "the output file is generated."
        )
    except BaseException as e:
        print(e)


def main():
    """
    Main client function
    """
    args = parse_args()
    streaming = args.streaming
    print(f"Streaming mode set to {streaming}")
    sample_rate = CONST_SAMPLE_48KHZ
    if args.sample_rate == CONST_SAMPLE_16KHZ:
        sample_rate = CONST_SAMPLE_16KHZ
    print(f"Sample Rate: {sample_rate}")
    input_filepath = args.input
    output_filepath = args.output

    # Check if input file path exists
    if os.path.isfile(input_filepath):
        print(f"The file '{input_filepath}' exists. Proceeding with processing.")
    else:
        raise FileNotFoundError(f"The file '{input_filepath}' does not exist. Exiting.")

    # Check the sample rate of the input audio file
    input_info = sf.info(input_filepath)
    input_sample_rate = input_info.samplerate
    print(f"Input file sample rate: {input_sample_rate}")

    # Check if the input file's sample rate matches the expected sample rate
    if input_sample_rate != sample_rate:
        raise ValueError(f"Sample rate mismatch: expected {sample_rate}, got {input_sample_rate}.")

    if args.preview_mode:
        if args.ssl_mode != "TLS":
            # Preview mode only supports TLS mode
            args.ssl_mode = "TLS"
            print("--ssl-mode is set as TLS, since preview_mode is enabled.")
        if args.ssl_root_cert:
            raise RuntimeError("Preview mode does not support custom root certificate.")

    if args.ssl_mode is not None:
        request_metadata = None
        root_certificates = None
        if args.ssl_mode == "MTLS":
            if not (args.ssl_key and args.ssl_cert and args.ssl_root_cert):
                raise RuntimeError(
                    "If --ssl-mode is MTLS, --ssl-key, --ssl-cert and "
                    "--ssl-root-cert are required."
                )

            private_key = read_file_content(args.ssl_key)
            certificate_chain = read_file_content(args.ssl_cert)
            root_certificates = read_file_content(args.ssl_root_cert)
            channel_credentials = grpc.ssl_channel_credentials(
                root_certificates=root_certificates,
                private_key=private_key,
                certificate_chain=certificate_chain,
            )
        else:
            # Running with NVCF
            if args.preview_mode:
                request_metadata = (
                    ("authorization", "Bearer {}".format(args.api_key)),
                    ("function-id", args.function_id),
                )
                channel_credentials = grpc.ssl_channel_credentials()
            # Running TLS mode, without NVCF
            else:
                if not (args.ssl_root_cert):
                    raise RuntimeError("If --ssl-mode is TLS, --ssl-root-cert is required.")
                root_certificates = read_file_content(args.ssl_root_cert)
                channel_credentials = grpc.ssl_channel_credentials(
                    root_certificates=root_certificates
                )

        with grpc.secure_channel(target=args.target, credentials=channel_credentials) as channel:
            process_request(
                channel=channel,
                input_filepath=input_filepath,
                output_filepath=output_filepath,
                sample_rate=sample_rate,
                streaming=streaming,
                request_metadata=request_metadata,
                intensity_ratio=args.intensity_ratio,
            )
    else:
        with grpc.insecure_channel(target=args.target) as channel:
            process_request(
                channel=channel,
                input_filepath=input_filepath,
                output_filepath=output_filepath,
                sample_rate=sample_rate,
                streaming=streaming,
                intensity_ratio=args.intensity_ratio,
            )


if __name__ == "__main__":
    main()
