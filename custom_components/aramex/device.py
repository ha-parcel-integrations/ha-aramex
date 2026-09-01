"""The device every entity of this integration belongs to.

One place, because sensors, the button and the calendar must all land on the
*same* device entry — and because the account-based variant only has to change
this file to name devices per account.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo

from .const import CONF_COUNTRY, DOMAIN

CONFIGURATION_URLS = {"AU": "https://www.aramex.com.au/", "NZ": "https://www.aramex.co.nz/"}

ATTRIBUTION = "Data provided by Aramex"


def build_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Return the DeviceInfo shared by every entity of this hub."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Aramex ({entry.options.get(CONF_COUNTRY, 'AU')})",
        manufacturer="Aramex",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=CONFIGURATION_URLS.get(entry.options.get(CONF_COUNTRY), CONFIGURATION_URLS["AU"]),
    )
