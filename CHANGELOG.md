# Changelog

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
