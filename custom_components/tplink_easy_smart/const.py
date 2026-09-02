"""TP-Link shared constants."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "tplink_easy_smart"

DATA_KEY_COORDINATOR: Final = "coordinator"
DATA_KEY_SERVICES: Final = "services_count"

DEFAULT_HOST: Final = "192.168.0.1"
DEFAULT_USER: Final = "admin"
DEFAULT_PORT: Final = 80
DEFAULT_SSL: Final = False
DEFAULT_PASS: Final = ""
DEFAULT_NAME: Final = "TP-Link Switch"
DEFAULT_VERIFY_SSL: Final = False
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 5
MAX_SCAN_INTERVAL: Final = 3600
DEFAULT_PORT_STATE_SWITCHES: Final = True
DEFAULT_POE_STATE_SWITCHES: Final = True
DEFAULT_ESTIMATED_PACKET_SIZE: Final = 1500
MIN_ESTIMATED_PACKET_SIZE: Final = 64
MAX_ESTIMATED_PACKET_SIZE: Final = 16384

OPT_PORT_STATE_SWITCHES: Final = "port_state_switches"
OPT_POE_STATE_SWITCHES: Final = "poe_state_switches"
OPT_ESTIMATED_PACKET_SIZE: Final = "estimated_packet_size"

ATTR_MANUFACTURER: Final = "TP-Link"
PLATFORMS: Final = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.SELECT,
]
