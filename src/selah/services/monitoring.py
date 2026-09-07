"""In-memory request-rate tracking for monitored API endpoints."""

import time
from collections import deque
from typing import Dict

WINDOW_SECONDS = 1

_request_log: Dict[str, deque] = {
    "/api/hymns/service": deque(maxlen=3600),
    "/api/program/current": deque(maxlen=3600),
    "/api/bible/service": deque(maxlen=3600),
}


def record_request(path: str) -> None:
    """Append the current timestamp to the log for the given path."""
    if path not in _request_log:
        _request_log[path] = deque(maxlen=3600)
    _request_log[path].append(time.time())


def get_rps(path: str, window: int = WINDOW_SECONDS) -> float:
    """Count requests in the last *window* seconds and return req/s."""
    if path not in _request_log:
        return 0.0
    now = time.time()
    cutoff = now - window
    count = sum(1 for t in _request_log[path] if t >= cutoff)
    return round(count / window, 2)


def get_all_stats(window: int = WINDOW_SECONDS) -> Dict[str, float]:
    """Return RPS for every monitored endpoint."""
    return {path: get_rps(path, window) for path in _request_log}
