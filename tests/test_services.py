"""Tests for service input validation and corrected display mappings."""

import pytest
import voluptuous as vol

from custom_components.tplink_easy_smart.client.classes import PoeClass
from custom_components.tplink_easy_smart.displayed_values import DISPLAYED_POE_CLASSES
from custom_components.tplink_easy_smart.services import SERVICES, ServiceNames


def _service_schema(name: ServiceNames) -> vol.Schema:
    return next(service.schema for service in SERVICES if service.name == name)


def test_service_boolean_string_is_parsed_correctly() -> None:
    schema = _service_schema(ServiceNames.SET_PORT_POE_SETTINGS)

    data = schema(
        {
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "port_number": 1,
            "enabled": "false",
            "priority": "Middle",
            "power_limit": "Auto",
        }
    )

    assert data["enabled"] is False


def test_manual_power_limit_is_validated_by_service_schema() -> None:
    schema = _service_schema(ServiceNames.SET_PORT_POE_SETTINGS)

    with pytest.raises(vol.Invalid):
        schema(
            {
                "mac_address": "AA:BB:CC:DD:EE:FF",
                "port_number": 1,
                "enabled": True,
                "priority": "Middle",
                "power_limit": "Manual",
                "manual_power_limit": 31,
            }
        )


def test_poe_class_labels_match_their_values() -> None:
    assert DISPLAYED_POE_CLASSES[PoeClass.CLASS_1] == "Class 1"
    assert DISPLAYED_POE_CLASSES[PoeClass.CLASS_2] == "Class 2"


def test_vlan_service_validates_port_lists_and_vlan_range() -> None:
    schema = _service_schema(ServiceNames.UPSERT_8021Q_VLAN)

    data = schema(
        {
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "vlan_id": "200",
            "name": "Cameras",
            "tagged_ports": ["5"],
            "untagged_ports": [1, 2],
        }
    )

    assert data["vlan_id"] == 200
    assert data["tagged_ports"] == [5]

    large_switch_data = schema(
        {
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "vlan_id": 200,
            "tagged_ports": [48],
        }
    )
    assert large_switch_data["tagged_ports"] == [48]
    with pytest.raises(vol.Invalid):
        schema(
            {
                "mac_address": "AA:BB:CC:DD:EE:FF",
                "vlan_id": 5000,
            }
        )
    with pytest.raises(vol.Invalid):
        schema(
            {
                "mac_address": "AA:BB:CC:DD:EE:FF",
                "vlan_id": 200,
                "name": "invalid name",
            }
        )

    port_vlan_schema = _service_schema(ServiceNames.UPSERT_PORT_VLAN)
    with pytest.raises(vol.Invalid):
        port_vlan_schema(
            {
                "mac_address": "AA:BB:CC:DD:EE:FF",
                "vlan_id": 1,
                "member_ports": [1],
            }
        )

    assert (
        port_vlan_schema(
            {
                "mac_address": "AA:BB:CC:DD:EE:FF",
                "vlan_id": 48,
                "member_ports": [48],
            }
        )["vlan_id"]
        == 48
    )


def test_storm_control_defaults_are_safe() -> None:
    schema = _service_schema(ServiceNames.SET_STORM_CONTROL)

    data = schema(
        {
            "mac_address": "AA:BB:CC:DD:EE:FF",
            "port_number": 1,
            "enabled": False,
        }
    )

    assert data["rate_kbps"] == 64
    assert data["unknown_unicast"] is False
    assert data["multicast"] is False
    assert data["broadcast"] is False
