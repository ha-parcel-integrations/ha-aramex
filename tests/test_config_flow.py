"""Tests for the Aramex config and options flow."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aramex.config_flow import (
    normalize_tracking_code,
    valid_tracking_code,
)
from custom_components.aramex.const import (
    CONF_COUNTRY,
    CONF_DELIVERED_FILTER_AMOUNT,
    CONF_DELIVERED_FILTER_TYPE,
    CONF_INCLUDE_HISTORY,
    CONF_PARCELS,
    CONF_TRACKING_CODE,
    DOMAIN,
)


def test_normalize_tracking_code_only_trims_whitespace():
    assert normalize_tracking_code(" MP0085494934 ") == "MP0085494934"
    assert normalize_tracking_code("") == ""
    assert normalize_tracking_code(None) == ""


def test_valid_tracking_code_bounds():
    assert valid_tracking_code("MP0085494934")
    assert not valid_tracking_code("ABC")  # too short
    assert not valid_tracking_code("A" * 31)  # too long


async def test_user_flow_requires_country_and_creates_hub(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_COUNTRY: "nz"})
    assert result["type"] == "create_entry"
    assert result["title"] == "Aramex (NZ)"
    assert result["data"] == {}
    assert result["options"][CONF_COUNTRY] == "NZ"
    assert result["options"][CONF_PARCELS] == []


async def test_second_hub_for_same_country_rejected(hass):
    MockConfigEntry(domain=DOMAIN, unique_id="AU").add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_COUNTRY: "au"})
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_second_hub_for_other_country_is_allowed(hass):
    MockConfigEntry(domain=DOMAIN, unique_id="AU").add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_COUNTRY: "nz"}
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "Aramex (NZ)"


def _hub(parcels: list[dict]) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="AU",
        options={CONF_COUNTRY: "AU", CONF_PARCELS: parcels},
    )


def _settings_input(
    *,
    history=False,
    filter_type="days",
    amount=7,
) -> dict:
    """Build the settings-form submission."""
    return {
        CONF_DELIVERED_FILTER_TYPE: filter_type,
        CONF_DELIVERED_FILTER_AMOUNT: amount,
        CONF_INCLUDE_HISTORY: history,
    }


async def _open_options_step(hass, entry, step_id: str):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "menu"
    assert result["menu_options"] == ["parcels", "settings"]
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step_id}
    )


async def test_options_add_parcel(hass):
    entry = _hub([])
    entry.add_to_hass(hass)

    result = await _open_options_step(hass, entry, "parcels")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tracking_codes": ["MP0085494934"]}
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_PARCELS] == [{CONF_TRACKING_CODE: "MP0085494934"}]


async def test_options_adds_multiple_parcels(hass):
    entry = _hub([])
    entry.add_to_hass(hass)
    result = await _open_options_step(hass, entry, "parcels")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tracking_codes": ["MP0085494934", "MP0085494935"]}
    )
    assert result["data"][CONF_PARCELS] == [
        {CONF_TRACKING_CODE: "MP0085494934"},
        {CONF_TRACKING_CODE: "MP0085494935"},
    ]


async def test_options_rejects_non_alphanumeric_code(hass):
    entry = _hub([])
    entry.add_to_hass(hass)
    result = await _open_options_step(hass, entry, "parcels")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tracking_codes": ["example-123 456"]}
    )
    assert result["type"] == "form"
    assert result["errors"]["base"] == "invalid_tracking_code"


async def test_options_add_invalid_tracking_code(hass):
    entry = _hub([])
    entry.add_to_hass(hass)
    result = await _open_options_step(hass, entry, "parcels")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tracking_codes": ["abc"]}
    )
    assert result["errors"]["base"] == "invalid_tracking_code"


async def test_options_replaces_the_single_label(hass):
    entry = _hub([{CONF_TRACKING_CODE: "MP0085494934"}])
    entry.add_to_hass(hass)
    result = await _open_options_step(hass, entry, "parcels")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tracking_codes": ["MP0085494935"]}
    )
    assert result["data"][CONF_PARCELS] == [{CONF_TRACKING_CODE: "MP0085494935"}]


async def test_options_replaces_a_legacy_multi_label_list(hass):
    entry = _hub([{CONF_TRACKING_CODE: "EXAMPLE111111"}, {CONF_TRACKING_CODE: "EXAMPLE222222"}])
    entry.add_to_hass(hass)
    result = await _open_options_step(hass, entry, "parcels")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tracking_codes": ["EXAMPLE222222"]}
    )
    assert result["type"] == "create_entry"
    codes = {p[CONF_TRACKING_CODE] for p in result["data"][CONF_PARCELS]}
    assert codes == {"EXAMPLE222222"}


async def test_options_can_clear_the_tracked_code_list(hass):
    entry = _hub([{CONF_TRACKING_CODE: "EXAMPLE111111"}])
    entry.add_to_hass(hass)
    result = await _open_options_step(hass, entry, "parcels")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"tracking_codes": []}
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_PARCELS] == []


async def test_options_changes_history_and_delivered(hass):
    entry = _hub([])
    entry.add_to_hass(hass)
    result = await _open_options_step(hass, entry, "settings")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        _settings_input(
            history=True,
            filter_type="parcels",
            amount=5,
        ),
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_INCLUDE_HISTORY] is True
    assert result["data"][CONF_DELIVERED_FILTER_TYPE] == "parcels"
    assert result["data"][CONF_DELIVERED_FILTER_AMOUNT] == 5
