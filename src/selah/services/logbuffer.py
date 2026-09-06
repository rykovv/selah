"""In-memory ring buffer of recent log records, served to the UI.

Keeps the last ~2000 formatted lines with monotonically increasing sequence
numbers so the log viewer can poll incrementally (?since=<last_seq>).
"""

import collections
import itertools
import logging
import threading

_BUFFER_SIZE = 2000

_buf = collections.deque(maxlen=_BUFFER_SIZE)
_lock = threading.Lock()
_counter = itertools.count(1)
_handler = None


class _RingHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
        except Exception:
            return
        with _lock:
            _buf.append((next(_counter), msg))


def install():
    """Attach the ring handler to the root logger (and to uvicorn's loggers
    when they are configured not to propagate, as in the dev CLI)."""
    global _handler
    if _handler is not None:
        return
    _handler = _RingHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s",
                          "%Y-%m-%d %H:%M:%S")
    )
    logging.getLogger().addHandler(_handler)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        if not lg.propagate:  # own handlers, records never reach root
            lg.addHandler(_handler)


def entries_since(since: int = 0, limit: int = 500):
    """Return (entries, last_seq) with entries newer than *since*."""
    with _lock:
        items = [(seq, msg) for seq, msg in _buf if seq > since]
        last = _buf[-1][0] if _buf else since
    return items[-limit:], max(last, since)
