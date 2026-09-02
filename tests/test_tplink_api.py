"""Tests for the high-level TP-Link Easy Smart API."""

import asyncio

import pytest

from custom_components.tplink_easy_smart.client.classes import PortSpeed
from custom_components.tplink_easy_smart.client.tplink_api import (
    DataFormatError,
    TpLinkApi,
)


class FakeCoreApi:
    """Minimal core API returning parsed fixture data."""

    def __init__(self, data: dict) -> None:
        self.data = data

    async def get_variables(self, _path, _variables):
        return self.data

    async def get_variable(self, _path, _variable, _variable_type):
        return self.data


def _api_with_data(data: dict) -> TpLinkApi:
    api = TpLinkApi("192.0.2.1", 80, False, "admin", "secret", False)
    api._core_api = FakeCoreApi(data)
    return api


def test_parse_port_statistics() -> None:
    api = _api_with_data(
        {
            "max_port_num": 2,
            "all_info": {
                "state": [1, 0],
                "link_status": [6, 0],
                "pkts": [100, 2, 200, 3, 300, 4, 400, 5],
            },
        }
    )

    result = asyncio.run(api.get_port_statistics())

    assert len(result) == 2
    assert result[0].number == 1
    assert result[0].enabled is True
    assert result[0].link_status is PortSpeed.FULL_1000M
    assert result[0].tx_good_packets == 100
    assert result[0].tx_bad_packets == 2
    assert result[0].rx_good_packets == 200
    assert result[0].rx_bad_packets == 3
    assert result[1].enabled is False


def test_unknown_link_speed_does_not_break_statistics() -> None:
    api = _api_with_data(
        {
            "max_port_num": 1,
            "all_info": {"state": [1], "link_status": [99], "pkts": [1, 2, 3, 4]},
        }
    )

    result = asyncio.run(api.get_port_statistics())

    assert result[0].link_status is PortSpeed.UNKNOWN


def test_device_info_normalizes_mac_and_supplies_default_name() -> None:
    """Require a stable identity while tolerating an empty description."""
    api = _api_with_data(
        {
            "descriStr": [""],
            "macStr": ["aa-bb-cc-dd-ee-ff"],
            "ipStr": ["192.0.2.1"],
        }
    )

    result = asyncio.run(api.get_device_info())

    assert result.name == "TP-Link Easy Smart"
    assert result.mac == "AA:BB:CC:DD:EE:FF"


@pytest.mark.parametrize("data", [{}, {"macStr": ["not-a-mac"]}])
def test_device_info_rejects_missing_or_invalid_mac(data: dict) -> None:
    """Do not let malformed identities reach Home Assistant entity setup."""
    api = _api_with_data(data)

    with pytest.raises(DataFormatError, match="MAC address"):
        asyncio.run(api.get_device_info())


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"max_port_num": 0, "all_info": {}},
        {"max_port_num": 2, "all_info": {"pkts": [1, 2, 3, 4]}},
        {"max_port_num": 1, "all_info": {"pkts": [1, 2, "bad", 4]}},
    ],
)
def test_invalid_port_statistics_raise_data_error(data: dict) -> None:
    api = _api_with_data(data)

    with pytest.raises(DataFormatError):
        asyncio.run(api.get_port_statistics())
