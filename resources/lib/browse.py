"""The media tree behind the browse button, worked out without Kodi.

Home Assistant answers ``media_player/browse_media`` with one level: a node
and its children. The node is not always the one that was asked for -
browsing a Radio Browser directory answers with that integration's own root,
and only the children belong to the level asked for - so the way back has to
be kept by whoever walks the tree.
"""

import collections

# What a line offers: opening it, playing it, or both. Home Assistant says so
# per child, and neither follows from the media class.
Row = collections.namedtuple(
    "Row", "title thumbnail content_type content_id expand play")


def rows(node, play_label):
    """The lines to offer for one level: the node itself, then its children.

    A node that can be played as well as opened - an album, a directory of
    stations - is offered as itself first, because Home Assistant puts that
    play button on the tile and a list has no tiles.
    """
    listing = []
    if node.get("can_play"):
        listing.append(Row(play_label, _text(node, "thumbnail"),
                           _text(node, "media_content_type"),
                           _text(node, "media_content_id"), False, True))
    for child in node.get("children") or []:
        listing.append(Row(_text(child, "title"), _text(child, "thumbnail"),
                           _text(child, "media_content_type"),
                           _text(child, "media_content_id"),
                           bool(child.get("can_expand")),
                           bool(child.get("can_play"))))
    return listing


def _text(item, key):
    value = item.get(key)
    return str(value) if value else ""
