"""Support for services."""

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceNotFound
from homeassistant.helpers.service import verify_domain_control

from .client.classes import PoePowerLimit, PoePriority, QosMode
from .const import DATA_KEY_COORDINATOR, DATA_KEY_SERVICES, DOMAIN
from .update_coordinator import TpLinkDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

_FIELD_MAC_ADDRESS: Final = "mac_address"
_FIELD_POWER_LIMIT: Final = "power_limit"
_FIELD_PORT_NUMBER: Final = "port_number"
_FIELD_ENABLED: Final = "enabled"
_FIELD_PRIORITY: Final = "priority"
_FIELD_MANUAL_POWER_LIMIT: Final = "manual_power_limit"
_FIELD_REPORT_SUPPRESSION: Final = "report_suppression"
_FIELD_DESTINATION_PORT: Final = "destination_port"
_FIELD_INGRESS_PORTS: Final = "ingress_ports"
_FIELD_EGRESS_PORTS: Final = "egress_ports"
_FIELD_GROUP_ID: Final = "group_id"
_FIELD_PORTS: Final = "ports"
_FIELD_UPLINK_PORT: Final = "uplink_port"
_FIELD_VLAN_ID: Final = "vlan_id"
_FIELD_MEMBER_PORTS: Final = "member_ports"
_FIELD_NAME: Final = "name"
_FIELD_TAGGED_PORTS: Final = "tagged_ports"
_FIELD_UNTAGGED_PORTS: Final = "untagged_ports"
_FIELD_MODE: Final = "mode"
_FIELD_INGRESS_KBPS: Final = "ingress_kbps"
_FIELD_EGRESS_KBPS: Final = "egress_kbps"
_FIELD_RATE_KBPS: Final = "rate_kbps"
_FIELD_UNKNOWN_UNICAST: Final = "unknown_unicast"
_FIELD_MULTICAST: Final = "multicast"
_FIELD_BROADCAST: Final = "broadcast"

_CV_MAC_ADDR: Final = cv.matches_regex("^([A-Fa-f0-9]{2}\\:){5}[A-Fa-f0-9]{2}$")

_POE_PRIORITY_MAP: dict[str, PoePriority] = {
    "High": PoePriority.HIGH,
    "Middle": PoePriority.MIDDLE,
    "Low": PoePriority.LOW,
}

_POE_POWER_LIMIT_MAP: dict[str, PoePowerLimit | None] = {
    "Auto": PoePowerLimit.AUTO,
    "Class 1": PoePowerLimit.CLASS_1,
    "Class 2": PoePowerLimit.CLASS_2,
    "Class 3": PoePowerLimit.CLASS_3,
    "Class 4": PoePowerLimit.CLASS_4,
    "Manual": None,
}

_QOS_MODE_MAP: dict[str, QosMode] = {
    "Port based": QosMode.PORT_BASED,
    "802.1p based": QosMode.IEEE_8021P,
    "DSCP/802.1p based": QosMode.DSCP_IEEE_8021P,
}

_CV_PORT: Final = vol.All(vol.Coerce(int), vol.Range(min=1))
_CV_PORTS: Final = vol.All(cv.ensure_list, [_CV_PORT])
_CV_VLAN_ID: Final = vol.All(vol.Coerce(int), vol.Range(min=1, max=4094))
_CV_PORT_VLAN_ID: Final = vol.All(vol.Coerce(int), vol.Range(min=2, max=4094))
_CV_DELETABLE_VLAN_ID: Final = vol.All(vol.Coerce(int), vol.Range(min=2, max=4094))
_CV_VLAN_NAME: Final = vol.All(
    str,
    vol.Length(max=10),
    vol.Match(r"^[A-Za-z0-9_-]*$"),
)


# ---------------------------
#   ServiceNames
# ---------------------------
class ServiceNames(StrEnum):
    SET_GENERAL_POE_LIMIT = "set_general_poe_limit"
    SET_PORT_POE_SETTINGS = "set_port_poe_settings"
    SET_IGMP_SNOOPING = "set_igmp_snooping"
    SET_LOOP_PREVENTION = "set_loop_prevention"
    RUN_CABLE_DIAGNOSTIC = "run_cable_diagnostic"
    SET_PORT_MIRROR = "set_port_mirror"
    SET_LAG = "set_lag"
    DELETE_LAG = "delete_lag"
    SET_MTU_VLAN = "set_mtu_vlan"
    SET_PORT_VLAN_MODE = "set_port_vlan_mode"
    UPSERT_PORT_VLAN = "upsert_port_vlan"
    DELETE_PORT_VLAN = "delete_port_vlan"
    SET_8021Q_VLAN_MODE = "set_8021q_vlan_mode"
    UPSERT_8021Q_VLAN = "upsert_8021q_vlan"
    DELETE_8021Q_VLAN = "delete_8021q_vlan"
    SET_PVID = "set_pvid"
    SET_QOS_MODE = "set_qos_mode"
    SET_QOS_PRIORITY = "set_qos_priority"
    SET_BANDWIDTH_CONTROL = "set_bandwidth_control"
    SET_STORM_CONTROL = "set_storm_control"


@dataclass
class ServiceDescription:
    name: str
    schema: vol.Schema


SERVICES = [
    ServiceDescription(
        name=ServiceNames.SET_GENERAL_POE_LIMIT,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_POWER_LIMIT): vol.All(
                    vol.Any(vol.Coerce(float), vol.Coerce(int)),
                    vol.Range(min=1, max=1000),
                ),
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.SET_PORT_POE_SETTINGS,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_PORT_NUMBER): vol.All(
                    vol.Coerce(int), vol.Range(min=1)
                ),
                vol.Required(_FIELD_ENABLED): cv.boolean,
                vol.Required(_FIELD_PRIORITY): vol.In(list(_POE_PRIORITY_MAP.keys())),
                vol.Required(_FIELD_POWER_LIMIT): vol.In(
                    list(_POE_POWER_LIMIT_MAP.keys())
                ),
                vol.Optional(_FIELD_MANUAL_POWER_LIMIT): vol.All(
                    vol.Coerce(float), vol.Range(min=0.1, max=30.0)
                ),
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.SET_IGMP_SNOOPING,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_ENABLED): cv.boolean,
                vol.Required(_FIELD_REPORT_SUPPRESSION): cv.boolean,
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.SET_LOOP_PREVENTION,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_ENABLED): cv.boolean,
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.RUN_CABLE_DIAGNOSTIC,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_PORT_NUMBER): _CV_PORT,
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.SET_PORT_MIRROR,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_ENABLED): cv.boolean,
                vol.Optional(_FIELD_DESTINATION_PORT): _CV_PORT,
                vol.Optional(_FIELD_INGRESS_PORTS, default=list): _CV_PORTS,
                vol.Optional(_FIELD_EGRESS_PORTS, default=list): _CV_PORTS,
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.SET_LAG,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_GROUP_ID): vol.All(
                    vol.Coerce(int), vol.Range(min=1)
                ),
                vol.Required(_FIELD_PORTS): _CV_PORTS,
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.DELETE_LAG,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_GROUP_ID): vol.All(
                    vol.Coerce(int), vol.Range(min=1)
                ),
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.SET_MTU_VLAN,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_ENABLED): cv.boolean,
                vol.Optional(_FIELD_UPLINK_PORT): _CV_PORT,
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.SET_PORT_VLAN_MODE,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_ENABLED): cv.boolean,
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.UPSERT_PORT_VLAN,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_VLAN_ID): _CV_PORT_VLAN_ID,
                vol.Required(_FIELD_MEMBER_PORTS): _CV_PORTS,
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.DELETE_PORT_VLAN,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_VLAN_ID): _CV_PORT_VLAN_ID,
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.SET_8021Q_VLAN_MODE,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_ENABLED): cv.boolean,
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.UPSERT_8021Q_VLAN,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_VLAN_ID): _CV_VLAN_ID,
                vol.Optional(_FIELD_NAME, default=""): _CV_VLAN_NAME,
                vol.Optional(_FIELD_TAGGED_PORTS, default=list): _CV_PORTS,
                vol.Optional(_FIELD_UNTAGGED_PORTS, default=list): _CV_PORTS,
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.DELETE_8021Q_VLAN,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_VLAN_ID): _CV_DELETABLE_VLAN_ID,
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.SET_PVID,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_PORTS): _CV_PORTS,
                vol.Required(_FIELD_VLAN_ID): _CV_VLAN_ID,
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.SET_QOS_MODE,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_MODE): vol.In(list(_QOS_MODE_MAP)),
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.SET_QOS_PRIORITY,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_PORT_NUMBER): _CV_PORT,
                vol.Required(_FIELD_PRIORITY): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=4)
                ),
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.SET_BANDWIDTH_CONTROL,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_PORT_NUMBER): _CV_PORT,
                vol.Required(_FIELD_INGRESS_KBPS): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=1_000_000)
                ),
                vol.Required(_FIELD_EGRESS_KBPS): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=1_000_000)
                ),
            }
        ),
    ),
    ServiceDescription(
        name=ServiceNames.SET_STORM_CONTROL,
        schema=vol.Schema(
            {
                vol.Required(_FIELD_MAC_ADDRESS): _CV_MAC_ADDR,
                vol.Required(_FIELD_PORT_NUMBER): _CV_PORT,
                vol.Required(_FIELD_ENABLED): cv.boolean,
                vol.Optional(_FIELD_RATE_KBPS, default=64): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=1_000_000)
                ),
                vol.Optional(_FIELD_UNKNOWN_UNICAST, default=False): cv.boolean,
                vol.Optional(_FIELD_MULTICAST, default=False): cv.boolean,
                vol.Optional(_FIELD_BROADCAST, default=False): cv.boolean,
            }
        ),
    ),
]


# ---------------------------
#   _find_coordinator
# ---------------------------
def _find_coordinator(
    hass: HomeAssistant, device_mac: str
) -> TpLinkDataUpdateCoordinator | None:
    _LOGGER.debug("Looking for coordinator with address '%s'", device_mac)
    normalized_mac = device_mac.replace("-", ":").upper()
    for key, item in hass.data[DOMAIN].items():
        if key == DATA_KEY_SERVICES:
            continue
        coordinator = item.get(DATA_KEY_COORDINATOR)
        if not coordinator or not isinstance(coordinator, TpLinkDataUpdateCoordinator):
            continue
        switch_info = coordinator.get_switch_info()
        if (
            switch_info
            and switch_info.mac
            and switch_info.mac.replace("-", ":").upper() == normalized_mac
        ):
            return coordinator
    return None


# ---------------------------
#   _async_set_general_poe_limit
# ---------------------------
async def _async_set_general_poe_limit(hass: HomeAssistant, service: ServiceCall):
    """Service to set general poe limit."""
    device_mac = service.data[_FIELD_MAC_ADDRESS].upper()
    coordinator = _find_coordinator(hass, device_mac)
    if not coordinator:
        raise HomeAssistantError(
            f"Can not find coordinator with mac address '{device_mac}'"
        )
    _LOGGER.debug(
        "Service '%s' called for mac '%s' with name %s",
        service.service,
        device_mac,
        coordinator.name,
    )
    try:
        limit = float(service.data[_FIELD_POWER_LIMIT])
        await coordinator.async_set_poe_limit(limit)
    except Exception as ex:
        raise HomeAssistantError(str(ex)) from ex


# ---------------------------
#   _async_set_port_poe_settings
# ---------------------------
async def _async_set_port_poe_settings(hass: HomeAssistant, service: ServiceCall):
    """Service to set port poe settings."""
    device_mac = service.data[_FIELD_MAC_ADDRESS].upper()

    coordinator = _find_coordinator(hass, device_mac)
    if not coordinator:
        raise HomeAssistantError(
            f"Can not find coordinator with mac address '{device_mac}'"
        )

    _LOGGER.debug(
        "Service '%s' called for mac '%s' with name %s",
        service.service,
        device_mac,
        coordinator.name,
    )

    try:
        port_number: int = service.data[_FIELD_PORT_NUMBER]
        enabled: bool = service.data[_FIELD_ENABLED]
        priority: PoePriority = _POE_PRIORITY_MAP[service.data[_FIELD_PRIORITY]]
        power_limit = _POE_POWER_LIMIT_MAP[service.data[_FIELD_POWER_LIMIT]]
        if power_limit is None:
            if _FIELD_MANUAL_POWER_LIMIT not in service.data:
                raise HomeAssistantError(
                    "manual_power_limit is required when power_limit is Manual"
                )
            power_limit = float(service.data[_FIELD_MANUAL_POWER_LIMIT])

        await coordinator.async_set_port_poe_settings(
            port_number, enabled, priority, power_limit
        )
    except Exception as ex:
        if isinstance(ex, HomeAssistantError):
            raise
        raise HomeAssistantError(str(ex)) from ex


_CONFIGURATION_SERVICE_NAMES: Final = {
    ServiceNames.SET_IGMP_SNOOPING,
    ServiceNames.SET_LOOP_PREVENTION,
    ServiceNames.RUN_CABLE_DIAGNOSTIC,
    ServiceNames.SET_PORT_MIRROR,
    ServiceNames.SET_LAG,
    ServiceNames.DELETE_LAG,
    ServiceNames.SET_MTU_VLAN,
    ServiceNames.SET_PORT_VLAN_MODE,
    ServiceNames.UPSERT_PORT_VLAN,
    ServiceNames.DELETE_PORT_VLAN,
    ServiceNames.SET_8021Q_VLAN_MODE,
    ServiceNames.UPSERT_8021Q_VLAN,
    ServiceNames.DELETE_8021Q_VLAN,
    ServiceNames.SET_PVID,
    ServiceNames.SET_QOS_MODE,
    ServiceNames.SET_QOS_PRIORITY,
    ServiceNames.SET_BANDWIDTH_CONTROL,
    ServiceNames.SET_STORM_CONTROL,
}


async def _async_run_configuration_service(
    hass: HomeAssistant, service: ServiceCall
) -> None:
    """Dispatch a validated non-PoE configuration service."""
    device_mac = service.data[_FIELD_MAC_ADDRESS].upper()
    coordinator = _find_coordinator(hass, device_mac)
    if coordinator is None:
        raise HomeAssistantError(
            f"Can not find coordinator with mac address '{device_mac}'"
        )

    data = service.data
    try:
        if service.service == ServiceNames.SET_IGMP_SNOOPING:
            await coordinator.async_set_igmp_snooping(
                data[_FIELD_ENABLED], data[_FIELD_REPORT_SUPPRESSION]
            )
        elif service.service == ServiceNames.SET_LOOP_PREVENTION:
            await coordinator.async_set_loop_prevention(data[_FIELD_ENABLED])
        elif service.service == ServiceNames.RUN_CABLE_DIAGNOSTIC:
            await coordinator.async_run_cable_diagnostic(data[_FIELD_PORT_NUMBER])
        elif service.service == ServiceNames.SET_PORT_MIRROR:
            await coordinator.async_set_port_mirror(
                data[_FIELD_ENABLED],
                data.get(_FIELD_DESTINATION_PORT),
                data[_FIELD_INGRESS_PORTS],
                data[_FIELD_EGRESS_PORTS],
            )
        elif service.service == ServiceNames.SET_LAG:
            await coordinator.async_set_lag(data[_FIELD_GROUP_ID], data[_FIELD_PORTS])
        elif service.service == ServiceNames.DELETE_LAG:
            await coordinator.async_delete_lag(data[_FIELD_GROUP_ID])
        elif service.service == ServiceNames.SET_MTU_VLAN:
            await coordinator.async_set_mtu_vlan(
                data[_FIELD_ENABLED], data.get(_FIELD_UPLINK_PORT)
            )
        elif service.service == ServiceNames.SET_PORT_VLAN_MODE:
            await coordinator.async_set_port_vlan_enabled(data[_FIELD_ENABLED])
        elif service.service == ServiceNames.UPSERT_PORT_VLAN:
            await coordinator.async_upsert_port_vlan(
                data[_FIELD_VLAN_ID], data[_FIELD_MEMBER_PORTS]
            )
        elif service.service == ServiceNames.DELETE_PORT_VLAN:
            await coordinator.async_delete_port_vlan(data[_FIELD_VLAN_ID])
        elif service.service == ServiceNames.SET_8021Q_VLAN_MODE:
            await coordinator.async_set_8021q_vlan_enabled(data[_FIELD_ENABLED])
        elif service.service == ServiceNames.UPSERT_8021Q_VLAN:
            await coordinator.async_upsert_8021q_vlan(
                data[_FIELD_VLAN_ID],
                data[_FIELD_NAME],
                data[_FIELD_TAGGED_PORTS],
                data[_FIELD_UNTAGGED_PORTS],
            )
        elif service.service == ServiceNames.DELETE_8021Q_VLAN:
            await coordinator.async_delete_8021q_vlan(data[_FIELD_VLAN_ID])
        elif service.service == ServiceNames.SET_PVID:
            await coordinator.async_set_pvid(data[_FIELD_PORTS], data[_FIELD_VLAN_ID])
        elif service.service == ServiceNames.SET_QOS_MODE:
            await coordinator.async_set_qos_mode(_QOS_MODE_MAP[data[_FIELD_MODE]])
        elif service.service == ServiceNames.SET_QOS_PRIORITY:
            await coordinator.async_set_qos_priority(
                data[_FIELD_PORT_NUMBER], data[_FIELD_PRIORITY]
            )
        elif service.service == ServiceNames.SET_BANDWIDTH_CONTROL:
            await coordinator.async_set_bandwidth_control(
                data[_FIELD_PORT_NUMBER],
                data[_FIELD_INGRESS_KBPS],
                data[_FIELD_EGRESS_KBPS],
            )
        elif service.service == ServiceNames.SET_STORM_CONTROL:
            await coordinator.async_set_storm_control(
                data[_FIELD_PORT_NUMBER],
                data[_FIELD_ENABLED],
                data[_FIELD_RATE_KBPS],
                data[_FIELD_UNKNOWN_UNICAST],
                data[_FIELD_MULTICAST],
                data[_FIELD_BROADCAST],
            )
        else:
            raise ServiceNotFound(DOMAIN, service.service)
    except Exception as ex:
        if isinstance(ex, (HomeAssistantError, ServiceNotFound)):
            raise
        raise HomeAssistantError(str(ex)) from ex


# ---------------------------
#   _change_instances_count
# ---------------------------
def _change_instances_count(hass: HomeAssistant, delta: int) -> int:
    current_count = hass.data.setdefault(DOMAIN, {}).setdefault(DATA_KEY_SERVICES, 0)
    result = max(0, current_count + delta)
    hass.data[DOMAIN][DATA_KEY_SERVICES] = result
    return result


async def async_setup_services(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Set up the TP-Link Easy Smart services."""
    active_instances = _change_instances_count(hass, 1)
    if active_instances > 1:
        _LOGGER.debug(
            "%s active instances has already been registered, skipping",
            active_instances - 1,
        )
        return

    @verify_domain_control(DOMAIN)
    async def async_call_service(service: ServiceCall) -> None:
        service_name = service.service

        if service_name == ServiceNames.SET_GENERAL_POE_LIMIT:
            await _async_set_general_poe_limit(hass, service)
        elif service_name == ServiceNames.SET_PORT_POE_SETTINGS:
            await _async_set_port_poe_settings(hass, service)
        elif service_name in _CONFIGURATION_SERVICE_NAMES:
            await _async_run_configuration_service(hass, service)
        else:
            raise ServiceNotFound(DOMAIN, service_name)

    registered_services = []
    try:
        for item in SERVICES:
            hass.services.async_register(
                domain=DOMAIN,
                service=item.name,
                service_func=async_call_service,
                schema=item.schema,
            )
            registered_services.append(item)
    except Exception:
        for item in registered_services:
            hass.services.async_remove(domain=DOMAIN, service=item.name)
        _change_instances_count(hass, -1)
        raise


async def async_unload_services(hass: HomeAssistant, config_entry: ConfigEntry):
    """Unload services."""
    active_instances = _change_instances_count(hass, -1)
    if active_instances > 0:
        _LOGGER.debug("%s active instances remaining, skipping", active_instances)
        return

    hass.data[DOMAIN].pop(DATA_KEY_SERVICES, None)
    for service in SERVICES:
        hass.services.async_remove(domain=DOMAIN, service=service.name)
