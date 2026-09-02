# Switches and selects

Configuration entities are attached to the switch device. Entity IDs include
the integration name configured during setup.

## Port state

`switch.<integration_name>_port_<n>_enabled` administratively enables or
disables a physical port. These entities are created by default and can be
disabled through **Port state switches** in the integration options.

Disabling the port carrying Home Assistant traffic immediately breaks switch
management until another path is available or the port is restored locally.

## Port flow control

`switch.<integration_name>_port_<n>_flow_control` controls IEEE 802.3x flow
control while preserving the port state and configured speed. It is enabled by
default in the entity registry.

Flow control only takes effect in the speed/duplex modes supported by the
switch firmware.

## Port speed and duplex

`select.<integration_name>_port_<n>_speed_and_duplex` provides the modes exposed
by the TL-SG105E V5 web interface:

- Auto negotiation
- 10 Mbps half or full duplex
- 100 Mbps half or full duplex
- 1 Gbps full duplex

These configuration entities are enabled by default. A forced mode must match
the device at the other end of the cable.

## IGMP and loop prevention

When supported by the firmware, the integration creates:

- `switch.<integration_name>_igmp_snooping`
- `switch.<integration_name>_igmp_report_suppression`
- `switch.<integration_name>_loop_prevention`

Changing report suppression preserves the current IGMP snooping state, and
vice versa.

## QoS

`select.<integration_name>_qos_mode` selects Port based, 802.1p based, or
DSCP/802.1p based classification when the page is supported.

`select.<integration_name>_port_<n>_qos_priority` is enabled by default and
applies priorities 1 (lowest) through 4 (highest). It can only be changed in
port-based QoS mode. Selecting a member of a static LAG updates the whole LAG,
matching the switch Web UI.

## Cable test

`button.<integration_name>_port_<n>_cable_test` starts the firmware's cable
diagnostic for one port. The matching cable-status and cable-length sensors are
refreshed when the test completes. The
`tplink_easy_smart.run_cable_diagnostic` action remains available for
automations.

A cable test can briefly interrupt the selected link. Do not run it on the Home
Assistant management path unless an independent route to the switch is
available.

## Port PoE state

`switch.<integration_name>_port_<n>_poe_enabled` enables or disables PoE while
preserving the port's priority and power limit. It is created by default when
PoE is detected and can be disabled through **Port PoE state switches** in the
integration options.

PoE changes can power-cycle connected equipment. Non-PoE models such as the
TL-SG105E do not expose these entities.
