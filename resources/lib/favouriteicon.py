"""A Kodi favourite's icon: the entity's icon with Home Assistant's logo in
its top left corner, so that among other favourites it shows where it leads.

Drawn when the favourite is added, in plain Python: Kodi brings no imaging
library along.
"""

import os
import struct
import zlib

_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def draw(icon, badge, cut, target):
    """Write the icon with the badge over its top left corner to target.

    The cut, a little larger than the badge, first clears the icon around
    the badge's shape, so the two do not run into each other.
    """
    width, _, pixels = read_png(icon)
    cut_width, cut_height, cut_pixels = read_png(cut)
    for y in range(cut_height):
        for x in range(cut_width):
            index = (y * width + x) * 4 + 3
            pixels[index] = pixels[index] * (255 - cut_pixels[(y * cut_width + x) * 4 + 3]) // 255

    badge_width, badge_height, badge_pixels = read_png(badge)
    for y in range(badge_height):
        for x in range(badge_width):
            source = (y * badge_width + x) * 4
            alpha = badge_pixels[source + 3]
            if not alpha:
                continue
            index = (y * width + x) * 4
            below = pixels[index + 3] * (255 - alpha) // 255
            total = alpha + below
            for channel in range(3):
                pixels[index + channel] = (badge_pixels[source + channel] * alpha
                                           + pixels[index + channel] * below) // total
            pixels[index + 3] = total

    # Written aside first: an icon already there is not drawn again, so a
    # half-written one would stay.
    with open(target + ".part", "wb") as handle:
        handle.write(encode_png(width, len(pixels) // (width * 4), pixels))
    os.replace(target + ".part", target)


def file_name(icon, badge, cut):
    """The name the icon is kept under once drawn. It changes with the logo:
    Kodi keeps an image in its texture cache by path, so one redrawn under
    the same name would go on showing the old logo."""
    checksum = 0
    for path in (badge, cut):
        with open(path, "rb") as handle:
            checksum = zlib.crc32(handle.read(), checksum)
    return "%s-%08x.png" % (os.path.splitext(os.path.basename(icon))[0], checksum)


def prune(directory, thumbnails):
    """Delete the icons in directory that none of the thumbnails names."""
    try:
        names = os.listdir(directory)
    except OSError:
        return
    for name in names:
        if not any(name in thumbnail for thumbnail in thumbnails):
            try:
                os.remove(os.path.join(directory, name))
            except OSError:
                pass


def read_png(path):
    """Width, height and RGBA bytes of an 8 bit, non-interlaced RGBA PNG."""
    with open(path, "rb") as handle:
        data = handle.read()
    if not data.startswith(_SIGNATURE):
        raise ValueError("not a PNG: %s" % path)
    position, compressed, header = len(_SIGNATURE), bytearray(), None
    while position < len(data):
        length, tag = struct.unpack("!I4s", data[position:position + 8])
        body = data[position + 8:position + 8 + length]
        if tag == b"IHDR":
            header = struct.unpack("!2I5B", body)
        elif tag == b"IDAT":
            compressed += body
        elif tag == b"IEND":
            break
        position += 12 + length
    if header is None or header[2:5] != (8, 6, 0) or header[6] != 0:
        raise ValueError("not an 8 bit RGBA PNG: %s" % path)

    width, height = header[0], header[1]
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as error:
        raise ValueError("%s: %s" % (path, error))
    stride = width * 4
    pixels = bytearray()
    previous = bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        method = raw[start]
        line = bytearray(raw[start + 1:start + 1 + stride])
        if method:
            _unfilter(method, line, previous)
        pixels += line
        previous = line
    return width, height, pixels


def encode_png(width, height, pixels):
    stride = width * 4
    raw = b"".join(b"\0" + bytes(pixels[y * stride:(y + 1) * stride])
                   for y in range(height))
    return (_SIGNATURE
            + _chunk(b"IHDR", struct.pack("!2I5B", width, height, 8, 6, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw))
            + _chunk(b"IEND", b""))


def _unfilter(method, line, previous):
    for x in range(len(line)):
        left = line[x - 4] if x >= 4 else 0
        above = previous[x]
        if method == 1:
            line[x] = (line[x] + left) & 255
        elif method == 2:
            line[x] = (line[x] + above) & 255
        elif method == 3:
            line[x] = (line[x] + (left + above) // 2) & 255
        elif method == 4:
            corner = previous[x - 4] if x >= 4 else 0
            estimate = left + above - corner
            distances = (abs(estimate - left), abs(estimate - above), abs(estimate - corner))
            if distances[0] <= distances[1] and distances[0] <= distances[2]:
                nearest = left
            elif distances[1] <= distances[2]:
                nearest = above
            else:
                nearest = corner
            line[x] = (line[x] + nearest) & 255


def _chunk(tag, body):
    return (struct.pack("!I", len(body)) + tag + body
            + struct.pack("!I", zlib.crc32(tag + body) & 0xFFFFFFFF))
