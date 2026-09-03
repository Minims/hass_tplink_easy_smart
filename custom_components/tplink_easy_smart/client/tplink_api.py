"""TP-Link Easy Smart web API."""

import asyncio
import logging
import re
from collections.abc import Iterable
from urllib.parse import urlencode

from aiohttp import ClientSession

from .classes import (
    BandwidthControl,
    CableDiagnostic,
    CableStatus,
    IgmpSnoopingState,
    LagState,
    LoopPreventionState,
    MtuVlanState,
    PoeClass,
    PoePowerLimit,
    PoePowerStatus,
    PoePriority,
    PoeState,
    PortMirrorState,
    PortPoeState,
    PortSpeed,
    PortState,
    PortStatistics,
    PortVlan,
    PortVlanState,
    QosMode,
    QosState,
    StormControl,
    TpLinkSystemInfo,
    Vlan8021Q,
    Vlan8021QState,
    VlanPvidState,
)
from .const import (
    FEATURE_POE,
    URL_8021Q_PVID_GET,
    URL_8021Q_PVID_SET,
    URL_8021Q_VLAN_GET,
    URL_8021Q_VLAN_SET,
    URL_BANDWIDTH_CONTROL_GET,
    URL_BANDWIDTH_CONTROL_SET,
    URL_CABLE_DIAGNOSTICS_GET,
    URL_CABLE_DIAGNOSTICS_SET,
    URL_DEVICE_INFO,
    URL_IGMP_SETTINGS_GET,
    URL_IGMP_SETTINGS_SET,
    URL_LAG_DELETE,
    URL_LAG_GET,
    URL_LAG_SET,
    URL_LED_SETTINGS_GET,
    URL_LED_SETTINGS_SET,
    URL_LOOP_PREVENTION_GET,
    URL_LOOP_PREVENTION_SET,
    URL_MIRROR_DESTINATION_SET,
    URL_MIRROR_SOURCE_SET,
    URL_MTU_VLAN_GET,
    URL_MTU_VLAN_SET,
    URL_POE_PORT_SETTINGS_SET,
    URL_POE_SETTINGS_GET,
    URL_POE_SETTINGS_SET,
    URL_PORT_MIRROR_GET,
    URL_PORT_SETTINGS_SET,
    URL_PORT_STATISTICS_GET,
    URL_PORT_VLAN_GET,
    URL_PORT_VLAN_SET,
    URL_PORTS_SETTINGS_GET,
    URL_QOS_GET,
    URL_QOS_MODE_SET,
    URL_QOS_PRIORITY_SET,
    URL_REBOOT,
    URL_STORM_CONTROL_GET,
    URL_STORM_CONTROL_SET,
)
from .coreapi import (
    APICALL_ERRCAT_DISCONNECTED,
    ApiCallError,
    TpLinkWebApi,
    VariableType,
)
from .utils import TpLinkFeaturesDetector

_LOGGER = logging.getLogger(__name__)

_POE_PRIORITIES_SET_MAP: dict[PoePriority, int] = {
    PoePriority.HIGH: 1,
    PoePriority.MIDDLE: 2,
    PoePriority.LOW: 3,
}

_POE_POWER_LIMITS_SET_MAP: dict[PoePowerLimit, tuple[int, str | None]] = {
    PoePowerLimit.AUTO: (1, None),
    PoePowerLimit.CLASS_1: (2, "(4w)"),
    PoePowerLimit.CLASS_2: (3, "(7w)"),
    PoePowerLimit.CLASS_3: (4, "(15.4w)"),
    PoePowerLimit.CLASS_4: (5, "(30w)"),
}


# ---------------------------
#   ActionError
# ---------------------------
class ActionError(Exception):
    def __init__(self, message: str):
        """Initialize."""
        super().__init__(message)
        self._message = message

    def __str__(self, *args, **kwargs) -> str:
        """Return str(self)."""
        return f"{self._message}"

    def __repr__(self) -> str:
        """Return repr(self)."""
        return self.__str__()


class DataFormatError(Exception):
    """Raised when the switch returns an incomplete or malformed data set."""


def _normalize_mac(value: str | None) -> str | None:
    """Normalize the common MAC formats returned by TP-Link firmware."""
    if not value:
        return None
    compact = re.sub(r"[^0-9A-Fa-f]", "", value)
    if len(compact) != 12:
        return None
    return ":".join(compact[index : index + 2] for index in range(0, 12, 2)).upper()


def _require_list(data: dict, key: str, minimum_length: int) -> list:
    """Return a list from a parsed page or raise a useful data error."""
    value = data.get(key)
    if not isinstance(value, list) or len(value) < minimum_length:
        raise DataFormatError(
            f"Invalid '{key}' array: expected at least {minimum_length} items"
        )
    return value


def _port_speed(value: object) -> PortSpeed:
    """Parse a firmware link-speed value without failing on new values."""
    try:
        return PortSpeed(int(value))
    except (TypeError, ValueError):
        return PortSpeed.UNKNOWN


def _int_list(value: object, name: str, minimum_length: int = 0) -> list[int]:
    """Convert a parsed firmware array to integers."""
    if not isinstance(value, list) or len(value) < minimum_length:
        raise DataFormatError(
            f"Invalid '{name}' array: expected at least {minimum_length} items"
        )
    try:
        return [int(item) for item in value]
    except (TypeError, ValueError) as ex:
        raise DataFormatError(f"Invalid integer value in '{name}'") from ex


def _decode_port_mask(mask: object, port_count: int) -> list[int]:
    """Decode a firmware port bitmask into one-based port numbers."""
    try:
        value = int(mask)
    except (TypeError, ValueError):
        value = 0
    return [
        number for number in range(1, port_count + 1) if value & (1 << (number - 1))
    ]


def _encode_port_mask(ports: Iterable[int]) -> int:
    """Encode one-based port numbers as a firmware port bitmask."""
    result = 0
    for port in ports:
        result |= 1 << (port - 1)
    return result


def _query(params: dict[str, object] | list[tuple[str, object]]) -> str:
    """Encode query parameters, preserving repeated keys."""
    return urlencode(params, doseq=True)


def _unique_ports(ports: Iterable[int]) -> list[int]:
    """Return sorted, unique integer port numbers."""
    try:
        return sorted({int(port) for port in ports})
    except (TypeError, ValueError) as ex:
        raise ActionError("Port numbers must be integers") from ex


def _validate_ports(
    ports: Iterable[int], port_count: int, *, allow_empty: bool = True
) -> list[int]:
    """Validate one-based port numbers against the device's port count."""
    result = _unique_ports(ports)
    if not allow_empty and not result:
        raise ActionError("At least one port must be selected")
    invalid = [port for port in result if port < 1 or port > port_count]
    if invalid:
        raise ActionError(
            f"Port numbers must be between 1 and {port_count}; invalid: {invalid}"
        )
    return result


def _expand_trunk_ports(ports: Iterable[int], trunk_groups: list[int]) -> list[int]:
    """Expand selected ports to every member of the same static LAG."""
    selected = set(_validate_ports(ports, len(trunk_groups)))
    selected_groups = {
        trunk_groups[port - 1] for port in selected if trunk_groups[port - 1] > 0
    }
    selected.update(
        index + 1
        for index, group in enumerate(trunk_groups)
        if group in selected_groups
    )
    return sorted(selected)


# ---------------------------
#   TpLinkApi
# ---------------------------
class TpLinkApi:
    def __init__(
        self,
        host: str,
        port: int,
        use_ssl: bool,
        user: str,
        password: str,
        verify_ssl: bool,
        session: ClientSession | None = None,
    ) -> None:
        """Initialize."""
        self._core_api = TpLinkWebApi(
            host, port, use_ssl, user, password, verify_ssl, session
        )
        self._is_features_updated = False
        self._features = TpLinkFeaturesDetector(self._core_api)
        _LOGGER.debug("New instance of TpLinkApi created")

    async def _ensure_features_updated(self):
        if not self._is_features_updated:
            _LOGGER.debug("Updating available features")
            await self._features.update()
            self._is_features_updated = True
            _LOGGER.debug("Available features updated")

    async def is_feature_available(self, feature: str) -> bool:
        """Return true if specified feature is known and available."""
        await self._ensure_features_updated()
        return self._features.is_available(feature)

    async def authenticate(self) -> None:
        """Perform authentication."""
        await self._core_api.authenticate()

    async def disconnect(self) -> None:
        """Disconnect from api."""
        await self._core_api.disconnect()

    async def _apply_get(self, path: str, query: str) -> str | None:
        """Apply a GET configuration request and handle firmware restarts."""
        try:
            return await self._core_api.get(path, query=query)
        except ApiCallError as ex:
            if ex.category != APICALL_ERRCAT_DISCONNECTED:
                raise
            # Several configuration CGIs restart the tiny embedded web server
            # after applying a write and close the socket before responding.
            self._core_api.invalidate_authentication()
            _LOGGER.debug("Switch closed the connection after applying %s", path)
            return None

    async def _apply_post(
        self,
        path: str,
        data: dict[str, object] | list[tuple[str, object]],
    ) -> str | None:
        """Apply a POST configuration request and handle firmware restarts."""
        try:
            return await self._core_api.post(path, data)
        except ApiCallError as ex:
            if ex.category != APICALL_ERRCAT_DISCONNECTED:
                raise
            self._core_api.invalidate_authentication()
            _LOGGER.debug("Switch closed the connection after applying %s", path)
            return None

    @property
    def device_url(self) -> str:
        """URL address of the device."""
        return self._core_api.device_url

    async def get_device_info(self) -> TpLinkSystemInfo:
        """Return the device information."""
        data = await self._core_api.get_variable(
            URL_DEVICE_INFO, "info_ds", VariableType.Dict
        )

        if not isinstance(data, dict):
            raise DataFormatError("Device information does not contain 'info_ds'")

        def get_value(key: str) -> str | None:
            array = data.get(key, [])
            if not isinstance(array, list) or len(array) != 1:
                return None
            return str(array[0])

        mac = _normalize_mac(get_value("macStr"))
        if mac is None:
            raise DataFormatError("Device information contains an invalid MAC address")

        return TpLinkSystemInfo(
            name=get_value("descriStr") or "TP-Link Easy Smart",
            mac=mac,
            ip=get_value("ipStr"),
            netmask=get_value("netmaskStr"),
            gateway=get_value("gatewayStr"),
            firmware=get_value("firmwareStr"),
            hardware=get_value("hardwareStr"),
        )

    async def get_led_state(self) -> bool:
        """Return the global front-panel LED state."""
        state = await self._core_api.get_variable(
            URL_LED_SETTINGS_GET, "led", VariableType.Int
        )
        if not isinstance(state, int):
            raise DataFormatError("LED settings do not contain 'led'")
        return bool(state)

    async def set_led_state(self, enabled: bool) -> None:
        """Enable or disable the front-panel LEDs after checking support."""
        await self.get_led_state()
        await self._apply_get(
            URL_LED_SETTINGS_SET,
            _query({"rd_led": int(enabled), "led_cfg": "Apply"}),
        )

    async def reboot(self) -> None:
        """Reboot the switch without changing its saved configuration."""
        await self._apply_post(
            URL_REBOOT,
            {"reboot_op": "reboot", "save_op": "false"},
        )
        self._core_api.invalidate_authentication()

    async def get_port_states(self) -> list[PortState]:
        """Return the port states."""
        data = await self._core_api.get_variables(
            URL_PORTS_SETTINGS_GET,
            [
                ("all_info", VariableType.Dict),
                ("max_port_num", VariableType.Int),
            ],
        )

        result: list[PortState] = []

        all_info = data.get("all_info")
        if not isinstance(all_info, dict):
            raise DataFormatError("Port settings do not contain 'all_info'")

        max_port_num = data.get("max_port_num")
        if not isinstance(max_port_num, int) or max_port_num < 1:
            raise DataFormatError("Port settings contain an invalid port count")

        enabled_flags = _require_list(all_info, "state", max_port_num)
        speeds_config = _require_list(all_info, "spd_cfg", max_port_num)
        speeds_actual = _require_list(all_info, "spd_act", max_port_num)
        fc_config_flags = _require_list(all_info, "fc_cfg", max_port_num)
        fc_actual_flags = _require_list(all_info, "fc_act", max_port_num)

        for number in range(1, max_port_num + 1):
            state = PortState(
                number=number,
                speed_config=_port_speed(speeds_config[number - 1]),
                speed_actual=_port_speed(speeds_actual[number - 1]),
                enabled=enabled_flags[number - 1] == 1,
                flow_control_config=fc_config_flags[number - 1] == 1,
                flow_control_actual=fc_actual_flags[number - 1] == 1,
            )
            result.append(state)

        return result

    async def get_port_statistics(self) -> list[PortStatistics]:
        """Return raw per-port packet counters."""
        data = await self._core_api.get_variables(
            URL_PORT_STATISTICS_GET,
            [
                ("all_info", VariableType.Dict),
                ("max_port_num", VariableType.Int),
            ],
        )

        all_info = data.get("all_info")
        if not isinstance(all_info, dict):
            raise DataFormatError("Port statistics do not contain 'all_info'")

        max_port_num = data.get("max_port_num")
        if not isinstance(max_port_num, int) or max_port_num < 1:
            raise DataFormatError("Port statistics contain an invalid port count")

        packet_values = _require_list(all_info, "pkts", max_port_num * 4)
        enabled_flags = all_info.get("state")
        link_values = all_info.get("link_status")
        result: list[PortStatistics] = []

        for index in range(max_port_num):
            packet_index = index * 4
            try:
                counters = [
                    int(value)
                    for value in packet_values[packet_index : packet_index + 4]
                ]
            except (TypeError, ValueError) as ex:
                raise DataFormatError(
                    f"Port {index + 1} statistics contain a non-integer counter"
                ) from ex

            result.append(
                PortStatistics(
                    number=index + 1,
                    enabled=(
                        bool(enabled_flags[index])
                        if isinstance(enabled_flags, list)
                        and len(enabled_flags) > index
                        else True
                    ),
                    link_status=(
                        _port_speed(link_values[index])
                        if isinstance(link_values, list) and len(link_values) > index
                        else PortSpeed.UNKNOWN
                    ),
                    tx_good_packets=counters[0],
                    tx_bad_packets=counters[1],
                    rx_good_packets=counters[2],
                    rx_bad_packets=counters[3],
                )
            )

        return result

    async def get_igmp_snooping(self) -> IgmpSnoopingState:
        """Return global IGMP snooping settings."""
        data = await self._core_api.get_variable(
            URL_IGMP_SETTINGS_GET, "igmp_ds", VariableType.Dict
        )
        if not isinstance(data, dict):
            raise DataFormatError("IGMP settings do not contain 'igmp_ds'")
        return IgmpSnoopingState(
            enabled=bool(data.get("state", 0)),
            report_suppression=bool(data.get("suppressionState", 0)),
        )

    async def set_igmp_snooping(self, enabled: bool, report_suppression: bool) -> None:
        """Set global IGMP snooping settings after checking support."""
        await self.get_igmp_snooping()
        await self._apply_get(
            URL_IGMP_SETTINGS_SET,
            _query(
                {
                    "igmp_mode": int(enabled),
                    "reportSu_mode": int(report_suppression),
                    "Apply": "Apply",
                }
            ),
        )

    async def get_loop_prevention(self) -> LoopPreventionState:
        """Return the loop-prevention setting."""
        enabled = await self._core_api.get_variable(
            URL_LOOP_PREVENTION_GET, "lpEn", VariableType.Int
        )
        if not isinstance(enabled, int):
            raise DataFormatError("Loop-prevention page does not contain 'lpEn'")
        return LoopPreventionState(enabled=bool(enabled))

    async def set_loop_prevention(self, enabled: bool) -> None:
        """Set loop prevention after checking support."""
        await self.get_loop_prevention()
        await self._apply_get(
            URL_LOOP_PREVENTION_SET,
            _query({"lpEn": int(enabled), "apply": "Apply"}),
        )

    async def get_cable_diagnostics(self) -> list[CableDiagnostic]:
        """Return cached cable-test results for every port."""
        data = await self._core_api.get_variables(
            URL_CABLE_DIAGNOSTICS_GET,
            [
                ("maxPort", VariableType.Int),
                ("cablestate", VariableType.List),
                ("cablelength", VariableType.List),
            ],
        )
        port_count = data.get("maxPort")
        if not isinstance(port_count, int) or port_count < 1:
            raise DataFormatError("Cable diagnostics contain an invalid port count")
        statuses = _int_list(data.get("cablestate"), "cablestate", port_count)
        lengths = _int_list(data.get("cablelength"), "cablelength", port_count)
        result: list[CableDiagnostic] = []
        for index in range(port_count):
            try:
                status = CableStatus(statuses[index])
            except ValueError:
                status = CableStatus.UNKNOWN
            raw_length = lengths[index]
            result.append(
                CableDiagnostic(
                    number=index + 1,
                    status=status,
                    length_m=raw_length if raw_length >= 0 else None,
                )
            )
        return result

    async def run_cable_diagnostic(self, port_number: int) -> list[CableDiagnostic]:
        """Run a cable test on one port and return the latest cached results."""
        if port_number < 1:
            raise ActionError("Port number must be greater than or equal to 1")
        response = await self._apply_get(
            URL_CABLE_DIAGNOSTICS_SET,
            _query({f"chk_{port_number}": port_number, "Apply": "Apply"}),
        )
        delay_match = re.search(
            r"\bvar\s+delayTime\s*=\s*(\d+)", response or "", re.IGNORECASE
        )
        await asyncio.sleep(int(delay_match.group(1)) if delay_match else 1)
        return await self.get_cable_diagnostics()

    async def get_port_mirror(self) -> PortMirrorState:
        """Return the current port-mirroring configuration."""
        data = await self._core_api.get_variables(
            URL_PORT_MIRROR_GET,
            [
                ("max_port_num", VariableType.Int),
                ("MirrEn", VariableType.Int),
                ("MirrPort", VariableType.Int),
                ("mirr_info", VariableType.Dict),
                ("porttrunkid", VariableType.List),
            ],
        )
        port_count = data.get("max_port_num")
        info = data.get("mirr_info")
        if not isinstance(port_count, int) or port_count < 1:
            raise DataFormatError("Port mirroring contains an invalid port count")
        if not isinstance(info, dict):
            raise DataFormatError("Port mirroring does not contain 'mirr_info'")
        ingress = _int_list(info.get("ingress"), "ingress", port_count)
        egress = _int_list(info.get("egress"), "egress", port_count)
        raw_trunk_groups = data.get("porttrunkid")
        trunk_groups = (
            _int_list(raw_trunk_groups, "porttrunkid", port_count)[:port_count]
            if isinstance(raw_trunk_groups, list)
            else [0] * port_count
        )
        destination = data.get("MirrPort")
        return PortMirrorState(
            enabled=bool(data.get("MirrEn", 0)),
            port_count=port_count,
            destination_port=(
                int(destination)
                if isinstance(destination, int) and 1 <= destination <= port_count
                else None
            ),
            ingress_ports=[index + 1 for index, value in enumerate(ingress) if value],
            egress_ports=[index + 1 for index, value in enumerate(egress) if value],
            trunk_groups=trunk_groups,
        )

    async def set_port_mirror(
        self,
        enabled: bool,
        destination_port: int | None,
        ingress_ports: Iterable[int],
        egress_ports: Iterable[int],
    ) -> None:
        """Set port mirroring while clearing obsolete source configuration."""
        current = await self.get_port_mirror()
        if not enabled:
            await self._apply_get(
                URL_MIRROR_DESTINATION_SET,
                _query({"state": 0, "mirrorenable": "Apply"}),
            )
            return

        if destination_port is None:
            raise ActionError("destination_port is required when mirroring is enabled")
        destination = _validate_ports(
            [destination_port], current.port_count, allow_empty=False
        )[0]
        ingress = _validate_ports(ingress_ports, current.port_count)
        egress = _validate_ports(egress_ports, current.port_count)
        source_ports = sorted(set(ingress) | set(egress))
        if not source_ports:
            raise ActionError("At least one ingress or egress source port is required")
        if destination in source_ports:
            raise ActionError("The mirror destination cannot also be a source port")
        lag_ports = [
            port
            for port in [destination, *source_ports]
            if current.trunk_groups[port - 1] > 0
        ]
        if lag_ports:
            raise ActionError(
                f"Port mirroring cannot use LAG member ports: {sorted(lag_ports)}"
            )

        await self._apply_get(
            URL_MIRROR_DESTINATION_SET,
            _query(
                {
                    "state": 1,
                    "mirroringport": destination,
                    "mirrorenable": "Apply",
                }
            ),
        )
        affected_ports = sorted(
            set(current.ingress_ports) | set(current.egress_ports) | set(source_ports)
        )
        for port in affected_ports:
            await self._apply_get(
                URL_MIRROR_SOURCE_SET,
                _query(
                    {
                        "mirroredport": port,
                        "ingressState": int(port in ingress),
                        "egressState": int(port in egress),
                        "mirrored_submit": "Apply",
                    }
                ),
            )

    async def get_lags(self) -> LagState:
        """Return static link aggregation groups."""
        data = await self._core_api.get_variables(
            URL_LAG_GET,
            [
                ("trunk_conf", VariableType.Dict),
                ("portNumPerTrunk", VariableType.Int),
            ],
        )
        configuration = data.get("trunk_conf")
        if not isinstance(configuration, dict):
            raise DataFormatError("LAG settings do not contain 'trunk_conf'")
        try:
            max_groups = int(configuration.get("maxTrunkNum", 0))
            port_count = int(configuration.get("portNum", 0))
            ports_per_group = int(data.get("portNumPerTrunk", 0))
        except (TypeError, ValueError) as ex:
            raise DataFormatError("LAG settings contain invalid limits") from ex
        if max_groups < 1 or port_count < 2 or ports_per_group < 2:
            raise DataFormatError("LAG settings contain invalid limits")
        groups: dict[int, list[int]] = {}
        for group_id in range(1, max_groups + 1):
            values = _int_list(
                configuration.get(f"portStr_g{group_id}", []), "LAG ports"
            )
            groups[group_id] = [
                index + 1 for index, value in enumerate(values[:port_count]) if value
            ]
        return LagState(
            max_groups=max_groups,
            port_count=port_count,
            ports_per_group=ports_per_group,
            groups=groups,
        )

    async def set_lag(self, group_id: int, ports: Iterable[int]) -> None:
        """Create or update a static LAG."""
        state = await self.get_lags()
        if group_id < 1 or group_id > state.max_groups:
            raise ActionError(f"group_id must be between 1 and {state.max_groups}")
        members = _validate_ports(ports, state.port_count, allow_empty=False)
        if len(members) < 2 or len(members) > state.ports_per_group:
            raise ActionError(
                f"A LAG must contain between 2 and {state.ports_per_group} ports"
            )
        minimum = ((group_id - 1) * state.ports_per_group) + 1
        maximum = min(group_id * state.ports_per_group, state.port_count)
        if any(port < minimum or port > maximum for port in members):
            raise ActionError(
                f"LAG {group_id} only supports ports {minimum} to {maximum}"
            )
        params: list[tuple[str, object]] = [
            ("groupId", group_id),
            ("setapply", "Apply"),
        ]
        params.extend(("portid", port) for port in members)
        await self._apply_get(URL_LAG_SET, _query(params))

    async def delete_lag(self, group_id: int) -> None:
        """Delete a static LAG after validating the device limits."""
        state = await self.get_lags()
        if group_id < 1 or group_id > state.max_groups:
            raise ActionError(f"group_id must be between 1 and {state.max_groups}")
        await self._apply_get(
            URL_LAG_DELETE,
            _query({"chk_trunk": group_id, "setDelete": "Delete"}),
        )

    async def get_mtu_vlan(self) -> MtuVlanState:
        """Return MTU VLAN settings."""
        data = await self._core_api.get_variable(
            URL_MTU_VLAN_GET, "mtu_ds", VariableType.Dict
        )
        if not isinstance(data, dict):
            raise DataFormatError("MTU VLAN settings do not contain 'mtu_ds'")
        try:
            port_count = int(data.get("portNum", 0))
            uplink_port = int(data.get("uplinkPort", 0))
        except (TypeError, ValueError) as ex:
            raise DataFormatError("MTU VLAN settings contain invalid ports") from ex
        if port_count < 1 or not 1 <= uplink_port <= port_count:
            raise DataFormatError("MTU VLAN settings contain invalid ports")
        return MtuVlanState(bool(data.get("state", 0)), port_count, uplink_port)

    async def set_mtu_vlan(self, enabled: bool, uplink_port: int | None) -> None:
        """Configure MTU VLAN mode."""
        state = await self.get_mtu_vlan()
        port = state.uplink_port if uplink_port is None else uplink_port
        port = _validate_ports([port], state.port_count, allow_empty=False)[0]
        if state.enabled != enabled:
            await self._apply_get(
                URL_MTU_VLAN_SET,
                _query({"mtu_en": int(enabled), "mtu_mode": "Apply"}),
            )

        if enabled and port != state.uplink_port:
            if not state.enabled:
                # Enabling a VLAN mode can briefly restart the embedded web
                # server. Give it time to accept the separate uplink form.
                await asyncio.sleep(1)
            await self._apply_get(
                URL_MTU_VLAN_SET,
                _query({"uplinkPort": port, "mtu_uplink": "Apply"}),
            )

    async def get_port_vlans(self) -> PortVlanState:
        """Return port-based VLAN configuration."""
        data = await self._core_api.get_variable(
            URL_PORT_VLAN_GET, "pvlan_ds", VariableType.Dict
        )
        if not isinstance(data, dict):
            raise DataFormatError("Port VLAN settings do not contain 'pvlan_ds'")
        try:
            port_count = int(data.get("portNum", 0))
            count = int(data.get("count", 0))
        except (TypeError, ValueError) as ex:
            raise DataFormatError("Port VLAN settings contain invalid limits") from ex
        if port_count < 1 or count < 0:
            raise DataFormatError("Port VLAN settings contain invalid limits")
        vlan_ids = _int_list(data.get("vids", []), "vids", count)
        masks = _int_list(data.get("mbrs", []), "mbrs", count)
        raw_trunk_groups = data.get("lagIds")
        trunk_groups = (
            _int_list(raw_trunk_groups, "lagIds", port_count)[:port_count]
            if isinstance(raw_trunk_groups, list)
            else [0] * port_count
        )
        return PortVlanState(
            enabled=bool(data.get("state", 0)),
            port_count=port_count,
            vlans=[
                PortVlan(vlan_ids[index], _decode_port_mask(masks[index], port_count))
                for index in range(count)
            ],
            trunk_groups=trunk_groups,
        )

    async def set_port_vlan_enabled(self, enabled: bool) -> None:
        """Enable or disable port-based VLAN mode."""
        await self.get_port_vlans()
        await self._apply_get(
            URL_PORT_VLAN_SET,
            _query({"pvlan_en": int(enabled), "pvlan_mode": "Apply"}),
        )
        self._core_api.invalidate_authentication()

    async def upsert_port_vlan(self, vlan_id: int, member_ports: Iterable[int]) -> None:
        """Create or update a port-based VLAN."""
        state = await self.get_port_vlans()
        if not state.enabled:
            raise ActionError("Port-based VLAN mode is disabled")
        if vlan_id < 2 or vlan_id > state.port_count:
            raise ActionError(
                f"Port-based vlan_id must be between 2 and {state.port_count}"
            )
        members = _expand_trunk_ports(member_ports, state.trunk_groups)
        if not members:
            raise ActionError("At least one port must be selected")
        params: list[tuple[str, object]] = [
            ("vid", vlan_id),
            ("pvlan_add", "Apply"),
        ]
        params.extend(("selPorts", port) for port in members)
        await self._apply_get(URL_PORT_VLAN_SET, _query(params))

    async def delete_port_vlan(self, vlan_id: int) -> None:
        """Delete a port-based VLAN."""
        state = await self.get_port_vlans()
        if vlan_id == 1:
            raise ActionError("The default VLAN 1 cannot be deleted")
        if vlan_id not in {vlan.vlan_id for vlan in state.vlans}:
            raise ActionError(f"Port VLAN {vlan_id} does not exist")
        await self._apply_get(
            URL_PORT_VLAN_SET,
            _query({"selVlans": vlan_id, "pvlan_del": "Delete"}),
        )

    async def get_8021q_vlans(self) -> Vlan8021QState:
        """Return IEEE 802.1Q VLAN configuration."""
        data = await self._core_api.get_variable(
            URL_8021Q_VLAN_GET, "qvlan_ds", VariableType.Dict
        )
        if not isinstance(data, dict):
            raise DataFormatError("802.1Q VLAN settings do not contain 'qvlan_ds'")
        try:
            port_count = int(data.get("portNum", 0))
            count = int(data.get("count", 0))
            max_vlans = int(data.get("maxVids", 0))
        except (TypeError, ValueError) as ex:
            raise DataFormatError("802.1Q VLAN settings contain invalid limits") from ex
        if port_count < 1 or count < 0 or max_vlans < 1:
            raise DataFormatError("802.1Q VLAN settings contain invalid limits")
        vlan_ids = _int_list(data.get("vids", []), "vids", count)
        tagged_masks = _int_list(data.get("tagMbrs", []), "tagMbrs", count)
        untagged_masks = _int_list(data.get("untagMbrs", []), "untagMbrs", count)
        raw_names = data.get("names", [])
        if not isinstance(raw_names, list) or len(raw_names) < count:
            raise DataFormatError("Invalid 'names' array")
        raw_trunk_groups = data.get("lagIds")
        trunk_groups = (
            _int_list(raw_trunk_groups, "lagIds", port_count)[:port_count]
            if isinstance(raw_trunk_groups, list)
            else [0] * port_count
        )
        vlans = [
            Vlan8021Q(
                vlan_id=vlan_ids[index],
                name=str(raw_names[index]),
                tagged_ports=_decode_port_mask(tagged_masks[index], port_count),
                untagged_ports=_decode_port_mask(untagged_masks[index], port_count),
            )
            for index in range(count)
        ]
        return Vlan8021QState(
            enabled=bool(data.get("state", 0)),
            port_count=port_count,
            max_vlans=max_vlans,
            vlans=vlans,
            trunk_groups=trunk_groups,
        )

    async def set_8021q_vlan_enabled(self, enabled: bool) -> None:
        """Enable or disable IEEE 802.1Q VLAN mode."""
        await self.get_8021q_vlans()
        await self._apply_get(
            URL_8021Q_VLAN_SET,
            _query({"qvlan_en": int(enabled), "qvlan_mode": "Apply"}),
        )
        self._core_api.invalidate_authentication()

    async def upsert_8021q_vlan(
        self,
        vlan_id: int,
        name: str,
        tagged_ports: Iterable[int],
        untagged_ports: Iterable[int],
    ) -> None:
        """Create or update an IEEE 802.1Q VLAN."""
        state = await self.get_8021q_vlans()
        if not state.enabled:
            raise ActionError("802.1Q VLAN mode is disabled")
        if vlan_id < 1 or vlan_id > 4094:
            raise ActionError("vlan_id must be between 1 and 4094")
        if not re.fullmatch(r"[A-Za-z0-9_-]{0,10}", name):
            raise ActionError(
                "VLAN name must contain at most 10 letters, digits, hyphens or "
                "underscores"
            )
        tagged = _expand_trunk_ports(tagged_ports, state.trunk_groups)
        untagged = _expand_trunk_ports(untagged_ports, state.trunk_groups)
        overlap = sorted(set(tagged) & set(untagged))
        if overlap:
            raise ActionError(f"Ports cannot be both tagged and untagged: {overlap}")
        if not tagged and not untagged:
            raise ActionError("At least one tagged or untagged port is required")
        existing_ids = {vlan.vlan_id for vlan in state.vlans}
        if vlan_id not in existing_ids and len(existing_ids) >= state.max_vlans:
            raise ActionError(f"The switch supports at most {state.max_vlans} VLANs")
        if vlan_id == 1:
            proposed_members = set(tagged) | set(untagged)
            other_members = {
                port
                for vlan in state.vlans
                if vlan.vlan_id != 1
                for port in [*vlan.tagged_ports, *vlan.untagged_ports]
            }
            orphaned = sorted(
                set(range(1, state.port_count + 1)) - proposed_members - other_members
            )
            if orphaned:
                raise ActionError(
                    f"Ports must remain members of at least one VLAN: {orphaned}"
                )

        params: dict[str, object] = {
            "vid": vlan_id,
            "vname": name,
            "qvlan_add": "Add/Modify",
        }
        for port in range(1, state.port_count + 1):
            params[f"selType_{port}"] = (
                1 if port in tagged else 0 if port in untagged else 2
            )
        await self._apply_get(URL_8021Q_VLAN_SET, _query(params))

    async def delete_8021q_vlan(self, vlan_id: int) -> None:
        """Delete an IEEE 802.1Q VLAN other than the immutable default VLAN."""
        state = await self.get_8021q_vlans()
        if vlan_id == 1:
            raise ActionError("The default VLAN 1 cannot be deleted")
        if vlan_id not in {vlan.vlan_id for vlan in state.vlans}:
            raise ActionError(f"VLAN {vlan_id} does not exist")
        await self._apply_get(
            URL_8021Q_VLAN_SET,
            _query({"selVlans": vlan_id, "qvlan_del": "Delete"}),
        )

    async def get_pvids(self) -> VlanPvidState:
        """Return PVID mode, values, VLAN IDs, membership masks and LAGs."""
        data = await self._core_api.get_variable(
            URL_8021Q_PVID_GET, "pvid_ds", VariableType.Dict
        )
        if not isinstance(data, dict):
            raise DataFormatError("PVID settings do not contain 'pvid_ds'")
        try:
            port_count = int(data.get("portNum", 0))
            count = int(data.get("count", 0))
        except (TypeError, ValueError) as ex:
            raise DataFormatError("PVID settings contain invalid limits") from ex
        if port_count < 1 or count < 0:
            raise DataFormatError("PVID settings contain invalid limits")
        pvids = _int_list(data.get("pvids"), "pvids", port_count)[:port_count]
        vlan_ids = _int_list(data.get("vids", []), "vids", count)[:count]
        member_masks = _int_list(data.get("mbrs", []), "mbrs", count)[:count]
        raw_trunk_groups = data.get("lagIds")
        trunk_groups = (
            _int_list(raw_trunk_groups, "lagIds", port_count)[:port_count]
            if isinstance(raw_trunk_groups, list)
            else [0] * port_count
        )
        return VlanPvidState(
            enabled=bool(data.get("state", 0)),
            port_count=port_count,
            pvids=pvids,
            vlan_ids=vlan_ids,
            member_masks=member_masks,
            trunk_groups=trunk_groups,
        )

    async def set_pvid(self, ports: Iterable[int], vlan_id: int) -> None:
        """Set the PVID of one or more physical ports."""
        state = await self.get_pvids()
        if not state.enabled:
            raise ActionError("802.1Q VLAN mode is disabled")
        members = _expand_trunk_ports(ports, state.trunk_groups)
        if not members:
            raise ActionError("At least one port must be selected")
        if vlan_id not in state.vlan_ids:
            raise ActionError(f"VLAN {vlan_id} does not exist")
        vlan_mask = state.member_masks[state.vlan_ids.index(vlan_id)]
        invalid_members = [
            port for port in members if not vlan_mask & (1 << (port - 1))
        ]
        if invalid_members:
            raise ActionError(
                f"Ports are not members of VLAN {vlan_id}: {invalid_members}"
            )
        await self._apply_get(
            URL_8021Q_PVID_SET,
            _query({"pbm": _encode_port_mask(members), "pvid": vlan_id}),
        )

    async def get_qos(self) -> QosState:
        """Return QoS mode and per-port priorities."""
        data = await self._core_api.get_variables(
            URL_QOS_GET,
            [
                ("portNumber", VariableType.Int),
                ("qosMode", VariableType.Int),
                ("pPri", VariableType.List),
                ("pTrunk", VariableType.List),
            ],
        )
        port_count = data.get("portNumber")
        if not isinstance(port_count, int) or port_count < 1:
            raise DataFormatError("QoS settings contain an invalid port count")
        try:
            mode = QosMode(int(data.get("qosMode")))
        except (TypeError, ValueError) as ex:
            raise DataFormatError("QoS settings contain an invalid mode") from ex
        return QosState(
            mode=mode,
            priorities=_int_list(data.get("pPri"), "pPri", port_count)[:port_count],
            trunk_groups=_int_list(data.get("pTrunk"), "pTrunk", port_count)[
                :port_count
            ],
        )

    async def set_qos_mode(self, mode: QosMode) -> None:
        """Set QoS classification mode."""
        await self.get_qos()
        try:
            parsed_mode = QosMode(mode)
        except (TypeError, ValueError) as ex:
            raise ActionError("Invalid QoS mode") from ex
        await self._apply_post(
            URL_QOS_MODE_SET,
            {"rd_qosmode": int(parsed_mode), "qosmode": "Apply"},
        )

    @staticmethod
    def _ports_for_trunk(port: int, trunk_groups: list[int]) -> list[int]:
        """Return all ports affected by a per-port setting on a LAG."""
        _validate_ports([port], len(trunk_groups), allow_empty=False)
        group = trunk_groups[port - 1]
        if group == 0:
            return [port]
        return [index + 1 for index, value in enumerate(trunk_groups) if value == group]

    async def set_qos_priority(self, port_number: int, priority: int) -> None:
        """Set port-based QoS priority, expanding a selected LAG member."""
        state = await self.get_qos()
        if state.mode != QosMode.PORT_BASED:
            raise ActionError("Port priority requires port-based QoS mode")
        if priority < 1 or priority > 4:
            raise ActionError("priority must be between 1 and 4")
        ports = self._ports_for_trunk(port_number, state.trunk_groups)
        data: dict[str, object] = {"port_queue": priority - 1, "apply": "Apply"}
        data.update({f"sel_{port}": 1 for port in ports})
        await self._apply_post(URL_QOS_PRIORITY_SET, data)

    async def get_bandwidth_controls(self) -> list[BandwidthControl]:
        """Return per-port ingress and egress rate limits."""
        data = await self._core_api.get_variables(
            URL_BANDWIDTH_CONTROL_GET,
            [
                ("portNumber", VariableType.Int),
                ("bcInfo", VariableType.List),
            ],
        )
        port_count = data.get("portNumber")
        if not isinstance(port_count, int) or port_count < 1:
            raise DataFormatError("Bandwidth settings contain an invalid port count")
        values = _int_list(data.get("bcInfo"), "bcInfo", port_count * 3)
        return [
            BandwidthControl(
                number=index + 1,
                ingress_kbps=values[index * 3],
                egress_kbps=values[index * 3 + 1],
                trunk_group=values[index * 3 + 2],
            )
            for index in range(port_count)
        ]

    async def set_bandwidth_control(
        self, port_number: int, ingress_kbps: int, egress_kbps: int
    ) -> None:
        """Set per-port ingress and egress rate limits (zero means unlimited)."""
        if not 0 <= ingress_kbps <= 1_000_000:
            raise ActionError("ingress_kbps must be between 0 and 1000000")
        if not 0 <= egress_kbps <= 1_000_000:
            raise ActionError("egress_kbps must be between 0 and 1000000")
        state = await self.get_bandwidth_controls()
        trunk_groups = [item.trunk_group for item in state]
        ports = self._ports_for_trunk(port_number, trunk_groups)
        data: dict[str, object] = {
            "igrRate": ingress_kbps,
            "egrRate": egress_kbps,
            "applay": "Apply",
        }
        data.update({f"sel_{port}": 1 for port in ports})
        await self._apply_post(URL_BANDWIDTH_CONTROL_SET, data)

    async def get_storm_controls(self) -> list[StormControl]:
        """Return per-port storm-control settings."""
        data = await self._core_api.get_variables(
            URL_STORM_CONTROL_GET,
            [
                ("portNumber", VariableType.Int),
                ("scInfo", VariableType.List),
            ],
        )
        port_count = data.get("portNumber")
        if not isinstance(port_count, int) or port_count < 1:
            raise DataFormatError(
                "Storm-control settings contain an invalid port count"
            )
        values = _int_list(data.get("scInfo"), "scInfo", port_count * 3)
        result: list[StormControl] = []
        for index in range(port_count):
            rate = values[index * 3]
            mask = values[index * 3 + 1]
            result.append(
                StormControl(
                    number=index + 1,
                    enabled=rate > 0 and mask > 0,
                    rate_kbps=rate,
                    unknown_unicast=bool(mask & 1),
                    multicast=bool(mask & 2),
                    broadcast=bool(mask & 4),
                    trunk_group=values[index * 3 + 2],
                )
            )
        return result

    async def set_storm_control(
        self,
        port_number: int,
        enabled: bool,
        rate_kbps: int,
        unknown_unicast: bool,
        multicast: bool,
        broadcast: bool,
    ) -> None:
        """Set storm control for a port or all members of its LAG."""
        if enabled and not 1 <= rate_kbps <= 1_000_000:
            raise ActionError("rate_kbps must be between 1 and 1000000")
        types = [
            value
            for value, selected in (
                (1, unknown_unicast),
                (2, multicast),
                (4, broadcast),
            )
            if selected
        ]
        if enabled and not types:
            raise ActionError("At least one storm type must be selected")
        state = await self.get_storm_controls()
        trunk_groups = [item.trunk_group for item in state]
        ports = self._ports_for_trunk(port_number, trunk_groups)
        data: list[tuple[str, object]] = [
            ("state", int(enabled)),
            ("applay", "Apply"),
        ]
        if enabled:
            data.append(("rate", rate_kbps))
            data.extend(("stormType", item) for item in types)
        data.extend((f"sel_{port}", 1) for port in ports)
        # The list of pairs preserves the independent stormType selections.
        await self._apply_post(URL_STORM_CONTROL_SET, data)

    async def get_port_poe_states(self) -> list[PortPoeState]:
        """Return the port states."""
        if not await self.is_feature_available(FEATURE_POE):
            return []

        data = await self._core_api.get_variables(
            URL_POE_SETTINGS_GET,
            [
                ("portConfig", VariableType.Dict),
                ("poe_port_num", VariableType.Int),
            ],
        )

        result: list[PortPoeState] = []

        port_config = data.get("portConfig")
        if not isinstance(port_config, dict):
            _LOGGER.debug("No portConfig found, returning")
            return result

        max_port_num = data.get("poe_port_num")
        if not max_port_num:
            _LOGGER.debug("No poe_port_num found, returning")
            return result

        state_flags = _require_list(port_config, "state", max_port_num)
        priority_flags = _require_list(port_config, "priority", max_port_num)
        powerlimit_flags = _require_list(port_config, "powerlimit", max_port_num)
        powers = _require_list(port_config, "power", max_port_num)
        currents = _require_list(port_config, "current", max_port_num)
        voltages = _require_list(port_config, "voltage", max_port_num)
        pdclass_flags = _require_list(port_config, "pdclass", max_port_num)
        powerstatus_flags = _require_list(port_config, "powerstatus", max_port_num)

        for number in range(1, max_port_num + 1):
            state = PortPoeState(
                number=number,
                enabled=state_flags[number - 1] == 1,
                priority=PoePriority(priority_flags[number - 1]),
                current=currents[number - 1],
                voltage=voltages[number - 1] / 10,
                power_limit=PoePowerLimit.try_parse(powerlimit_flags[number - 1])
                or powerlimit_flags[number - 1] / 10,
                power_status=PoePowerStatus(powerstatus_flags[number - 1]),
                pd_class=PoeClass.try_parse(pdclass_flags[number - 1]),
                power=powers[number - 1] / 10,
            )
            result.append(state)

        return result

    async def get_poe_state(self) -> PoeState | None:
        """Return the port states."""
        if not await self.is_feature_available(FEATURE_POE):
            return None

        _LOGGER.debug("Begin fetching POE states")

        poe_config = await self._core_api.get_variable(
            URL_POE_SETTINGS_GET, "globalConfig", VariableType.Dict
        )
        if not poe_config:
            _LOGGER.debug("No globalConfig found, returning")
            return None

        return PoeState(
            power_limit=poe_config.get("system_power_limit", 0) / 10,
            power_remain=poe_config.get("system_power_remain", 0) / 10,
            power_limit_min=poe_config.get("system_power_limit_min", 0) / 10,
            power_limit_max=poe_config.get("system_power_limit_max", 0) / 10,
            power_consumption=poe_config.get("system_power_consumption", 0) / 10,
        )

    async def set_port_state(
        self,
        number: int,
        enabled: bool,
        speed_config: PortSpeed,
        flow_control_config: bool,
    ) -> None:
        """Change port state."""
        query: str = (
            f"portid={number}&"
            f"state={1 if enabled else 0}&"
            f"speed={speed_config.value}&"
            f"flowcontrol={1 if flow_control_config else 0}&"
            f"apply=Apply"
        )
        await self._apply_get(URL_PORT_SETTINGS_SET, query)

    async def set_poe_limit(self, limit: float) -> None:
        """Change poe limit."""
        if not await self.is_feature_available(FEATURE_POE):
            raise ActionError("POE feature is not supported by device")

        current_state = await self.get_poe_state()
        if not current_state:
            raise ActionError("Can not get actual PoE state")

        if limit < current_state.power_limit_min:
            raise ActionError(
                "PoE limit should be greater than or equal to "
                f"{current_state.power_limit_min}"
            )
        if limit > current_state.power_limit_max:
            raise ActionError(
                "PoE limit should be less than or equal to "
                f"{current_state.power_limit_max}"
            )

        data = {
            "name_powerlimit": limit,
            "name_powerconsumption": current_state.power_consumption,
            "name_powerremain": current_state.power_remain,
            "applay": "Apply",
        }
        result = await self._apply_post(URL_POE_SETTINGS_SET, data)
        _LOGGER.debug("POE_SET_RESULT: %s", result)

    async def set_port_poe_settings(
        self,
        port_number: int,
        enabled: bool,
        priority: PoePriority,
        power_limit: PoePowerLimit | float,
    ) -> None:
        """Change port PoE settings."""
        if not await self.is_feature_available(FEATURE_POE):
            raise ActionError("POE feature is not supported by device")
        if port_number < 1:
            raise ActionError("Port number should be greater than or equals to 1")

        poe_ports_count = await self._core_api.get_variable(
            URL_POE_SETTINGS_GET, "poe_port_num", VariableType.Int
        )
        if not poe_ports_count:
            raise ActionError("Can not get PoE ports count")

        if port_number > poe_ports_count:
            raise ActionError(
                f"Port number should be less than or equals to {poe_ports_count}"
            )

        pstate = 2 if enabled else 1

        ppriority = _POE_PRIORITIES_SET_MAP.get(priority)
        if not ppriority:
            raise ActionError("Invalid PoePriority specified")

        if isinstance(power_limit, PoePowerLimit):
            mapped_limit = _POE_POWER_LIMITS_SET_MAP.get(power_limit)
            if mapped_limit is None:
                raise ActionError("Invalid PoePowerLimit specified")
            ppowerlimit, ppowerlimit2 = mapped_limit
            if not ppowerlimit:
                raise ActionError("Invalid PoePowerLimit specified")
        elif isinstance(power_limit, (int, float)) and not isinstance(
            power_limit, bool
        ):
            power_limit = float(power_limit)
            if 0.1 <= power_limit <= 30.0:  # hardcoded in Tp-Link javascript
                ppowerlimit = 6
                ppowerlimit2 = power_limit
            else:
                raise ActionError("Power limit must be in range of 0.1-30.0")
        else:
            raise ActionError("Invalid power_limit specified")

        data = {
            "name_pstate": pstate,
            "name_ppriority": ppriority,
            "name_ppowerlimit": ppowerlimit,
            "name_ppowerlimit2": ppowerlimit2,
            f"sel_{port_number}": 1,
            "applay": "Apply",
        }
        result = await self._apply_post(URL_POE_PORT_SETTINGS_SET, data)
        _LOGGER.debug("POE_PORT_SETTINGS_SET_RESULT: %s", result)
