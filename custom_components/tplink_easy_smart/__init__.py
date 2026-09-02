"""TP-Link Easy Smart integration."""

import logging
import re
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation
from homeassistant.helpers import entity_registry as er

from .const import (
    DEFAULT_POE_STATE_SWITCHES,
    DOMAIN,
    OPT_POE_STATE_SWITCHES,
    PLATFORMS,
)
from .helpers import pop_coordinator, set_coordinator
from .services import async_setup_services, async_unload_services
from .update_coordinator import TpLinkDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

_NEW_DEFAULT_ENTITY_UNIQUE_ID: Final = re.compile(
    r"_(?:igmp_report_suppression|port_\d+_(?:cable_length|cable_status|"
    r"flow_control|qos_priority|rx_estimated_mbps|speed|total_estimated_mbps|"
    r"tx_estimated_mbps))_[^_]+$"
)

CONFIG_SCHEMA = config_validation.removed(DOMAIN, raise_if_present=False)


# ---------------------------
#   async_setup
# ---------------------------
async def async_setup(hass, _config):
    """Set up configured TP-Link Controller."""
    hass.data.setdefault(DOMAIN, {})
    return True


# ---------------------------
#   async_setup_entry
# ---------------------------
async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up TP-Link as config entry."""
    coordinator = TpLinkDataUpdateCoordinator(hass, config_entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await coordinator.async_unload()
        raise

    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))

    set_coordinator(hass, config_entry, coordinator)
    platforms_loaded = False
    services_loaded = False
    try:
        # Mark the forwarding attempt so partially loaded platforms are also
        # rolled back if one platform raises during setup.
        platforms_loaded = True
        await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
        await async_setup_services(hass, config_entry)
        services_loaded = True
    except Exception:
        if services_loaded:
            await async_unload_services(hass, config_entry)
        if platforms_loaded:
            await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS)
        pop_coordinator(hass, config_entry)
        await coordinator.async_unload()
        raise
    return True


# ---------------------------
#   update_listener
# ---------------------------
async def update_listener(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Update listener."""
    await hass.config_entries.async_reload(config_entry.entry_id)


# ---------------------------
#   async_unload_entry
# ---------------------------
async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )
    if unload_ok:
        coordinator = pop_coordinator(hass, config_entry)
        if coordinator and isinstance(coordinator, TpLinkDataUpdateCoordinator):
            await coordinator.async_unload()
        await async_unload_services(hass, config_entry)
    return unload_ok


async def async_migrate_entry(hass, config_entry: ConfigEntry):
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", config_entry.version)

    updated_data = {**config_entry.data}
    updated_options = {**config_entry.options}

    new_version = config_entry.version
    if new_version == 1:
        _LOGGER.debug("Migrating to version 2")
        updated_options[OPT_POE_STATE_SWITCHES] = DEFAULT_POE_STATE_SWITCHES
        new_version = 2

    if new_version == 2:
        _LOGGER.debug("Migrating to version 3")
        registry = er.async_get(hass)
        enabled_entities = 0
        for entity in er.async_entries_for_config_entry(
            registry, config_entry.entry_id
        ):
            if (
                entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION
                and _NEW_DEFAULT_ENTITY_UNIQUE_ID.search(entity.unique_id)
            ):
                registry.async_update_entity(entity.entity_id, disabled_by=None)
                enabled_entities += 1
        _LOGGER.debug(
            "Enabled %s entities whose integration default changed", enabled_entities
        )
        new_version = 3

    hass.config_entries.async_update_entry(
        config_entry,
        data=updated_data,
        options=updated_options,
        version=new_version,
    )

    _LOGGER.info("Migration to version %s successful", new_version)

    return True
