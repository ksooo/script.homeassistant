#!/usr/bin/env python3
"""Generates the skin textures.

Run from the addon root: ``python3 tools/make_textures.py``. Output is
deterministic, so regenerating never produces a spurious diff. The addon icon
is not generated here - it is the Home Assistant logo.
"""

import os
import struct
import zlib

MEDIA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "resources", "skins", "Default", "media")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ACCENT = (0x41, 0xBD, 0xF5)

SUPERSAMPLE = 4


def write_png(path, width, height, pixels):
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)
        raw += pixels[y * stride:(y + 1) * stride]

    def chunk(tag, data):
        return (struct.pack("!I", len(data)) + tag + data
                + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    header = struct.pack("!2I5B", width, height, 8, 6, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", header)
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as handle:
        handle.write(png)
    return path


def render(width, height, shader):
    """Draws with 4x4 supersampling; shader returns (r, g, b, a) or None."""
    pixels = bytearray(width * height * 4)
    step = 1.0 / SUPERSAMPLE
    offset = step / 2.0
    samples = SUPERSAMPLE * SUPERSAMPLE

    for y in range(height):
        for x in range(width):
            red = green = blue = alpha = 0.0
            for sy in range(SUPERSAMPLE):
                for sx in range(SUPERSAMPLE):
                    colour = shader(x + sx * step + offset, y + sy * step + offset)
                    if colour is None:
                        continue
                    red += colour[0] * colour[3]
                    green += colour[1] * colour[3]
                    blue += colour[2] * colour[3]
                    alpha += colour[3]
            index = (y * width + x) * 4
            if alpha <= 0:
                continue
            pixels[index] = int(red / alpha)
            pixels[index + 1] = int(green / alpha)
            pixels[index + 2] = int(blue / alpha)
            pixels[index + 3] = int(alpha / samples * 255)
    return pixels


def rounded_rect(width, height, radius, colour, opacity=1.0, border=None,
                 border_width=2.0):
    def shader(x, y):
        distance = _rounded_distance(x, y, width, height, radius)
        if distance > 0:
            return None
        if border is not None and distance > -border_width:
            return (border[0], border[1], border[2], 1.0)
        return (colour[0], colour[1], colour[2], opacity)
    return render(width, height, shader)


def circle(size, colour):
    radius = size / 2.0

    def shader(x, y):
        dx, dy = x - radius, y - radius
        if (dx * dx + dy * dy) ** 0.5 > radius:
            return None
        return (colour[0], colour[1], colour[2], 1.0)
    return render(size, size, shader)


def vertical_gradient(width, height, top, bottom):
    pixels = bytearray(width * height * 4)
    for y in range(height):
        ratio = y / float(height - 1)
        red = int(top[0] + (bottom[0] - top[0]) * ratio)
        green = int(top[1] + (bottom[1] - top[1]) * ratio)
        blue = int(top[2] + (bottom[2] - top[2]) * ratio)
        row = bytes((red, green, blue, 255)) * width
        pixels[y * width * 4:(y + 1) * width * 4] = row
    return pixels


def _rounded_distance(x, y, width, height, radius):
    """Signed distance to a rounded rectangle, negative inside."""
    half_w, half_h = width / 2.0, height / 2.0
    dx = abs(x - half_w) - (half_w - radius)
    dy = abs(y - half_h) - (half_h - radius)
    outside = ((max(dx, 0.0) ** 2 + max(dy, 0.0) ** 2) ** 0.5)
    return outside + min(max(dx, dy), 0.0) - radius


def main():
    os.makedirs(MEDIA, exist_ok=True)
    made = []

    made.append(write_png(os.path.join(MEDIA, "background.png"), 1280, 720,
                          vertical_gradient(1280, 720, (0x14, 0x1A, 0x24),
                                            (0x0B, 0x0E, 0x14))))
    made.append(write_png(os.path.join(MEDIA, "tile.png"), 64, 64,
                          rounded_rect(64, 64, 14, (0xFF, 0xFF, 0xFF), 0.07)))
    made.append(write_png(os.path.join(MEDIA, "tile_focus.png"), 64, 64,
                          rounded_rect(64, 64, 14, ACCENT, 0.22, border=ACCENT,
                                       border_width=2.5)))
    made.append(write_png(os.path.join(MEDIA, "item.png"), 48, 48,
                          rounded_rect(48, 48, 10, (0xFF, 0xFF, 0xFF), 0.05)))
    # Same treatment as the tiles: faint fill plus an accent outline.
    made.append(write_png(os.path.join(MEDIA, "item_focus.png"), 48, 48,
                          rounded_rect(48, 48, 10, ACCENT, 0.22, border=ACCENT,
                                       border_width=2.5)))
    made.append(write_png(os.path.join(MEDIA, "separator.png"), 8, 2,
                          rounded_rect(8, 2, 0, (0xFF, 0xFF, 0xFF), 0.15)))

    # The media window's panel, and the one bar its progress is drawn with:
    # tinted faint for the track and accent for the part already played.
    made.append(write_png(os.path.join(MEDIA, "panel.png"), 64, 64,
                          rounded_rect(64, 64, 16, (0x16, 0x1C, 0x26), 0.98)))
    made.append(write_png(os.path.join(MEDIA, "bar.png"), 8, 2,
                          rounded_rect(8, 2, 0, (0xFF, 0xFF, 0xFF), 1.0)))

    # One white circle, tinted per entity by the skin.
    made.append(write_png(os.path.join(MEDIA, "circle.png"), 64,
                          64, circle(64, (0xFF, 0xFF, 0xFF))))

    for path in made:
        print("%7d  %s" % (os.path.getsize(path), os.path.relpath(path, ROOT)))


if __name__ == "__main__":
    main()
