"""Update coordinator for TP-Link."""

import logging
from datetime import timedelta
from time import monotonic

import aiohttp
from homeassistant.config_entries import ConfigEntry
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
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .client.classes import (
    CableDiagnostic,
    IgmpSnoopingState,
    LoopPreventionState,
    PoePowerLimit,
    PoePriority,
    PortStatistics,
    PortTrafficRates,
    QosMode,
    QosState,
    TpLinkSystemInfo,
)
from .client.const import FEATURE_POE
from .client.coreapi import ApiCallError
from .client.statistics import PortStatisticsRateCalculator
from .client.tplink_api import (
    DataFormatError,
    PoeState,
    PortPoeState,
    PortSpeed,
    PortState,
    TpLinkApi,
)
from .const import (
    ATTR_MANUFACTURER,
    DEFAULT_ESTIMATED_PACKET_SIZE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    OPT_ESTIMATED_PACKET_SIZE,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------
#   TpLinkDataUpdateCoordinator
# ---------------------------
class TpLinkDataUpdateCoordinator(DataUpdateCoordinator[None]):
    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize."""
        session = async_create_clientsession(
            hass,
            verify_ssl=config_entry.data[CONF_VERIFY_SSL],
            auto_cleanup=False,
            cookie_jar=aiohttp.CookieJar(unsafe=True),
        )

        self._api: TpLinkApi = TpLinkApi(
            host=config_entry.data[CONF_HOST],
            port=config_entry.data[CONF_PORT],
            use_ssl=config_entry.data[CONF_SSL],
            user=config_entry.data[CONF_USERNAME],
            password=config_entry.data[CONF_PASSWORD],
            verify_ssl=config_entry.data[CONF_VERIFY_SSL],
            session=session,
        )
        self._switch_info: TpLinkSystemInfo | None = None
        self._port_states: list[PortState] = []
        self._port_statistics: list[PortStatistics] = []
        self._port_traffic_rates: dict[int, PortTrafficRates] = {}
        self._port_statistics_supported: bool | None = None
        self._port_poe_states: list[PortPoeState] = []
        self._poe_state: PoeState | None = None
        self._igmp_state: IgmpSnoopingState | None = None
        self._igmp_supported: bool | None = None
        self._loop_prevention_state: LoopPreventionState | None = None
        self._loop_prevention_supported: bool | None = None
        self._cable_diagnostics: list[CableDiagnostic] = []
        self._cable_diagnostics_supported: bool | None = None
        self._qos_state: QosState | None = None
        self._qos_supported: bool | None = None

        estimated_packet_size = config_entry.options.get(
            OPT_ESTIMATED_PACKET_SIZE, DEFAULT_ESTIMATED_PACKET_SIZE
        )
        self._statistics_rate_calculator = PortStatisticsRateCalculator(
            estimated_packet_size
        )

        update_interval = config_entry.options.get(
            CONF_SCAN_INTERVAL,
            config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=config_entry.data[CONF_NAME],
            update_method=self.async_update,
            update_interval=timedelta(seconds=update_interval),
        )

    @property
    def unique_id(self) -> str:
        """Return the system descriptor."""
        entry = self.config_entry

        if entry.unique_id:
            return entry.unique_id

        return entry.entry_id

    @property
    def ports_count(self) -> int:
        """Return ports count of the device."""
        return len(self._port_states)

    @property
    def ports_poe_count(self) -> int:
        """Return PoE ports count of the device."""
        return len(self._port_poe_states)

    @property
    def port_statistics_count(self) -> int:
        """Return the number of ports exposing packet counters."""
        return len(self._port_statistics)

    def get_port_state(self, number: int) -> PortState | None:
        """Return the specified port state."""
        if number > self.ports_count or number < 1:
            return None
        return self._port_states[number - 1]

    def get_port_poe_state(self, number: int) -> PortPoeState | None:
        """Return the specified port PoE state."""
        if number > self.ports_poe_count or number < 1:
            return None
        return self._port_poe_states[number - 1]

    def get_port_statistics(self, number: int) -> PortStatistics | None:
        """Return packet counters for a port."""
        if number > self.port_statistics_count or number < 1:
            return None
        return self._port_statistics[number - 1]

    def get_port_traffic_rates(self, number: int) -> PortTrafficRates | None:
        """Return calculated traffic rates for a port."""
        return self._port_traffic_rates.get(number)

    def get_switch_info(self) -> TpLinkSystemInfo | None:
        """Return the information of the switch."""
        return self._switch_info

    def get_poe_state(self) -> PoeState | None:
        """Return the switch PoE state."""
        return self._poe_state

    @property
    def igmp_supported(self) -> bool:
        """Return whether the switch exposed IGMP settings."""
        return self._igmp_supported is True

    @property
    def loop_prevention_supported(self) -> bool:
        """Return whether the switch exposed loop prevention."""
        return self._loop_prevention_supported is True

    @property
    def qos_supported(self) -> bool:
        """Return whether the switch exposed QoS settings."""
        return self._qos_supported is True

    def get_igmp_state(self) -> IgmpSnoopingState | None:
        """Return current IGMP settings."""
        return self._igmp_state

    def get_loop_prevention_state(self) -> LoopPreventionState | None:
        """Return current loop-prevention settings."""
        return self._loop_prevention_state

    def get_cable_diagnostic(self, number: int) -> CableDiagnostic | None:
        """Return cached cable diagnostics for one port."""
        if number < 1 or number > len(self._cable_diagnostics):
            return None
        return self._cable_diagnostics[number - 1]

    def get_qos_state(self) -> QosState | None:
        """Return current QoS settings."""
        return self._qos_state

    async def _safe_disconnect(self, api: TpLinkApi) -> None:
        """Disconnect from API."""
        try:
            await api.disconnect()
        except Exception as ex:
            _LOGGER.warning("Can not schedule disconnect: %s", str(ex))

    async def is_feature_available(self, feature: str) -> bool:
        """Return true if specified feature is known and available."""
        return await self._api.is_feature_available(feature)

    async def async_update(self) -> None:
        """Asynchronous update of all data."""
        _LOGGER.debug("Update started")
        await self._update_switch_info()
        await self._update_port_states()
        await self._update_port_statistics()
        await self._update_igmp_state()
        await self._update_loop_prevention_state()
        await self._update_cable_diagnostics()
        await self._update_qos_state()
        await self._update_poe_state()
        await self._update_port_poe_states()
        _LOGGER.debug("Update completed")

    async def async_unload(self) -> None:
        """Unload the coordinator and disconnect from API."""
        await self._safe_disconnect(self._api)

    async def _update_switch_info(self):
        """Update the switch info."""
        self._switch_info = await self._api.get_device_info()

    async def _update_port_states(self):
        """Update port states."""
        try:
            self._port_states = await self._api.get_port_states()
        except Exception as ex:
            _LOGGER.warning("Can not get port states: %s", repr(ex))
            self._port_states = []

    async def _update_port_statistics(self) -> None:
        """Update port packet counters and derived rates."""
        if self._port_statistics_supported is False:
            return

        try:
            statistics = await self._api.get_port_statistics()
        except Exception as ex:
            if (
                isinstance(ex, ApiCallError)
                and ex.code == 404
                and self._port_statistics_supported is None
            ):
                _LOGGER.info("Port statistics are not supported by this switch")
                self._port_statistics_supported = False
            else:
                _LOGGER.warning("Can not get port statistics: %s", repr(ex))
            self._port_statistics = []
            self._port_traffic_rates = {}
            return

        self._port_statistics_supported = True
        self._port_statistics = statistics
        self._port_traffic_rates = self._statistics_rate_calculator.update(
            statistics, monotonic()
        )

    async def _update_poe_state(self):
        """Update the switch PoE state."""

        if not await self.is_feature_available(FEATURE_POE):
            return

        try:
            self._poe_state = await self._api.get_poe_state()
        except Exception as ex:
            _LOGGER.warning("Can not get poe state: %s", repr(ex))
            self._poe_state = None

    @staticmethod
    def _is_unsupported_error(ex: Exception) -> bool:
        """Return true for an optional API surface not exposed by a device."""
        return isinstance(ex, (AttributeError, DataFormatError)) or (
            isinstance(ex, ApiCallError) and ex.code == 404
        )

    async def _update_igmp_state(self) -> None:
        """Update optional IGMP settings."""
        if self._igmp_supported is False:
            return
        try:
            self._igmp_state = await self._api.get_igmp_snooping()
        except Exception as ex:
            self._igmp_state = None
            if self._is_unsupported_error(ex):
                self._igmp_supported = False
            else:
                _LOGGER.warning("Can not get IGMP settings: %r", ex)
            return
        self._igmp_supported = True

    async def _update_loop_prevention_state(self) -> None:
        """Update optional loop-prevention settings."""
        if self._loop_prevention_supported is False:
            return
        try:
            self._loop_prevention_state = await self._api.get_loop_prevention()
        except Exception as ex:
            self._loop_prevention_state = None
            if self._is_unsupported_error(ex):
                self._loop_prevention_supported = False
            else:
                _LOGGER.warning("Can not get loop-prevention settings: %r", ex)
            return
        self._loop_prevention_supported = True

    async def _update_cable_diagnostics(self) -> None:
        """Update optional cached cable diagnostics."""
        if self._cable_diagnostics_supported is False:
            return
        try:
            self._cable_diagnostics = await self._api.get_cable_diagnostics()
        except Exception as ex:
            self._cable_diagnostics = []
            if self._is_unsupported_error(ex):
                self._cable_diagnostics_supported = False
            else:
                _LOGGER.warning("Can not get cable diagnostics: %r", ex)
            return
        self._cable_diagnostics_supported = True

    async def _update_qos_state(self) -> None:
        """Update optional QoS settings."""
        if self._qos_supported is False:
            return
        try:
            self._qos_state = await self._api.get_qos()
        except Exception as ex:
            self._qos_state = None
            if self._is_unsupported_error(ex):
                self._qos_supported = False
            else:
                _LOGGER.warning("Can not get QoS settings: %r", ex)
            return
        self._qos_supported = True

    async def _update_port_poe_states(self):
        """Update port PoE states."""

        if not await self.is_feature_available(FEATURE_POE):
            return

        try:
            self._port_poe_states = await self._api.get_port_poe_states()
        except Exception as ex:
            _LOGGER.warning("Can not get port poe states: %s", repr(ex))
            self._port_poe_states = []

    def get_device_info(self) -> DeviceInfo | None:
        """Return the DeviceInfo."""
        switch_info = self.get_switch_info()
        if not switch_info:
            _LOGGER.debug("Device info not found")
            return None

        result = DeviceInfo(
            configuration_url=self._api.device_url,
            connections={(dr.CONNECTION_NETWORK_MAC, switch_info.mac)},
            identifiers={(DOMAIN, switch_info.mac)},
            manufacturer=ATTR_MANUFACTURER,
            name=switch_info.name,
            model=switch_info.name,
            hw_version=switch_info.hardware,
            sw_version=switch_info.firmware,
        )
        return result

    async def set_port_state(
        self,
        number: int,
        enabled: bool,
        speed_config: PortSpeed,
        flow_control_config: bool,
    ) -> None:
        """Set the port state."""
        await self._api.set_port_state(
            number, enabled, speed_config, flow_control_config
        )

        index = number - 1
        if len(self._port_states) > index:
            state = self._port_states[index]
            state.enabled = enabled
            state.speed_config = speed_config
            state.flow_control_config = flow_control_config
            self.async_update_listeners()

    async def async_set_igmp_snooping(
        self, enabled: bool, report_suppression: bool
    ) -> None:
        """Set and refresh global IGMP snooping settings."""
        await self._api.set_igmp_snooping(enabled, report_suppression)
        self._igmp_state = IgmpSnoopingState(enabled, report_suppression)
        self.async_update_listeners()

    async def async_set_loop_prevention(self, enabled: bool) -> None:
        """Set and refresh global loop prevention."""
        await self._api.set_loop_prevention(enabled)
        self._loop_prevention_state = LoopPreventionState(enabled)
        self.async_update_listeners()

    async def async_run_cable_diagnostic(self, port_number: int) -> None:
        """Run one cable test and publish its latest results."""
        if self.get_port_state(port_number) is None:
            raise ValueError(f"Port number must be between 1 and {self.ports_count}")
        self._cable_diagnostics = await self._api.run_cable_diagnostic(port_number)
        self._cable_diagnostics_supported = True
        self.async_update_listeners()

    async def async_set_qos_mode(self, mode: QosMode) -> None:
        """Set QoS mode without immediately polling a restarting web server."""
        await self._api.set_qos_mode(mode)
        if self._qos_state is not None:
            self._qos_state.mode = mode
        self.async_update_listeners()

    async def async_set_qos_priority(self, port_number: int, priority: int) -> None:
        """Set and locally refresh one port or LAG's QoS priority."""
        await self._api.set_qos_priority(port_number, priority)
        state = self._qos_state
        if state is not None and 1 <= port_number <= len(state.priorities):
            group = state.trunk_groups[port_number - 1]
            for index, trunk_group in enumerate(state.trunk_groups):
                if index + 1 == port_number or (group > 0 and trunk_group == group):
                    state.priorities[index] = priority
        self.async_update_listeners()

    async def async_set_port_mirror(
        self,
        enabled: bool,
        destination_port: int | None,
        ingress_ports: list[int],
        egress_ports: list[int],
    ) -> None:
        """Configure port mirroring."""
        await self._api.set_port_mirror(
            enabled, destination_port, ingress_ports, egress_ports
        )

    async def async_set_lag(self, group_id: int, ports: list[int]) -> None:
        """Create or update a static LAG."""
        await self._api.set_lag(group_id, ports)

    async def async_delete_lag(self, group_id: int) -> None:
        """Delete a static LAG."""
        await self._api.delete_lag(group_id)

    async def async_set_mtu_vlan(self, enabled: bool, uplink_port: int | None) -> None:
        """Configure MTU VLAN mode."""
        await self._api.set_mtu_vlan(enabled, uplink_port)

    async def async_set_port_vlan_enabled(self, enabled: bool) -> None:
        """Enable or disable port-based VLAN mode."""
        await self._api.set_port_vlan_enabled(enabled)

    async def async_upsert_port_vlan(
        self, vlan_id: int, member_ports: list[int]
    ) -> None:
        """Create or update a port-based VLAN."""
        await self._api.upsert_port_vlan(vlan_id, member_ports)

    async def async_delete_port_vlan(self, vlan_id: int) -> None:
        """Delete a port-based VLAN."""
        await self._api.delete_port_vlan(vlan_id)

    async def async_set_8021q_vlan_enabled(self, enabled: bool) -> None:
        """Enable or disable IEEE 802.1Q VLAN mode."""
        await self._api.set_8021q_vlan_enabled(enabled)

    async def async_upsert_8021q_vlan(
        self,
        vlan_id: int,
        name: str,
        tagged_ports: list[int],
        untagged_ports: list[int],
    ) -> None:
        """Create or update an IEEE 802.1Q VLAN."""
        await self._api.upsert_8021q_vlan(vlan_id, name, tagged_ports, untagged_ports)

    async def async_delete_8021q_vlan(self, vlan_id: int) -> None:
        """Delete an IEEE 802.1Q VLAN."""
        await self._api.delete_8021q_vlan(vlan_id)

    async def async_set_pvid(self, ports: list[int], vlan_id: int) -> None:
        """Set the PVID of one or more ports."""
        await self._api.set_pvid(ports, vlan_id)

    async def async_set_bandwidth_control(
        self, port_number: int, ingress_kbps: int, egress_kbps: int
    ) -> None:
        """Set per-port bandwidth limits."""
        await self._api.set_bandwidth_control(port_number, ingress_kbps, egress_kbps)

    async def async_set_storm_control(
        self,
        port_number: int,
        enabled: bool,
        rate_kbps: int,
        unknown_unicast: bool,
        multicast: bool,
        broadcast: bool,
    ) -> None:
        """Set per-port storm control."""
        await self._api.set_storm_control(
            port_number,
            enabled,
            rate_kbps,
            unknown_unicast,
            multicast,
            broadcast,
        )

    async def async_set_poe_limit(self, limit: float) -> None:
        """Set general PoE limit."""
        await self._api.set_poe_limit(limit)
        await self._update_poe_state()
        self.async_update_listeners()

    async def async_set_port_poe_settings(
        self,
        port_number: int,
        enabled: bool,
        priority: PoePriority,
        power_limit: PoePowerLimit | float,
    ) -> None:
        """Set the port PoE settings."""
        await self._api.set_port_poe_settings(
            port_number, enabled, priority, power_limit
        )
        await self._update_port_poe_states()
        self.async_update_listeners()
