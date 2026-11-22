"""One value codec for the Firestore client and the cache replication: the values of the SQLite cache (None, bool,
int, float including NaN and infinities, text, bytes) keep the exact encoding the replication has always written,
and come back unchanged."""

from __future__ import annotations

import datetime
import math
from typing import Any

import pytest

from infrastructure.firestore.client import firestore_to_python_value, python_to_firestore_value

# Encoding written by the replication before the two codecs were merged (cloud_sync.common.encode_value)
ENCODED = [
    (None, {"nullValue": None}),
    (True, {"booleanValue": True}),
    (0, {"integerValue": "0"}),
    (-42, {"integerValue": "-42"}),
    (2.5, {"doubleValue": 2.5}),
    (float("inf"), {"doubleValue": "Infinity"}),
    (float("-inf"), {"doubleValue": "-Infinity"}),
    ("Élodie ; « 1 »", {"stringValue": "Élodie ; « 1 »"}),
    (b"\x00\xff", {"bytesValue": "AP8="}),
]


@pytest.mark.parametrize(("value", "encoded"), ENCODED)
def test_cache_values_keep_their_encoding(value: Any, encoded: dict) -> None:  # Any: every type of a SQLite column
    assert python_to_firestore_value(value) == encoded


@pytest.mark.parametrize(("value", "encoded"), ENCODED)
def test_cache_values_round_trip(value: Any, encoded: dict) -> None:  # Any: as above
    assert firestore_to_python_value(encoded) == value


def test_nan_round_trip() -> None:
    assert python_to_firestore_value(float("nan")) == {"doubleValue": "NaN"}
    assert math.isnan(firestore_to_python_value({"doubleValue": "NaN"}))


@pytest.mark.parametrize(("value", "timestamp"), [
    pytest.param(datetime.date(2026, 11, 22), "2026-11-22T00:00:00Z", id="date-at-midnight-utc"),
    pytest.param(datetime.datetime(2026, 11, 22, 10, 30), "2026-11-22T10:30:00Z", id="naive-datetime-gets-z"),
])
def test_dates_are_encoded_as_timestamps(value: datetime.date, timestamp: str) -> None:
    assert python_to_firestore_value(value) == {"timestampValue": timestamp}
    assert firestore_to_python_value({"timestampValue": timestamp}) == timestamp


def test_lists_and_maps_round_trip() -> None:
    value = {"tags": ["U14", 3, None], "club": {"name": "ALJ", "active": True}}
    assert firestore_to_python_value(python_to_firestore_value(value)) == value


@pytest.mark.parametrize(("encoded", "decoded"), [
    pytest.param({"integerValue": "abc"}, 0, id="corrupt-integer"),
    pytest.param({"doubleValue": "abc"}, 0.0, id="corrupt-double"),
    pytest.param({"geoPointValue": {}}, None, id="unknown-kind"),
    pytest.param("not a field", None, id="not-a-field"),
])
def test_unreadable_values_decode_to_a_default(encoded: Any, decoded: Any) -> None:  # Any: malformed inputs and defaults
    assert firestore_to_python_value(encoded) == decoded
