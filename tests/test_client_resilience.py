"""Tests for optional endpoints and connection error handling."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.tplink_easy_smart.client.const import FEATURE_POE
from custom_components.tplink_easy_smart.client.coreapi import (
    APICALL_ERRCAT_REQUEST,
    APICALL_ERRCODE_REQUEST,
    AUTH_FAILURE_CANNOT_CONNECT,
    ApiCallError,
    AuthenticationError,
    TpLinkWebApi,
)
from custom_components.tplink_easy_smart.client.utils import TpLinkFeaturesDetector


class FakeCookieJar:
    """Minimal cookie jar used by the injected session fixture."""

    def clear(self) -> None:
        return None


class FakeSession:
    """Minimal injected session used before the mocked request fails."""

    def __init__(self) -> None:
        self.cookie_jar = FakeCookieJar()
        self.detached = False

    def detach(self) -> None:
        self.detached = True


async def test_authentication_submits_complete_firmware_form(monkeypatch) -> None:
    """Include the hidden confirmation-password field used by newer firmware."""
    api = TpLinkWebApi("192.0.2.1", 80, False, "admin", "secret", False, FakeSession())
    captured = {}

    async def capture_login(path, data):
        captured.update({"path": path, "data": data})
        return SimpleNamespace(
            status=200,
            content=SimpleNamespace(
                read=AsyncMock(
                    return_value=b'<script>var logonInfo = new Array("0");</script>'
                )
            ),
        )

    monkeypatch.setattr(api, "_post_raw", capture_login)

    await api.authenticate()

    assert captured == {
        "path": "logon.cgi",
        "data": {
            "username": "admin",
            "password": "secret",
            "cpassword": "",
            "logon": "Login",
        },
    }


async def test_authentication_maps_request_failure_to_cannot_connect(
    monkeypatch,
) -> None:
    session = FakeSession()
    api = TpLinkWebApi("192.0.2.1", 80, False, "admin", "secret", False, session)

    async def raise_request_error(*_args, **_kwargs):
        raise ApiCallError("offline", APICALL_ERRCODE_REQUEST, APICALL_ERRCAT_REQUEST)

    monkeypatch.setattr(api, "_post_raw", raise_request_error)

    with pytest.raises(AuthenticationError) as error:
        await api.authenticate()

    assert error.value.reason_code == AUTH_FAILURE_CANNOT_CONNECT
    await api.disconnect()
    assert session.detached is True


async def test_missing_optional_poe_page_means_feature_is_unavailable() -> None:
    class MissingPoeApi:
        async def get_variables(self, *_args, **_kwargs):
            raise ApiCallError("missing", 404, APICALL_ERRCAT_REQUEST)

    detector = TpLinkFeaturesDetector(MissingPoeApi())

    await detector.update()

    assert detector.is_available(FEATURE_POE) is False
