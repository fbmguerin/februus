"""Result sounds, generated at startup (no audio file in the repository).

Each sound is a short sequence of tones, built as a WAV file in memory:
- green:  two rising notes (all good)
- orange: two identical notes (attention)
- red:    alarm, high and low notes; played in a loop by the page until
          the key is removed (also used when the key is removed too early)
"""

import io
import math
import struct
import wave

SAMPLE_RATE = 22050
VOLUME = 0.5

# (frequency in Hz, duration in ms); frequency 0 is a silence.
SOUNDS: dict[str, tuple[tuple[int, int], ...]] = {
    "green": ((660, 150), (880, 300)),
    "orange": ((660, 250), (0, 100), (660, 250)),
    "red": ((880, 250), (440, 250), (880, 250), (440, 250), (0, 500)),
}


def generate_sounds() -> dict[str, bytes]:
    """Every sound, as WAV bytes."""
    return {name: _wav(notes) for name, notes in SOUNDS.items()}


def _wav(notes: tuple[tuple[int, int], ...]) -> bytes:
    frames = bytearray()
    for frequency, duration_ms in notes:
        count = SAMPLE_RATE * duration_ms // 1000
        for i in range(count):
            # Short fade in and out of each note, to avoid clicks.
            fade = min(1.0, i / 200, (count - i) / 200)
            value = math.sin(2 * math.pi * frequency * i / SAMPLE_RATE) if frequency else 0.0
            frames += struct.pack("<h", int(value * fade * VOLUME * 32767))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(frames))
    return buffer.getvalue()
