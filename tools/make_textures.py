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


def horizontal_band(width, height, thickness, colour, opacity):
    """A line of the given thickness, centred in a taller transparent strip."""
    top = (height - thickness) / 2.0

    def shader(x, y):
        if y < top or y > top + thickness:
            return None
        return (colour[0], colour[1], colour[2], opacity)
    return render(width, height, shader)


def ground(width, height, top, bottom, glow, reach, strength):
    """The window's ground: a vertical fade with a light in one corner.

    Reach and the distance are in fractions of the long edge, so the light
    keeps its shape whatever size this is drawn at. Written out pixel by
    pixel rather than through render(): a fade has no edge to antialias, and
    supersampling a whole screen in python would take minutes.
    """
    pixels = bytearray(width * height * 4)
    scale = float(max(width, height))
    for y in range(height):
        ratio = y / float(height - 1)
        base = [top[i] + (bottom[i] - top[i]) * ratio for i in range(3)]
        fy = y / scale
        for x in range(width):
            fx = x / scale
            fade = 1.0 - ((fx * fx + fy * fy) ** 0.5) / reach
            lift = strength * fade * fade if fade > 0 else 0.0
            index = (y * width + x) * 4
            for channel in range(3):
                value = base[channel] + glow[channel] * lift
                pixels[index + channel] = 255 if value > 255 else int(value)
            pixels[index + 3] = 255
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
                          ground(1280, 720, (0x14, 0x1A, 0x24),
                                 (0x0B, 0x0E, 0x14), ACCENT, 0.86, 0.18)))
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
                          rounded_rect(64, 64, 16, (0x16, 0x1C, 0x26), 1.0)))
    made.append(write_png(os.path.join(MEDIA, "bar.png"), 8, 2,
                          rounded_rect(8, 2, 0, (0xFF, 0xFF, 0xFF), 1.0)))

    # The scrollbars, drawn 12 wide: a stadium whose ends stay put while the
    # middle stretches. Kodi draws a border one to one, so the radius is the
    # border value, the way the tiles and the rows are done.
    made.append(write_png(os.path.join(MEDIA, "scroll.png"), 12, 16,
                          rounded_rect(12, 16, 6, (0xFF, 0xFF, 0xFF), 1.0)))

    # The volume slider's track and thumb. Kodi sizes the thumb from the
    # *track* texture's height - fScale = slider height / track texture height
    # - and then gives it a box twice as wide as tall, which its KEEP aspect
    # ratio leaves square. So the two textures scale together: at four times
    # the drawn size fScale comes out a quarter, the thumb still lands on
    # twenty pixels, and there are four times the pixels to draw it from. Kodi
    # stretches the whole skin to the screen, and a twenty pixel circle went
    # soft on the way.
    made.append(write_png(os.path.join(MEDIA, "slider_track.png"), 32, 80,
                          horizontal_band(32, 80, 24, (0xFF, 0xFF, 0xFF), 0.20)))
    made.append(write_png(os.path.join(MEDIA, "slider_nib.png"), 80, 80,
                          circle(80, (0xFF, 0xFF, 0xFF))))

    # One white circle, tinted per entity by the skin.
    made.append(write_png(os.path.join(MEDIA, "circle.png"), 64,
                          64, circle(64, (0xFF, 0xFF, 0xFF))))

    for path in made:
        print("%7d  %s" % (os.path.getsize(path), os.path.relpath(path, ROOT)))


if __name__ == "__main__":
    main()
