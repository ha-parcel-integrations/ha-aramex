"""Tests for Aramex sensor property logic."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from custom_components.aramex.const import ParcelStatus
from custom_components.aramex.sensor import (
    AramexAwaitingPickupSensor,
    AramexDeliveredParcelsSensor,
    AramexEnRouteToPickupPointSensor,
    AramexIncomingParcelsSensor,
    AramexLastUpdateSensor,
    AramexNextDeliverySensor,
    AramexParcelSensor,
)


def _entry(entry_id: str = "e1") -> MagicMock:
    entry = MagicMock()
    entry.entry_id = entry_id
    return entry


def _coordinator(data: list[dict], delivered: list[dict] | None = None) -> MagicMock:
    coordinator = MagicMock()
    coordinator.data = data
    coordinator.delivered = delivered if delivered is not None else []
    return coordinator


def _parcel(
    barcode: str,
    status: ParcelStatus = ParcelStatus.IN_TRANSIT,
    pickup: bool = False,
    planned_from: str | None = None,
    planned_to: str | None = None,
) -> dict:
    return {
        "carrier": "Aramex",
        "barcode": barcode,
        "sender": "Sender",
        "receiver": None,
        "status": status,
        "pickup": pickup,
        "planned_from": planned_from,
        "planned_to": planned_to,
    }


def test_incoming_counts_and_lists():
    coordinator = _coordinator([_parcel("A"), _parcel("B")])
    sensor = AramexIncomingParcelsSensor(coordinator, _entry(), lambda _: None, set())
    assert sensor.native_value == 2
    assert len(sensor.extra_state_attributes["parcels"]) == 2


def test_parcel_sensor_status_and_attributes():
    parcel = _parcel("A", status=ParcelStatus.OUT_FOR_DELIVERY)
    sensor = AramexParcelSensor(_coordinator([parcel]), _entry(), "A")
    assert sensor.native_value == ParcelStatus.OUT_FOR_DELIVERY
    assert sensor.extra_state_attributes["barcode"] == "A"


def test_parcel_sensor_missing_barcode():
    sensor = AramexParcelSensor(_coordinator([_parcel("A")]), _entry(), "OTHER")
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}


def test_next_delivery_picks_earliest():
    coordinator = _coordinator(
        [
            _parcel("A", planned_from="2099-05-02T10:00:00Z"),
            _parcel("B", planned_from="2099-05-01T10:00:00Z"),
        ]
    )
    sensor = AramexNextDeliverySensor(coordinator, _entry())
    assert sensor.native_value == datetime(2099, 5, 1, 10, 0, tzinfo=UTC)
    assert sensor.extra_state_attributes["barcode"] == "B"


def test_next_delivery_skips_a_window_that_has_ended():
    coordinator = _coordinator(
        [
            _parcel("OLD", planned_from="2000-05-01T00:00:00Z"),
            _parcel(
                "DAY",
                planned_from="2000-05-01T00:00:00Z",
                planned_to="2099-05-01T23:59:59Z",
            ),
        ]
    )
    sensor = AramexNextDeliverySensor(coordinator, _entry())
    assert sensor.extra_state_attributes["barcode"] == "DAY"


def test_next_delivery_none_without_moments():
    sensor = AramexNextDeliverySensor(_coordinator([_parcel("A")]), _entry())
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}


def test_next_delivery_skips_unparseable_moment():
    coordinator = _coordinator(
        [
            _parcel("A", planned_from="not-a-date"),
            _parcel("B", planned_from="2099-05-01T10:00:00Z"),
        ]
    )
    sensor = AramexNextDeliverySensor(coordinator, _entry())
    assert sensor.extra_state_attributes["barcode"] == "B"


def test_delivered_sensor():
    coordinator = _coordinator(
        [], delivered=[_parcel("D", status=ParcelStatus.DELIVERED)]
    )
    sensor = AramexDeliveredParcelsSensor(coordinator, _entry())
    assert sensor.native_value == 1
    assert sensor.extra_state_attributes["parcels"][0]["barcode"] == "D"


def test_last_update_sensor():
    coordinator = _coordinator([])
    moment = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    coordinator.last_success_time = moment
    sensor = AramexLastUpdateSensor(coordinator, _entry())
    assert sensor.native_value == moment


def _pickup_coordinator() -> MagicMock:
    return _coordinator(
        [
            _parcel("EN", ParcelStatus.IN_TRANSIT, pickup=True),
            _parcel("OFD", ParcelStatus.OUT_FOR_DELIVERY, pickup=True),
            _parcel("AT", ParcelStatus.AT_PICKUP_POINT, pickup=True),
            _parcel("RET", ParcelStatus.RETURNING, pickup=True),
            _parcel("HOME", ParcelStatus.IN_TRANSIT),
        ],
        delivered=[_parcel("DONE", ParcelStatus.DELIVERED, pickup=True)],
    )


def test_en_route_to_pickup_point_sensor():
    sensor = AramexEnRouteToPickupPointSensor(_pickup_coordinator(), _entry())
    assert sensor.native_value == 2
    codes = [p["barcode"] for p in sensor.extra_state_attributes["parcels"]]
    assert codes == ["EN", "OFD"]
    assert sensor.unique_id == "e1_en_route_to_pickup_point"


def test_awaiting_pickup_sensor():
    sensor = AramexAwaitingPickupSensor(_pickup_coordinator(), _entry())
    assert sensor.native_value == 1
    assert sensor.extra_state_attributes["parcels"][0]["barcode"] == "AT"
    assert sensor.unique_id == "e1_awaiting_pickup"


def test_pickup_sensors_empty_without_data():
    coordinator = _coordinator([])
    coordinator.data = None
    assert AramexAwaitingPickupSensor(coordinator, _entry()).native_value == 0
    assert AramexEnRouteToPickupPointSensor(coordinator, _entry()).native_value == 0
