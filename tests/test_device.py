"""Tests for the country-specific Aramex device."""
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.aramex.const import CONF_COUNTRY, DOMAIN
from custom_components.aramex.device import build_device_info


def test_device_uses_new_zealand_configuration_url():
    entry = MockConfigEntry(domain=DOMAIN, options={CONF_COUNTRY: "NZ"})
    assert build_device_info(entry)["configuration_url"] == "https://www.aramex.co.nz/"
