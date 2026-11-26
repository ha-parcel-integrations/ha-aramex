"""Tests for update_contents, the track_parcel field and the store lifecycle."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.aramex.const import (
    CONF_COUNTRY,
    CONF_PARCELS,
    CONF_TRACKING_CODE,
    DOMAIN,
)
from custom_components.aramex.contents import CONTENTS_STORE_MAX_CODES
from custom_components.aramex.coordinator import AramexCoordinator

from .payloads import ACTIVE_CODE, active_sample

CLIENT = "custom_components.aramex.api.AramexApiClient"
COORD = f"{AramexCoordinator.__module__}.AramexCoordinator"
UNTRACKED = "EXAMPLE555555"
OTHER_CODE = "EXAMPLE777777"
SHOES = "Running shoes"
STORE_KEY = f"{DOMAIN}.contents.%s"


def _config_entry(
    codes: list[str], country: str = "AU", unique_id: str | None = None
) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=unique_id or country,
        options={
            CONF_COUNTRY: country,
            CONF_PARCELS: [{CONF_TRACKING_CODE: code} for code in codes],
        },
    )


async def _setup(hass, *entries: MockConfigEntry) -> MockConfigEntry:
    for entry in entries:
        entry.add_to_hass(hass)
        with patch(
            f"{CLIENT}.async_get_parcel",
            new=AsyncMock(side_effect=lambda code, country: active_sample(code)),
        ):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
    return entries[0]


async def _hub(hass, codes: list[str] | None = None) -> MockConfigEntry:
    return await _setup(hass, _config_entry(codes or []))


async def _call(hass, service: str, data: dict) -> None:
    with patch(
        f"{CLIENT}.async_get_parcel",
        new=AsyncMock(side_effect=lambda code, country: active_sample(code)),
    ):
        await hass.services.async_call(DOMAIN, service, data, blocking=True)
        await hass.async_block_till_done()
        # A refresh requested inside the debouncer's cooldown runs after it.
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done()


def _contents(entry: MockConfigEntry, code: str) -> str | None:
    coordinator = entry.runtime_data.coordinator
    parcels = {p["barcode"]: p for p in [*coordinator.data, *coordinator.delivered]}
    return parcels[code]["contents"]


class _NoPoll:
    """Patch every way a contents change could reach the carrier."""

    def __enter__(self):
        self.refresh = patch(f"{COORD}.async_request_refresh", new=AsyncMock())
        self.fetch = patch(f"{CLIENT}.async_get_parcel", new=AsyncMock())
        self.refresh_mock = self.refresh.start()
        self.fetch_mock = self.fetch.start()
        return self

    def __exit__(self, *exc):
        self.refresh.stop()
        self.fetch.stop()

    def assert_idle(self):
        self.refresh_mock.assert_not_called()
        self.fetch_mock.assert_not_called()


async def test_a_parcel_has_no_contents_without_a_stored_value(hass):
    entry = await _hub(hass, [ACTIVE_CODE])
    assert _contents(entry, ACTIVE_CODE) is None


async def test_update_contents_sets_replaces_and_clears(hass):
    entry = await _hub(hass, [ACTIVE_CODE])

    await _call(
        hass,
        "update_contents",
        {CONF_TRACKING_CODE: ACTIVE_CODE, "contents": " Running  shoes "},
    )
    assert _contents(entry, ACTIVE_CODE) == SHOES

    await _call(
        hass,
        "update_contents",
        {CONF_TRACKING_CODE: ACTIVE_CODE, "contents": "Winter socks"},
    )
    assert _contents(entry, ACTIVE_CODE) == "Winter socks"

    await _call(
        hass, "update_contents", {CONF_TRACKING_CODE: ACTIVE_CODE, "contents": "  "}
    )
    assert _contents(entry, ACTIVE_CODE) is None


async def test_update_contents_without_text_clears(hass):
    entry = await _hub(hass, [ACTIVE_CODE])
    await _call(
        hass, "update_contents", {CONF_TRACKING_CODE: ACTIVE_CODE, "contents": SHOES}
    )

    await _call(hass, "update_contents", {CONF_TRACKING_CODE: ACTIVE_CODE})

    assert _contents(entry, ACTIVE_CODE) is None


async def test_update_contents_normalizes_the_code(hass):
    entry = await _hub(hass, [ACTIVE_CODE])
    await _call(
        hass,
        "update_contents",
        {CONF_TRACKING_CODE: " mp0085494934 ", "contents": SHOES},
    )
    assert _contents(entry, ACTIVE_CODE) == SHOES


async def test_update_contents_works_for_a_code_that_is_not_tracked(hass):
    entry = await _hub(hass, [ACTIVE_CODE])
    await _call(
        hass, "update_contents", {CONF_TRACKING_CODE: UNTRACKED, "contents": SHOES}
    )

    assert entry.runtime_data.coordinator.contents_store.get(UNTRACKED) == SHOES
    assert entry.options[CONF_PARCELS] == [{CONF_TRACKING_CODE: ACTIVE_CODE}]


async def test_update_contents_never_polls_and_notifies_once_per_change(hass):
    entry = await _hub(hass, [ACTIVE_CODE])
    coordinator = entry.runtime_data.coordinator
    data = {CONF_TRACKING_CODE: ACTIVE_CODE, "contents": SHOES}
    with _NoPoll() as no_poll:
        with patch.object(
            coordinator,
            "async_update_listeners",
            wraps=coordinator.async_update_listeners,
        ) as listeners:
            await _call(hass, "update_contents", data)
            assert listeners.call_count == 1
            await _call(hass, "update_contents", data)
            assert listeners.call_count == 1
            await _call(hass, "update_contents", {CONF_TRACKING_CODE: UNTRACKED})
            assert listeners.call_count == 1
            await _call(hass, "update_contents", {CONF_TRACKING_CODE: ACTIVE_CODE})
            assert listeners.call_count == 2
        no_poll.assert_idle()


async def test_update_contents_rejects_an_empty_code(hass):
    await _hub(hass)
    with pytest.raises(ServiceValidationError):
        await _call(hass, "update_contents", {CONF_TRACKING_CODE: "   "})


async def test_update_contents_needs_a_loaded_entry(hass):
    entry = await _hub(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_RETRY)
    with pytest.raises(ServiceValidationError):
        await _call(
            hass,
            "update_contents",
            {CONF_TRACKING_CODE: ACTIVE_CODE, "contents": SHOES},
        )


async def test_track_parcel_stores_contents_for_a_new_code_and_refreshes(hass):
    entry = await _hub(hass)
    await _call(
        hass,
        "track_parcel",
        {CONF_TRACKING_CODE: ACTIVE_CODE, "contents": SHOES},
    )

    assert entry.options[CONF_PARCELS] == [{CONF_TRACKING_CODE: ACTIVE_CODE}]
    assert _contents(entry, ACTIVE_CODE) == SHOES


async def test_track_parcel_without_contents_is_unchanged(hass):
    entry = await _hub(hass)
    await _call(hass, "track_parcel", {CONF_TRACKING_CODE: ACTIVE_CODE})

    assert entry.runtime_data.coordinator.contents_store.get(ACTIVE_CODE) is None
    assert _contents(entry, ACTIVE_CODE) is None


async def test_track_parcel_keeps_country_and_contents_apart(hass):
    entry = await _hub(hass)
    await _call(
        hass,
        "track_parcel",
        {CONF_TRACKING_CODE: ACTIVE_CODE, "country": "AU", "contents": SHOES},
    )
    assert _contents(entry, ACTIVE_CODE) == SHOES


async def test_track_parcel_on_a_tracked_code_reapplies_without_polling(hass):
    entry = await _hub(hass, [ACTIVE_CODE])
    coordinator = entry.runtime_data.coordinator
    track = {CONF_TRACKING_CODE: ACTIVE_CODE}
    with _NoPoll() as no_poll:
        with patch.object(
            coordinator,
            "async_update_listeners",
            wraps=coordinator.async_update_listeners,
        ) as listeners:
            await _call(hass, "track_parcel", {**track, "contents": SHOES})
            assert _contents(entry, ACTIVE_CODE) == SHOES
            await _call(hass, "track_parcel", {**track, "contents": SHOES})
            assert listeners.call_count == 1
            await _call(hass, "track_parcel", {**track, "contents": "Winter socks"})
            assert _contents(entry, ACTIVE_CODE) == "Winter socks"
            await _call(hass, "track_parcel", {**track, "contents": ""})
            assert _contents(entry, ACTIVE_CODE) is None
            assert listeners.call_count == 3
        no_poll.assert_idle()
    assert entry.options[CONF_PARCELS] == [{CONF_TRACKING_CODE: ACTIVE_CODE}]


async def test_track_parcel_with_contents_needs_a_loaded_entry(hass):
    entry = await _hub(hass)
    entry.mock_state(hass, ConfigEntryState.SETUP_RETRY)
    with pytest.raises(ServiceValidationError):
        await _call(
            hass,
            "track_parcel",
            {CONF_TRACKING_CODE: ACTIVE_CODE, "contents": SHOES},
        )


async def test_untrack_parcel_drops_the_contents(hass):
    entry = await _hub(hass, [ACTIVE_CODE])
    await _call(
        hass, "update_contents", {CONF_TRACKING_CODE: ACTIVE_CODE, "contents": SHOES}
    )

    await _call(hass, "untrack_parcel", {CONF_TRACKING_CODE: ACTIVE_CODE})

    assert entry.runtime_data.coordinator.contents_store.get(ACTIVE_CODE) is None
    assert entry.options[CONF_PARCELS] == []


async def test_the_store_drops_the_oldest_code_at_201(hass):
    entry = await _hub(hass)
    store = entry.runtime_data.coordinator.contents_store
    for number in range(CONTENTS_STORE_MAX_CODES + 1):
        store.async_set(f"EXAMPLE{number}", SHOES)
    assert store.get("EXAMPLE0") is None
    assert store.get("EXAMPLE1") == SHOES
    assert store.get(f"EXAMPLE{CONTENTS_STORE_MAX_CODES}") == SHOES


async def test_a_barcode_less_parcel_keeps_its_contents_after_reapply_and_poll(hass):
    entry = await _hub(hass, [ACTIVE_CODE])
    coordinator = entry.runtime_data.coordinator
    await _call(
        hass, "update_contents", {CONF_TRACKING_CODE: ACTIVE_CODE, "contents": SHOES}
    )
    for parcel in coordinator.data:
        parcel["barcode"] = None

    coordinator.async_reapply_contents()
    assert coordinator.data[0]["contents"] == SHOES

    with patch(
        f"{CLIENT}.async_get_parcel",
        new=AsyncMock(return_value={**active_sample(), "result": {"Scans": []}}),
    ):
        await coordinator.async_refresh()
    assert coordinator.data[0]["contents"] == SHOES


async def test_a_stored_value_survives_a_restart_of_the_entry(hass, hass_storage):
    entry = await _hub(hass, [ACTIVE_CODE])
    await _call(
        hass, "update_contents", {CONF_TRACKING_CODE: ACTIVE_CODE, "contents": SHOES}
    )
    store = entry.runtime_data.coordinator.contents_store
    await store._store.async_save(store._data_to_save())

    assert await hass.config_entries.async_unload(entry.entry_id)
    with patch(
        f"{CLIENT}.async_get_parcel", new=AsyncMock(return_value=active_sample())
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert _contents(entry, ACTIVE_CODE) == SHOES


async def test_an_entry_without_a_store_file_works(hass, hass_storage):
    entry = await _hub(hass, [ACTIVE_CODE])
    assert STORE_KEY % entry.entry_id not in hass_storage
    assert _contents(entry, ACTIVE_CODE) is None


async def test_removing_the_entry_removes_its_store(hass, hass_storage):
    entry = await _hub(hass, [ACTIVE_CODE])
    await _call(
        hass, "update_contents", {CONF_TRACKING_CODE: ACTIVE_CODE, "contents": SHOES}
    )
    store = entry.runtime_data.coordinator.contents_store
    await store._store.async_save(store._data_to_save())
    key = STORE_KEY % entry.entry_id
    assert key in hass_storage

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert key not in hass_storage


async def test_a_contents_change_alone_fires_no_event(hass):
    await _hub(hass, [ACTIVE_CODE])
    events = []
    for name in ("registered", "status_changed", "delivered"):
        hass.bus.async_listen(f"{DOMAIN}_parcel_{name}", events.append)

    await _call(
        hass, "update_contents", {CONF_TRACKING_CODE: ACTIVE_CODE, "contents": SHOES}
    )

    assert events == []


# --- several hubs ----------------------------------------------------------


async def _two_hubs(hass):
    au = _config_entry([ACTIVE_CODE], "AU")
    nz = _config_entry([OTHER_CODE], "NZ")
    await _setup(hass, au, nz)
    return au, nz


async def test_known_codes_list_what_the_hub_follows(hass):
    au, nz = await _two_hubs(hass)
    assert au.runtime_data.coordinator.known_codes == {ACTIVE_CODE}
    assert nz.runtime_data.coordinator.known_codes == {OTHER_CODE}


async def test_update_contents_goes_to_the_hub_that_follows_the_code(hass):
    au, nz = await _two_hubs(hass)
    await _call(
        hass, "update_contents", {CONF_TRACKING_CODE: OTHER_CODE, "contents": SHOES}
    )
    assert _contents(nz, OTHER_CODE) == SHOES
    assert au.runtime_data.coordinator.contents_store.get(OTHER_CODE) is None


async def test_a_code_two_hubs_follow_gets_the_value_in_both(hass):
    au = _config_entry([ACTIVE_CODE], "AU")
    nz = _config_entry([ACTIVE_CODE], "NZ")
    await _setup(hass, au, nz)
    await _call(
        hass, "update_contents", {CONF_TRACKING_CODE: ACTIVE_CODE, "contents": SHOES}
    )
    assert _contents(au, ACTIVE_CODE) == SHOES
    assert _contents(nz, ACTIVE_CODE) == SHOES


async def test_a_code_no_hub_follows_needs_a_hub(hass):
    await _two_hubs(hass)
    with pytest.raises(ServiceValidationError) as err:
        await _call(
            hass,
            "update_contents",
            {CONF_TRACKING_CODE: UNTRACKED, "contents": SHOES},
        )
    assert err.value.translation_key == "update_contents_entry_required"


async def test_config_entry_id_targets_exactly_that_hub(hass):
    au, nz = await _two_hubs(hass)
    await _call(
        hass,
        "update_contents",
        {
            CONF_TRACKING_CODE: UNTRACKED,
            "contents": SHOES,
            "config_entry_id": nz.entry_id,
        },
    )
    assert nz.runtime_data.coordinator.contents_store.get(UNTRACKED) == SHOES
    assert au.runtime_data.coordinator.contents_store.get(UNTRACKED) is None


async def test_an_unknown_config_entry_id_is_rejected(hass):
    await _two_hubs(hass)
    with pytest.raises(ServiceValidationError):
        await _call(
            hass,
            "update_contents",
            {CONF_TRACKING_CODE: ACTIVE_CODE, "config_entry_id": "nope"},
        )


async def test_an_unloaded_hub_is_never_targeted(hass):
    au, nz = await _two_hubs(hass)
    assert await hass.config_entries.async_unload(nz.entry_id)
    await _call(
        hass, "update_contents", {CONF_TRACKING_CODE: ACTIVE_CODE, "contents": SHOES}
    )
    assert _contents(au, ACTIVE_CODE) == SHOES
    with pytest.raises(ServiceValidationError):
        await _call(
            hass,
            "update_contents",
            {
                CONF_TRACKING_CODE: ACTIVE_CODE,
                "contents": SHOES,
                "config_entry_id": nz.entry_id,
            },
        )


async def test_the_services_go_with_the_last_loaded_hub(hass):
    au, nz = await _two_hubs(hass)
    assert await hass.config_entries.async_unload(au.entry_id)
    assert hass.services.has_service(DOMAIN, "update_contents")
    assert await hass.config_entries.async_unload(nz.entry_id)
    assert not hass.services.has_service(DOMAIN, "update_contents")
