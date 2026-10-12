"""Kodi's select, multiselect, context menu, yes/no and OK dialogs, drawn in
this add-on's look rather than the skin's.

Run modally and answering as Kodi's do, so a call site only swaps the call.
The selection dialogs also name what they are about, as the slider dialog
does: a small heading and, under it, the entity.
"""

import xbmc
import xbmcgui

from . import kodi

SELECT_XML = "script.homeassistant-select.xml"
MESSAGE_XML = "script.homeassistant-message.xml"

GROUP_ALL = 80
IMAGE_PANEL = 90
LABEL_HEADING = 100
LABEL_NAME = 101
LABEL_TEXT = 102
LIST_ROWS = 50
BUTTON_SECOND = 120
BUTTON_FIRST = 121

ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92

# Kodi's own words for the buttons: No, Yes, OK.
_NO = 106
_YES = 107
_OK = 186

# The select skin's measures, top to bottom; the panel is laid out around
# the rows in use and centred on the screen.
_SCREEN = 1080
_HEAD = 147
_ROW = 96
_MOST_ROWS = 8
_FOOT = 36
_BUTTON_GAP = 24
_BUTTON = 84
_BUTTON_FOOT = 42


def select(heading, name, entries, preselect=-1):
    """The index picked, -1 when cancelled. An entry is a text or a
    ListItem, which may bring a second line and a thumb."""
    result = _run(heading, name, entries, False,
                  [preselect] if preselect >= 0 else [])
    return -1 if result is None else result


def multiselect(heading, name, entries, preselect=()):
    """The indices ticked, None when cancelled."""
    return _run(heading, name, entries, True, list(preselect))


def yesno(heading, text):
    """True for yes. No has the focus, as in Kodi's."""
    return _ask(heading, text, [_NO, _YES])


def ok(heading, text):
    _ask(heading, text, [_OK])


def _run(heading, name, entries, multi, chosen):
    dialog = _SelectDialog(SELECT_XML, kodi.ADDON_PATH, "Default", "1080i",
                           heading=heading, name=name, multi=multi,
                           chosen=chosen, items=[_item(entry) for entry in entries])
    dialog.doModal()
    result = dialog.result
    del dialog
    return result


def _ask(heading, text, buttons):
    dialog = _MessageDialog(MESSAGE_XML, kodi.ADDON_PATH, "Default", "1080i",
                            heading=heading, text=text, buttons=buttons)
    dialog.doModal()
    result = dialog.result
    del dialog
    return result


def _item(entry):
    if isinstance(entry, xbmcgui.ListItem):
        return entry
    return xbmcgui.ListItem(str(entry))


class _SelectDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, xml_file, resource_path, theme_skin, theme_res, **kwargs):
        super().__init__()
        self._heading = kwargs["heading"]
        self._name = kwargs["name"]
        self._multi = kwargs["multi"]
        self._chosen = kwargs["chosen"]
        self._items = kwargs["items"]
        self._laid_out = False
        self.result = None

    def onInit(self):
        _label(self, LABEL_HEADING, self._heading)
        _label(self, LABEL_NAME, self._name)
        if self._multi:
            self.setProperty("multi", "true")
        if any(item.getArt("thumb") for item in self._items):
            self.setProperty("pictures", "true")
        for index in self._chosen:
            if 0 <= index < len(self._items):
                self._items[index].setProperty("chosen", "true")
        try:
            rows = self.getControl(LIST_ROWS)
            rows.reset()
            rows.addItems(self._items)
            button = self.getControl(BUTTON_FIRST)
            button.setLabel(xbmc.getLocalizedString(_OK))
            button.setVisible(self._multi)
        except RuntimeError:
            return
        self._layout()
        self.setFocusId(LIST_ROWS)
        if self._chosen:
            rows.selectItem(min(self._chosen))

    def onAction(self, action):
        if action.getId() in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.close()

    def onClick(self, control_id):
        try:
            rows = self.getControl(LIST_ROWS)
        except RuntimeError:
            return
        if control_id == LIST_ROWS:
            position = rows.getSelectedPosition()
            if not self._multi:
                self.result = position
                self.close()
                return
            item = rows.getListItem(position)
            item.setProperty("chosen", "" if item.getProperty("chosen") else "true")
        elif control_id == BUTTON_FIRST and self._multi:
            self.result = [index for index in range(rows.size())
                           if rows.getListItem(index).getProperty("chosen")]
            self.close()

    def _layout(self):
        if self._laid_out:
            return
        self._laid_out = True
        shown = max(1, min(len(self._items), _MOST_ROWS))
        foot = _BUTTON_GAP + _BUTTON + _BUTTON_FOOT if self._multi else _FOOT
        height = _HEAD + shown * _ROW + foot
        top = (_SCREEN - height) // 2
        try:
            self.getControl(GROUP_ALL).setPosition(0, top)
            self.getControl(IMAGE_PANEL).setHeight(height)
            button = self.getControl(BUTTON_FIRST)
            button.setPosition(button.getX(),
                               top + _HEAD + shown * _ROW + _BUTTON_GAP)
        except RuntimeError:
            pass


class _MessageDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, xml_file, resource_path, theme_skin, theme_res, **kwargs):
        super().__init__()
        self._heading = kwargs["heading"]
        self._text = kwargs["text"]
        self._buttons = kwargs["buttons"]
        self.result = False

    def onInit(self):
        _label(self, LABEL_HEADING, self._heading)
        try:
            self.getControl(LABEL_TEXT).setText(self._text)
            first = self.getControl(BUTTON_FIRST)
            second = self.getControl(BUTTON_SECOND)
            first.setLabel(xbmc.getLocalizedString(self._buttons[-1]))
            if len(self._buttons) > 1:
                second.setLabel(xbmc.getLocalizedString(self._buttons[0]))
            else:
                second.setVisible(False)
        except RuntimeError:
            return
        self.setFocusId(BUTTON_SECOND if len(self._buttons) > 1 else BUTTON_FIRST)

    def onAction(self, action):
        if action.getId() in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.close()

    def onClick(self, control_id):
        if control_id in (BUTTON_FIRST, BUTTON_SECOND):
            self.result = control_id == BUTTON_FIRST and len(self._buttons) > 1
            self.close()


def _label(window, control_id, text):
    try:
        window.getControl(control_id).setLabel(text)
    except RuntimeError:
        pass
