"""TP-Link core classes."""

from dataclasses import dataclass
from enum import IntEnum


# ---------------------------
#   TpLinkSystemInfo
# ---------------------------
@dataclass()
class TpLinkSystemInfo:
    name: str | None = None
    mac: str | None = None
    ip: str | None = None
    netmask: str | None = None
    gateway: str | None = None
    firmware: str | None = None
    hardware: str | None = None


# ---------------------------
#   PortSpeed
# ---------------------------
class PortSpeed(IntEnum):
    LINK_DOWN = 0
    AUTO = 1
    HALF_10M = 2
    FULL_10M = 3
    HALF_100M = 4
    FULL_100M = 5
    FULL_1000M = 6
    UNKNOWN = 7


class QosMode(IntEnum):
    """QoS classification mode used by Easy Smart switches."""

    PORT_BASED = 0
    IEEE_8021P = 1
    DSCP_IEEE_8021P = 2


class CableStatus(IntEnum):
    """Cable diagnostic result returned by the switch firmware."""

    NOT_TESTED = -1
    NO_CABLE = 0
    NORMAL = 1
    OPEN = 2
    SHORT = 3
    OPEN_SHORT = 4
    CROSS_CABLE = 5
    UNKNOWN = 255


# ---------------------------
#   PoePriority
# ---------------------------
class PoePriority(IntEnum):
    HIGH = 0
    MIDDLE = 1
    LOW = 2

    @classmethod
    def try_parse(cls, value):
        if value in cls._value2member_map_:
            return PoePriority(value)
        return None


# ---------------------------
#   PoePowerLimit
# ---------------------------
class PoePowerLimit(IntEnum):
    AUTO = 330
    CLASS_1 = 40
    CLASS_2 = 70
    CLASS_3 = 154
    CLASS_4 = 300

    @classmethod
    def try_parse(cls, value):
        if value in cls._value2member_map_:
            return PoePowerLimit(value)
        return None


# ---------------------------
#   PoeClass
# ---------------------------
class PoeClass(IntEnum):
    CLASS_1 = 40
    CLASS_2 = 70
    CLASS_3 = 154
    CLASS_4 = 300
    CLASS_0 = 330

    @classmethod
    def try_parse(cls, value):
        if value in cls._value2member_map_:
            return PoeClass(value)
        return None


# ---------------------------
#   PoePowerStatus
# ---------------------------
class PoePowerStatus(IntEnum):
    OFF = 0
    TURNING_ON = 1
    ON = 2
    OVERLOAD = 3
    OVELOAD = 3  # Backward-compatible alias for the original typo.
    SHORT = 4
    NOSTANDARD_PD = 5
    VOLTAGE_HIGH = 6
    VOLTAGE_LOW = 7
    HARDWARE_FAULT = 8
    OVERTEMPERATURE = 9

    @classmethod
    def try_parse(cls, value):
        if value in cls._value2member_map_:
            return PoePowerStatus(value)
        return None


# ---------------------------
#   PortState
# ---------------------------
@dataclass
class PortState:
    number: int
    enabled: bool
    flow_control_config: bool
    flow_control_actual: bool
    speed_config: PortSpeed
    speed_actual: PortSpeed


@dataclass
class IgmpSnoopingState:
    """Global IGMP snooping settings."""

    enabled: bool
    report_suppression: bool


@dataclass
class LoopPreventionState:
    """Global loop-prevention setting."""

    enabled: bool


@dataclass
class CableDiagnostic:
    """Cable diagnostic state for one port."""

    number: int
    status: CableStatus
    length_m: int | None


@dataclass
class PortMirrorState:
    """Port mirroring configuration."""

    enabled: bool
    port_count: int
    destination_port: int | None
    ingress_ports: list[int]
    egress_ports: list[int]
    trunk_groups: list[int]


@dataclass
class LagState:
    """Static link aggregation configuration."""

    max_groups: int
    port_count: int
    ports_per_group: int
    groups: dict[int, list[int]]


@dataclass
class MtuVlanState:
    """MTU VLAN configuration."""

    enabled: bool
    port_count: int
    uplink_port: int


@dataclass
class PortVlan:
    """One port-based VLAN entry."""

    vlan_id: int
    member_ports: list[int]


@dataclass
class PortVlanState:
    """Port-based VLAN configuration."""

    enabled: bool
    port_count: int
    vlans: list[PortVlan]
    trunk_groups: list[int]


@dataclass
class Vlan8021Q:
    """One IEEE 802.1Q VLAN entry."""

    vlan_id: int
    name: str
    tagged_ports: list[int]
    untagged_ports: list[int]


@dataclass
class Vlan8021QState:
    """IEEE 802.1Q VLAN configuration."""

    enabled: bool
    port_count: int
    max_vlans: int
    vlans: list[Vlan8021Q]
    trunk_groups: list[int]


@dataclass
class QosState:
    """QoS mode and per-port priority configuration."""

    mode: QosMode
    priorities: list[int]
    trunk_groups: list[int]


@dataclass
class BandwidthControl:
    """Per-port ingress and egress bandwidth limits."""

    number: int
    ingress_kbps: int
    egress_kbps: int
    trunk_group: int


@dataclass
class StormControl:
    """Per-port storm-control configuration."""

    number: int
    enabled: bool
    rate_kbps: int
    unknown_unicast: bool
    multicast: bool
    broadcast: bool
    trunk_group: int


# ---------------------------
#   PortStatistics
# ---------------------------
@dataclass
class PortStatistics:
    """Raw packet counters exposed by the switch for one port."""

    number: int
    enabled: bool
    link_status: PortSpeed
    tx_good_packets: int
    tx_bad_packets: int
    rx_good_packets: int
    rx_bad_packets: int


# ---------------------------
#   PortTrafficRates
# ---------------------------
@dataclass
class PortTrafficRates:
    """Rates calculated from two consecutive packet counter samples."""

    tx_packets_per_second: float
    rx_packets_per_second: float
    tx_estimated_mbps: float
    rx_estimated_mbps: float

    @property
    def total_estimated_mbps(self) -> float:
        """Return the combined estimated transmit and receive rate."""
        return self.tx_estimated_mbps + self.rx_estimated_mbps


# ---------------------------
#   PortPoeState
# ---------------------------
@dataclass
class PortPoeState:
    number: int
    enabled: bool
    priority: PoePriority
    power_limit: PoePowerLimit | float
    power: float
    current: float
    voltage: float
    pd_class: PoeClass | None
    power_status: PoePowerStatus


# ---------------------------
#   PoeState
# ---------------------------
@dataclass
class PoeState:
    power_limit: float
    power_limit_min: float
    power_limit_max: float
    power_consumption: float
    power_remain: float
