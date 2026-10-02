"""The slider a lamp's brightness or colour temperature is set with.

Shown rather than run modally, like the media dialog, so the dashboard's loop
can send where the slider stands while it moves - at most twice a second.
OK or Back closes it.
"""

import os
import time

import xbmcgui

from . import actions as ha_actions
from . import kelvin, kodi

LABEL_HEADING = 100
LABEL_NAME = 101
LABEL_VALUE = 102
IMAGE_GRADIENT = 103
IMAGE_TRACK = 104
SLIDER = 110

_INTERVAL = 0.5

ACTION_SELECT_ITEM = 7
ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92


class SliderDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, xml_file, resource_path, theme_skin, theme_res, **kwargs):
        super().__init__()
        self._name = kwargs["name"]
        self._action = kwargs["action"]
        self._value = kwargs["start"]
        self._send = kwargs["send"]
        self._pending = None
        self._due = 0.0
        self.closed = False

    def onInit(self):
        data = self._action.data
        self._set(LABEL_HEADING, kodi.tr(self._action.label_key))
        self._set(LABEL_NAME, self._name)
        gradient = data["as"] == "color_temp_kelvin"
        try:
            if gradient:
                self.getControl(IMAGE_GRADIENT).setImage(
                    _gradient(data["min"], data["max"]), False)
            self.getControl(IMAGE_GRADIENT).setVisible(gradient)
            self.getControl(IMAGE_TRACK).setVisible(not gradient)
        except RuntimeError:
            pass
        self._place(self._value)
        self.setFocusId(SLIDER)

    def onAction(self, action):
        if action.getId() in (ACTION_SELECT_ITEM, ACTION_PREVIOUS_MENU,
                              ACTION_NAV_BACK):
            self.finish()
            return
        # As in the media dialog: Kodi has moved the slider by now but says
        # nothing about it, so the value is read back.
        try:
            raw = self.getControl(SLIDER).getInt()
        except RuntimeError:
            return
        value = ha_actions.slider_value(raw, self._action.data)
        if value != raw or value != self._value:
            self._place(value)
        if value != self._value:
            self._value = self._pending = value

    def tick(self):
        if self._pending is not None and time.time() >= self._due:
            self._flush()

    def finish(self):
        if self._pending is not None:
            self._flush()
        self.closed = True
        self.close()

    def _flush(self):
        self._due = time.time() + _INTERVAL
        value, self._pending = self._pending, None
        self._send({self._action.data["as"]: value})

    def _place(self, value):
        data = self._action.data
        try:
            self.getControl(SLIDER).setInt(value, data["min"], data["step"],
                                           data["max"])
        except RuntimeError:
            pass
        self._set(LABEL_VALUE, "%d %s" % (value, data["unit"]))

    def _set(self, control_id, text):
        try:
            self.getControl(control_id).setLabel(text)
        except RuntimeError:
            pass


def _gradient(low, high):
    path = os.path.join(kodi.temp_directory(), "kelvin-%d-%d.png" % (low, high))
    if not os.path.exists(path):
        with open(path, "wb") as image:
            image.write(kelvin.gradient_png(low, high))
    return path
