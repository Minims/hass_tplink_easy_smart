# Actions

Home Assistant exposes the following actions under the
`tplink_easy_smart` domain. Every action targets a switch by its normalized MAC
address, for example `AA:BB:CC:DD:EE:FF`.

| Action | Purpose |
|---|---|
| `set_general_poe_limit` | Set the total PoE budget |
| `set_port_poe_settings` | Set per-port PoE state, priority, and limit |
| `set_igmp_snooping` | Set snooping and report suppression together |
| `set_loop_prevention` | Enable or disable loop prevention |
| `run_cable_diagnostic` | Run TDR on one port and refresh cable sensors |
| `set_port_mirror` | Replace the destination and ingress/egress sources |
| `set_lag`, `delete_lag` | Create, replace, or remove a static LAG |
| `set_mtu_vlan` | Set MTU VLAN mode and its uplink |
| `set_port_vlan_mode` | Enable or disable port-based VLAN mode |
| `upsert_port_vlan`, `delete_port_vlan` | Manage port-based VLAN membership |
| `set_8021q_vlan_mode` | Enable or disable IEEE 802.1Q VLAN mode |
| `upsert_8021q_vlan`, `delete_8021q_vlan` | Manage tagged and untagged VLAN membership |
| `set_pvid` | Assign a VLAN PVID to physical ports |
| `set_qos_mode`, `set_qos_priority` | Configure classification and port priority |
| `set_bandwidth_control` | Set ingress and egress rate limits |
| `set_storm_control` | Limit unknown-unicast, multicast, and broadcast traffic |

The actions appear with field selectors in **Developer tools > Actions**. YAML
lists use one-based physical port numbers, for example `[1, 2]`.

## Examples

### Cable diagnostic

The selected link can be interrupted briefly while TDR runs. Results are
published to the enabled-by-default cable sensors. The same diagnostic can be
started from `button.<integration_name>_port_<n>_cable_test`.

```yaml
action: tplink_easy_smart.run_cable_diagnostic
data:
  mac_address: AA:BB:CC:DD:EE:FF
  port_number: 3
```

### Port mirroring

This replaces the complete mirror configuration and clears sources omitted
from the call. The destination cannot be a source or a LAG member.

```yaml
action: tplink_easy_smart.set_port_mirror
data:
  mac_address: AA:BB:CC:DD:EE:FF
  enabled: true
  destination_port: 5
  ingress_ports: [1, 2]
  egress_ports: [2]
```

To disable mirroring, set `enabled: false`; source lists and destination can be
omitted.

### Static LAG

The integration reads the model-specific group and port limits before writing.
The TL-SG105E V5 supports LAG 1 with two to four members selected from ports
1–4.

```yaml
action: tplink_easy_smart.set_lag
data:
  mac_address: AA:BB:CC:DD:EE:FF
  group_id: 1
  ports: [1, 2]
```

### IEEE 802.1Q VLAN

Enable 802.1Q mode first. Ports omitted from both lists become non-members.
Names contain up to 10 ASCII letters, digits, hyphens, or underscores. LAG
members are expanded automatically. VLAN 1 can be modified but cannot be
deleted, and every port must remain in at least one VLAN.

```yaml
action: tplink_easy_smart.upsert_8021q_vlan
data:
  mac_address: AA:BB:CC:DD:EE:FF
  vlan_id: 100
  name: IoT
  tagged_ports: [5]
  untagged_ports: [1, 2]
```

Assign the PVID only after the selected ports are members of that VLAN:

```yaml
action: tplink_easy_smart.set_pvid
data:
  mac_address: AA:BB:CC:DD:EE:FF
  ports: [1, 2]
  vlan_id: 100
```

### Port-based VLAN

On this firmware, port-based VLAN IDs range from 2 to the number of physical
ports. Enabling this mode disables the mutually exclusive MTU and 802.1Q VLAN
modes and can clear their settings.

```yaml
action: tplink_easy_smart.upsert_port_vlan
data:
  mac_address: AA:BB:CC:DD:EE:FF
  vlan_id: 2
  member_ports: [1, 5]
```

### Bandwidth and storm control

Rates are in kbit/s. Zero means unlimited for bandwidth control. Per-port QoS,
bandwidth, and storm changes apply to every member when the selected port is in
a static LAG.

```yaml
action: tplink_easy_smart.set_bandwidth_control
data:
  mac_address: AA:BB:CC:DD:EE:FF
  port_number: 1
  ingress_kbps: 100000
  egress_kbps: 50000
```

```yaml
action: tplink_easy_smart.set_storm_control
data:
  mac_address: AA:BB:CC:DD:EE:FF
  port_number: 1
  enabled: true
  rate_kbps: 1024
  unknown_unicast: true
  multicast: true
  broadcast: true
```

### PoE

```yaml
action: tplink_easy_smart.set_port_poe_settings
data:
  mac_address: AA:BB:CC:DD:EE:FF
  port_number: 1
  enabled: true
  priority: Middle
  power_limit: Manual
  manual_power_limit: 12.3
```

`manual_power_limit` is required only when `power_limit` is `Manual` and must
be between 0.1 and 30 watts.

## Safety and validation

The client reads current state before every advanced write, validates physical
ports and firmware limits, prevents tagged/untagged overlap, preserves repeated
form fields, and treats the expected Web-server restart after some mode changes
as a successful apply.

These checks do not know which VLAN carries Home Assistant. Keep local access
to the switch available when testing VLAN, LAG, mirror, port-state, or rate-limit
changes.
