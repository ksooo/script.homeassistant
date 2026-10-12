"""A lamp's favourite colours, swatches in rows as in Home Assistant's
more-info dialog. OK sets the one in focus and leaves them open, so several
can be tried in turn; Back closes them.
"""

import xbmcgui

from . import formatting, kodi

LABEL_HEADING = 100
LABEL_NAME = 101
LIST_COLOURS = 50
IMAGE_PANEL = 90

# The skin's grid: swatches to a row, a row's height, and the rows it has
# room for before it scrolls. Its panel is drawn for one row.
_PER_ROW = 8
_ROW_HEIGHT = 144
_MOST_ROWS = 3

ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92


class FavouritesDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, xml_file, resource_path, theme_skin, theme_res, **kwargs):
        super().__init__()
        self._name = kwargs["name"]
        self._favourites = kwargs["favourites"]
        self._attributes = kwargs["attributes"]
        self._send = kwargs["send"]
        self.closed = False

    def onInit(self):
        self._set(LABEL_HEADING, kodi.tr("action_favourite_colours"))
        self._set(LABEL_NAME, self._name)
        items = []
        for favourite in self._favourites:
            item = xbmcgui.ListItem()
            item.setProperty("colour", formatting.favourite_swatch(
                favourite, self._attributes))
            item.setProperty("note", formatting.favourite_note(favourite))
            items.append(item)
        try:
            grid = self.getControl(LIST_COLOURS)
            grid.reset()
            grid.addItems(items)
        except RuntimeError:
            return
        self._fit(len(items))
        self.setFocusId(LIST_COLOURS)

    def onAction(self, action):
        if action.getId() in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.finish()

    def onClick(self, control_id):
        if control_id != LIST_COLOURS:
            return
        try:
            position = self.getControl(LIST_COLOURS).getSelectedPosition()
        except RuntimeError:
            return
        if 0 <= position < len(self._favourites):
            self._send(dict(self._favourites[position]))

    def tick(self):
        pass

    def finish(self):
        self.closed = True
        self.close()

    def _fit(self, count):
        """Grow the panel by the rows beyond the first, as much upwards as
        downwards, so that the dialog stays centred."""
        rows = min(max(1, -(-count // _PER_ROW)), _MOST_ROWS)
        extra = (rows - 1) * _ROW_HEIGHT
        if not extra:
            return
        try:
            for control_id in (IMAGE_PANEL, LABEL_HEADING, LABEL_NAME,
                               LIST_COLOURS):
                control = self.getControl(control_id)
                control.setPosition(control.getX(), control.getY() - extra // 2)
            panel = self.getControl(IMAGE_PANEL)
            panel.setHeight(panel.getHeight() + extra)
        except RuntimeError:
            pass

    def _set(self, control_id, text):
        try:
            self.getControl(control_id).setLabel(text)
        except RuntimeError:
            pass
