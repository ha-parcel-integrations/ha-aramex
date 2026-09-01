"""Tests for Aramex AU/NZ scan normalisation."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aramex.const import CAPABILITIES, DOMAIN, ParcelStatus
from custom_components.aramex.parcels import (
    apply_delivered_filter,
    build_history,
    eta_window,
    format_dimensions,
    map_event_status,
    map_parcel_status,
    normalize_parcel,
    parse_iso,
    sort_parcels_by_ts,
    to_iso_timestamp,
)


def _scan(code: str, timestamp: str | None, description: str | None = None) -> dict:
    return {"Status": code, "RealDateTime": timestamp, "StatusDescription": description or code}


def _raw(country="AU", scans=None, label="MP0085494934", eta_date=None) -> dict:
    return {
        "country": country,
        "tracking_code": label,
        "result": {"LabelNumber": label, "DeliveryETADate": eta_date, "Scans": scans or []},
    }


@pytest.mark.parametrize(("code", "expected"), [("PP8", ParcelStatus.REGISTERED), ("PPP", ParcelStatus.IN_TRANSIT), ("TRN", ParcelStatus.IN_TRANSIT), ("ONB", ParcelStatus.OUT_FOR_DELIVERY), ("R36", ParcelStatus.DELIVERED), ("YES", ParcelStatus.DELIVERED), ("U03", ParcelStatus.PROBLEM), ("UND", ParcelStatus.PROBLEM), ("RTS", ParcelStatus.RETURNING)])
def test_known_scan_codes(code, expected):
    assert map_parcel_status(code) is expected
    assert map_event_status(code) is expected


def test_unknown_and_held_scan_codes_warn_once(caplog):
    assert map_parcel_status("ONH") is ParcelStatus.UNKNOWN
    assert map_parcel_status("ONH") is ParcelStatus.UNKNOWN
    assert caplog.text.count("ONH") == 1
    assert "issues/new" in caplog.text
    assert map_event_status(None) is None


def test_history_sorts_uses_date_fallback_and_caps():
    scans = [_scan("R36", "2026-05-04T10:00:00Z"), {"Status": "PP8", "Date": "2026-04-29T10:00:00Z", "StatusDescription": "Booked"}]
    history = build_history(scans)
    assert [item["status"] for item in history] == [ParcelStatus.REGISTERED, ParcelStatus.DELIVERED]
    assert len(build_history([_scan("PPP", f"2026-04-{day:02d}T00:00:00Z") for day in range(1, 26)])) == 20


def test_history_ignores_missing_or_bad_events():
    assert build_history(None) == []
    assert build_history(["bad", {"Status": "PPP"}]) == []


def test_normalize_uses_selected_country_and_redacts_pii():
    raw = _raw("NZ", [_scan("PP8", "2026-04-29T10:00:00Z", "Booked"), _scan("R36", "2026-05-04T10:00:00Z", "Delivered")])
    raw["result"].update({"AddressOnParcel": "private", "Signature": "private", "Reference": "private"})
    parcel = normalize_parcel(raw, include_history=True)
    assert list(parcel) == ["carrier", "barcode", "sender", "receiver", "status", "raw_status", "delivered", "delivered_at", "planned_from", "planned_to", "pickup", "pickup_point", "url", "weight", "dimensions", "history", "raw"]
    assert parcel["carrier"] == "Aramex New Zealand"
    assert parcel["status"] is ParcelStatus.DELIVERED
    assert parcel["delivered_at"] == "2026-05-04T10:00:00Z"
    assert parcel["history"][0]["status"] is ParcelStatus.REGISTERED
    assert parcel["raw"] == {"status": "R36", "status_text": "Delivered", "timestamp": "2026-05-04T10:00:00Z"}
    assert parcel["sender"] is parcel["receiver"] is parcel["weight"] is parcel["dimensions"] is None
    assert parcel["url"] == "https://www.aramex.co.nz/tools/track?l=" + parcel["barcode"]


def test_eta_window_parses_ddmmyyyy_into_local_all_day_window():
    planned_from, planned_to = eta_window("14/02/2025", "AU")
    assert planned_from == "2025-02-14T00:00:00+11:00"
    assert planned_to == "2025-02-14T23:59:59.999999+11:00"
    assert eta_window("14/02/2025", "NZ")[0] == "2025-02-14T00:00:00+13:00"
    assert eta_window(None, "AU") == (None, None)
    assert eta_window("not-a-date", "AU") == (None, None)


def test_normalize_fills_planned_window_from_eta_unless_delivered():
    raw = _raw("AU", [_scan("PPP", "2026-04-29T10:00:00Z")], eta_date="03/08/2026")
    parcel = normalize_parcel(raw)
    assert parcel["planned_from"] == "2026-08-03T00:00:00+10:00"
    assert parcel["planned_to"] == "2026-08-03T23:59:59.999999+10:00"

    delivered_raw = _raw("AU", [_scan("R36", "2026-05-04T10:00:00Z")], eta_date="03/08/2026")
    delivered_parcel = normalize_parcel(delivered_raw)
    assert delivered_parcel["planned_from"] is None
    assert delivered_parcel["planned_to"] is None


def test_status_descriptions_are_sanitized_before_history_and_raw():
    parcel = normalize_parcel(
        _raw(scans=[_scan("ONB", "2026-04-29T10:00:00Z", "  Out\nfor\t delivery \x00")]),
        include_history=True,
    )
    assert parcel["raw_status"] == "Out for delivery"
    assert parcel["history"][0]["raw_status"] == "Out for delivery"


def test_normalize_pending_and_history_off():
    parcel = normalize_parcel(_raw())
    assert parcel["barcode"] == "MP0085494934"
    assert parcel["status"] is ParcelStatus.UNKNOWN
    assert parcel["history"] is None
    assert parcel["delivered_at"] is None


def test_capabilities_and_utility_helpers():
    assert CAPABILITIES == {"delivery_window", "url", "history"}
    assert parse_iso("2026-04-29T10:00:00Z").tzinfo is not None
    assert parse_iso("bad") is None
    assert to_iso_timestamp(1784203767167) == "2026-07-16T12:09:27.167000+00:00"
    assert to_iso_timestamp(None) is None
    assert format_dimensions(1, 2, 3)["text"] == "1 x 2 x 3 cm"
    assert format_dimensions(1, None, 3) is None


def test_sort_and_delivered_filter():
    assert [p["barcode"] for p in sort_parcels_by_ts([{"barcode": "b", "planned_from": None}, {"barcode": "a", "planned_from": "2026-01-01T00:00:00Z"}], "planned_from")] == ["a", "b"]
    entry = MockConfigEntry(domain=DOMAIN, options={"delivered_filter_type": "parcels", "delivered_filter_amount": 1})
    assert len(apply_delivered_filter([{"delivered_at": "2026-01-02T00:00:00Z"}, {"delivered_at": "2026-01-01T00:00:00Z"}], entry)) == 1
    days_entry = MockConfigEntry(
        domain=DOMAIN,
        options={"delivered_filter_type": "days", "delivered_filter_amount": 1},
    )
    assert apply_delivered_filter([{"delivered_at": None}], days_entry)
