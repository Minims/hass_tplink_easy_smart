"""Integration-level tests against the current Home Assistant API."""

from typing import Any

import pytest
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tplink_easy_smart import async_migrate_entry
from custom_components.tplink_easy_smart.client.classes import (
    CableDiagnostic,
    CableStatus,
    IgmpSnoopingState,
    LagState,
    LoopPreventionState,
    MtuVlanState,
    PortSpeed,
    PortState,
    PortStatistics,
    PortTrafficRates,
    PortVlan,
    PortVlanState,
    QosMode,
    QosState,
    TpLinkSystemInfo,
    Vlan8021Q,
    Vlan8021QState,
    VlanPvidState,
)
from custom_components.tplink_easy_smart.client.tplink_api import DataFormatError
from custom_components.tplink_easy_smart.const import DATA_KEY_COORDINATOR, DOMAIN
from custom_components.tplink_easy_smart.services import ServiceNames
from custom_components.tplink_easy_smart.update_coordinator import (
    TpLinkDataUpdateCoordinator,
)


class FakeTpLinkApi:
    """Switch API fixture used by the Home Assistant setup test."""

    instance: "FakeTpLinkApi | None" = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        type(self).instance = self
        self.poe_limit: float | None = None
        self.igmp_setting: tuple[bool, bool] | None = None
        self.led_setting: bool | None = None
        self.reboot_calls = 0
        self.cable_test_ports: list[int] = []
        self.session = kwargs.get("session")

    @property
    def device_url(self) -> str:
        return "http://192.0.2.1:80"

    async def get_device_info(self) -> TpLinkSystemInfo:
        return TpLinkSystemInfo(
            name="TL-SG105E",
            mac="AA:BB:CC:DD:EE:FF",
            ip="192.0.2.1",
            netmask="255.255.255.0",
            gateway="192.0.2.254",
            firmware="1.0.0 Build 20250710 Rel.71066",
            hardware="TL-SG105E 5.0",
        )

    async def get_port_states(self) -> list[PortState]:
        return [
            PortState(
                number=1,
                enabled=True,
                flow_control_config=True,
                flow_control_actual=True,
                speed_config=PortSpeed.AUTO,
                speed_actual=PortSpeed.FULL_1000M,
            )
        ]

    async def get_port_statistics(self) -> list[PortStatistics]:
        return [
            PortStatistics(
                number=1,
                enabled=True,
                link_status=PortSpeed.FULL_1000M,
                tx_good_packets=100,
                tx_bad_packets=2,
                rx_good_packets=200,
                rx_bad_packets=3,
            )
        ]

    async def get_led_state(self) -> bool:
        return True if self.led_setting is None else self.led_setting

    async def get_lags(self) -> LagState:
        return LagState(
            max_groups=1,
            port_count=1,
            ports_per_group=1,
            groups={1: []},
        )

    async def get_mtu_vlan(self) -> MtuVlanState:
        return MtuVlanState(enabled=False, port_count=1, uplink_port=1)

    async def get_port_vlans(self) -> PortVlanState:
        return PortVlanState(
            enabled=False,
            port_count=1,
            vlans=[PortVlan(vlan_id=1, member_ports=[1])],
            trunk_groups=[0],
        )

    async def get_8021q_vlans(self) -> Vlan8021QState:
        return Vlan8021QState(
            enabled=False,
            port_count=1,
            max_vlans=32,
            vlans=[
                Vlan8021Q(
                    vlan_id=1,
                    name="Default",
                    tagged_ports=[],
                    untagged_ports=[1],
                )
            ],
            trunk_groups=[0],
        )

    async def get_pvids(self) -> VlanPvidState:
        return VlanPvidState(
            enabled=False,
            port_count=1,
            pvids=[1],
            vlan_ids=[1],
            member_masks=[1],
            trunk_groups=[0],
        )

    async def is_feature_available(self, _feature: str) -> bool:
        return False

    async def get_igmp_snooping(self) -> IgmpSnoopingState:
        return IgmpSnoopingState(enabled=True, report_suppression=False)

    async def get_loop_prevention(self) -> LoopPreventionState:
        return LoopPreventionState(enabled=True)

    async def get_cable_diagnostics(self) -> list[CableDiagnostic]:
        return [CableDiagnostic(number=1, status=CableStatus.NORMAL, length_m=12)]

    async def run_cable_diagnostic(self, port_number: int) -> list[CableDiagnostic]:
        self.cable_test_ports.append(port_number)
        return [CableDiagnostic(number=1, status=CableStatus.NORMAL, length_m=12)]

    async def get_qos(self) -> QosState:
        return QosState(
            mode=QosMode.PORT_BASED,
            priorities=[2],
            trunk_groups=[0],
        )

    async def set_port_state(
        self,
        _number: int,
        _enabled: bool,
        _speed_config: PortSpeed,
        _flow_control_config: bool,
    ) -> None:
        return None

    async def set_poe_limit(self, limit: float) -> None:
        self.poe_limit = limit

    async def set_igmp_snooping(self, enabled: bool, report_suppression: bool) -> None:
        self.igmp_setting = (enabled, report_suppression)

    async def set_led_state(self, enabled: bool) -> None:
        self.led_setting = enabled

    async def reboot(self) -> None:
        self.reboot_calls += 1

    async def disconnect(self) -> None:
        if self.session is not None and not self.session.closed:
            self.session.detach()


class InitialCableProbeFailureApi(FakeTpLinkApi):
    """Fail the startup probe but allow a user-triggered cable test."""

    async def get_cable_diagnostics(self) -> list[CableDiagnostic]:
        raise DataFormatError("Cable diagnostics are not initialized")


class InitialOptionalProbeFailureApi(FakeTpLinkApi):
    """Fail optional startup reads once, then recover on the next update."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.statistics_calls = 0
        self.igmp_calls = 0
        self.loop_prevention_calls = 0
        self.qos_calls = 0

    async def get_port_statistics(self) -> list[PortStatistics]:
        self.statistics_calls += 1
        if self.statistics_calls == 1:
            raise RuntimeError("temporary statistics failure")
        return await super().get_port_statistics()

    async def get_igmp_snooping(self) -> IgmpSnoopingState:
        self.igmp_calls += 1
        if self.igmp_calls == 1:
            raise RuntimeError("temporary IGMP failure")
        return await super().get_igmp_snooping()

    async def get_loop_prevention(self) -> LoopPreventionState:
        self.loop_prevention_calls += 1
        if self.loop_prevention_calls == 1:
            raise RuntimeError("temporary loop-prevention failure")
        return await super().get_loop_prevention()

    async def get_qos(self) -> QosState:
        self.qos_calls += 1
        if self.qos_calls == 1:
            raise RuntimeError("temporary QoS failure")
        return await super().get_qos()


class PortStateFailureApi(FakeTpLinkApi):
    """Fail the core port-state read."""

    async def get_port_states(self) -> list[PortState]:
        raise RuntimeError("temporary port-state failure")


async def test_migration_enables_new_defaults_on_every_port(
    hass: HomeAssistant,
) -> None:
    """Re-enable integration-disabled entities without overriding the user."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Switch",
        unique_id="aa:bb:cc:dd:ee:ff",
        data={},
        version=2,
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    integration_disabled = []

    entity_specs = [("switch", "igmp_report_suppression")]
    for port_number in range(1, 6):
        entity_specs.extend(
            (
                ("switch", f"port_{port_number}_flow_control"),
                ("select", f"port_{port_number}_speed"),
                ("select", f"port_{port_number}_qos_priority"),
                ("sensor", f"port_{port_number}_tx_estimated_mbps"),
                ("sensor", f"port_{port_number}_rx_estimated_mbps"),
                ("sensor", f"port_{port_number}_total_estimated_mbps"),
                ("sensor", f"port_{port_number}_cable_status"),
                ("sensor", f"port_{port_number}_cable_length"),
            )
        )
    for domain, function_uid in entity_specs:
        integration_disabled.append(
            registry.async_get_or_create(
                domain,
                DOMAIN,
                f"{entry.unique_id}_{function_uid}_{entry.unique_id}",
                config_entry=entry,
                disabled_by=er.RegistryEntryDisabler.INTEGRATION,
            )
        )

    user_disabled = registry.async_get_or_create(
        "select",
        DOMAIN,
        f"{entry.unique_id}_port_6_speed_{entry.unique_id}",
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    bad_packets = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.unique_id}_port_2_tx_bad_packets_{entry.unique_id}",
        config_entry=entry,
        disabled_by=er.RegistryEntryDisabler.INTEGRATION,
    )

    assert await async_migrate_entry(hass, entry)
    assert entry.version == 3
    assert all(
        registry.async_get(entity.entity_id).disabled_by is None
        for entity in integration_disabled
    )
    assert (
        registry.async_get(user_disabled.entity_id).disabled_by
        is er.RegistryEntryDisabler.USER
    )
    assert (
        registry.async_get(bad_packets.entity_id).disabled_by
        is er.RegistryEntryDisabler.INTEGRATION
    )


async def test_setup_entities_and_general_poe_service(
    hass: HomeAssistant, monkeypatch
) -> None:
    """Set up the integration, its entities, and dispatch its first service."""
    monkeypatch.setattr(
        "custom_components.tplink_easy_smart.update_coordinator.TpLinkApi",
        FakeTpLinkApi,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Switch",
        data={
            CONF_NAME: "Test Switch",
            CONF_HOST: "192.0.2.1",
            CONF_PORT: 80,
            CONF_SSL: False,
            CONF_VERIFY_SSL: False,
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
        },
        options={},
        version=2,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.test_switch_port_1_tx_good_packets").state == "100"
    assert hass.states.get("sensor.test_switch_port_1_rx_good_packets").state == "200"
    assert hass.states.get("binary_sensor.test_switch_port_1_state").state == "on"
    assert hass.states.get("switch.test_switch_port_1_enabled").state == "on"
    assert hass.states.get("switch.test_switch_port_1_flow_control").state == "on"
    assert hass.states.get("switch.test_switch_igmp_snooping").state == "on"
    assert hass.states.get("switch.test_switch_igmp_report_suppression").state == "off"
    assert hass.states.get("switch.test_switch_loop_prevention").state == "on"
    assert hass.states.get("switch.test_switch_leds").state == "on"
    assert hass.states.get("select.test_switch_port_1_speed_and_duplex").state == "Auto"
    assert hass.states.get("select.test_switch_qos_mode").state == "Port based"
    assert (
        hass.states.get("select.test_switch_port_1_qos_priority").state == "2 (Normal)"
    )
    assert hass.states.get("sensor.test_switch_port_1_tx_estimated_bandwidth")
    assert hass.states.get("sensor.test_switch_port_1_rx_estimated_bandwidth")
    assert hass.states.get("sensor.test_switch_port_1_estimated_bandwidth")
    assert hass.states.get("sensor.test_switch_port_1_cable_status").state == "normal"
    assert hass.states.get("sensor.test_switch_port_1_cable_length").state == "12"
    assert hass.states.get("button.test_switch_port_1_cable_test")
    assert hass.states.get("button.test_switch_reboot")
    assert hass.states.get("sensor.test_switch_lag_configuration").state == "0"
    assert (
        hass.states.get("sensor.test_switch_mtu_vlan_configuration").state == "disabled"
    )
    assert (
        hass.states.get("sensor.test_switch_port_vlan_configuration").state
        == "disabled"
    )
    assert (
        hass.states.get("sensor.test_switch_802_1q_vlan_configuration").state
        == "disabled"
    )
    assert hass.states.get("sensor.test_switch_802_1q_pvid_configuration").attributes[
        "port_pvids"
    ] == {"1": 1}

    device = dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, "AA:BB:CC:DD:EE:FF")}
    )
    assert device is not None
    assert (dr.CONNECTION_NETWORK_MAC, "aa:bb:cc:dd:ee:ff") in device.connections

    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_KEY_COORDINATOR]
    assert coordinator.config_entry is entry
    coordinator._port_traffic_rates[1] = PortTrafficRates(
        tx_packets_per_second=10,
        rx_packets_per_second=20,
        tx_estimated_mbps=0.12345678,
        rx_estimated_mbps=0.2,
    )
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    port_attributes = hass.states.get(
        "binary_sensor.test_switch_port_1_state"
    ).attributes
    assert port_attributes["tx_estimated_bandwidth_mbps"] == 0.123457
    assert port_attributes["rx_estimated_bandwidth_mbps"] == 0.2
    assert port_attributes["total_estimated_bandwidth_mbps"] == 0.323457

    async def fail_igmp_poll() -> IgmpSnoopingState:
        raise RuntimeError("temporary IGMP polling failure")

    monkeypatch.setattr(FakeTpLinkApi.instance, "get_igmp_snooping", fail_igmp_poll)
    await coordinator._update_igmp_state()
    assert coordinator.get_igmp_state() is None

    await hass.services.async_call(
        DOMAIN,
        ServiceNames.SET_GENERAL_POE_LIMIT,
        {"mac_address": "aa:bb:cc:dd:ee:ff", "power_limit": 50},
        blocking=True,
    )

    assert FakeTpLinkApi.instance is not None
    assert FakeTpLinkApi.instance.poe_limit == 50

    await hass.services.async_call(
        DOMAIN,
        ServiceNames.SET_IGMP_SNOOPING,
        {
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "enabled": False,
            "report_suppression": True,
        },
        blocking=True,
    )

    assert FakeTpLinkApi.instance.igmp_setting == (False, True)

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.test_switch_leds"},
        blocking=True,
    )
    assert FakeTpLinkApi.instance.led_setting is False

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.test_switch_reboot"},
        blocking=True,
    )
    assert FakeTpLinkApi.instance.reboot_calls == 1

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.test_switch_port_1_cable_test"},
        blocking=True,
    )
    assert FakeTpLinkApi.instance.cable_test_ports == [1]

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.entry_id not in hass.data[DOMAIN]
    assert not hass.services.has_service(DOMAIN, ServiceNames.SET_GENERAL_POE_LIMIT)


async def test_cable_button_exists_when_initial_probe_fails(
    hass: HomeAssistant, monkeypatch
) -> None:
    """Expose cable diagnostics so the first button press can initialize them."""
    monkeypatch.setattr(
        "custom_components.tplink_easy_smart.update_coordinator.TpLinkApi",
        InitialCableProbeFailureApi,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Switch",
        unique_id="aa:bb:cc:dd:ee:ff",
        data={
            CONF_NAME: "Test Switch",
            CONF_HOST: "192.0.2.1",
            CONF_PORT: 80,
            CONF_SSL: False,
            CONF_VERIFY_SSL: False,
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
        },
        version=3,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    button_id = "button.test_switch_port_1_cable_test"
    status_id = "sensor.test_switch_port_1_cable_status"
    length_id = "sensor.test_switch_port_1_cable_length"
    assert hass.states.get(button_id) is not None
    assert hass.states.get(status_id).state == "unavailable"
    assert hass.states.get(length_id).state == "unavailable"

    await hass.services.async_call(
        "button", "press", {"entity_id": button_id}, blocking=True
    )
    assert hass.states.get(status_id).state == "normal"
    assert hass.states.get(length_id).state == "12"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_optional_entities_recover_after_initial_probe_failure(
    hass: HomeAssistant, monkeypatch
) -> None:
    """Keep optional entities when the first read fails transiently."""
    monkeypatch.setattr(
        "custom_components.tplink_easy_smart.update_coordinator.TpLinkApi",
        InitialOptionalProbeFailureApi,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Switch",
        unique_id="aa:bb:cc:dd:ee:ff",
        data={
            CONF_NAME: "Test Switch",
            CONF_HOST: "192.0.2.1",
            CONF_PORT: 80,
            CONF_SSL: False,
            CONF_VERIFY_SSL: False,
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
        },
        version=3,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entity_ids = (
        "sensor.test_switch_port_1_tx_good_packets",
        "sensor.test_switch_port_1_tx_estimated_bandwidth",
        "switch.test_switch_igmp_snooping",
        "switch.test_switch_loop_prevention",
        "select.test_switch_qos_mode",
    )
    assert all(
        hass.states.get(entity_id).state == "unavailable" for entity_id in entity_ids
    )

    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_KEY_COORDINATOR]
    await coordinator._update_port_statistics()
    await coordinator._update_port_statistics()
    await coordinator._update_igmp_state()
    await coordinator._update_loop_prevention_state()
    await coordinator._update_qos_state()
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    assert hass.states.get(entity_ids[0]).state == "100"
    assert hass.states.get(entity_ids[1]).state == "0.0"
    assert hass.states.get(entity_ids[2]).state == "on"
    assert hass.states.get(entity_ids[3]).state == "on"
    assert hass.states.get(entity_ids[4]).state == "Port based"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_core_port_state_failure_fails_the_update(
    hass: HomeAssistant, monkeypatch
) -> None:
    """Do not complete setup without the port count needed by all platforms."""
    monkeypatch.setattr(
        "custom_components.tplink_easy_smart.update_coordinator.TpLinkApi",
        PortStateFailureApi,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Test Switch",
        unique_id="aa:bb:cc:dd:ee:ff",
        data={
            CONF_NAME: "Test Switch",
            CONF_HOST: "192.0.2.1",
            CONF_PORT: 80,
            CONF_SSL: False,
            CONF_VERIFY_SSL: False,
            CONF_USERNAME: "admin",
            CONF_PASSWORD: "secret",
        },
        version=3,
    )

    coordinator = TpLinkDataUpdateCoordinator(hass, entry)
    with pytest.raises(UpdateFailed, match="Can not get port states"):
        await coordinator.async_update()
    assert coordinator.ports_count == 0
    await coordinator.async_unload()
