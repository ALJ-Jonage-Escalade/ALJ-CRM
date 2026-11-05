"""In-memory cache shared by the server's features: one value per key, kept for a limited time.

- A lifetime of 0 (or less) keeps nothing: every call loads.
- A failed load is never cached and its exception reaches the caller. An expired value is never served: a caller that
  wants to fall back on an older copy keeps it itself.
- One load at a time per key: other callers of that key wait for its result, and different keys load in parallel.
  A load must not ask the same cache for its own key (it would wait for itself).
- A lifetime counts from the start of the load, so a value is never older than its lifetime.
- `invalidate()` applies to a load already running: its result goes to its caller but is not kept, so it can't bring
  back data read before the change that caused the invalidation.

Keys are never forgotten (their load lock stays): use a small, bounded set of keys.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Generic, Hashable, Optional, Tuple, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")

Clock = Callable[[], float]


class TimedCache(Generic[K, V]):

    def __init__(self, cache_seconds: float, clock: Clock = time.monotonic) -> None:
        self.cache_seconds = cache_seconds
        self.clock = clock
        self._lock = threading.Lock()  # guards the three attributes below; never held during a load
        self._entries: Dict[K, Tuple[V, float]] = {}  # key -> (value, time it expires)
        self._load_locks: Dict[K, threading.Lock] = {}
        self._invalidations = 0

    def get_or_load(self, key: K, load: Callable[[], V]) -> V:
        """The value of this key, loaded when missing or expired."""
        return self.get_or_load_expiring(key, lambda: (load(), self.cache_seconds))

    def get_or_load_expiring(self, key: K, load: Callable[[], Tuple[V, float]]) -> V:
        """Same, for a value whose lifetime comes with it: `load` returns (value, seconds). `cache_seconds` stays the
        ceiling (math.inf: none), and a value given 0 seconds is returned without being kept."""
        if self.cache_seconds <= 0:
            return load()[0]
        with self._lock:
            load_lock = self._load_locks.setdefault(key, threading.Lock())
        with load_lock:
            with self._lock:
                entry = self._entries.get(key)
                started_at = self.clock()
                if entry is not None and started_at < entry[1]:
                    return entry[0]
                invalidations = self._invalidations
            value, seconds = load()
            with self._lock:
                seconds = min(seconds, self.cache_seconds)
                if seconds > 0 and invalidations == self._invalidations:
                    self._entries[key] = (value, started_at + seconds)
            return value

    def invalidate(self, key: Optional[K] = None) -> None:
        """Drops this key's value, or every value without a key: the next call loads again."""
        with self._lock:
            self._invalidations += 1
            if key is None:
                self._entries.clear()
            else:
                self._entries.pop(key, None)
