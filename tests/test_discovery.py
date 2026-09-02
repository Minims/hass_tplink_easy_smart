"""Tests for credential-free Easy Smart UDP discovery."""

import asyncio
import struct
from ipaddress import IPv4Address

import pytest

from custom_components.tplink_easy_smart.client import discovery

_CLIENT_MAC = bytes.fromhex("020000000001")
_SWITCH_MAC = bytes.fromhex("AABBCCDDEEFF")
_SEQUENCE = 42


def _response_packet(
    *,
    client_mac: bytes = _CLIENT_MAC,
    switch_mac: bytes = _SWITCH_MAC,
    sequence: int = _SEQUENCE,
) -> bytes:
    """Build an independently assembled discovery response fixture."""
    values = (
        (1, b"TL-SG105E\x00"),
        (2, b"Office switch\x00"),
        (3, switch_mac),
        (4, IPv4Address("192.0.2.10").packed),
        (7, b"1.0.0 Build 20250710 Rel.71066\x00"),
        (8, b"TL-SG105E 5.0\x00"),
    )
    payload = b"".join(
        struct.pack("!HH", value_type, len(value)) + value
        for value_type, value in values
    )
    packet_length = discovery._HEADER_LENGTH + len(payload) + len(discovery._PACKET_END)
    header = struct.pack(
        discovery._HEADER_FORMAT,
        1,
        discovery._DISCOVERY_RESPONSE,
        switch_mac,
        client_mac,
        sequence,
        0,
        packet_length,
        0,
        0,
        0,
        0,
    )
    return discovery._crypt(header + payload + discovery._PACKET_END)


def test_discovery_request_matches_known_escp_vector() -> None:
    """Generate the exact encrypted request for a fixed MAC and sequence."""
    assert discovery._build_discovery_packet(_CLIENT_MAC, 1).hex() == (
        "5d746a047dbeb0b2f96b06c314947e94422ba2f5d78baeed508f463dc202909aa4ec81c6"
    )


def test_parse_discovery_response() -> None:
    """Read identity, addressing, and version TLVs from a valid reply."""
    result = discovery._parse_discovery_response(
        _response_packet(), "192.0.2.10", _CLIENT_MAC, _SEQUENCE
    )
    assert result == discovery.DiscoveredSwitch(
        host="192.0.2.10",
        mac="AA:BB:CC:DD:EE:FF",
        model="TL-SG105E",
        name="Office switch",
        firmware="1.0.0 Build 20250710 Rel.71066",
        hardware="TL-SG105E 5.0",
    )


def test_parse_rejects_a_response_for_another_scan() -> None:
    """Ignore broadcasts addressed to another discovery client."""
    assert (
        discovery._parse_discovery_response(
            _response_packet(client_mac=bytes.fromhex("020000000002")),
            "192.0.2.10",
            _CLIENT_MAC,
            _SEQUENCE,
        )
        is None
    )


async def test_async_discovery_sends_broadcast_and_collects_response(
    monkeypatch,
) -> None:
    """Bind the ESCP client port and collect replies from the switch port."""
    loop = asyncio.get_running_loop()
    sent: list[tuple[bytes, tuple[str, int]]] = []
    closed = False

    class FakeTransport:
        def __init__(self, protocol) -> None:
            self.protocol = protocol

        def sendto(self, data: bytes, target: tuple[str, int]) -> None:
            sent.append((data, target))
            self.protocol.datagram_received(
                _response_packet(), ("192.0.2.10", discovery._SWITCH_PORT)
            )

        def close(self) -> None:
            nonlocal closed
            closed = True

    async def create_datagram_endpoint(protocol_factory, **kwargs):
        assert kwargs["local_addr"] == ("0.0.0.0", discovery._CLIENT_PORT)
        assert kwargs["allow_broadcast"] is True
        protocol = protocol_factory()
        return FakeTransport(protocol), protocol

    monkeypatch.setattr(loop, "create_datagram_endpoint", create_datagram_endpoint)
    monkeypatch.setattr(discovery, "_random_client_mac", lambda: _CLIENT_MAC)
    monkeypatch.setattr(discovery.secrets, "randbelow", lambda _limit: _SEQUENCE)

    result = await discovery.async_discover_switches(
        broadcast_addresses=["192.0.2.255"], timeout=0.01
    )

    assert [item.host for item in result] == ["192.0.2.10"]
    assert sent == [
        (
            discovery._build_discovery_packet(_CLIENT_MAC, _SEQUENCE),
            ("192.0.2.255", discovery._SWITCH_PORT),
        )
    ]
    assert closed


async def test_async_discovery_reports_socket_failure(monkeypatch) -> None:
    """Convert an occupied UDP client port into a controlled discovery error."""
    loop = asyncio.get_running_loop()

    async def create_datagram_endpoint(*_args, **_kwargs):
        raise OSError("address already in use")

    monkeypatch.setattr(loop, "create_datagram_endpoint", create_datagram_endpoint)
    with pytest.raises(discovery.DiscoveryError, match="29809"):
        await discovery.async_discover_switches(timeout=0)
