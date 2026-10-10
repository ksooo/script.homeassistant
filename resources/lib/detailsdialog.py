"""The details of an entity: its state on top, then everything Home
Assistant knows about it, in two lists.

Run modally - it changes nothing, so nothing has to be carried forward while
it stands.
"""

import xbmcgui

LABEL_NAME = 100
LABEL_PLACE = 101
LABEL_STATE = 102
LABEL_CHANGED = 103
IMAGE_ICON = 104
ROW_LIST = 50

ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92


class DetailsDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, xml_file, resource_path, theme_skin, theme_res, **kwargs):
        super().__init__()
        self._header = kwargs["header"]
        self._groups = kwargs["groups"]

    def onInit(self):
        header = self._header
        self.getControl(LABEL_NAME).setLabel(header["name"])
        self.getControl(LABEL_PLACE).setLabel(header["place"])
        self.getControl(LABEL_STATE).setLabel(header["state"])
        self.getControl(LABEL_CHANGED).setLabel(header["changed"])
        self.getControl(IMAGE_ICON).setImage(header["icon"], False)
        self.setProperty("colour", header["colour"])

        rows = self.getControl(ROW_LIST)
        rows.reset()
        for title, entries in self._groups:
            item = xbmcgui.ListItem(title)
            item.setProperty("kind", "header")
            rows.addItem(item)
            for label, value in entries:
                item = xbmcgui.ListItem(label, value)
                item.setProperty("kind", "row")
                rows.addItem(item)
        self.setFocusId(ROW_LIST)

    def onAction(self, action):
        if action.getId() in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.close()
