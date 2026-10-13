"""What the number dialog holds while it is typed into, worked out without
Kodi.

The entry is kept with a point as its decimal separator and shown with the
one the language uses. The value the dialog opened with stands until the
first key replaces it, as a preselected field does.
"""

_LIMIT = 12


class Entry:
    def __init__(self, current=None, low=None, high=None, step=1.0,
                 separator=".", code=False):
        self.low = low
        self.high = high
        self.step = step
        self.code = code
        self.separator = separator
        self.decimals = 0 if code else _decimals(step)
        self.text = "" if code or current is None else _plain(current, self.decimals)
        self._fresh = bool(self.text)

    def digit(self, number):
        self._start()
        if len(self.text) >= _LIMIT:
            return
        if "." in self.text and len(self.text.split(".")[1]) >= self.decimals:
            return
        if self.text == "0" and not self.code:
            self.text = ""
        self.text += str(number)

    def point(self):
        if self.code or not self.decimals:
            return
        self._start()
        if "." not in self.text:
            self.text = (self.text or "0") + "."

    def delete(self):
        self._fresh = False
        self.text = self.text[:-1]

    def nudge(self, direction):
        """One step up or down from what stands, kept within the bounds."""
        base = self.value()
        if base is None:
            base = self.low if self.low is not None else 0.0
        value = round(base + direction * self.step, self.decimals)
        if self.low is not None:
            value = max(value, self.low)
        if self.high is not None:
            value = min(value, self.high)
        self.text = _plain(value, self.decimals)
        self._fresh = True

    def value(self):
        try:
            return float(self.text)
        except ValueError:
            return None

    def in_range(self):
        value = self.value()
        if value is None:
            return False
        return ((self.low is None or value >= self.low)
                and (self.high is None or value <= self.high))

    def shown(self):
        if self.code:
            return "●" * len(self.text)
        return self.text.replace(".", self.separator)

    def number_text(self, value):
        """A bound or step written as the entry writes its value."""
        return _plain(value, self.decimals).replace(".", self.separator)

    def _start(self):
        if self._fresh:
            self.text = ""
            self._fresh = False


def _decimals(step):
    text = ("%.6f" % step).rstrip("0").rstrip(".")
    return len(text.split(".")[1]) if "." in text else 0


def _plain(value, decimals):
    return ("%.*f" % (decimals, value)) if decimals else str(int(round(value)))
