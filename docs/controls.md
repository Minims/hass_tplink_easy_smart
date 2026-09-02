# Switches and selects

Configuration entities are attached to the switch device. Entity IDs include
the integration name configured during setup.

## Port state

`switch.<integration_name>_port_<n>_enabled` administratively enables or
disables a physical port. These entities are only created when **Port state
switches** is enabled in the integration options.

Disabling the port carrying Home Assistant traffic immediately breaks switch
management until another path is available or the port is restored locally.

## Port flow control

`switch.<integration_name>_port_<n>_flow_control` controls IEEE 802.3x flow
control while preserving the port state and configured speed. It is created
disabled by default in the entity registry.

Flow control only takes effect in the speed/duplex modes supported by the
switch firmware.

## Port speed and duplex

`select.<integration_name>_port_<n>_speed_and_duplex` provides the modes exposed
by the TL-SG105E V5 web interface:

- Auto negotiation
- 10 Mbps half or full duplex
- 100 Mbps half or full duplex
- 1 Gbps full duplex

These configuration entities are disabled by default. A forced mode must match
the device at the other end of the cable.

## IGMP and loop prevention

When supported by the firmware, the integration creates:

- `switch.<integration_name>_igmp_snooping`
- `switch.<integration_name>_igmp_report_suppression` (disabled by default)
- `switch.<integration_name>_loop_prevention`

Changing report suppression preserves the current IGMP snooping state, and
vice versa.

## QoS

`select.<integration_name>_qos_mode` selects Port based, 802.1p based, or
DSCP/802.1p based classification when the page is supported.

`select.<integration_name>_port_<n>_qos_priority` is created disabled by default
and applies priorities 1 (lowest) through 4 (highest). It can only be changed
in port-based QoS mode. Selecting a member of a static LAG updates the whole
LAG, matching the switch Web UI.

## Port PoE state

`switch.<integration_name>_port_<n>_poe_enabled` enables or disables PoE while
preserving the port's priority and power limit. It is only created when PoE is
detected and **Port PoE state switches** is enabled in integration options.

PoE changes can power-cycle connected equipment. Non-PoE models such as the
TL-SG105E do not expose these entities.
