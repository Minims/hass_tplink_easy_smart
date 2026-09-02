# Sensors

## Network information

`sensor.<integration_name>_network_info` reports the switch IP address and
exposes these attributes:

| Attribute | Description |
|---|---|
| `mac` | Switch MAC address |
| `gateway` | Default gateway |
| `netmask` | Subnet mask |

## Port packet statistics

The integration reads `PortStatisticsRpm.htm` and creates the following
diagnostic sensors for every detected port:

| Entity suffix | Value | Enabled by default |
|---|---|:---:|
| `port_<n>_tx_good_packets` | Successfully transmitted packets | Yes |
| `port_<n>_rx_good_packets` | Successfully received packets | Yes |
| `port_<n>_tx_bad_packets` | Failed transmitted packets | No |
| `port_<n>_rx_bad_packets` | Failed received packets | No |
| `port_<n>_tx_estimated_bandwidth` | Estimated transmit rate in Mbps | No |
| `port_<n>_rx_estimated_bandwidth` | Estimated receive rate in Mbps | No |
| `port_<n>_estimated_bandwidth` | Combined estimated TX and RX rate in Mbps | No |

The full entity ID starts with `sensor.<integration_name>_`. Disabled entities
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

When the firmware exposes its cable-test page, the integration creates two
diagnostic sensors per port, disabled by default:

| Entity suffix | Value |
|---|---|
| `port_<n>_cable_status` | `not tested`, `no cable`, `normal`, `open`, `short`, `open short`, `cross cable`, or `unknown` |
| `port_<n>_cable_length` | Cable length or fault distance in metres |

Call `tplink_easy_smart.run_cable_diagnostic` to run the TDR test and refresh
these values. Testing can briefly interrupt the selected port. The integration
uses the delay returned by the firmware before reading the result.
