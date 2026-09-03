"""Tests for parsing the JavaScript variables returned by TP-Link firmware."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.tplink_easy_smart.client.coreapi import (
    APICALL_ERRCAT_REQUEST,
    ApiCallError,
    VariableType,
    _check_authorized,
    _convert_value,
    _get_response_text,
    _get_variables,
    _raise_on_unexpected_status,
)


def test_get_variables_accepts_script_attributes_and_multiple_scripts() -> None:
    page = """
    <html>
      <script type="text/javascript">var ignored = 1;</script>
      <script>
        var max_port_num = 5;
        var all_info = {state:[1,1,0,1,1], pkts:[1,2,3,4]};
      </script>
    </html>
    """

    assert _get_variables(page) == {
        "ignored": "1",
        "max_port_num": "5",
        "all_info": "{state:[1,1,0,1,1], pkts:[1,2,3,4]}",
    }


def test_get_variables_accepts_firmware_assignments_without_semicolons() -> None:
    """Parse consecutive variables exactly as emitted by the LED page."""
    page = """
    <script>
    var led = 1
    var tip = "";
    </script>
    """

    assert _get_variables(page) == {"led": "1", "tip": '""'}


def test_convert_firmware_values() -> None:
    assert _convert_value("5", VariableType.Int) == 5
    assert _convert_value('new Array("0", "session")', VariableType.List) == [
        "0",
        "session",
    ]
    assert _convert_value("{state:[1,0], trailing:true,}", VariableType.Dict) == {
        "state": [1, 0],
        "trailing": True,
    }


def test_get_variables_handles_missing_page() -> None:
    assert _get_variables(None) == {}
    assert _get_variables("<html>No scripts</html>") == {}


def test_empty_success_response_is_not_misclassified_as_unauthorized() -> None:
    response = SimpleNamespace(status=200)

    assert _check_authorized(response, "") is True


def test_unexpected_http_status_is_a_request_error() -> None:
    response = SimpleNamespace(status=404)

    with pytest.raises(ApiCallError) as error:
        _raise_on_unexpected_status(response, "missing.htm")

    assert error.value.code == 404
    assert error.value.category == APICALL_ERRCAT_REQUEST


async def test_response_text_supports_gb2312_firmware_pages() -> None:
    """Decode localized firmware pages that are not valid UTF-8."""
    expected = "交换机"
    response = SimpleNamespace(
        content=SimpleNamespace(read=AsyncMock(return_value=expected.encode("gb2312")))
    )

    assert await _get_response_text(response) == expected
