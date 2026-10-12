"""The colour a lamp is set to: hue and saturation, each on a slider.

Home Assistant picks a colour on a wheel - the angle is the hue, the
distance from the middle the saturation - and sends it as hs_color. A wheel
is hard to steer with a remote; two sliders take the same two values.
Shown rather than run modally, like the brightness slider, so the
dashboard's loop can send the colour while it changes.
"""

import time

import xbmcgui

from . import formatting, kodi

LABEL_HEADING = 100
LABEL_NAME = 101
LABEL_HUE = 102
LABEL_HUE_VALUE = 103
LABEL_SATURATION = 104
LABEL_SATURATION_VALUE = 105
SLIDER_HUE = 110
SLIDER_SATURATION = 111

_INTERVAL = 0.5
_HUE_STEP = 5
_SATURATION_STEP = 5

ACTION_SELECT_ITEM = 7
ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92


class ColourDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, xml_file, resource_path, theme_skin, theme_res, **kwargs):
        super().__init__()
        self._name = kwargs["name"]
        self._hue, self._saturation = kwargs["start"]
        self._send = kwargs["send"]
        self._pending = False
        self._due = 0.0
        self.closed = False

    def onInit(self):
        self._set(LABEL_HEADING, kodi.tr("action_colour"))
        self._set(LABEL_NAME, self._name)
        self._set(LABEL_HUE, kodi.tr("colour_hue"))
        self._set(LABEL_SATURATION, kodi.tr("colour_saturation"))
        self._place()
        self.setFocusId(SLIDER_HUE)

    def onAction(self, action):
        if action.getId() in (ACTION_SELECT_ITEM, ACTION_PREVIOUS_MENU,
                              ACTION_NAV_BACK):
            self.finish()
            return
        # Kodi has moved the slider by now but says nothing about it, so the
        # values are read back.
        try:
            hue = self.getControl(SLIDER_HUE).getInt() % 360
            saturation = self.getControl(SLIDER_SATURATION).getInt()
        except RuntimeError:
            return
        if (hue, saturation) != (self._hue, self._saturation):
            self._hue, self._saturation = hue, saturation
            self._pending = True
            self._show()

    def tick(self):
        if self._pending and time.time() >= self._due:
            self._flush()

    def finish(self):
        if self._pending:
            self._flush()
        self.closed = True
        self.close()

    def _flush(self):
        self._due = time.time() + _INTERVAL
        self._pending = False
        self._send({"hs_color": [self._hue, self._saturation]})

    def _place(self):
        try:
            self.getControl(SLIDER_HUE).setInt(self._hue, 0, _HUE_STEP, 360)
            self.getControl(SLIDER_SATURATION).setInt(
                self._saturation, 0, _SATURATION_STEP, 100)
        except RuntimeError:
            pass
        self._show()

    def _show(self):
        self._set(LABEL_HUE_VALUE, "%d°" % self._hue)
        self._set(LABEL_SATURATION_VALUE, "%d %%" % self._saturation)
        self.setProperty("colour", formatting.hs_colour(self._hue, self._saturation))
        self.setProperty("hue", formatting.hs_colour(self._hue, 100))

    def _set(self, control_id, text):
        try:
            self.getControl(control_id).setLabel(text)
        except RuntimeError:
            pass
