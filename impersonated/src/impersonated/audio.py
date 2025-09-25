import soundfile as sf
import subprocess
import io


def play_audio_stream(audio_data, sample_rate):
    """
    Plays raw audio data by streaming it to ffplay.
    The audio data is converted to WAV format in-memory.
    """
    command = [
        "ffplay",
        "-nodisp",      # No graphical display
        "-autoexit",    # Exit when playback finishes
        "-i", "-"       # Read from standard input
    ]

    # Create an in-memory binary buffer
    buffer = io.BytesIO()

    # Write the NumPy audio data to the buffer as a WAV file
    sf.write(buffer, audio_data, sample_rate, format='WAV')

    # Reset the buffer's position to the beginning
    buffer.seek(0)

    # Start the ffplay process
    player_process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    try:
        # Write the in-memory WAV file bytes to ffplay's stdin
        player_process.stdin.write(buffer.read())
        player_process.stdin.close()
        player_process.wait()
    except (BrokenPipeError, IOError):
        # This can happen if ffplay is closed manually
        print("Playback stopped or failed.")
    finally:
        # Ensure the process is terminated
        if player_process.poll() is None:
            player_process.terminate()