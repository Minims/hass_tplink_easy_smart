"""Tests for the integration configuration and options flows."""

from typing import Any

import pytest
from homeassistant import config_entries
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tplink_easy_smart.client.classes import TpLinkSystemInfo
from custom_components.tplink_easy_smart.client.discovery import DiscoveredSwitch
from custom_components.tplink_easy_smart.config_flow import TpLinkControllerConfigFlow
from custom_components.tplink_easy_smart.const import (
    DOMAIN,
    OPT_ESTIMATED_PACKET_SIZE,
    OPT_POE_STATE_SWITCHES,
    OPT_PORT_STATE_SWITCHES,
)


@pytest.fixture(autouse=True)
def _disable_network_discovery(monkeypatch) -> None:
    """Keep existing config-flow tests independent from the local network."""

    async def no_switches(_flow) -> list[DiscoveredSwitch]:
        return []

    monkeypatch.setattr(
        TpLinkControllerConfigFlow,
        "_async_find_switches",
        no_switches,
    )


class FakeConfigApi:
    """API fixture used while validating configuration data."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.session = kwargs.get("session")

    @property
    def device_url(self) -> str:
        return "http://192.0.2.1:80"

    async def authenticate(self) -> None:
        return None

    async def get_device_info(self) -> TpLinkSystemInfo:
        return TpLinkSystemInfo(
            name="TL-SG105E",
            mac="AA-BB-CC-DD-EE-FF",
            ip="192.0.2.1",
        )

    async def disconnect(self) -> None:
        if self.session is not None and not self.session.closed:
            self.session.detach()

    async def get_port_states(self) -> list:
        return []

    async def get_port_statistics(self) -> list:
        return []

    async def is_feature_available(self, _feature: str) -> bool:
        return False


async def test_user_flow_prefills_a_discovered_switch(
    hass: HomeAssistant, monkeypatch
) -> None:
    """Select a discovered switch and verify its identity before setup."""

    async def discovered_switches(_flow) -> list[DiscoveredSwitch]:
        return [
            DiscoveredSwitch(
                host="192.0.2.1",
                mac="AA:BB:CC:DD:EE:FF",
                model="TL-SG105E",
                name="Office switch",
                firmware="1.0.0 Build 20250710 Rel.71066",
                hardware="TL-SG105E 5.0",
            )
        ]

    monkeypatch.setattr(
        TpLinkControllerConfigFlow,
        "_async_find_switches",
        discovered_switches,
    )
    monkeypatch.setattr(
        "custom_components.tplink_easy_smart.config_flow.TpLinkApi", FakeConfigApi
    )
    monkeypatch.setattr(
        "custom_components.tplink_easy_smart.update_coordinator.TpLinkApi",
        FakeConfigApi,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device": "aa:bb:cc:dd:ee:ff"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_credentials"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Office switch",
            CONF_HOST: "192.0.2.1",
            CONF_PORT: 80,
            CONF_SSL: False,
            CONF_VERIFY_SSL: False,
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == "192.0.2.1"
    assert result["result"].unique_id == "aa:bb:cc:dd:ee:ff"
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(result["result"].entry_id)


async def test_discovery_keeps_manual_configuration_available(
    hass: HomeAssistant, monkeypatch
) -> None:
    """Allow entering an address even when the UDP scan finds a switch."""

    async def discovered_switches(_flow) -> list[DiscoveredSwitch]:
        return [
            DiscoveredSwitch(
                host="192.0.2.1",
                mac="AA:BB:CC:DD:EE:FF",
                model="TL-SG105E",
                name="Office switch",
            )
        ]

    monkeypatch.setattr(
        TpLinkControllerConfigFlow,
        "_async_find_switches",
        discovered_switches,
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device": "__manual__"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_discovery_rejects_a_different_http_device(
    hass: HomeAssistant, monkeypatch
) -> None:
    """Do not trust an unauthenticated UDP identity during entry creation."""

    async def discovered_switches(_flow) -> list[DiscoveredSwitch]:
        return [
            DiscoveredSwitch(
                host="192.0.2.1",
                mac="11:22:33:44:55:66",
                model="TL-SG105E",
                name="Office switch",
            )
        ]

    monkeypatch.setattr(
        TpLinkControllerConfigFlow,
        "_async_find_switches",
        discovered_switches,
    )
    monkeypatch.setattr(
        "custom_components.tplink_easy_smart.config_flow.TpLinkApi", FakeConfigApi
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device": "11:22:33:44:55:66"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Office switch",
            CONF_HOST: "192.0.2.1",
            CONF_PORT: 80,
            CONF_SSL: False,
            CONF_VERIFY_SSL: False,
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_credentials"
    assert result["errors"] == {"base": "wrong_device"}


async def test_user_flow_creates_unique_entry(hass: HomeAssistant, monkeypatch) -> None:
    """Validate the switch and use its normalized MAC as entry unique ID."""
    monkeypatch.setattr(
        "custom_components.tplink_easy_smart.config_flow.TpLinkApi", FakeConfigApi
    )
    monkeypatch.setattr(
        "custom_components.tplink_easy_smart.update_coordinator.TpLinkApi",
        FakeConfigApi,
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Office switch",
            CONF_HOST: "192.0.2.1",
            CONF_PORT: 80,
            CONF_SSL: False,
            CONF_VERIFY_SSL: False,
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "aa:bb:cc:dd:ee:ff"
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(result["result"].entry_id)


async def test_options_flow_validates_polling_and_estimation_settings(
    hass: HomeAssistant,
) -> None:
    """Store all basic and feature options through the two-step flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Office switch",
        data={CONF_NAME: "Office switch", CONF_SCAN_INTERVAL: 30},
        version=2,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "basic_options"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 15, OPT_ESTIMATED_PACKET_SIZE: 512},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "features_select"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {OPT_PORT_STATE_SWITCHES: True, OPT_POE_STATE_SWITCHES: False},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_SCAN_INTERVAL: 15,
        OPT_ESTIMATED_PACKET_SIZE: 512,
        OPT_PORT_STATE_SWITCHES: True,
        OPT_POE_STATE_SWITCHES: False,
    }


async def test_reconfigure_updates_connection_settings(
    hass: HomeAssistant, monkeypatch
) -> None:
    """Validate the same device before replacing its connection data."""
    monkeypatch.setattr(
        "custom_components.tplink_easy_smart.config_flow.TpLinkApi", FakeConfigApi
    )
    monkeypatch.setattr(
        "custom_components.tplink_easy_smart.update_coordinator.TpLinkApi",
        FakeConfigApi,
    )
    scheduled_reloads = []
    monkeypatch.setattr(
        hass.config_entries,
        "async_schedule_reload",
        scheduled_reloads.append,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Office switch",
        unique_id="aa:bb:cc:dd:ee:ff",
        data={
            CONF_NAME: "Office switch",
            CONF_HOST: "192.0.2.1",
            CONF_PORT: 80,
            CONF_SSL: False,
            CONF_VERIFY_SSL: False,
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "old",
        },
        version=2,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_NAME: "Office switch renamed",
            CONF_HOST: "192.0.2.2",
            CONF_PORT: 8080,
            CONF_SSL: False,
            CONF_VERIFY_SSL: False,
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "new",
        },
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.title == "Office switch renamed"
    assert entry.data[CONF_HOST] == "192.0.2.2"
    assert entry.data[CONF_PASSWORD] == "new"
    assert scheduled_reloads == [entry.entry_id]
