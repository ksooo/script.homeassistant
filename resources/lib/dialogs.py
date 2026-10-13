"""Kodi's select, multiselect, context menu, yes/no, OK and number dialogs,
drawn in this add-on's look rather than the skin's.

Run modally and answering as Kodi's do, so a call site only swaps the call.
The selection dialogs also name what they are about, as the slider dialog
does: a small heading and, under it, the entity.
"""

import xbmc
import xbmcgui

from . import kodi, numberpad

SELECT_XML = "script.homeassistant-select.xml"
MESSAGE_XML = "script.homeassistant-message.xml"
NUMBER_XML = "script.homeassistant-number.xml"

GROUP_ALL = 80
IMAGE_PANEL = 90
LABEL_HEADING = 100
LABEL_NAME = 101
LABEL_TEXT = 102
LIST_ROWS = 50
BUTTON_SECOND = 120
BUTTON_FIRST = 121

LABEL_VALUE = 103
BUTTON_DIGIT = 200
BUTTON_POINT = 210
BUTTON_DELETE = 211
BUTTON_MINUS = 212
BUTTON_PLUS = 213
BUTTON_OK = 214

ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
# REMOTE_0 to REMOTE_9: the digit keys of a remote or a keyboard.
ACTION_DIGIT_FIRST = 58

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


def number(heading, name, current, bounds=None, step=1.0):
    """A number typed or stepped in, held to the bounds (low, high, unit);
    None when cancelled."""
    low, high, unit = bounds if bounds else (None, None, "")
    entry = numberpad.Entry(current, low, high, step,
                            separator="," if kodi.LANGUAGE == "de" else ".")
    result = _pad(heading, name, entry, unit, bounds is not None)
    return None if result is None else entry.value()


def code(heading, name):
    """A code typed in hidden, as text; None when cancelled or left empty."""
    entry = numberpad.Entry(code=True)
    if _pad(heading, name, entry, "", False) is None:
        return None
    return entry.text or None


def _pad(heading, name, entry, unit, bounded):
    dialog = _NumberDialog(NUMBER_XML, kodi.ADDON_PATH, "Default", "1080i",
                           heading=heading, name=name, entry=entry, unit=unit,
                           bounded=bounded)
    dialog.doModal()
    result = dialog.result
    del dialog
    return result


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


class _NumberDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, xml_file, resource_path, theme_skin, theme_res, **kwargs):
        super().__init__()
        self._heading = kwargs["heading"]
        self._name = kwargs["name"]
        self._entry = kwargs["entry"]
        self._unit = kwargs["unit"]
        self._bounded = kwargs["bounded"]
        self.result = None

    def onInit(self):
        entry = self._entry
        _label(self, LABEL_HEADING, self._heading)
        _label(self, LABEL_NAME, self._name)
        for number in range(10):
            _label(self, BUTTON_DIGIT + number, str(number))
        _label(self, BUTTON_POINT, entry.separator)
        _label(self, BUTTON_OK, xbmc.getLocalizedString(_OK))
        if entry.code:
            self.setProperty("code", "true")
        for control_id, shown in ((BUTTON_POINT, entry.decimals > 0),
                                  (BUTTON_MINUS, not entry.code),
                                  (BUTTON_PLUS, not entry.code)):
            try:
                self.getControl(control_id).setVisible(shown)
            except RuntimeError:
                pass
        self._hint()
        self._show()

    def onAction(self, action):
        code = action.getId()
        if code in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self.close()
        elif ACTION_DIGIT_FIRST <= code < ACTION_DIGIT_FIRST + 10:
            self._entry.digit(code - ACTION_DIGIT_FIRST)
            self._show()

    def onClick(self, control_id):
        entry = self._entry
        if BUTTON_DIGIT <= control_id < BUTTON_DIGIT + 10:
            entry.digit(control_id - BUTTON_DIGIT)
        elif control_id == BUTTON_POINT:
            entry.point()
        elif control_id == BUTTON_DELETE:
            entry.delete()
        elif control_id in (BUTTON_MINUS, BUTTON_PLUS):
            entry.nudge(-1 if control_id == BUTTON_MINUS else 1)
        elif control_id == BUTTON_OK:
            if entry.code or entry.in_range():
                self.result = True
                self.close()
                return
        self._show()

    def _hint(self):
        entry = self._entry
        parts = []
        if self._bounded:
            parts.append("%s\u2013%s" % (entry.number_text(entry.low),
                                          _with_unit(entry.number_text(entry.high),
                                                     self._unit)))
        if not entry.code and entry.step != 1:
            parts.append(kodi.tr("number_step") % entry.number_text(entry.step))
        self.setProperty("hint", " \u00b7 ".join(parts))

    def _show(self):
        entry = self._entry
        shown = entry.shown()
        _label(self, LABEL_VALUE, _with_unit(shown, self._unit) if shown else "")
        out = bool(entry.text) and not entry.code and not entry.in_range()
        self.setProperty("out_of_range", "true" if out else "")


def _with_unit(text, unit):
    return ("%s %s" % (text, unit)).strip() if unit else text


def _label(window, control_id, text):
    try:
        window.getControl(control_id).setLabel(text)
    except RuntimeError:
        pass
