"""Support for switches."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Final

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client.const import FEATURE_POE
from .const import (
    DEFAULT_POE_STATE_SWITCHES,
    DEFAULT_PORT_STATE_SWITCHES,
    OPT_POE_STATE_SWITCHES,
    OPT_PORT_STATE_SWITCHES,
)
from .helpers import (
    generate_entity_id,
    generate_entity_name,
    generate_entity_unique_id,
    get_coordinator,
)
from .update_coordinator import TpLinkDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


_FUNCTION_DISPLAYED_NAME_PORT_STATE_FORMAT: Final = "Port {} enabled"
_FUNCTION_UID_PORT_STATE_FORMAT: Final = "port_{}_enabled"

_FUNCTION_DISPLAYED_NAME_PORT_FLOW_CONTROL_FORMAT: Final = "Port {} flow control"
_FUNCTION_UID_PORT_FLOW_CONTROL_FORMAT: Final = "port_{}_flow_control"

_FUNCTION_DISPLAYED_NAME_PORT_POE_STATE_FORMAT: Final = "Port {} PoE enabled"
_FUNCTION_UID_PORT_POE_STATE_FORMAT: Final = "port_{}_poe_enabled"

_FUNCTION_DISPLAYED_NAME_IGMP: Final = "IGMP snooping"
_FUNCTION_UID_IGMP: Final = "igmp_snooping"
_FUNCTION_DISPLAYED_NAME_IGMP_SUPPRESSION: Final = "IGMP report suppression"
_FUNCTION_UID_IGMP_SUPPRESSION: Final = "igmp_report_suppression"
_FUNCTION_DISPLAYED_NAME_LOOP_PREVENTION: Final = "Loop prevention"
_FUNCTION_UID_LOOP_PREVENTION: Final = "loop_prevention"
_FUNCTION_DISPLAYED_NAME_LED: Final = "LEDs"
_FUNCTION_UID_LED: Final = "leds"

ENTITY_DOMAIN: Final = "switch"


# ---------------------------
#   TpLinkSwitchEntityDescription
# ---------------------------
@dataclass
class TpLinkSwitchEntityDescription(SwitchEntityDescription):
    """A class that describes switch."""

    function_name: str | None = None
    function_uid: str | None = None
    device_name: str | None = None
    name: str | None = field(init=False)

    def __post_init__(self):
        self.name = generate_entity_name(self.function_name, self.device_name)


# ---------------------------
#   TpLinkPortSwitchEntityDescription
# ---------------------------
@dataclass
class TpLinkPortSwitchEntityDescription(TpLinkSwitchEntityDescription):
    """A class that describes port switch."""

    port_number: int | None = None


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

    sensors = []

    if config_entry.options.get(OPT_PORT_STATE_SWITCHES, DEFAULT_PORT_STATE_SWITCHES):
        for port_number in range(1, coordinator.ports_count + 1):
            sensors.append(
                TpLinkPortStateSwitch(
                    coordinator,
                    TpLinkPortSwitchEntityDescription(
                        key=f"port_{port_number}_enabled",
                        icon="mdi:ethernet",
                        port_number=port_number,
                        device_name=coordinator.get_switch_info().name,
                        function_uid=_FUNCTION_UID_PORT_STATE_FORMAT.format(
                            port_number
                        ),
                        function_name=_FUNCTION_DISPLAYED_NAME_PORT_STATE_FORMAT.format(
                            port_number
                        ),
                    ),
                )
            )

    for port_number in range(1, coordinator.ports_count + 1):
        sensors.append(
            TpLinkPortFlowControlSwitch(
                coordinator,
                TpLinkPortSwitchEntityDescription(
                    key=f"port_{port_number}_flow_control",
                    icon="mdi:swap-horizontal",
                    entity_registry_enabled_default=True,
                    port_number=port_number,
                    device_name=coordinator.get_switch_info().name,
                    function_uid=_FUNCTION_UID_PORT_FLOW_CONTROL_FORMAT.format(
                        port_number
                    ),
                    function_name=_FUNCTION_DISPLAYED_NAME_PORT_FLOW_CONTROL_FORMAT.format(
                        port_number
                    ),
                ),
            )
        )

    if coordinator.led_supported:
        sensors.append(
            TpLinkLedSwitch(
                coordinator,
                TpLinkSwitchEntityDescription(
                    key="leds",
                    icon="mdi:led-on",
                    entity_registry_enabled_default=True,
                    device_name=coordinator.get_switch_info().name,
                    function_uid=_FUNCTION_UID_LED,
                    function_name=_FUNCTION_DISPLAYED_NAME_LED,
                ),
            )
        )

    if coordinator.igmp_supported:
        sensors.extend(
            (
                TpLinkIgmpSwitch(
                    coordinator,
                    TpLinkSwitchEntityDescription(
                        key="igmp_snooping",
                        icon="mdi:multicast",
                        device_name=coordinator.get_switch_info().name,
                        function_uid=_FUNCTION_UID_IGMP,
                        function_name=_FUNCTION_DISPLAYED_NAME_IGMP,
                    ),
                ),
                TpLinkIgmpSuppressionSwitch(
                    coordinator,
                    TpLinkSwitchEntityDescription(
                        key="igmp_report_suppression",
                        icon="mdi:message-off-outline",
                        entity_registry_enabled_default=True,
                        device_name=coordinator.get_switch_info().name,
                        function_uid=_FUNCTION_UID_IGMP_SUPPRESSION,
                        function_name=_FUNCTION_DISPLAYED_NAME_IGMP_SUPPRESSION,
                    ),
                ),
            )
        )

    if coordinator.loop_prevention_supported:
        sensors.append(
            TpLinkLoopPreventionSwitch(
                coordinator,
                TpLinkSwitchEntityDescription(
                    key="loop_prevention",
                    icon="mdi:shield-sync-outline",
                    device_name=coordinator.get_switch_info().name,
                    function_uid=_FUNCTION_UID_LOOP_PREVENTION,
                    function_name=_FUNCTION_DISPLAYED_NAME_LOOP_PREVENTION,
                ),
            )
        )

    if config_entry.options.get(
        OPT_POE_STATE_SWITCHES, DEFAULT_POE_STATE_SWITCHES
    ) and await coordinator.is_feature_available(FEATURE_POE):
        for port_number in range(1, coordinator.ports_poe_count + 1):
            sensors.append(
                TpLinkPortPoeStateSwitch(
                    coordinator,
                    TpLinkPortSwitchEntityDescription(
                        key=f"port_{port_number}_poe_enabled",
                        icon="mdi:lightning-bolt-outline",
                        port_number=port_number,
                        device_name=coordinator.get_switch_info().name,
                        function_uid=_FUNCTION_UID_PORT_POE_STATE_FORMAT.format(
                            port_number
                        ),
                        function_name=_FUNCTION_DISPLAYED_NAME_PORT_POE_STATE_FORMAT.format(
                            port_number
                        ),
                    ),
                )
            )

    async_add_entities(sensors)


# ---------------------------
#   TpLinkSwitch
# ---------------------------
class TpLinkSwitch(CoordinatorEntity[TpLinkDataUpdateCoordinator], SwitchEntity, ABC):
    entity_description: TpLinkSwitchEntityDescription

    def __init__(
        self,
        coordinator: TpLinkDataUpdateCoordinator,
        description: TpLinkSwitchEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)

        self.entity_description = description
        self._attr_device_info = coordinator.get_device_info()
        self._attr_unique_id = generate_entity_unique_id(
            coordinator, description.function_uid
        )
        self.entity_id = generate_entity_id(
            coordinator, ENTITY_DOMAIN, description.function_name
        )

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        self._handle_coordinator_update()
        _LOGGER.debug("Switch %s added to hass", self.entity_description.name)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success and self.is_on is not None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        super()._handle_coordinator_update()

    @abstractmethod
    async def _go_to_state(self, state: bool) -> None:
        raise NotImplementedError()

    async def __go_to_state(self, state: bool) -> None:
        """Perform transition to the specified state."""
        await self._go_to_state(state)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """async_turn_off."""
        await self.__go_to_state(False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """async_turn_on."""
        await self.__go_to_state(True)


# ---------------------------
#   TpLinkPortStateSwitch
# ---------------------------
class TpLinkPortStateSwitch(TpLinkSwitch):
    entity_description: TpLinkPortSwitchEntityDescription

    def __init__(
        self,
        coordinator: TpLinkDataUpdateCoordinator,
        description: TpLinkPortSwitchEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, description)
        self._attr_is_on = None
        self._attr_extra_state_attributes = {}
        self._port_number = description.port_number

    async def _go_to_state(self, state: bool) -> None:
        info = self._port_info
        if not info:
            _LOGGER.warning(
                "Can not change switch '%s' state: port info not found", self.name
            )
            return
        await self.coordinator.set_port_state(
            info.number, state, info.speed_config, info.flow_control_config
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self._port_info = self.coordinator.get_port_state(self._port_number)
        self._attr_is_on = self._port_info.enabled if self._port_info else None
        super()._handle_coordinator_update()


class TpLinkPortFlowControlSwitch(TpLinkSwitch):
    """Control IEEE 802.3x flow control on one port."""

    entity_description: TpLinkPortSwitchEntityDescription

    def __init__(
        self,
        coordinator: TpLinkDataUpdateCoordinator,
        description: TpLinkPortSwitchEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, description)
        self._attr_is_on = None
        self._port_number = description.port_number

    async def _go_to_state(self, state: bool) -> None:
        info = self.coordinator.get_port_state(self._port_number)
        if not info:
            return
        await self.coordinator.set_port_state(
            info.number, info.enabled, info.speed_config, state
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        info = self.coordinator.get_port_state(self._port_number)
        self._attr_is_on = info.flow_control_config if info else None
        super()._handle_coordinator_update()


class TpLinkIgmpSwitch(TpLinkSwitch):
    """Control global IGMP snooping."""

    async def _go_to_state(self, state: bool) -> None:
        info = self.coordinator.get_igmp_state()
        if info:
            await self.coordinator.async_set_igmp_snooping(
                state, info.report_suppression
            )

    @callback
    def _handle_coordinator_update(self) -> None:
        info = self.coordinator.get_igmp_state()
        self._attr_is_on = info.enabled if info else None
        super()._handle_coordinator_update()


class TpLinkIgmpSuppressionSwitch(TpLinkSwitch):
    """Control IGMP report-message suppression."""

    async def _go_to_state(self, state: bool) -> None:
        info = self.coordinator.get_igmp_state()
        if info:
            await self.coordinator.async_set_igmp_snooping(info.enabled, state)

    @callback
    def _handle_coordinator_update(self) -> None:
        info = self.coordinator.get_igmp_state()
        self._attr_is_on = info.report_suppression if info else None
        super()._handle_coordinator_update()


class TpLinkLoopPreventionSwitch(TpLinkSwitch):
    """Control the switch loop-prevention feature."""

    async def _go_to_state(self, state: bool) -> None:
        await self.coordinator.async_set_loop_prevention(state)

    @callback
    def _handle_coordinator_update(self) -> None:
        info = self.coordinator.get_loop_prevention_state()
        self._attr_is_on = info.enabled if info else None
        super()._handle_coordinator_update()


class TpLinkLedSwitch(TpLinkSwitch):
    """Control the switch's front-panel LEDs."""

    async def _go_to_state(self, state: bool) -> None:
        await self.coordinator.async_set_led_state(state)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._attr_is_on = self.coordinator.get_led_state()
        super()._handle_coordinator_update()


# ---------------------------
#   TpLinkPortPoeStateSwitch
# ---------------------------
class TpLinkPortPoeStateSwitch(TpLinkSwitch):
    entity_description: TpLinkPortSwitchEntityDescription

    def __init__(
        self,
        coordinator: TpLinkDataUpdateCoordinator,
        description: TpLinkPortSwitchEntityDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, description)
        self._attr_is_on = None
        self._attr_extra_state_attributes = {}
        self._port_number = description.port_number

    async def _go_to_state(self, state: bool) -> None:
        info = self._port_poe_info
        if not info:
            _LOGGER.warning(
                "Can not change switch '%s' PoE state: port info not found", self.name
            )
            return
        await self.coordinator.async_set_port_poe_settings(
            info.number, state, info.priority, info.power_limit
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        self._port_poe_info = self.coordinator.get_port_poe_state(self._port_number)
        self._attr_is_on = self._port_poe_info.enabled if self._port_poe_info else None
        super()._handle_coordinator_update()
