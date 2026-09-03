# Changelog

## 2026.9.7

- Fix cable diagnostics on TL-SG105E V5 firmware 20250710 by parsing the
  JavaScript array literals used for `cablestate` and `cablelength`.
- Apply the same parser fix to QoS, bandwidth-control, storm-control and port
  mirroring pages that may use literal arrays.

## 2026.9.6

- Fix LED-state parsing for firmware pages that separate JavaScript variables
  with newlines instead of semicolons.
- Replace the unavailable loop-prevention icon with the supported
  `mdi:shield-sync-outline` icon.

## 2026.9.5

- Add an enabled-by-default front-panel LED switch and reboot button using the
  exact forms verified in TL-SG105E V5 firmware
  `1.0.0 Build 20250710 Rel.71066`.
- Add enabled-by-default diagnostic summaries for empty or configured LAGs,
  MTU VLAN, port VLAN, 802.1Q VLAN and per-port PVID values.
- Add a direct **Open HACS repository** button to the installation guide.
- Keep statistics, estimated-bandwidth, IGMP, loop-prevention and QoS entities
  available for automatic recovery after a transient initial probe failure.
- Fail and retry integration setup when the core port-state read fails instead
  of completing setup without any per-port entities.
- Clarify negotiated speed, estimated-bandwidth attributes, cable diagnostics,
  entity defaults and post-upgrade behavior in the README.

## 2026.9.4

- Add estimated TX, RX and combined bandwidth in Mbps to every port-state
  binary sensor's attributes, while retaining the dedicated metric sensors for
  history, graphs and automations.

## 2026.9.3

- Always create cable-test buttons and diagnostic sensors for every physical
  port, allowing a first test to recover when the initial capability probe
  fails or returns incomplete data.
- Validate cable-test port numbers against the coordinator's detected ports.

## 2026.9.2

- Re-enable every existing entity whose default changed in 2026.9.1, including
  TX, RX and combined estimated bandwidth, cable diagnostics, flow control,
  speed/duplex and QoS priority on every port, plus IGMP report suppression.
  Entities disabled explicitly by the user remain disabled.

## 2026.9.1

- Add credential-free ESCP discovery on the local IPv4 broadcast domains, with
  a manual configuration fallback, validated on a physical TL-SG105E V5 running
  firmware `1.0.0 Build 20250710 Rel.71066`.
- Expose the normalized switch MAC as a native Home Assistant device
  connection.
- Add an enabled-by-default cable-test button for every supported port while
  retaining the cable-diagnostic action for automations.
- Enable estimated bandwidth, cable diagnostic sensors, port state, PoE, flow
  control, speed/duplex, IGMP suppression and QoS priority entities by default.
- Clarify which compatibility claims come from physical devices, upstream
  reports or static firmware analysis.

## 2026.9.0

- Merge monitoring and switch-management features into one integration and
  one asynchronous login session.
- Add per-port TX/RX good and bad packet counters.
- Add configurable estimated TX, RX and combined bandwidth sensors.
- Add cable-test status and distance sensors.
- Add configuration entities for port speed/duplex, flow control, IGMP
  snooping, IGMP report suppression, loop prevention and QoS.
- Add actions for cable diagnostics, mirroring, static LAG, MTU/port/802.1Q
  VLAN, PVID, QoS, bandwidth control and storm control.
- Add device connection reconfiguration with target-MAC verification.
- Verify the extended CGI protocol against TL-SG105E V5 firmware
  `1.0.0 Build 20250710 Rel.71066`.
- Handle LAG-aware VLAN, PVID, QoS, bandwidth and storm-control writes.
- Read the firmware's per-LAG port limit instead of assuming four members.
- Handle the embedded Web-server restart that follows some configuration
  writes without reporting a false failure.
- Use actual sample timing and handle packet-counter reset and 32-bit wrap.
- Add French config-flow translations and complete integration strings.
- Use Home Assistant-managed asynchronous HTTP sessions.
- Fix PoE service dispatch, manual limit validation and MAC matching.
- Fix disabled ports being incorrectly marked unavailable.
- Fix synchronous switch methods that could deadlock Home Assistant.
- Harden firmware parsing, authentication, session cleanup and setup rollback.
- Reject malformed device identities before entity setup and clear stale optional
  state after polling failures.
- Validate port and LAG limits against the connected switch instead of a
  service-level 32-port ceiling.
- Fix PoE class labels and several indexing/default-value errors.
- Remove unused legacy helpers and pass config entries explicitly to the update
  coordinator.
- Add tests against the current Home Assistant API and automated validation.
- Move repository metadata, links and code ownership to Minims.
- Adopt Home Assistant-style `YYYY.M.patch` versioning and add Minims funding.
