"""Read-only discovery for TP-Link Easy Smart switches."""

from __future__ import annotations

import asyncio
import secrets
import struct
from collections.abc import Iterable
from dataclasses import dataclass
from ipaddress import AddressValueError, IPv4Address
from typing import Final, cast

_BROADCAST_ADDRESS: Final = "255.255.255.255"
_SWITCH_PORT: Final = 29808
_CLIENT_PORT: Final = 29809
_HEADER_FORMAT: Final = "!BB6s6sHIHHHHI"
_HEADER_LENGTH: Final = struct.calcsize(_HEADER_FORMAT)
_PACKET_END: Final = b"\xff\xff\x00\x00"
_DISCOVERY_REQUEST: Final = 0
_DISCOVERY_RESPONSE: Final = 2
_MAX_RESPONSES: Final = 64
_MAX_QUEUED_PACKETS: Final = 128
_MAX_PACKET_SIZE: Final = 4096

# Static permutation used by the Easy Smart Configuration Protocol. It only
# obfuscates discovery datagrams and does not provide confidentiality.
_CIPHER_STATE: Final = bytes.fromhex(
    "bf9be3ca63a24f683112bea41e4cbd831734566acf7d7ea9c41cac3abc84a003"
    "247890a80ce7742c29616cd52ac62094da6bf770cc0e42445be0ceeb2182cbb20"
    "186c74ef97b079149d0d1644a7348760816f393406005573c71e9981fdb8faee"
    "899f59efe46aa4b4dd7d33b4785d69d97062e515e88a6d2042bf11ddfb0433fb"
    "a898128f8ff370f3eb7de69ecc57f36b3c2e5b9255aedb8199cad1abbdc02e10"
    "0f032fbd4fda711c1cdb115b5f652e22665a3b6f25c140b5f0de610797c6dc3"
    "752762ef54388ba12fc93387fa0a13962d6f1b188e505553ea8ad8395d419a8d"
    "7a228c80ee58590992ab9535663d7245d9af67e423b4fcc8c0a59fddf46e7730"
)


class DiscoveryError(Exception):
    """Raised when the discovery socket cannot be opened."""


@dataclass(frozen=True, slots=True)
class DiscoveredSwitch:
    """Identity returned by an Easy Smart discovery response."""

    host: str
    mac: str
    model: str
    name: str
    firmware: str | None = None
    hardware: str | None = None


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    """Collect UDP datagrams without doing parsing in the callback."""

    def __init__(self, queue: asyncio.Queue[tuple[bytes, tuple[str, int]]]) -> None:
        self._queue = queue

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Queue one received datagram."""
        if len(data) <= _MAX_PACKET_SIZE and not self._queue.full():
            self._queue.put_nowait((data, addr))


def _crypt(data: bytes) -> bytes:
    """Encode or decode an ESCP datagram using its symmetric stream cipher."""
    output = bytearray(data)
    state = bytearray(_CIPHER_STATE)
    j = 0
    for index in range(len(output)):
        i = (index + 1) & 0xFF
        j = (j + state[i]) & 0xFF
        state[i], state[j] = state[j], state[i]
        output[index] ^= state[(state[i] + state[j]) & 0xFF]
    return bytes(output)


def _build_discovery_packet(client_mac: bytes, sequence: int) -> bytes:
    """Build a credential-free ESCP discovery request."""
    if len(client_mac) != 6:
        raise ValueError("The discovery client MAC must contain six bytes")
    packet_length = _HEADER_LENGTH + len(_PACKET_END)
    header = struct.pack(
        _HEADER_FORMAT,
        1,
        _DISCOVERY_REQUEST,
        bytes(6),
        client_mac,
        sequence,
        0,
        packet_length,
        0,
        0,
        0,
        0,
    )
    return _crypt(header + _PACKET_END)


def _decode_text(value: bytes) -> str:
    """Decode a null-terminated firmware string."""
    value = value.split(b"\x00", 1)[0]
    for encoding in ("utf-8", "gb18030"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode("latin-1", errors="replace")


def _format_mac(value: bytes) -> str:
    """Format a six-byte MAC address."""
    if len(value) != 6 or not any(value) or value == b"\xff" * 6:
        raise ValueError("Invalid switch MAC address")
    return ":".join(f"{part:02X}" for part in value)


def _valid_host(value: str) -> str | None:
    """Return a usable IPv4 address or None."""
    try:
        address = IPv4Address(value)
    except AddressValueError:
        return None
    if address.is_unspecified or address.is_multicast or address.is_loopback:
        return None
    return str(address)


def _parse_discovery_response(
    data: bytes,
    source_host: str,
    client_mac: bytes,
    sequence: int,
) -> DiscoveredSwitch | None:
    """Parse and validate one ESCP discovery response."""
    decoded = _crypt(data)
    if len(decoded) < _HEADER_LENGTH + len(_PACKET_END):
        return None
    if not decoded.endswith(_PACKET_END):
        return None

    (
        version,
        operation,
        header_switch_mac,
        response_client_mac,
        response_sequence,
        error_code,
        packet_length,
        fragment_offset,
        _flags,
        _token,
        _checksum,
    ) = struct.unpack(_HEADER_FORMAT, decoded[:_HEADER_LENGTH])
    if (
        version != 1
        or operation != _DISCOVERY_RESPONSE
        or response_client_mac != client_mac
        or response_sequence != sequence
        or error_code != 0
        or packet_length != len(decoded)
        or fragment_offset != 0
    ):
        return None

    values: dict[int, bytes] = {}
    payload = decoded[_HEADER_LENGTH : -len(_PACKET_END)]
    offset = 0
    while offset < len(payload):
        if len(payload) - offset < 4:
            return None
        value_type, value_length = struct.unpack("!HH", payload[offset : offset + 4])
        offset += 4
        end = offset + value_length
        if end > len(payload):
            return None
        values[value_type] = payload[offset:end]
        offset = end

    try:
        mac = _format_mac(values.get(3, header_switch_mac))
    except ValueError:
        return None
    if 3 in values and values[3] != header_switch_mac:
        return None

    host = None
    if len(ip_value := values.get(4, b"")) == 4:
        host = _valid_host(str(IPv4Address(ip_value)))
    host = host or _valid_host(source_host)
    if host is None:
        return None

    model = _decode_text(values.get(1, b""))
    name = _decode_text(values.get(2, b"")) or model
    if not model:
        return None

    return DiscoveredSwitch(
        host=host,
        mac=mac,
        model=model,
        name=name,
        firmware=_decode_text(values[7]) if 7 in values else None,
        hardware=_decode_text(values[8]) if 8 in values else None,
    )


def _random_client_mac() -> bytes:
    """Create a locally administered unicast identifier for one scan."""
    value = bytearray(secrets.token_bytes(6))
    value[0] = (value[0] & 0xFE) | 0x02
    return bytes(value)


async def async_discover_switches(
    *,
    broadcast_addresses: Iterable[str] = (_BROADCAST_ADDRESS,),
    timeout: float = 2.0,
) -> list[DiscoveredSwitch]:
    """Discover Easy Smart switches on the local IPv4 broadcast domains."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[bytes, tuple[str, int]]] = asyncio.Queue(
        maxsize=_MAX_QUEUED_PACKETS
    )
    client_mac = _random_client_mac()
    sequence = secrets.randbelow(0x10000)

    try:
        raw_transport, _protocol = await loop.create_datagram_endpoint(
            lambda: _DiscoveryProtocol(queue),
            local_addr=("0.0.0.0", _CLIENT_PORT),
            allow_broadcast=True,
        )
    except OSError as ex:
        raise DiscoveryError(
            f"Could not open UDP discovery port {_CLIENT_PORT}: {ex}"
        ) from ex

    transport = cast(asyncio.DatagramTransport, raw_transport)
    packet = _build_discovery_packet(client_mac, sequence)
    discovered: dict[str, DiscoveredSwitch] = {}
    try:
        packet_sent = False
        for address in set(broadcast_addresses) or {_BROADCAST_ADDRESS}:
            if target := _valid_host(address):
                try:
                    transport.sendto(packet, (target, _SWITCH_PORT))
                except OSError:
                    continue
                packet_sent = True
        if not packet_sent:
            raise DiscoveryError("Could not send an Easy Smart discovery request")

        deadline = loop.time() + max(0.0, timeout)
        while len(discovered) < _MAX_RESPONSES:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                data, source = await asyncio.wait_for(queue.get(), remaining)
            except TimeoutError:
                break
            if source[1] != _SWITCH_PORT:
                continue
            if result := _parse_discovery_response(
                data, source[0], client_mac, sequence
            ):
                discovered[result.mac] = result
    finally:
        transport.close()

    return sorted(
        discovered.values(), key=lambda item: (item.model, item.name, item.mac)
    )
