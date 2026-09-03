"""TP-Link web api core functions."""

import asyncio
import logging
import re
from collections.abc import Callable, Iterable, Mapping
from enum import Enum
from typing import Any, Final

import aiohttp
import json5
from aiohttp import ClientResponse, ServerDisconnectedError

TIMEOUT: Final = 5.0

APICALL_ERRCODE_UNAUTHORIZED: Final = -2
APICALL_ERRCODE_REQUEST: Final = -3
APICALL_ERRCODE_DISCONNECTED: Final = -4

APICALL_ERRCAT_REQUEST: Final = "request_error"
APICALL_ERRCAT_UNAUTHORIZED: Final = "unauthorized"
APICALL_ERRCAT_DISCONNECTED: Final = "disconnected"

AUTH_FAILURE_GENERAL: Final = "auth_general"
AUTH_FAILURE_CANNOT_CONNECT: Final = "cannot_connect"
AUTH_FAILURE_CREDENTIALS: Final = "auth_invalid_credentials"
AUTH_USER_BLOCKED: Final = "auth_user_blocked"
AUTH_TOO_MANY_USERS: Final = "auth_too_many_users"
AUTH_SESSION_TIMEOUT: Final = "auth_session_timeout"

_SCRIPT_REGEX = re.compile(
    r"<script(?:\s[^>]*)?>(.*?)</script>", re.IGNORECASE | re.DOTALL
)
_VARIABLES_REGEX = re.compile(
    r"\bvar\s+(?P<variable>[a-zA-Z0-9_]+)\s*=\s*(?P<value>[^;]+);",
    re.DOTALL,
)
_ARRAY_VALUES_REGEX = re.compile(r"\s*new\s*Array\s*\((?P<items>[^\)]*)\)")

_LOGGER = logging.getLogger(__name__)

type VariableValue = str | int | list[str] | dict[str, Any]

_VAR_LOGON_INFO: str = "logonInfo"


# ---------------------------
#   VariableType
# ---------------------------
class VariableType(Enum):
    Str = 0
    Int = 1
    List = 2
    Dict = 3


# ---------------------------
#   AuthenticationError
# ---------------------------
class AuthenticationError(Exception):
    def __init__(self, message: str, reason_code: str) -> None:
        """Initialize."""
        super().__init__(message)
        self._message = message
        self._reason_code = reason_code

    @property
    def reason_code(self) -> str | None:
        """Error reason code."""
        return self._reason_code

    def __str__(self, *args, **kwargs) -> str:
        """Return str(self)."""
        return f"{self._message}; reason: {self._reason_code}"

    def __repr__(self) -> str:
        """Return repr(self)."""
        return self.__str__()


# ---------------------------
#   ApiCallError
# ---------------------------
class ApiCallError(Exception):
    def __init__(
        self, message: str, error_code: int | None, error_category: str | None
    ):
        """Initialize."""
        super().__init__(message)
        self._message = message
        self._error_code = error_code
        self._error_category = error_category

    @property
    def code(self) -> int | None:
        """Error code."""
        return self._error_code

    @property
    def category(self) -> str | None:
        """Error category."""
        return self._error_category

    def __str__(self, *args, **kwargs) -> str:
        """Return str(self)."""
        return (
            f"{self._message}; code: {self._error_code}, "
            f"category: {self._error_category}"
        )

    def __repr__(self) -> str:
        """Return repr(self)."""
        return self.__str__()


# ---------------------------
#   _get_response_text
# ---------------------------
async def _get_response_text(response: ClientResponse) -> str:
    content_bytes = await response.content.read()
    try:
        return content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        # Current Easy Smart pages declare GB2312, while other revisions emit
        # UTF-8. GB18030 is a compatible superset for non-ASCII device names.
        return content_bytes.decode("gb18030", errors="replace")


# ---------------------------
#   _get_variables
# ---------------------------
def _get_variables(page: str | None) -> dict[str, str]:
    result = {}
    if not page:
        return result

    for script_match in _SCRIPT_REGEX.finditer(page):
        for variable_match in _VARIABLES_REGEX.finditer(script_match.group(1)):
            variable = variable_match.group("variable")
            value = variable_match.group("value")
            result[variable] = value.strip()

    return result


# ---------------------------
#   _to_array
# ---------------------------
def _to_list(array_data: str) -> Iterable[str]:
    match = _ARRAY_VALUES_REGEX.fullmatch(array_data)
    if not match:
        return
    array_items = match.group("items")
    if array_items:
        for item in array_items.split(","):
            yield item.strip(" ,\r\n\t\"'")


# ---------------------------
#   _to_dict
# ---------------------------
def _to_dict(json_data: str) -> dict[str, Any] | None:
    return json5.loads(json_data) if json_data else None


# ---------------------------
#   _convert_value
# ---------------------------
def _convert_value(
    value: str | None, variable_type: VariableType
) -> VariableValue | None:
    if value is None:
        return None
    if variable_type == VariableType.Str:
        return value.strip("'\"")
    if variable_type == VariableType.Int:
        return int(value)
    if variable_type == VariableType.List:
        return list(_to_list(value))
    if variable_type == VariableType.Dict:
        return _to_dict(value)
    return None


# ---------------------------
#   _get_variable
# ---------------------------
def _get_variable(
    page: str, name: str, variable_type: VariableType
) -> VariableValue | None:
    variables = _get_variables(page)
    if not variables:
        return None

    variable_str = variables.get(name)
    if not variable_str:
        return None

    return _convert_value(variable_str, variable_type)


# ---------------------------
#   _check_authorized
# ---------------------------
def _check_authorized(response: ClientResponse, result: str) -> bool:
    if response.status != 200:
        return False
    logon_info = _get_variable(result, _VAR_LOGON_INFO, VariableType.Str)
    return not logon_info


def _raise_on_unexpected_status(response: ClientResponse, path: str) -> None:
    """Raise a request error without misclassifying an HTTP failure as auth."""
    if response.status in (200, 401, 403):
        return
    raise ApiCallError(
        f"Api call error at {path}, status: {response.status}",
        response.status,
        APICALL_ERRCAT_REQUEST,
    )


# ---------------------------
#   TpLinkWebApi
# ---------------------------
class TpLinkWebApi:
    def __init__(
        self,
        host: str,
        port: int,
        use_ssl: bool,
        user: str,
        password: str,
        verify_ssl: bool,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize."""
        _LOGGER.debug("New instance of TpLinkWebApi created")
        self._user: str = user
        self._password: str = password
        self._verify_ssl: bool = verify_ssl
        self._session: aiohttp.ClientSession | None = session
        self._session_injected = session is not None
        self._is_initialized: bool = False
        self._call_locker = asyncio.Lock()

        schema = "https" if use_ssl else "http"
        self._base_url: str = f"{schema}://{host}:{port}"

    @property
    def device_url(self) -> str:
        """Return switch's configuration url."""
        return self._base_url

    def invalidate_authentication(self) -> None:
        """Force authentication before the next request."""
        self._is_initialized = False

    def _get_url(self, path: str) -> str:
        """Return full address to the endpoint."""
        return self._base_url + "/" + path

    async def _ensure_initialized(self) -> None:
        """Ensure that initial authorization was completed successfully."""
        if not self._is_initialized:
            await self.authenticate()
            self._is_initialized = True

    async def _get_raw(self, path: str) -> ClientResponse:
        """Perform GET and return the raw response."""
        try:
            if self._session is None:
                raise RuntimeError("HTTP session is not initialized")
            _LOGGER.debug("Performing GET to %s", path)
            response = await self._session.get(
                url=self._get_url(path),
                allow_redirects=True,
                ssl=self._verify_ssl,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT),
            )
            _LOGGER.debug("GET %s performed, status: %s", path, response.status)
            return response
        except ServerDisconnectedError as ex:
            raise ApiCallError(
                f"Can not perform GET request at {path} cause of {ex!r}",
                APICALL_ERRCODE_DISCONNECTED,
                APICALL_ERRCAT_DISCONNECTED,
            ) from ex
        except Exception as ex:
            _LOGGER.error("GET %s failed: %s", path, str(ex))
            raise ApiCallError(
                f"Can not perform GET request at {path} cause of {ex!r}",
                APICALL_ERRCODE_REQUEST,
                APICALL_ERRCAT_REQUEST,
            ) from ex

    async def _post_raw(
        self,
        path: str,
        data: Mapping[str, Any] | Iterable[tuple[str, Any]] | None,
    ) -> ClientResponse:
        """Perform POST and return the raw response."""
        try:
            if self._session is None:
                raise RuntimeError("HTTP session is not initialized")
            _LOGGER.debug("Performing POST to %s", path)
            response = await self._session.post(
                url=self._get_url(path),
                data=data,
                ssl=self._verify_ssl,
                timeout=aiohttp.ClientTimeout(total=TIMEOUT),
            )
            _LOGGER.debug("POST to %s performed, status: %s", path, response.status)
            return response
        except ServerDisconnectedError as ex:
            raise ApiCallError(
                f"Can not perform POST request at {path} cause of {ex!r}",
                APICALL_ERRCODE_DISCONNECTED,
                APICALL_ERRCAT_DISCONNECTED,
            ) from ex
        except Exception as ex:
            _LOGGER.error("POST %s failed: %s", path, str(ex))
            raise ApiCallError(
                f"Can not perform POST request at {path} cause of {ex!r}",
                APICALL_ERRCODE_REQUEST,
                APICALL_ERRCAT_REQUEST,
            ) from ex

    def _refresh_session(self) -> None:
        """Initialize the client session (if not exists) and clear cookies."""
        _LOGGER.debug("Refresh session called")
        if self._session is None:
            # The switch is normally addressed by IP, so cookies need an unsafe jar.
            jar = aiohttp.CookieJar(unsafe=True)
            self._session = aiohttp.ClientSession(cookie_jar=jar)
            self._session_injected = False
            _LOGGER.debug("Session created")
        self._session.cookie_jar.clear()

    async def authenticate(self) -> None:
        """Perform authentication and return true when authentication success"""
        self._is_initialized = False
        try:
            _LOGGER.debug("Authentication started")
            self._refresh_session()
            _LOGGER.debug("Performing logon")
            response = await self._post_raw(
                "logon.cgi",
                {
                    "username": self._user,
                    "password": self._password,
                    "cpassword": "",
                    "logon": "Login",
                },
            )

            if response.status != 200:
                _LOGGER.error(
                    "Authentication failed: can not perform POST, status is %s",
                    response.status,
                )
                raise AuthenticationError("Failed to get index", AUTH_FAILURE_GENERAL)

            result = await _get_response_text(response)
            if not result:
                raise AuthenticationError(
                    "Failed to get Logon response body", AUTH_FAILURE_GENERAL
                )

            array_items = _get_variable(result, _VAR_LOGON_INFO, VariableType.List)
            if not isinstance(array_items, list) or not array_items:
                raise AuthenticationError(
                    "Invalid Logon response body", AUTH_FAILURE_GENERAL
                )

            if array_items[0] == "0":
                _LOGGER.debug("Authentication success")
                self._is_initialized = True
                return
            if array_items[0] == "1":
                raise AuthenticationError(
                    "The user name or the password is wrong", AUTH_FAILURE_CREDENTIALS
                )
            if array_items[0] == "2":
                raise AuthenticationError(
                    "The user is not allowed to login", AUTH_USER_BLOCKED
                )
            if array_items[0] == "3":
                raise AuthenticationError(
                    "The number of the user that allowed to login has been full",
                    AUTH_TOO_MANY_USERS,
                )
            if array_items[0] == "4":
                raise AuthenticationError(
                    "The number of logged-in users has reached the limit of 16",
                    AUTH_TOO_MANY_USERS,
                )
            if array_items[0] == "5":
                raise AuthenticationError(
                    "The session is timeout.",
                    AUTH_SESSION_TIMEOUT,
                )
            raise AuthenticationError(
                f"Unknown error {array_items[0]}", AUTH_FAILURE_GENERAL
            )

        except AuthenticationError as ex:
            _LOGGER.warning("Authentication failed: %r", ex)
            raise
        except ApiCallError as ex:
            _LOGGER.warning("Authentication failed: %r", ex)
            raise AuthenticationError(
                "Authentication failed due to api call error",
                AUTH_FAILURE_CANNOT_CONNECT,
            ) from ex
        except Exception as ex:
            _LOGGER.warning("Authentication failed: %r", ex)
            raise AuthenticationError(
                "Authentication failed due to unknown error", AUTH_FAILURE_GENERAL
            ) from ex

    async def get(
        self, path: str, query: str | None = None, **kwargs: Any
    ) -> str | None:
        """Perform GET request to the relative address."""
        async with self._call_locker:
            await self._ensure_initialized()

            relative_url = path if not query else f"{path}?{query}"

            check_authorized: Callable[[ClientResponse, str], bool] = (
                kwargs.get("check_authorized") or _check_authorized
            )

            response = await self._get_raw(relative_url)
            response_text = await _get_response_text(response)
            _raise_on_unexpected_status(response, relative_url)
            _LOGGER.debug("Response: %s", response_text)

            if not check_authorized(response, response_text):
                _LOGGER.debug("GET seems unauthorized, trying to re-authenticate")
                await self.authenticate()

                response = await self._get_raw(relative_url)
                response_text = await _get_response_text(response)
                _raise_on_unexpected_status(response, relative_url)

                if not check_authorized(response, response_text):
                    raise ApiCallError(
                        f"Api call error, status:{response.status}",
                        APICALL_ERRCODE_UNAUTHORIZED,
                        APICALL_ERRCAT_UNAUTHORIZED,
                    )

            return response_text

    async def post(
        self,
        path: str,
        data: Mapping[str, Any] | Iterable[tuple[str, Any]] | None = None,
        **kwargs: Any,
    ) -> str | None:
        """Perform POST request to the relative address."""
        async with self._call_locker:
            await self._ensure_initialized()

            check_authorized: Callable[[ClientResponse, str], bool] = (
                kwargs.get("check_authorized") or _check_authorized
            )

            response = await self._post_raw(path, data)
            response_text = await _get_response_text(response)
            _raise_on_unexpected_status(response, path)
            _LOGGER.debug("Response: %s", response_text)

            if not check_authorized(response, response_text):
                _LOGGER.debug("POST seems unauthorized, trying to re-authenticate")
                await self.authenticate()

                response = await self._post_raw(path, data)
                response_text = await _get_response_text(response)
                _raise_on_unexpected_status(response, path)

                if not check_authorized(response, response_text):
                    raise ApiCallError(
                        f"Api call error, status:{response.status}",
                        APICALL_ERRCODE_UNAUTHORIZED,
                        APICALL_ERRCAT_UNAUTHORIZED,
                    )

            return response_text

    async def get_variables(
        self,
        path: str,
        variables: Iterable[tuple[str, VariableType]],
        **kwargs: Any,
    ) -> dict[str, VariableValue | None]:
        """Perform GET and return the requested JavaScript variables."""
        response_text = await self.get(path, **kwargs)
        result = {}
        response_variables = _get_variables(response_text)

        for variable, variable_type in variables:
            result[variable] = _convert_value(
                response_variables.get(variable), variable_type
            )

        _LOGGER.debug("Result is %s", result)

        return result

    async def get_variable(
        self, path: str, variable: str, variable_type: VariableType, **kwargs: Any
    ) -> VariableValue | None:
        """Perform GET and return one JavaScript variable."""
        result = await self.get_variables(path, [(variable, variable_type)], **kwargs)
        return result.get(variable) if result else None

    async def disconnect(self) -> None:
        """Close session."""
        _LOGGER.debug("Disconnecting")
        if self._session is not None:
            if self._session_injected:
                # Home Assistant owns the shared connector. Detach this dedicated
                # session instead of closing the connector or leaking the session.
                self._session.detach()
            else:
                await self._session.close()
            self._session = None
            self._session_injected = False
        self._is_initialized = False
