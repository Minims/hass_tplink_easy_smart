"""Support for additional sensors."""

import logging
from dataclasses import dataclass, field
from typing import Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfDataRate, UnitOfLength, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client.const import FEATURE_POE
from .helpers import (
    generate_entity_id,
    generate_entity_name,
    generate_entity_unique_id,
    get_coordinator,
)
from .update_coordinator import TpLinkDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

_FUNCTION_DISPLAYED_NAME_NETWORK_INFO: Final = "Network info"
_FUNCTION_UID_NETWORK_INFO: Final = "network_info"

_FUNCTION_DISPLAYED_NAME_POE_INFO: Final = "PoE consumption"
_FUNCTION_UID_POE_INFO: Final = "poe_consumption"

_PORT_STATISTIC_TYPES: Final = (
    (
        "tx_good_packets",
        "TX good packets",
        "tx_good_packets",
        None,
        "packets",
        None,
        SensorStateClass.TOTAL_INCREASING,
        "mdi:upload-network",
        True,
    ),
    (
        "rx_good_packets",
        "RX good packets",
        "rx_good_packets",
        None,
        "packets",
        None,
        SensorStateClass.TOTAL_INCREASING,
        "mdi:download-network",
        True,
    ),
    (
        "tx_bad_packets",
        "TX bad packets",
        "tx_bad_packets",
        None,
        "packets",
        None,
        SensorStateClass.TOTAL_INCREASING,
        "mdi:upload-network-outline",
        False,
    ),
    (
        "rx_bad_packets",
        "RX bad packets",
        "rx_bad_packets",
        None,
        "packets",
        None,
        SensorStateClass.TOTAL_INCREASING,
        "mdi:download-network-outline",
        False,
    ),
    (
        "tx_estimated_mbps",
        "TX estimated bandwidth",
        None,
        "tx_estimated_mbps",
        UnitOfDataRate.MEGABITS_PER_SECOND,
        SensorDeviceClass.DATA_RATE,
        SensorStateClass.MEASUREMENT,
        "mdi:upload-network",
        True,
    ),
    (
        "total_estimated_mbps",
        "estimated bandwidth",
        None,
        "total_estimated_mbps",
        UnitOfDataRate.MEGABITS_PER_SECOND,
        SensorDeviceClass.DATA_RATE,
        SensorStateClass.MEASUREMENT,
        "mdi:swap-horizontal",
        True,
    ),
    (
        "rx_estimated_mbps",
        "RX estimated bandwidth",
        None,
        "rx_estimated_mbps",
        UnitOfDataRate.MEGABITS_PER_SECOND,
        SensorDeviceClass.DATA_RATE,
        SensorStateClass.MEASUREMENT,
        "mdi:download-network",
        True,
    ),
)

ENTITY_DOMAIN: Final = "sensor"


# ---------------------------
#   TpLinkSensorEntityDescription
# ---------------------------
@dataclass
class TpLinkSensorEntityDescription(SensorEntityDescription):
    """A class that describes sensor entities."""

    function_name: str | None = None
    function_uid: str | None = None
    device_name: str | None = None
    name: str | None = field(init=False)

    def __post_init__(self):
        self.name = generate_entity_name(self.function_name, self.device_name)


@dataclass
class TpLinkPortStatisticsSensorEntityDescription(TpLinkSensorEntityDescription):
    """Describe one raw or derived per-port statistic."""

    port_number: int = 0
    statistics_attribute: str | None = None
    rates_attribute: str | None = None


@dataclass
class TpLinkCableSensorEntityDescription(TpLinkSensorEntityDescription):
    """Describe one cable diagnostic sensor."""

    port_number: int = 0
    value_kind: str = "status"


@dataclass
class TpLinkConfigurationSensorEntityDescription(TpLinkSensorEntityDescription):
    """Describe a switch configuration summary sensor."""

    configuration_kind: str = ""


# ---------------------------
#   async_setup_entry
# ---------------------------
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for TP-Link component."""
    coordinator: TpLinkDataUpdateCoordinator = get_coordinator(hass, config_entry)

    sensors = [
        TpLinkNetworkInfoSensor(
            coordinator,
            TpLinkSensorEntityDescription(
                key="network_info",
                icon="mdi:network-pos",
                device_name=coordinator.get_switch_info().name,
                function_uid=_FUNCTION_UID_NETWORK_INFO,
                function_name=_FUNCTION_DISPLAYED_NAME_NETWORK_INFO,
            ),
        ),
    ]

    if await coordinator.is_feature_available(FEATURE_POE):
        sensors.append(
            TpLinkPoeInfoSensor(
                coordinator,
                TpLinkSensorEntityDescription(
                    key="poe_consumption",
                    icon="mdi:lightning-bolt",
                    device_class=SensorDeviceClass.POWER,
                    native_unit_of_measurement=UnitOfPower.WATT,
                    state_class=SensorStateClass.MEASUREMENT,
                    device_name=coordinator.get_switch_info().name,
                    function_uid=_FUNCTION_UID_POE_INFO,
                    function_name=_FUNCTION_DISPLAYED_NAME_POE_INFO,
                ),
            )
        )

    configuration_sensors = (
        (
            coordinator.lag_supported,
            "lag_configuration",
            "LAG configuration",
            "mdi:link-variant",
            "lag",
        ),
        (
            coordinator.mtu_vlan_supported,
            "mtu_vlan_configuration",
            "MTU VLAN configuration",
            "mdi:lan",
            "mtu_vlan",
        ),
        (
            coordinator.port_vlan_supported,
            "port_vlan_configuration",
            "Port VLAN configuration",
            "mdi:lan-connect",
            "port_vlan",
        ),
        (
            coordinator.vlan_8021q_supported,
            "8021q_vlan_configuration",
            "802.1Q VLAN configuration",
            "mdi:tag-multiple",
            "8021q_vlan",
        ),
        (
            coordinator.pvid_supported,
            "pvid_configuration",
            "802.1Q PVID configuration",
            "mdi:tag-arrow-down",
            "pvid",
        ),
    )
    for supported, key, name, icon, kind in configuration_sensors:
        if supported:
            sensors.append(
                TpLinkConfigurationSensor(
                    coordinator,
                    TpLinkConfigurationSensorEntityDescription(
                        key=key,
                        icon=icon,
                        entity_category=EntityCategory.DIAGNOSTIC,
                        entity_registry_enabled_default=True,
                        device_name=coordinator.get_switch_info().name,
                        function_uid=key,
                        function_name=name,
                        configuration_kind=kind,
                    ),
                )
            )

    if coordinator.port_statistics_supported:
        for port_number in range(1, coordinator.ports_count + 1):
            for (
                metric_key,
                metric_name,
                statistics_attribute,
                rates_attribute,
                unit,
                device_class,
                state_class,
                icon,
                enabled_default,
            ) in _PORT_STATISTIC_TYPES:
                sensors.append(
                    TpLinkPortStatisticsSensor(
                        coordinator,
                        TpLinkPortStatisticsSensorEntityDescription(
                            key=f"port_{port_number}_{metric_key}",
                            icon=icon,
                            device_class=device_class,
                            native_unit_of_measurement=unit,
                            state_class=state_class,
                            entity_category=EntityCategory.DIAGNOSTIC,
                            entity_registry_enabled_default=enabled_default,
                            device_name=coordinator.get_switch_info().name,
                            function_uid=f"port_{port_number}_{metric_key}",
                            function_name=f"Port {port_number} {metric_name}",
                            port_number=port_number,
                            statistics_attribute=statistics_attribute,
                            rates_attribute=rates_attribute,
                        ),
                    )
                )

    for port_number in range(1, coordinator.ports_count + 1):
        sensors.extend(
            (
                TpLinkCableDiagnosticSensor(
                    coordinator,
                    TpLinkCableSensorEntityDescription(
                        key=f"port_{port_number}_cable_status",
                        icon="mdi:ethernet-cable",
                        entity_category=EntityCategory.DIAGNOSTIC,
                        entity_registry_enabled_default=True,
                        device_name=coordinator.get_switch_info().name,
                        function_uid=f"port_{port_number}_cable_status",
                        function_name=f"Port {port_number} cable status",
                        port_number=port_number,
                        value_kind="status",
                    ),
                ),
                TpLinkCableDiagnosticSensor(
                    coordinator,
                    TpLinkCableSensorEntityDescription(
                        key=f"port_{port_number}_cable_length",
                        icon="mdi:tape-measure",
                        device_class=SensorDeviceClass.DISTANCE,
                        native_unit_of_measurement=UnitOfLength.METERS,
                        state_class=SensorStateClass.MEASUREMENT,
                        entity_category=EntityCategory.DIAGNOSTIC,
                        entity_registry_enabled_default=True,
                        device_name=coordinator.get_switch_info().name,
                        function_uid=f"port_{port_number}_cable_length",
                        function_name=f"Port {port_number} cable length",
                        port_number=port_number,
                        value_kind="length",
                    ),
                ),
            )
        )

    async_add_entities(sensors)


# ---------------------------
#   TpLinkSensor
# ---------------------------
class TpLinkSensor(CoordinatorEntity[TpLinkDataUpdateCoordinator], SensorEntity):
    entity_description: TpLinkSensorEntityDescription

    def __init__(
        self,
        coordinator: TpLinkDataUpdateCoordinator,
        description: TpLinkSensorEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = coordinator.get_device_info()
        self._attr_unique_id = generate_entity_unique_id(
            coordinator, description.function_uid
        )
        self._attr_available = False
        self.entity_id = generate_entity_id(
            coordinator, ENTITY_DOMAIN, description.function_name
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self._attr_available

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()
        _LOGGER.debug("%s added to hass", self.name)


# ---------------------------
#   TpLinkNetworkInfoSensor
# ---------------------------
class TpLinkNetworkInfoSensor(TpLinkSensor):
    entity_description: TpLinkSensorEntityDescription
    _attr_native_value: str | None = None

    def __init__(
        self,
        coordinator: TpLinkDataUpdateCoordinator,
        description: TpLinkSensorEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, description)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    @callback
    def _handle_coordinator_update(self) -> None:
        system_info = self.coordinator.get_switch_info()
        if system_info:
            self._attr_native_value = system_info.ip
            self._attr_extra_state_attributes["mac"] = system_info.mac
            self._attr_extra_state_attributes["gateway"] = system_info.gateway
            self._attr_extra_state_attributes["netmask"] = system_info.netmask
            self._attr_available = True
        else:
            self._attr_available = False
        super()._handle_coordinator_update()


# ---------------------------
#   TpLinkPoeInfoSensor
# ---------------------------
class TpLinkPoeInfoSensor(TpLinkSensor):
    entity_description: TpLinkSensorEntityDescription
    _attr_native_value: float | None = None

    def __init__(
        self,
        coordinator: TpLinkDataUpdateCoordinator,
        description: TpLinkSensorEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, description)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    @callback
    def _handle_coordinator_update(self) -> None:
        poe_state = self.coordinator.get_poe_state()
        if poe_state:
            self._attr_native_value = poe_state.power_consumption
            self._attr_extra_state_attributes["power_limit_w"] = poe_state.power_limit
            self._attr_extra_state_attributes["power_remain_w"] = poe_state.power_remain
            self._attr_available = True
        else:
            self._attr_available = False
        super()._handle_coordinator_update()


class TpLinkPortStatisticsSensor(TpLinkSensor):
    """Represent one per-port counter or calculated traffic rate."""

    entity_description: TpLinkPortStatisticsSensorEntityDescription

    def __init__(
        self,
        coordinator: TpLinkDataUpdateCoordinator,
        description: TpLinkPortStatisticsSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description)
        self._port_number = description.port_number
        if description.rates_attribute:
            self._attr_suggested_display_precision = 3

    @callback
    def _handle_coordinator_update(self) -> None:
        description = self.entity_description
        statistics = self.coordinator.get_port_statistics(self._port_number)
        rates = self.coordinator.get_port_traffic_rates(self._port_number)

        if description.statistics_attribute and statistics is not None:
            self._attr_native_value = getattr(
                statistics, description.statistics_attribute
            )
            self._attr_available = True
        elif description.rates_attribute and rates is not None:
            self._attr_native_value = round(
                getattr(rates, description.rates_attribute), 6
            )
            self._attr_available = True
        else:
            self._attr_native_value = None
            self._attr_available = False

        super()._handle_coordinator_update()


class TpLinkConfigurationSensor(TpLinkSensor):
    """Summarize one switch configuration page."""

    entity_description: TpLinkConfigurationSensorEntityDescription

    @callback
    def _handle_coordinator_update(self) -> None:
        """Publish configuration state and structured attributes."""
        kind = self.entity_description.configuration_kind
        self._attr_extra_state_attributes = {}

        if kind == "lag":
            state = self.coordinator.get_lag_state()
            if state is not None:
                groups = [
                    {"group_id": group_id, "ports": ports}
                    for group_id, ports in state.groups.items()
                    if ports
                ]
                self._attr_native_value = len(groups)
                self._attr_extra_state_attributes = {
                    "port_count": state.port_count,
                    "max_groups": state.max_groups,
                    "ports_per_group": state.ports_per_group,
                    "groups": groups,
                }
        elif kind == "mtu_vlan":
            state = self.coordinator.get_mtu_vlan_state()
            if state is not None:
                self._attr_native_value = "enabled" if state.enabled else "disabled"
                self._attr_extra_state_attributes = {
                    "port_count": state.port_count,
                    "uplink_port": state.uplink_port,
                }
        elif kind == "port_vlan":
            state = self.coordinator.get_port_vlan_state()
            if state is not None:
                self._attr_native_value = "enabled" if state.enabled else "disabled"
                self._attr_extra_state_attributes = {
                    "port_count": state.port_count,
                    "vlans": [
                        {
                            "vlan_id": vlan.vlan_id,
                            "member_ports": vlan.member_ports,
                        }
                        for vlan in state.vlans
                    ],
                }
        elif kind == "8021q_vlan":
            state = self.coordinator.get_vlan_8021q_state()
            if state is not None:
                self._attr_native_value = "enabled" if state.enabled else "disabled"
                self._attr_extra_state_attributes = {
                    "port_count": state.port_count,
                    "max_vlans": state.max_vlans,
                    "vlans": [
                        {
                            "vlan_id": vlan.vlan_id,
                            "name": vlan.name,
                            "tagged_ports": vlan.tagged_ports,
                            "untagged_ports": vlan.untagged_ports,
                        }
                        for vlan in state.vlans
                    ],
                }
        elif kind == "pvid":
            state = self.coordinator.get_pvid_state()
            if state is not None:
                self._attr_native_value = "enabled" if state.enabled else "disabled"
                self._attr_extra_state_attributes = {
                    "port_count": state.port_count,
                    "port_pvids": {
                        str(port): pvid for port, pvid in enumerate(state.pvids, 1)
                    },
                }
        else:
            state = None

        self._attr_available = state is not None
        if state is None:
            self._attr_native_value = None
        super()._handle_coordinator_update()


class TpLinkCableDiagnosticSensor(TpLinkSensor):
    """Represent one cached cable diagnostic value."""

    entity_description: TpLinkCableSensorEntityDescription

    @callback
    def _handle_coordinator_update(self) -> None:
        """Read the latest cable diagnostic result."""
        info = self.coordinator.get_cable_diagnostic(
            self.entity_description.port_number
        )
        if info is None:
            self._attr_native_value = None
            self._attr_available = False
        elif self.entity_description.value_kind == "length":
            self._attr_native_value = info.length_m
            self._attr_available = info.length_m is not None
        else:
            self._attr_native_value = info.status.name.lower().replace("_", " ")
            self._attr_available = True
        super()._handle_coordinator_update()
