"""Helpers for deriving traffic rates from TP-Link packet counters."""

from __future__ import annotations

from collections.abc import Iterable

from .classes import PortStatistics, PortTrafficRates

_COUNTER_MODULUS = 2**32
_WRAP_THRESHOLD = int(_COUNTER_MODULUS * 0.9)


def _counter_delta(current: int, previous: int) -> int:
    """Return a non-negative delta, accounting for reset and 32-bit wrap."""
    if current >= previous:
        return current - previous
    if previous >= _WRAP_THRESHOLD:
        return _COUNTER_MODULUS - previous + current
    return current


class PortStatisticsRateCalculator:
    """Calculate per-port rates using the real elapsed sampling time."""

    def __init__(self, assumed_packet_size: int) -> None:
        """Initialize the calculator."""
        self._assumed_packet_size = assumed_packet_size
        self._previous: dict[int, PortStatistics] = {}
        self._previous_sample_time: float | None = None

    def update(
        self, statistics: Iterable[PortStatistics], sample_time: float
    ) -> dict[int, PortTrafficRates]:
        """Store a sample and return rates when a previous sample exists."""
        current = {item.number: item for item in statistics}
        previous_time = self._previous_sample_time
        elapsed = None if previous_time is None else sample_time - previous_time
        rates: dict[int, PortTrafficRates] = {}

        if elapsed is not None and elapsed > 0:
            for number, item in current.items():
                previous = self._previous.get(number)
                if previous is None:
                    continue

                tx_delta = _counter_delta(
                    item.tx_good_packets, previous.tx_good_packets
                )
                rx_delta = _counter_delta(
                    item.rx_good_packets, previous.rx_good_packets
                )
                tx_pps = tx_delta / elapsed
                rx_pps = rx_delta / elapsed
                bits_per_packet = self._assumed_packet_size * 8

                rates[number] = PortTrafficRates(
                    tx_packets_per_second=tx_pps,
                    rx_packets_per_second=rx_pps,
                    tx_estimated_mbps=tx_pps * bits_per_packet / 1_000_000,
                    rx_estimated_mbps=rx_pps * bits_per_packet / 1_000_000,
                )

        self._previous = current
        self._previous_sample_time = sample_time
        return rates
