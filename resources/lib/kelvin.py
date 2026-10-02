"""What a colour temperature looks like, for the slider that sets one.

The colours follow temperature2rgb in Home Assistant's frontend, so the slider
shades from warm to cold the way Home Assistant's own does.
"""

import math
import struct
import zlib


def rgb(kelvin):
    value = kelvin / 100.0
    return tuple(int(channel + 0.5)
                 for channel in (_red(value), _green(value), _blue(value)))


def gradient_png(low, high, width=64):
    """A strip one pixel tall shading from low to high, as PNG bytes."""
    row = bytearray([0])
    for x in range(width):
        row.extend(rgb(low + (high - low) * x / (width - 1)))
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack("!2I5B", width, 1, 8, 2, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(bytes(row)))
            + _chunk(b"IEND", b""))


def _chunk(tag, body):
    return (struct.pack("!I", len(body)) + tag + body
            + struct.pack("!I", zlib.crc32(tag + body) & 0xFFFFFFFF))


def _clamp(value):
    return max(0.0, min(255.0, value))


def _red(value):
    if value <= 66:
        return 255.0
    return _clamp(329.698727446 * (value - 60) ** -0.1332047592)


def _green(value):
    if value <= 66:
        return _clamp(99.4708025861 * math.log(value) - 161.1195681661)
    return _clamp(288.1221695283 * (value - 60) ** -0.0755148492)


def _blue(value):
    if value >= 66:
        return 255.0
    if value <= 19:
        return 0.0
    return _clamp(138.5177312231 * math.log(value - 10) - 305.0447927307)
