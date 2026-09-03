# Sensors

## Network information

`sensor.<integration_name>_network_info` reports the switch IP address and
exposes these attributes:

| Attribute | Description |
|---|---|
| `mac` | Switch MAC address |
| `gateway` | Default gateway |
| `netmask` | Subnet mask |

The MAC address is also registered as the native network connection of the
Home Assistant device and appears in its device information.

## Port packet statistics

When `PortStatisticsRpm.htm` is supported, the integration creates the following
diagnostic sensors for every detected port. If the first request fails
temporarily, the entities are created as unavailable and recover automatically:

| Entity suffix | Value | Enabled by default |
|---|---|:---:|
| `port_<n>_tx_good_packets` | Successfully transmitted packets | Yes |
| `port_<n>_rx_good_packets` | Successfully received packets | Yes |
| `port_<n>_tx_bad_packets` | Failed transmitted packets | No |
| `port_<n>_rx_bad_packets` | Failed received packets | No |
| `port_<n>_tx_estimated_bandwidth` | Estimated transmit rate in Mbps | Yes |
| `port_<n>_rx_estimated_bandwidth` | Estimated receive rate in Mbps | Yes |
| `port_<n>_estimated_bandwidth` | Combined estimated TX and RX rate in Mbps | Yes |

The full entity ID starts with `sensor.<integration_name>_`. Bad-packet sensors
can be enabled from **Settings > Devices & services > Entities**.

Packet counters are exact switch values and use Home Assistant's
`total_increasing` state class. Counter resets and 32-bit wraps are handled when
calculating rates.

### Estimated bandwidth

The firmware does not expose byte counters. A rate is estimated from the change
in good-packet counters, the actual elapsed polling time and the configured
assumed packet size:

```text
Mbps = packet delta × assumed packet size × 8 ÷ elapsed seconds ÷ 1,000,000
```

The default assumed size is 1500 bytes. It represents an assumed average packet
size, despite often being called MTU in other tools. The estimate can be very
different from real traffic when packets are smaller, and it excludes or
approximates link-layer overhead. Rate sensors remain unavailable until two
successful samples have been collected.

## PoE consumption

`sensor.<integration_name>_poe_consumption` reports the current total PoE
consumption in watts. It is created only when PoE support is detected.

| Attribute | Description |
|---|---|
| `power_limit_w` | Configured system PoE limit |
| `power_remain_w` | Remaining power before reaching the limit |

# Binary sensors

## Port status

`binary_sensor.<integration_name>_port_<n>_state` is on when the port is enabled
and has an active link. An administratively disabled or disconnected port is
reported as off; the entity becomes unavailable only when data cannot be read.

| Attribute | Description |
|---|---|
| `number` | Port number |
| `enabled` | Administrative state |
| `flow_control_config` | Configured flow-control state |
| `flow_control_actual` | Negotiated flow-control state |
| `speed` | Current connection speed |
| `speed_config` | Configured connection speed |
| `tx_estimated_bandwidth_mbps` | Estimated transmit rate in Mbps |
| `rx_estimated_bandwidth_mbps` | Estimated receive rate in Mbps |
| `total_estimated_bandwidth_mbps` | Combined estimated rate in Mbps |

Possible speed values are `Link Down`, `Auto`, `10MH`, `10MF`, `100MH`,
`100MF`, and `1000MF`.

## Port PoE status

`binary_sensor.<integration_name>_port_<n>_poe_state` is created only for PoE
ports. It is on while PoE is enabled and the power status is not `Off`.

| Attribute | Description |
|---|---|
| `priority` | Port power priority |
| `power_limit` | Automatic, class-based or manual limit |
| `power_w` | Current power in watts |
| `current_ma` | Current in milliamps |
| `voltage_v` | Voltage in volts |
| `pd_class` | Detected powered-device class |
| `power_status` | Current PoE status |

Possible power statuses include `On`, `Off`, `Turning on`, `Overload`, `Short`,
`Non-standard PD`, `Voltage high`, `Voltage low`, `Hardware fault`, and
`Overtemperature`.

## Cable diagnostics

The integration creates two diagnostic sensors per detected physical port,
enabled by default:

| Entity suffix | Value |
|---|---|
| `port_<n>_cable_status` | `not tested`, `no cable`, `normal`, `open`, `short`, `open short`, `cross cable`, or `unknown` |
| `port_<n>_cable_length` | Cable length or fault distance in metres |

Press `button.<integration_name>_port_<n>_cable_test` or call
`tplink_easy_smart.run_cable_diagnostic` to run the TDR test and refresh these
values. A sensor remains unavailable until the firmware returns a diagnostic
result. Testing can briefly interrupt the selected port. The integration uses
the delay returned by the firmware before reading the result.

## VLAN and LAG configuration

Enabled-by-default diagnostic sensors expose configuration even when no custom
VLAN or LAG exists:

| Sensor suffix | State | Main attributes |
|---|---|---|
| `lag_configuration` | Number of configured LAGs (`0` when empty) | `port_count`, `max_groups`, `ports_per_group`, `groups` |
| `mtu_vlan_configuration` | `enabled` or `disabled` | `port_count`, `uplink_port` |
| `port_vlan_configuration` | `enabled` or `disabled` | `port_count`, `vlans` |
| `802_1q_vlan_configuration` | `enabled` or `disabled` | `port_count`, `max_vlans`, `vlans` |
| `802_1q_pvid_configuration` | `enabled` or `disabled` | `port_count`, `port_pvids` |

An explicitly unsupported firmware page is omitted. A temporary read failure
makes the corresponding sensor unavailable until a later poll succeeds. VLAN
and LAG changes remain available through the actions documented in
[Actions](services.md).
