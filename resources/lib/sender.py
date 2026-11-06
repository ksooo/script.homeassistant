"""Commands carried out one after another on a thread of their own.

Home Assistant answers a command only once the device has. Waited for on the
window's thread, that holds up every key behind it, and the stop due after
them.
"""

import collections
import queue
import threading


class Sender:
    """Takes commands at once and carries them out in order.

    A command is a callable that returns whether Home Assistant reports it
    done; the answers are collected later with answers().
    """

    def __init__(self):
        self._queue = queue.Queue()
        self._answers = collections.deque()
        self._open = 0
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, name="ha-sender")
        self._thread.daemon = True
        self._thread.start()

    @property
    def busy(self):
        """Whether a command is still waiting for its answer."""
        return self._open > 0

    def send(self, command, tag):
        with self._lock:
            self._open += 1
        self._queue.put((command, tag))

    def answers(self):
        """(tag, done) for each command answered since the last call."""
        taken = []
        while self._answers:
            taken.append(self._answers.popleft())
        return taken

    def close(self, timeout):
        """Carry out what is still queued, then end, waiting no longer than timeout."""
        self._queue.put(None)
        self._thread.join(timeout)

    def _run(self):
        while True:
            item = self._queue.get()
            if item is None:
                return
            command, tag = item
            self._answers.append((tag, command()))
            with self._lock:
                self._open -= 1
