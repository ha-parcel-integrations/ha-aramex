"""Tests for the Aramex services (track_parcel / untrack_parcel)."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aramex.const import (
    CONF_COUNTRY,
    CONF_PARCELS,
    CONF_TRACKING_CODE,
    DOMAIN,
)
from custom_components.aramex.services import _resolve_entry

from .payloads import active_sample

_SAMPLE = active_sample()



async def _setup(hass, parcels: list[dict] | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="AU",
        options={CONF_COUNTRY: "AU", CONF_PARCELS: parcels or []},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.aramex.api.AramexApiClient.async_get_parcel",
        new=AsyncMock(return_value=_SAMPLE),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_track_parcel_adds_to_options(hass):
    entry = await _setup(hass)
    with patch(
        "custom_components.aramex.api.AramexApiClient.async_get_parcel",
        new=AsyncMock(return_value=_SAMPLE),
    ):
        await hass.services.async_call(
            DOMAIN,
            "track_parcel",
            {CONF_TRACKING_CODE: "EXAMPLE999999"},
            blocking=True,
        )
        await hass.async_block_till_done()

    parcels = entry.options[CONF_PARCELS]
    assert parcels == [{CONF_TRACKING_CODE: "EXAMPLE999999"}]


async def test_track_parcel_accepts_a_code_with_separators(hass):
    entry = await _setup(hass)
    with patch(
        "custom_components.aramex.api.AramexApiClient.async_get_parcel",
        new=AsyncMock(return_value=_SAMPLE),
    ):
        await hass.services.async_call(
            DOMAIN,
            "track_parcel",
            {CONF_TRACKING_CODE: "example-999 999"},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert entry.options[CONF_PARCELS] == [
        {CONF_TRACKING_CODE: "example-999 999"}
    ]


async def test_track_parcel_rejects_empty_code(hass):
    await _setup(hass)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "track_parcel", {CONF_TRACKING_CODE: "   "}, blocking=True
        )


async def test_track_parcel_duplicate_is_noop(hass):
    entry = await _setup(hass)
    with patch(
        "custom_components.aramex.api.AramexApiClient.async_get_parcel",
        new=AsyncMock(return_value=_SAMPLE),
    ):
        for _ in range(2):
            await hass.services.async_call(
                DOMAIN,
                "track_parcel",
                {CONF_TRACKING_CODE: "EXAMPLE999999"},
                blocking=True,
            )
            await hass.async_block_till_done()

    assert len(entry.options[CONF_PARCELS]) == 1


async def test_untrack_parcel_removes_from_options(hass):
    entry = await _setup(
        hass, parcels=[{CONF_TRACKING_CODE: "EXAMPLE999999"}]
    )
    with patch(
        "custom_components.aramex.api.AramexApiClient.async_get_parcel",
        new=AsyncMock(return_value=_SAMPLE),
    ):
        await hass.services.async_call(
            DOMAIN,
            "untrack_parcel",
            {CONF_TRACKING_CODE: "EXAMPLE999999"},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert entry.options[CONF_PARCELS] == []


async def test_untrack_unknown_code_is_noop(hass):
    entry = await _setup(
        hass, parcels=[{CONF_TRACKING_CODE: "EXAMPLE999999"}]
    )
    with patch(
        "custom_components.aramex.api.AramexApiClient.async_get_parcel",
        new=AsyncMock(return_value=_SAMPLE),
    ):
        await hass.services.async_call(
            DOMAIN,
            "untrack_parcel",
            {CONF_TRACKING_CODE: "EXAMPLE000000"},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert len(entry.options[CONF_PARCELS]) == 1


async def _setup_country(hass, country: str) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=country,
        options={CONF_COUNTRY: country, CONF_PARCELS: []},
    )
    entry.add_to_hass(hass)
    with patch(
        "custom_components.aramex.api.AramexApiClient.async_get_parcel",
        new=AsyncMock(return_value=_SAMPLE),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def test_resolve_entry_without_a_hub(hass):
    with pytest.raises(ServiceValidationError, match="not set up"):
        _resolve_entry(hass)


async def test_track_parcel_needs_a_country_with_several_hubs(hass):
    await _setup_country(hass, "AU")
    await _setup_country(hass, "NZ")
    with pytest.raises(ServiceValidationError, match="Multiple"):
        await hass.services.async_call(
            DOMAIN,
            "track_parcel",
            {CONF_TRACKING_CODE: "EXAMPLE999999"},
            blocking=True,
        )


async def test_track_parcel_routes_to_the_named_country(hass):
    au = await _setup_country(hass, "AU")
    nz = await _setup_country(hass, "NZ")
    with patch(
        "custom_components.aramex.api.AramexApiClient.async_get_parcel",
        new=AsyncMock(return_value=_SAMPLE),
    ):
        await hass.services.async_call(
            DOMAIN,
            "track_parcel",
            {CONF_TRACKING_CODE: "EXAMPLE999999", CONF_COUNTRY: "nz"},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert nz.options[CONF_PARCELS] == [{CONF_TRACKING_CODE: "EXAMPLE999999"}]
    assert au.options[CONF_PARCELS] == []


async def test_track_parcel_rejects_an_unconfigured_country(hass):
    await _setup_country(hass, "AU")
    with pytest.raises(ServiceValidationError, match="No Aramex hub configured for US"):
        await hass.services.async_call(
            DOMAIN,
            "track_parcel",
            {CONF_TRACKING_CODE: "EXAMPLE999999", CONF_COUNTRY: "us"},
            blocking=True,
        )
