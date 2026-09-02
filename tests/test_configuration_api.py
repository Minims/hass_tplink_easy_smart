"""Tests for Easy Smart configuration parsing and write requests."""

from urllib.parse import parse_qs

import pytest

from custom_components.tplink_easy_smart.client.classes import QosMode
from custom_components.tplink_easy_smart.client.coreapi import (
    APICALL_ERRCAT_DISCONNECTED,
    APICALL_ERRCODE_DISCONNECTED,
    ApiCallError,
)
from custom_components.tplink_easy_smart.client.tplink_api import ActionError, TpLinkApi


class FakeCoreApi:
    """Return parsed firmware variables and capture configuration writes."""

    def __init__(self, pages: dict[str, dict]) -> None:
        self.pages = pages
        self.get_calls: list[tuple[str, str]] = []
        self.post_calls: list[tuple[str, object]] = []
        self.authentication_invalidations = 0

    async def get_variable(self, path, variable, _variable_type):
        return self.pages[path].get(variable)

    async def get_variables(self, path, variables):
        page = self.pages[path]
        return {variable: page.get(variable) for variable, _kind in variables}

    async def get(self, path, query=None):
        self.get_calls.append((path, query or ""))
        return ""

    async def post(self, path, data=None):
        self.post_calls.append((path, data))
        return ""

    def invalidate_authentication(self) -> None:
        self.authentication_invalidations += 1


def _api(pages: dict[str, dict]) -> tuple[TpLinkApi, FakeCoreApi]:
    api = TpLinkApi("192.0.2.1", 80, False, "admin", "secret", False)
    core = FakeCoreApi(pages)
    api._core_api = core
    return api, core


def _configuration_pages() -> dict[str, dict]:
    return {
        "IgmpSnoopingRpm.htm": {"igmp_ds": {"state": 1, "suppressionState": 0}},
        "LoopPreventionRpm.htm": {"lpEn": 1},
        "CableDiagRpm.htm": {
            "maxPort": 5,
            "cablestate": [-1, 1, 2, 3, 0],
            "cablelength": [-1, 12, 20, 4, 0],
        },
        "PortMirrorRpm.htm": {
            "max_port_num": 5,
            "MirrEn": 1,
            "MirrPort": 5,
            "mirr_info": {
                "ingress": [1, 1, 0, 0, 0],
                "egress": [0, 1, 0, 0, 0],
            },
            "porttrunkid": [0, 0, 0, 0, 0],
        },
        "PortTrunkRpm.htm": {
            "portNumPerTrunk": 4,
            "trunk_conf": {
                "maxTrunkNum": 1,
                "portNum": 4,
                "portStr_g1": [1, 1, 0, 0],
            },
        },
        "Vlan8021QRpm.htm": {
            "qvlan_ds": {
                "state": 1,
                "portNum": 5,
                "count": 2,
                "maxVids": 32,
                "vids": [1, 100],
                "names": ["Default", "IoT"],
                "tagMbrs": [0, 16],
                "untagMbrs": [31, 3],
                "lagIds": [1, 1, 0, 0, 0],
            }
        },
        "Vlan8021QPvidRpm.htm": {
            "pvid_ds": {
                "state": 1,
                "portNum": 5,
                "count": 2,
                "vids": [1, 100],
                "mbrs": [31, 19],
                "pvids": [1, 1, 1, 1, 100],
                "lagIds": [1, 1, 0, 0, 0],
            }
        },
        "VlanMtuRpm.htm": {"mtu_ds": {"state": 0, "portNum": 5, "uplinkPort": 1}},
        "VlanPortBasicRpm.htm": {
            "pvlan_ds": {
                "state": 1,
                "portNum": 5,
                "count": 1,
                "vids": [2],
                "mbrs": [5],
                "lagIds": [1, 1, 0, 0, 0],
            }
        },
        "QosBasicRpm.htm": {
            "portNumber": 5,
            "qosMode": 0,
            "pPri": [1, 2, 3, 4, 1],
            "pTrunk": [1, 1, 0, 0, 0],
        },
        "QosBandWidthControlRpm.htm": {
            "portNumber": 5,
            "bcInfo": [100, 200, 1, 100, 200, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        },
        "QosStormControlRpm.htm": {
            "portNumber": 5,
            "scInfo": [64, 5, 1, 64, 5, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        },
    }


async def test_parse_configuration_pages() -> None:
    """Parse mirroring, LAG, VLAN and QoS state from firmware variables."""
    api, _core = _api(_configuration_pages())

    igmp = await api.get_igmp_snooping()
    assert igmp.enabled is True
    assert igmp.report_suppression is False
    assert (await api.get_loop_prevention()).enabled is True

    cables = await api.get_cable_diagnostics()
    assert cables[1].status.name == "NORMAL"
    assert cables[1].length_m == 12

    mtu = await api.get_mtu_vlan()
    assert mtu.uplink_port == 1
    port_vlans = await api.get_port_vlans()
    assert port_vlans.vlans[0].member_ports == [1, 3]

    mirror = await api.get_port_mirror()
    assert mirror.destination_port == 5
    assert mirror.ingress_ports == [1, 2]
    assert mirror.egress_ports == [2]

    lag = await api.get_lags()
    assert lag.groups == {1: [1, 2]}
    assert lag.ports_per_group == 4

    vlans = await api.get_8021q_vlans()
    assert vlans.vlans[1].tagged_ports == [5]
    assert vlans.vlans[1].untagged_ports == [1, 2]

    qos = await api.get_qos()
    assert qos.mode is QosMode.PORT_BASED
    assert qos.priorities == [1, 2, 3, 4, 1]

    bandwidth = await api.get_bandwidth_controls()
    assert bandwidth[0].ingress_kbps == 100
    assert bandwidth[0].trunk_group == 1

    storm = await api.get_storm_controls()
    assert storm[0].unknown_unicast is True
    assert storm[0].multicast is False
    assert storm[0].broadcast is True


async def test_vlan_write_is_complete_and_strictly_validated() -> None:
    """Encode every port membership and reject unsafe VLAN changes."""
    api, core = _api(_configuration_pages())

    await api.upsert_8021q_vlan(200, "Cameras", [5], [1])

    path, query = core.get_calls[-1]
    params = parse_qs(query)
    assert path == "qvlanSet.cgi"
    assert params["qvlan_add"] == ["Add/Modify"]
    assert [params[f"selType_{port}"][0] for port in range(1, 6)] == [
        "0",
        "0",
        "2",
        "2",
        "1",
    ]

    with pytest.raises(ActionError, match="both tagged and untagged"):
        await api.upsert_8021q_vlan(200, "Bad", [1], [1])
    with pytest.raises(ActionError, match="at most 10"):
        await api.upsert_8021q_vlan(200, "invalid name", [5], [1])
    with pytest.raises(ActionError, match="VLAN 1"):
        await api.delete_8021q_vlan(1)
    with pytest.raises(ActionError, match="VLAN 1"):
        await api.delete_port_vlan(1)


async def test_port_vlan_and_pvid_expand_lag_members() -> None:
    """Match the web UI by applying VLAN and PVID changes to whole LAGs."""
    api, core = _api(_configuration_pages())

    await api.upsert_port_vlan(3, [1])
    path, query = core.get_calls[-1]
    assert path == "pvlanSet.cgi"
    assert parse_qs(query)["selPorts"] == ["1", "2"]

    await api.set_pvid([1], 100)
    path, query = core.get_calls[-1]
    assert path == "vlanPvidSet.cgi"
    assert parse_qs(query)["pbm"] == ["3"]

    with pytest.raises(ActionError, match="not members"):
        await api.set_pvid([3], 100)
    with pytest.raises(ActionError, match="between 2 and 5"):
        await api.upsert_port_vlan(10, [1])


async def test_cable_diagnostic_uses_firmware_checkbox_fields(monkeypatch) -> None:
    """Submit the exact GET form embedded in the 20250710 firmware."""
    api, core = _api(_configuration_pages())

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(
        "custom_components.tplink_easy_smart.client.tplink_api.asyncio.sleep",
        no_sleep,
    )
    await api.run_cable_diagnostic(3)

    path, query = core.get_calls[-1]
    assert path == "cable_diag_get.cgi"
    assert parse_qs(query) == {"chk_3": ["3"], "Apply": ["Apply"]}


async def test_mtu_vlan_uses_separate_mode_and_uplink_forms() -> None:
    """Do not mix fields from the firmware's two independent MTU forms."""
    pages = _configuration_pages()
    pages["VlanMtuRpm.htm"]["mtu_ds"]["state"] = 1
    api, core = _api(pages)

    await api.set_mtu_vlan(True, 5)

    path, query = core.get_calls[-1]
    assert path == "mtuVlanSet.cgi"
    assert parse_qs(query) == {"uplinkPort": ["5"], "mtu_uplink": ["Apply"]}


async def test_mirror_and_lag_writes_clear_stale_state_and_validate_limits() -> None:
    """Clear removed mirror sources and enforce model-specific LAG ports."""
    api, core = _api(_configuration_pages())

    await api.set_port_mirror(True, 5, [3], [3])
    source_updates = [
        parse_qs(query)
        for path, query in core.get_calls
        if path == "mirrored_port_set.cgi"
    ]
    assert {int(item["mirroredport"][0]) for item in source_updates} == {1, 2, 3}
    cleared = next(item for item in source_updates if item["mirroredport"] == ["1"])
    assert cleared["ingressState"] == ["0"]
    assert cleared["egressState"] == ["0"]

    await api.set_lag(1, [1, 2, 4])
    lag_query = parse_qs(core.get_calls[-1][1])
    assert lag_query["portid"] == ["1", "2", "4"]

    with pytest.raises(ActionError, match="between 1 and 4"):
        await api.set_lag(1, [1, 5])


async def test_qos_writes_expand_lag_and_preserve_storm_type_fields() -> None:
    """Apply port settings to all LAG members and preserve repeated fields."""
    api, core = _api(_configuration_pages())

    await api.set_qos_priority(1, 4)
    assert core.post_calls[-1] == (
        "qos_port_priority_set.cgi",
        {"port_queue": 3, "apply": "Apply", "sel_1": 1, "sel_2": 1},
    )

    await api.set_storm_control(1, True, 900, True, False, True)
    path, data = core.post_calls[-1]
    assert path == "qos_storm_set.cgi"
    assert isinstance(data, list)
    assert [value for key, value in data if key == "stormType"] == [1, 4]
    assert ("sel_1", 1) in data
    assert ("sel_2", 1) in data


async def test_configuration_disconnect_is_treated_as_applied() -> None:
    """Accept the web-server restart that some write CGIs trigger."""
    api, core = _api(_configuration_pages())

    async def disconnect_after_apply(_path, query=None):
        raise ApiCallError(
            "server restarted",
            APICALL_ERRCODE_DISCONNECTED,
            APICALL_ERRCAT_DISCONNECTED,
        )

    core.get = disconnect_after_apply
    await api.set_port_vlan_enabled(True)
    assert core.authentication_invalidations == 2
