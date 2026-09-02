"""Cable-test buttons for TP-Link Easy Smart switches."""

from dataclasses import dataclass, field
from typing import Final

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .helpers import (
    generate_entity_id,
    generate_entity_name,
    generate_entity_unique_id,
    get_coordinator,
)
from .update_coordinator import TpLinkDataUpdateCoordinator

ENTITY_DOMAIN: Final = "button"


@dataclass
class TpLinkCableTestButtonDescription(ButtonEntityDescription):
    """Describe one port cable-test button."""

    function_name: str | None = None
    function_uid: str | None = None
    device_name: str | None = None
    port_number: int = 0
    name: str | None = field(init=False)

    def __post_init__(self) -> None:
        """Build the legacy entity name used by this integration."""
        self.name = generate_entity_name(self.function_name, self.device_name)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up cable-test buttons for every physical port."""
    coordinator = get_coordinator(hass, config_entry)
    device_name = coordinator.get_switch_info().name
    async_add_entities(
        TpLinkCableTestButton(
            coordinator,
            TpLinkCableTestButtonDescription(
                key=f"port_{port_number}_cable_test",
                icon="mdi:ethernet-cable",
                entity_category=EntityCategory.DIAGNOSTIC,
                entity_registry_enabled_default=True,
                device_name=device_name,
                port_number=port_number,
                function_uid=f"port_{port_number}_cable_test",
                function_name=f"Port {port_number} cable test",
            ),
        )
        for port_number in range(1, coordinator.ports_count + 1)
    )


class TpLinkCableTestButton(
    CoordinatorEntity[TpLinkDataUpdateCoordinator], ButtonEntity
):
    """Run a cable diagnostic on one physical port."""

    entity_description: TpLinkCableTestButtonDescription

    def __init__(
        self,
        coordinator: TpLinkDataUpdateCoordinator,
        description: TpLinkCableTestButtonDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_device_info = coordinator.get_device_info()
        self._attr_unique_id = generate_entity_unique_id(
            coordinator, description.function_uid
        )
        self.entity_id = generate_entity_id(
            coordinator, ENTITY_DOMAIN, description.function_name
        )

    async def async_press(self) -> None:
        """Run the test and refresh the cable diagnostic sensors."""
        await self.coordinator.async_run_cable_diagnostic(
            self.entity_description.port_number
        )
