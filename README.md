# TP-Link Easy Smart for Home Assistant

A local Home Assistant integration for monitoring and configuring TP-Link Easy
Smart switches through their embedded web interface.

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://www.hacs.xyz/docs/faq/custom_repositories/)
[![License](https://img.shields.io/github/license/Minims/hass_tplink_easy_smart)](https://github.com/Minims/hass_tplink_easy_smart/blob/master/LICENSE.md)
[![Release](https://img.shields.io/github/v/release/Minims/hass_tplink_easy_smart)](https://github.com/Minims/hass_tplink_easy_smart/releases/latest)
[![Release date](https://img.shields.io/github/release-date/Minims/hass_tplink_easy_smart)](https://github.com/Minims/hass_tplink_easy_smart/releases/latest)
[![Buy me a coffee](https://img.shields.io/badge/Buy_me_a_coffee-minims-FFDD00?logo=buymeacoffee&logoColor=000)](https://www.buymeacoffee.com/minims)
![Maintained](https://img.shields.io/maintenance/yes/2026)

## Features

Monitoring:

- Switch identity, network, hardware, and firmware information.
- Administrative state, link state, speed/duplex, and flow control per port.
- Exact TX/RX good and bad packet counters.
- Estimated TX, RX, and combined traffic rates.
- Cable-test status and fault distance.
- PoE state, power measurements, priorities, and limits when supported.

Configuration:

- Port enable/disable, speed/duplex, and IEEE 802.3x flow control.
- IGMP snooping, report suppression, and loop prevention.
- QoS mode and port priority.
- Port mirroring and static LAGs.
- MTU VLAN, port-based VLAN, IEEE 802.1Q VLAN, and PVID.
- Ingress/egress bandwidth limits and storm control.
- Global and per-port PoE settings on compatible PoE models.
- Reconfiguration of the address, port, credentials, HTTP/HTTPS, and TLS
  verification without deleting the device.

Unsupported pages are detected at runtime, so entities are only exposed when
the switch firmware provides the corresponding data. Advanced configuration is
available through Home Assistant actions; see [Actions](docs/services.md).

This Minims-maintained integration consolidates Easy Smart management and the
port-statistics approach from
[`bairnhard/ha-tplink-monitor`](https://github.com/bairnhard/ha-tplink-monitor)
in one asynchronous client, coordinator, and switch login session.

## Compatibility

| Model | Revision | Status | Notes |
|---|---:|:---:|---|
| [TL-SG105E](https://www.tp-link.com/en/business-networking/easy-smart-switch/tl-sg105e/) | V5 | Target | Protocol verified against firmware `1.0.0 Build 20250710 Rel.71066`; no PoE |
| [TL-SG1016PE](https://www.tp-link.com/en/business-networking/poe-switch/tl-sg1016pe/) | V1, V3 | Supported | Existing integration support, including PoE; advanced pages depend on firmware |
| [TL-SG108E](https://www.tp-link.com/en/business-networking/easy-smart-switch/tl-sg108e/) | V6 | Reported | Core monitoring supported; advanced pages depend on firmware |
| Other Easy Smart models using the same web UI | — | Best effort | Unsupported pages are skipped; compatibility reports are welcome |

The 20250710 TL-SG105E V5 firmware image was inspected to verify the CGI paths,
form field names, limits, and cable-test delay handling. A first installation
should still be tested on a non-critical port before automating configuration
writes.

## Installation

### HACS

1. In HACS, open **Integrations**, then **Custom repositories**.
2. Add `https://github.com/Minims/hass_tplink_easy_smart` as an **Integration**.
3. Install **TP-Link Easy Smart** and restart Home Assistant.
4. Open **Settings > Devices & services > Add integration** and select
   **TP-Link Easy Smart**.

### Manual

Copy `custom_components/tplink_easy_smart` from the
[latest release](https://github.com/Minims/hass_tplink_easy_smart/releases/latest)
to `<home-assistant-config>/custom_components/tplink_easy_smart`, then restart
Home Assistant.

The switch account is stored in the Home Assistant config entry. Use a local
account dedicated to Home Assistant when the model supports multiple accounts.

## Configuration and options

Select **Configure** on the integration to change polling options. Select
**Reconfigure** from the integration menu to change the connection details.
Reconfiguration verifies the target MAC address to prevent silently attaching
the entry to a different switch.

| Option | Default |
|---|---:|
| Update interval | 30 seconds |
| Assumed packet size used for rate estimates | 1500 bytes |
| [Port state switches](docs/controls.md#port-state) | Disabled |
| [Port PoE state switches](docs/controls.md#port-poe-state) | Disabled |

Good-packet counters are enabled by default. Bad-packet counters, estimated
rates, cable diagnostics, speed/duplex selects, flow-control switches, and
per-port QoS priority selects are created disabled by default. Enable only the
entities you need from the entity registry.

## Traffic-rate accuracy

Easy Smart firmware exposes packet counters, not byte counters. Rates are
therefore estimates:

```text
packet delta × assumed packet size × 8 ÷ actual elapsed time
```

The default assumed packet size is 1500 bytes. Small packets, VLAN tags, and
Ethernet overhead can make the estimate differ substantially from the wire
rate. Raw packet counters remain the exact values reported by the switch.

## Network safety

VLAN, LAG, mirroring, port-state, and rate-limit changes can interrupt the Home
Assistant management path. In particular, enabling one VLAN mode disables the
other mutually exclusive VLAN modes and may clear their configuration. The
integration validates known device limits and automatically expands LAG member
changes, but it cannot determine your intended management topology.

The integration deliberately does not expose firmware upgrade, factory reset,
reboot, switch IP configuration, or account-password changes.

## Documentation

- [Sensors and binary sensors](docs/sensors.md)
- [Switches and selects](docs/controls.md)
- [Actions and examples](docs/services.md)

## Versioning

Releases use Home Assistant-style calendar versions: `YYYY.M.patch`. The first
release of this merged feature set is `2026.9.0`.

## Development

From the repository root:

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Support the project

If this integration is useful to you, you can support its maintenance through
[Ko-fi](https://ko-fi.com/minims) or
[Buy Me a Coffee](https://www.buymeacoffee.com/minims).
