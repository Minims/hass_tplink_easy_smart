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

- Automatic local discovery through the credential-free ESCP discovery request.
- Switch identity, MAC connection, network, hardware, and firmware information.
- Administrative state, link state, speed/duplex, and flow control per port.
- Exact TX/RX good and bad packet counters.
- Estimated TX, RX, and combined traffic rates.
- Per-port cable-test buttons, status, and fault distance.
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

| Model | Revision | Validation status | Notes |
|---|---:|:---:|---|
| [TL-SG105E](https://www.tp-link.com/en/business-networking/easy-smart-switch/tl-sg105e/) | V5 | Discovery verified | ESCP discovery was validated on firmware `1.0.0 Build 20250710 Rel.71066`; CGI paths and forms were reviewed in the same firmware; full Home Assistant validation is pending; no PoE |
| [TL-SG1016PE](https://www.tp-link.com/en/business-networking/poe-switch/tl-sg1016pe/) | V1, V3 | Previously confirmed | Core monitoring, port control, and PoE were confirmed by the upstream integration; the new advanced actions have not been revalidated |
| [TL-SG108E](https://www.tp-link.com/en/business-networking/easy-smart-switch/tl-sg108e/) | V6 | Previously confirmed | Network information and port status were confirmed by the upstream integration; configuration actions have not been revalidated |
| Other Easy Smart models using the same legacy web UI | — | Untested | They may work through runtime capability detection, but compatibility is not guaranteed |

These labels distinguish physical-device reports from static firmware analysis.
Automated tests use simulated switch responses and do not establish hardware
compatibility by themselves.

ESCP discovery was tested successfully on a physical TL-SG105E V5 running the
20250710 firmware. Its firmware image was also statically inspected to map CGI
paths, form field names, limits, and the cable-test delay. This reduces
integration risk but does not validate every monitoring and configuration path.
Perform the first configuration writes on a non-critical port and keep an
independent management path available.

## Installation

### HACS

1. In HACS, open **Integrations**, then **Custom repositories**.
2. Add `https://github.com/Minims/hass_tplink_easy_smart` as an **Integration**.
3. Install **TP-Link Easy Smart** and restart Home Assistant.
4. Open **Settings > Devices & services > Add integration** and select
   **TP-Link Easy Smart**.

Setup scans the enabled local IPv4 broadcast domains for Easy Smart switches.
Select a discovered device and enter its credentials, or choose manual
configuration. Discovery uses UDP ports `29808` and `29809`, does not transmit
credentials, and normally does not cross routers or VLAN boundaries.

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
| [Port state switches](docs/controls.md#port-state) | Enabled |
| [Port PoE state switches](docs/controls.md#port-poe-state) | Enabled |

Good-packet counters, estimated rates, cable diagnostics, and all available
configuration entities are enabled by default. Bad-packet counters remain
disabled by default and can be enabled from the entity registry.

Upgrading from an older release re-enables these entities on every port when
they were disabled by the integration. Entities disabled manually by a user
remain disabled.

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

VLAN, LAG, mirroring, port-state, cable-test, and rate-limit operations can
interrupt traffic or the Home Assistant management path. In particular,
enabling one VLAN mode disables the other mutually exclusive VLAN modes and may
clear their configuration. The integration validates known device limits and
automatically expands LAG member changes, but it cannot determine your intended
management topology.

The integration deliberately does not expose firmware upgrade, factory reset,
reboot, switch IP configuration, or account-password changes.

## Documentation

- [Sensors and binary sensors](docs/sensors.md)
- [Switches and selects](docs/controls.md)
- [Actions and examples](docs/services.md)

## Versioning

Releases use Home Assistant-style calendar versions: `YYYY.M.patch`. The merged
feature set starts at `2026.9.0`.

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
