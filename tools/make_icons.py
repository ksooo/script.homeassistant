#!/usr/bin/env python3
"""Generates the entity icons from Material Design Icons.

Run from the addon root: ``python3 tools/make_icons.py``. It reads the wanted
icon names from ``tools/icons.txt``, fetches the MDI path data once, and
rasterises each icon to a white PNG under the skin's ``media/icons``. White is
what lets the skin tint an icon by entity state.

Needs a rasteriser: ``rsvg-convert`` where available, otherwise macOS
QuickLook. Pass ``--source mdi.js`` to work from a local copy instead of
downloading.

QuickLook renders thumbnails onto opaque white, so with it the glyph is drawn
black and its brightness is turned back into an alpha mask afterwards.
"""

import argparse
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from make_textures import write_png

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIST = os.path.join(ROOT, "tools", "icons.txt")
OUT = os.path.join(ROOT, "resources", "skins", "Default", "media", "icons")
SOURCE_URL = "https://cdn.jsdelivr.net/npm/@mdi/js@latest/mdi.js"

SIZE = 64
BATCH = 200

_DEFINITION = re.compile(r'export var mdi([A-Za-z0-9]+)\s*=\s*"([^"]+)"')

# No width or height on purpose: QuickLook then scales the viewBox to the
# size it was asked for. With them it renders the glyph at a fraction of the
# canvas, in the top left corner.
SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
       '<path fill="%s" d="%s"/></svg>')


def camel_case(name):
    """ceiling-light -> CeilingLight, as @mdi/js names its exports."""
    return "".join(part if part.isdigit() else part.capitalize()
                   for part in name.split("-"))


def load_paths(source):
    if source:
        data = open(source, encoding="utf-8").read()
    else:
        print("fetching %s" % SOURCE_URL)
        with urllib.request.urlopen(SOURCE_URL, timeout=120) as response:
            data = response.read().decode("utf-8")
    version = re.search(r"Material Design Icons v([\d.]+)", data)
    print("Material Design Icons %s, %d paths"
          % (version.group(1) if version else "?", data.count("export var mdi")))
    return dict(_DEFINITION.findall(data))


def rasteriser():
    if shutil.which("rsvg-convert"):
        return "rsvg-convert"
    if shutil.which("qlmanage"):
        return "qlmanage"
    sys.exit("no rasteriser found: install rsvg-convert")


def render(tool, svg_files, out_dir):
    if tool == "rsvg-convert":
        for path in svg_files:
            target = os.path.join(out_dir, os.path.basename(path)[:-4] + ".png")
            subprocess.run([tool, "-w", str(SIZE), "-h", str(SIZE),
                            "-o", target, path], check=True)
        return

    for start in range(0, len(svg_files), BATCH):
        subprocess.run([tool, "-t", "-s", str(SIZE), "-o", out_dir]
                       + svg_files[start:start + BATCH],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=False)
    # QuickLook appends its own suffix.
    for name in os.listdir(out_dir):
        if name.endswith(".svg.png"):
            os.replace(os.path.join(out_dir, name),
                       os.path.join(out_dir, name[:-8] + ".png"))
    for name in os.listdir(out_dir):
        if name.endswith(".png"):
            to_alpha_mask(os.path.join(out_dir, name))


def read_png(path):
    """Minimal reader for the 8 bit non-interlaced PNGs QuickLook writes."""
    data = open(path, "rb").read()
    position, compressed, header = 8, b"", None
    while position < len(data):
        length = struct.unpack("!I", data[position:position + 4])[0]
        tag = data[position + 4:position + 8]
        chunk = data[position + 8:position + 8 + length]
        if tag == b"IHDR":
            header = struct.unpack("!2I5B", chunk)
        elif tag == b"IDAT":
            compressed += chunk
        elif tag == b"IEND":
            break
        position += 12 + length

    width, height, depth, colour = header[0], header[1], header[2], header[3]
    if depth != 8 or colour not in (2, 6):
        raise ValueError("unexpected PNG format in %s" % path)

    channels = 4 if colour == 6 else 3
    raw = zlib.decompress(compressed)
    stride = width * channels
    pixels, previous, offset = bytearray(), bytearray(stride), 0
    for _ in range(height):
        method = raw[offset]
        offset += 1
        line = bytearray(raw[offset:offset + stride])
        offset += stride
        for x in range(stride):
            left = line[x - channels] if x >= channels else 0
            above = previous[x]
            corner = previous[x - channels] if x >= channels else 0
            if method == 1:
                line[x] = (line[x] + left) & 255
            elif method == 2:
                line[x] = (line[x] + above) & 255
            elif method == 3:
                line[x] = (line[x] + (left + above) // 2) & 255
            elif method == 4:
                estimate = left + above - corner
                da, db, dc = (abs(estimate - left), abs(estimate - above),
                              abs(estimate - corner))
                nearest = left if da <= db and da <= dc else above if db <= dc else corner
                line[x] = (line[x] + nearest) & 255
        pixels += line
        previous = line
    return width, height, channels, pixels


def to_alpha_mask(path):
    """Black glyph on white becomes a white glyph with an alpha channel."""
    width, height, channels, pixels = read_png(path)
    out = bytearray(width * height * 4)
    for index in range(width * height):
        alpha = 255 - pixels[index * channels]
        out[index * 4] = 255
        out[index * 4 + 1] = 255
        out[index * 4 + 2] = 255
        out[index * 4 + 3] = alpha
    write_png(path, width, height, out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", help="local copy of mdi.js")
    arguments = parser.parse_args()

    wanted = [line.strip() for line in open(LIST, encoding="utf-8")
              if line.strip() and not line.startswith("#")]
    paths = load_paths(arguments.source)

    missing = [name for name in wanted if camel_case(name) not in paths]
    if missing:
        print("not in this MDI release, skipped: %s" % ", ".join(missing))

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    tool = rasteriser()
    colour = "#FFFFFF" if tool == "rsvg-convert" else "#000000"
    with tempfile.TemporaryDirectory() as work:
        svg_files = []
        for name in wanted:
            path = paths.get(camel_case(name))
            if not path:
                continue
            svg_file = os.path.join(work, "%s.svg" % name)
            with open(svg_file, "w", encoding="utf-8") as handle:
                handle.write(SVG % (colour, path))
            svg_files.append(svg_file)

        print("rasterising %d icons with %s ..." % (len(svg_files), tool))
        render(tool, svg_files, OUT)

    written = sorted(name for name in os.listdir(OUT) if name.endswith(".png"))
    total = sum(os.path.getsize(os.path.join(OUT, name)) for name in written)
    print("%d icons, %.0f KB total, average %.0f bytes"
          % (len(written), total / 1024.0, total / max(len(written), 1)))

    failed = [name for name in wanted
              if camel_case(name) in paths and "%s.png" % name not in written]
    if failed:
        print("FAILED to rasterise: %s" % ", ".join(failed[:20]))


if __name__ == "__main__":
    main()
