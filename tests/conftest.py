"""Shared Home Assistant test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    """Allow tests to load integrations from custom_components."""
    return enable_custom_integrations
