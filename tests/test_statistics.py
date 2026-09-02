"""Tests for packet rate calculations."""

import pytest

from custom_components.tplink_easy_smart.client.classes import PortSpeed, PortStatistics
from custom_components.tplink_easy_smart.client.statistics import (
    PortStatisticsRateCalculator,
)


def _statistics(tx: int, rx: int, port: int = 1) -> PortStatistics:
    return PortStatistics(
        number=port,
        enabled=True,
        link_status=PortSpeed.FULL_1000M,
        tx_good_packets=tx,
        tx_bad_packets=0,
        rx_good_packets=rx,
        rx_bad_packets=0,
    )


def test_first_sample_has_no_rate() -> None:
    calculator = PortStatisticsRateCalculator(1500)

    assert calculator.update([_statistics(10, 20)], 100.0) == {}


def test_rates_use_actual_elapsed_time() -> None:
    calculator = PortStatisticsRateCalculator(1500)
    calculator.update([_statistics(100, 200)], 100.0)

    rates = calculator.update([_statistics(300, 300)], 110.0)[1]

    assert rates.tx_packets_per_second == 20
    assert rates.rx_packets_per_second == 10
    assert rates.tx_estimated_mbps == pytest.approx(0.24)
    assert rates.rx_estimated_mbps == pytest.approx(0.12)
    assert rates.total_estimated_mbps == pytest.approx(0.36)


def test_counter_reset_does_not_produce_a_negative_rate() -> None:
    calculator = PortStatisticsRateCalculator(1500)
    calculator.update([_statistics(10_000, 20_000)], 100.0)

    rates = calculator.update([_statistics(10, 20)], 110.0)[1]

    assert rates.tx_packets_per_second == 1
    assert rates.rx_packets_per_second == 2


def test_32_bit_counter_wrap_is_accounted_for() -> None:
    calculator = PortStatisticsRateCalculator(1500)
    calculator.update([_statistics(2**32 - 10, 2**32 - 20)], 100.0)

    rates = calculator.update([_statistics(10, 20)], 110.0)[1]

    assert rates.tx_packets_per_second == 2
    assert rates.rx_packets_per_second == 4
