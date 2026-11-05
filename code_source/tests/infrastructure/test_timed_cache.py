"""infrastructure.timed_cache: lifetime, failed loads, invalidation and concurrent loads."""

from __future__ import annotations

import math
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List

import pytest

from infrastructure.timed_cache import TimedCache

WAIT_SECONDS = 5


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Loads:
    """A load giving "value 1", "value 2"…: the number of calls shows when the cache did not answer."""

    def __init__(self) -> None:
        self.count = 0

    def __call__(self) -> str:
        self.count += 1
        return f"value {self.count}"


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def test_value_kept_until_its_lifetime_ends(clock: FakeClock) -> None:
    cache: TimedCache[str, str] = TimedCache(60, clock)
    load = Loads()
    assert cache.get_or_load("key", load) == "value 1"
    clock.now += 59
    assert cache.get_or_load("key", load) == "value 1"
    clock.now += 1
    assert cache.get_or_load("key", load) == "value 2"


def test_one_value_per_key(clock: FakeClock) -> None:
    cache: TimedCache[str, str] = TimedCache(60, clock)
    assert cache.get_or_load("a", lambda: "A") == "A"
    assert cache.get_or_load("b", lambda: "B") == "B"
    assert cache.get_or_load("a", lambda: "other") == "A"


@pytest.mark.parametrize("cache_seconds", [0, -1])
def test_no_lifetime_keeps_nothing(clock: FakeClock, cache_seconds: int) -> None:
    cache: TimedCache[str, str] = TimedCache(cache_seconds, clock)
    load = Loads()
    cache.get_or_load("key", load)
    assert cache.get_or_load("key", load) == "value 2"
    assert cache.get_or_load_expiring("key", lambda: ("expiring", 60)) == "expiring"
    assert cache.get_or_load("key", load) == "value 3"


def test_falsy_values_are_cached(clock: FakeClock) -> None:
    cache: TimedCache[str, List[str]] = TimedCache(60, clock)
    assert cache.get_or_load("key", list) == []
    assert cache.get_or_load("key", lambda: ["other"]) == []


def test_failed_load_is_not_cached_and_reaches_the_caller(clock: FakeClock) -> None:
    cache: TimedCache[str, str] = TimedCache(60, clock)

    def failing() -> str:
        raise ValueError("down")

    with pytest.raises(ValueError, match="down"):
        cache.get_or_load("key", failing)
    assert cache.get_or_load("key", lambda: "back") == "back"


def test_failed_load_does_not_serve_the_expired_value(clock: FakeClock) -> None:
    cache: TimedCache[str, str] = TimedCache(60, clock)
    cache.get_or_load("key", lambda: "old")
    clock.now += 60

    def failing() -> str:
        raise ValueError("down")

    with pytest.raises(ValueError, match="down"):
        cache.get_or_load("key", failing)
    with pytest.raises(ValueError, match="down"):  # nor on the next call
        cache.get_or_load("key", failing)


def test_lifetime_counts_from_the_start_of_the_load(clock: FakeClock) -> None:
    cache: TimedCache[str, str] = TimedCache(60, clock)

    def slow_load() -> str:
        clock.now += 50
        return "slow"

    cache.get_or_load("key", slow_load)
    clock.now += 9
    assert cache.get_or_load("key", lambda: "other") == "slow"
    clock.now += 1
    assert cache.get_or_load("key", lambda: "other") == "other"


def test_lifetime_given_by_the_value(clock: FakeClock) -> None:
    cache: TimedCache[str, str] = TimedCache(math.inf, clock)
    cache.get_or_load_expiring("key", lambda: ("first", 10))
    clock.now += 9
    assert cache.get_or_load_expiring("key", lambda: ("other", 10)) == "first"
    clock.now += 1
    assert cache.get_or_load_expiring("key", lambda: ("second", 10)) == "second"


def test_cache_seconds_is_the_ceiling_of_a_value_lifetime(clock: FakeClock) -> None:
    cache: TimedCache[str, str] = TimedCache(5, clock)
    cache.get_or_load_expiring("key", lambda: ("first", 3600))
    clock.now += 5
    assert cache.get_or_load_expiring("key", lambda: ("second", 3600)) == "second"


def test_value_given_no_lifetime_is_not_kept(clock: FakeClock) -> None:
    cache: TimedCache[str, str] = TimedCache(math.inf, clock)
    assert cache.get_or_load_expiring("key", lambda: ("first", 0)) == "first"
    assert cache.get_or_load_expiring("key", lambda: ("second", 10)) == "second"


def test_invalidate_one_key_or_all(clock: FakeClock) -> None:
    cache: TimedCache[str, str] = TimedCache(60, clock)
    cache.get_or_load("a", lambda: "A")
    cache.get_or_load("b", lambda: "B")
    cache.invalidate("a")
    assert cache.get_or_load("a", lambda: "A2") == "A2"
    assert cache.get_or_load("b", lambda: "B2") == "B"
    cache.invalidate()
    assert cache.get_or_load("a", lambda: "A3") == "A3"
    assert cache.get_or_load("b", lambda: "B3") == "B3"


def test_invalidate_during_a_load_does_not_keep_its_result(clock: FakeClock) -> None:
    """A role removed while the list is being read: the list read before the removal must not stay cached."""
    cache: TimedCache[str, str] = TimedCache(60, clock)

    def load_then_invalidated() -> str:
        cache.invalidate()
        return "read before the change"

    assert cache.get_or_load("key", load_then_invalidated) == "read before the change"
    assert cache.get_or_load("key", lambda: "read after") == "read after"


def in_threads(count: int, call: Callable[[], str]) -> List[str]:
    with ThreadPoolExecutor(max_workers=count) as pool:
        futures = [pool.submit(call) for _ in range(count)]
        return [future.result(timeout=WAIT_SECONDS) for future in futures]


def test_concurrent_callers_of_a_key_share_one_load() -> None:
    cache: TimedCache[str, str] = TimedCache(60)
    load = Loads()
    release = threading.Event()

    def blocking_load() -> str:
        assert release.wait(WAIT_SECONDS)  # noqa: S101 - fails the test instead of hanging
        return load()

    threading.Timer(0.05, release.set).start()
    assert in_threads(4, lambda: cache.get_or_load("key", blocking_load)) == ["value 1"] * 4
    assert load.count == 1


def test_different_keys_load_in_parallel() -> None:
    cache: TimedCache[int, str] = TimedCache(60)
    both_loading = threading.Barrier(2, timeout=WAIT_SECONDS)  # broken, so failing, if one load waits for the other

    def load() -> str:
        both_loading.wait()
        return "loaded"

    keys = iter([1, 2])
    assert in_threads(2, lambda: cache.get_or_load(next(keys), load)) == ["loaded", "loaded"]
