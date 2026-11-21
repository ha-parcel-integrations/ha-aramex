"""The parcel contract's checks, run over every normalised sample."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.aramex.const import ParcelStatus
from custom_components.aramex.parcels import (
    is_pickup,
    normalize_parcel,
    parse_iso,
    planned_window,
)

from .payloads import active_sample, delivered_sample, event

CANONICAL_KEYS = [
    "carrier",
    "barcode",
    "sender",
    "receiver",
    "status",
    "raw_status",
    "delivered",
    "delivered_at",
    "planned_from",
    "planned_to",
    "pickup",
    "pickup_point",
    "url",
    "weight",
    "dimensions",
    "history",
    "raw",
]


def _returning() -> dict:
    sample = active_sample()
    sample["result"]["Scans"].append(event("RTS", "2026-04-30T08:00:00Z", "Return"))
    return sample


def _problem() -> dict:
    sample = active_sample()
    sample["result"]["Scans"].append(event("UND", "2026-04-30T08:00:00Z", "Undeliv"))
    return sample


def _with_eta(sample: dict) -> dict:
    sample["result"]["DeliveryETADate"] = "03/08/2099"
    return sample


SAMPLES = {
    "delivered": lambda: _with_eta(delivered_sample()),
    "active": lambda: _with_eta(active_sample()),
    "returning": lambda: _with_eta(_returning()),
    "problem": lambda: _with_eta(_problem()),
    "no_eta": active_sample,
    "bare": lambda: {"tracking_code": "EXAMPLE000001", "country": "NZ", "result": {}},
}


@pytest.fixture(params=SAMPLES)
def parcel(request) -> dict:
    return normalize_parcel(SAMPLES[request.param]())


def test_keys_and_order(parcel):
    assert list(parcel) == CANONICAL_KEYS


def test_delivered_follows_status(parcel):
    assert parcel["delivered"] is (parcel["status"] is ParcelStatus.DELIVERED)


def test_delivered_at_only_when_delivered(parcel):
    if not parcel["delivered"]:
        assert parcel["delivered_at"] is None


def test_planned_window_is_ordered_and_anchored(parcel):
    if parcel["planned_to"] is not None:
        assert parcel["planned_from"] is not None
        assert parse_iso(parcel["planned_to"]) > parse_iso(parcel["planned_from"])


def test_planned_is_empty_when_the_parcel_is_done_or_waiting(parcel):
    if parcel["status"] in (
        ParcelStatus.DELIVERED,
        ParcelStatus.AT_PICKUP_POINT,
        ParcelStatus.RETURNING,
    ):
        assert parcel["planned_from"] is None
        assert parcel["planned_to"] is None


def test_there_are_no_pickup_points(parcel):
    assert parcel["pickup"] is False
    assert parcel["pickup_point"] is None


def test_a_returning_parcel_is_not_delivered_and_has_no_window():
    parcel = normalize_parcel(_with_eta(_returning()))
    assert parcel["status"] is ParcelStatus.RETURNING
    assert parcel["delivered"] is False
    assert parcel["planned_from"] is None


def test_an_active_parcel_keeps_its_window():
    parcel = normalize_parcel(_with_eta(active_sample()))
    assert parcel["planned_from"] is not None


def test_a_date_covers_the_whole_day():
    parcel = normalize_parcel(_with_eta(active_sample()))
    start = datetime.fromisoformat(parcel["planned_from"])
    end = datetime.fromisoformat(parcel["planned_to"])
    assert (start.hour, start.minute, start.second) == (0, 0, 0)
    assert (end.hour, end.minute, end.second, end.microsecond) == (23, 59, 59, 0)
    assert start.date() == end.date()


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (
            "2099-03-01T10:00:00+11:00",
            None,
            ("2099-03-01T10:00:00+11:00", "2099-03-01T23:59:59+11:00"),
        ),
        ("2099-03-01T23:59:59+11:00", None, ("2099-03-01T23:59:59+11:00", None)),
        (
            "2099-03-01",
            "2099-03-03",
            ("2099-03-01T00:00:00+11:00", "2099-03-03T23:59:59+11:00"),
        ),
        (
            "2099-03-01T10:00:00",
            "2099-03-01T12:00:00",
            ("2099-03-01T10:00:00+11:00", "2099-03-01T12:00:00+11:00"),
        ),
        (
            "2099-03-01T12:00:00+11:00",
            "2099-03-01T10:00:00+11:00",
            ("2099-03-01T10:00:00+11:00", "2099-03-01T12:00:00+11:00"),
        ),
        (
            None,
            "2099-03-01",
            ("2099-03-01T00:00:00+11:00", "2099-03-01T23:59:59+11:00"),
        ),
        ("bad", None, (None, None)),
        (None, None, (None, None)),
        (
            date(2099, 3, 1),
            None,
            ("2099-03-01T00:00:00+11:00", "2099-03-01T23:59:59+11:00"),
        ),
        (
            datetime(2099, 3, 1, 9),
            None,
            ("2099-03-01T09:00:00+11:00", "2099-03-01T23:59:59+11:00"),
        ),
        (5, None, (None, None)),
        (
            "2099-03-01T10:00:00Z",
            None,
            ("2099-03-01T10:00:00Z", "2099-03-01T23:59:59+11:00"),
        ),
    ],
)
def test_planned_window_shapes(start, end, expected):
    assert planned_window(start, end, zone=ZoneInfo("Australia/Sydney")) == expected


def test_is_pickup_is_sticky():
    assert is_pickup(None, ParcelStatus.DELIVERED, [ParcelStatus.AT_PICKUP_POINT])
    assert is_pickup(True, ParcelStatus.IN_TRANSIT)
    assert not is_pickup(None, ParcelStatus.IN_TRANSIT, [None])
