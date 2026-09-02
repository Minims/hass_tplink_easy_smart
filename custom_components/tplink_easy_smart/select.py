"""Configuration selects for TP-Link Easy Smart switches."""

from dataclasses import dataclass, field
from typing import Final

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client.classes import PortSpeed, QosMode
from .helpers import (
    generate_entity_id,
    generate_entity_name,
    generate_entity_unique_id,
    get_coordinator,
)
from .update_coordinator import TpLinkDataUpdateCoordinator

ENTITY_DOMAIN: Final = "select"

_PORT_SPEED_OPTIONS: Final = {
    PortSpeed.AUTO: "Auto",
    PortSpeed.HALF_10M: "10 Mbps half duplex",
    PortSpeed.FULL_10M: "10 Mbps full duplex",
    PortSpeed.HALF_100M: "100 Mbps half duplex",
    PortSpeed.FULL_100M: "100 Mbps full duplex",
    PortSpeed.FULL_1000M: "1 Gbps full duplex",
}
_PORT_SPEED_VALUES: Final = {value: key for key, value in _PORT_SPEED_OPTIONS.items()}

_QOS_MODE_OPTIONS: Final = {
    QosMode.PORT_BASED: "Port based",
    QosMode.IEEE_8021P: "802.1p based",
    QosMode.DSCP_IEEE_8021P: "DSCP/802.1p based",
}
_QOS_MODE_VALUES: Final = {value: key for key, value in _QOS_MODE_OPTIONS.items()}

_QOS_PRIORITY_OPTIONS: Final = {
    1: "1 (Lowest)",
    2: "2 (Normal)",
    3: "3 (Medium)",
    4: "4 (Highest)",
}
_QOS_PRIORITY_VALUES: Final = {
    value: key for key, value in _QOS_PRIORITY_OPTIONS.items()
}


@dataclass
class TpLinkSelectEntityDescription(SelectEntityDescription):
    """Describe a TP-Link configuration select."""

    function_name: str | None = None
    function_uid: str | None = None
    device_name: str | None = None
    port_number: int | None = None
    name: str | None = field(init=False)

    def __post_init__(self) -> None:
        """Build the legacy entity name used by this integration."""
        self.name = generate_entity_name(self.function_name, self.device_name)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up configuration selects."""
    coordinator = get_coordinator(hass, config_entry)
    device_name = coordinator.get_switch_info().name
    entities: list[SelectEntity] = []

    for port_number in range(1, coordinator.ports_count + 1):
        entities.append(
            TpLinkPortSpeedSelect(
                coordinator,
                TpLinkSelectEntityDescription(
                    key=f"port_{port_number}_speed",
                    icon="mdi:speedometer",
                    entity_category=EntityCategory.CONFIG,
                    entity_registry_enabled_default=True,
                    options=list(_PORT_SPEED_OPTIONS.values()),
                    device_name=device_name,
                    port_number=port_number,
                    function_uid=f"port_{port_number}_speed",
                    function_name=f"Port {port_number} speed and duplex",
                ),
            )
        )

    if coordinator.qos_supported:
        entities.append(
            TpLinkQosModeSelect(
                coordinator,
                TpLinkSelectEntityDescription(
                    key="qos_mode",
                    icon="mdi:priority-high",
                    entity_category=EntityCategory.CONFIG,
                    options=list(_QOS_MODE_OPTIONS.values()),
                    device_name=device_name,
                    function_uid="qos_mode",
                    function_name="QoS mode",
                ),
            )
        )
        for port_number in range(1, coordinator.ports_count + 1):
            entities.append(
                TpLinkQosPrioritySelect(
                    coordinator,
                    TpLinkSelectEntityDescription(
                        key=f"port_{port_number}_qos_priority",
                        icon="mdi:format-list-numbered",
                        entity_category=EntityCategory.CONFIG,
                        entity_registry_enabled_default=True,
                        options=list(_QOS_PRIORITY_OPTIONS.values()),
                        device_name=device_name,
                        port_number=port_number,
                        function_uid=f"port_{port_number}_qos_priority",
                        function_name=f"Port {port_number} QoS priority",
                    ),
                )
            )

    async_add_entities(entities)


class TpLinkSelect(CoordinatorEntity[TpLinkDataUpdateCoordinator], SelectEntity):
    """Base class for TP-Link selects."""

    entity_description: TpLinkSelectEntityDescription

    def __init__(
        self,
        coordinator: TpLinkDataUpdateCoordinator,
        description: TpLinkSelectEntityDescription,
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = coordinator.get_device_info()
        self._attr_unique_id = generate_entity_unique_id(
            coordinator, description.function_uid
        )
        self.entity_id = generate_entity_id(
            coordinator, ENTITY_DOMAIN, description.function_name
        )

    @property
    def available(self) -> bool:
        """Return entity availability."""
        return self.coordinator.last_update_success and self.current_option is not None

    async def async_added_to_hass(self) -> None:
        """Populate the initial state."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()


class TpLinkPortSpeedSelect(TpLinkSelect):
    """Configure one port's speed and duplex."""

    async def async_select_option(self, option: str) -> None:
        """Select a speed and duplex mode."""
        info = self.coordinator.get_port_state(self.entity_description.port_number)
        if info is None:
            return
        await self.coordinator.set_port_state(
            info.number,
            info.enabled,
            _PORT_SPEED_VALUES[option],
            info.flow_control_config,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Read the configured port speed."""
        info = self.coordinator.get_port_state(self.entity_description.port_number)
        self._attr_current_option = (
            _PORT_SPEED_OPTIONS.get(info.speed_config) if info else None
        )
        super()._handle_coordinator_update()


class TpLinkQosModeSelect(TpLinkSelect):
    """Configure the global QoS classification mode."""

    async def async_select_option(self, option: str) -> None:
        """Select the QoS mode."""
        await self.coordinator.async_set_qos_mode(_QOS_MODE_VALUES[option])

    @callback
    def _handle_coordinator_update(self) -> None:
        """Read the current QoS mode."""
        info = self.coordinator.get_qos_state()
        self._attr_current_option = _QOS_MODE_OPTIONS.get(info.mode) if info else None
        super()._handle_coordinator_update()


class TpLinkQosPrioritySelect(TpLinkSelect):
    """Configure a port's priority in port-based QoS mode."""

    async def async_select_option(self, option: str) -> None:
        """Select the port priority."""
        await self.coordinator.async_set_qos_priority(
            self.entity_description.port_number, _QOS_PRIORITY_VALUES[option]
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Read the current port priority."""
        info = self.coordinator.get_qos_state()
        port_number = self.entity_description.port_number
        if info and port_number and len(info.priorities) >= port_number:
            self._attr_current_option = _QOS_PRIORITY_OPTIONS.get(
                info.priorities[port_number - 1]
            )
        else:
            self._attr_current_option = None
        super()._handle_coordinator_update()
