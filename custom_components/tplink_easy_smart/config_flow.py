"""Config flow to configure TP-Link."""

import logging

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SSL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.device_registry import format_mac

from .client.coreapi import AuthenticationError
from .client.tplink_api import DataFormatError, TpLinkApi
from .const import (
    DEFAULT_ESTIMATED_PACKET_SIZE,
    DEFAULT_HOST,
    DEFAULT_NAME,
    DEFAULT_PASS,
    DEFAULT_POE_STATE_SWITCHES,
    DEFAULT_PORT,
    DEFAULT_PORT_STATE_SWITCHES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SSL,
    DEFAULT_USER,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    MAX_ESTIMATED_PACKET_SIZE,
    MAX_SCAN_INTERVAL,
    MIN_ESTIMATED_PACKET_SIZE,
    MIN_SCAN_INTERVAL,
    OPT_ESTIMATED_PACKET_SIZE,
    OPT_POE_STATE_SWITCHES,
    OPT_PORT_STATE_SWITCHES,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------
#   configured_instances
# ---------------------------
@callback
def configured_instances(hass, exclude_entry_id: str | None = None):
    """Return a set of configured instances."""
    return set(
        entry.data.get(CONF_NAME, entry.title)
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.entry_id != exclude_entry_id
    )


# ---------------------------
#   TpLinkControllerConfigFlow
# ---------------------------
class TpLinkControllerConfigFlow(ConfigFlow, domain=DOMAIN):
    """TpLinkControllerConfigFlow class"""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return TpLinkControllerOptionsFlowHandler(config_entry)

    async def async_step_import(self, user_input=None):
        """Occurs when a previous entry setup fails and is re-initiated."""
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        errors = {}
        if user_input is not None:
            # Check if instance with this name already exists
            if user_input[CONF_NAME] in configured_instances(self.hass):
                errors["base"] = "name_exists"

            switch_info, validation_error = await self._async_validate_switch(
                user_input
            )
            if validation_error:
                errors["base"] = validation_error

            # Save instance
            if not errors and switch_info and switch_info.mac:
                await self.async_set_unique_id(format_mac(switch_info.mac))
                self._abort_if_unique_id_configured(
                    updates={CONF_HOST: user_input[CONF_HOST]}
                )
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )

            return self._show_config_form(
                step_id="user", user_input=user_input, errors=errors
            )

        return self._show_config_form(
            step_id="user",
            user_input={
                CONF_NAME: DEFAULT_NAME,
                CONF_HOST: DEFAULT_HOST,
                CONF_USERNAME: DEFAULT_USER,
                CONF_PASSWORD: DEFAULT_PASS,
                CONF_PORT: DEFAULT_PORT,
                CONF_SSL: DEFAULT_SSL,
                CONF_VERIFY_SSL: DEFAULT_VERIFY_SSL,
            },
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Allow connection settings and credentials to be changed."""
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            if user_input[CONF_NAME] in configured_instances(self.hass, entry.entry_id):
                errors["base"] = "name_exists"

            switch_info, validation_error = await self._async_validate_switch(
                user_input
            )
            if validation_error:
                errors["base"] = validation_error
            elif (
                switch_info
                and switch_info.mac
                and entry.unique_id
                and format_mac(switch_info.mac) != entry.unique_id
            ):
                errors["base"] = "wrong_device"

            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    title=user_input[CONF_NAME],
                    data=user_input,
                )

            return self._show_config_form(
                step_id="reconfigure", user_input=user_input, errors=errors
            )

        defaults = {
            CONF_NAME: entry.data.get(CONF_NAME, entry.title),
            CONF_HOST: entry.data.get(CONF_HOST, DEFAULT_HOST),
            CONF_USERNAME: entry.data.get(CONF_USERNAME, DEFAULT_USER),
            CONF_PASSWORD: entry.data.get(CONF_PASSWORD, DEFAULT_PASS),
            CONF_PORT: entry.data.get(CONF_PORT, DEFAULT_PORT),
            CONF_SSL: entry.data.get(CONF_SSL, DEFAULT_SSL),
            CONF_VERIFY_SSL: entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL),
        }
        return self._show_config_form(
            step_id="reconfigure", user_input=defaults, errors=errors
        )

    async def _async_validate_switch(self, user_input):
        """Authenticate and return switch information plus an error key."""
        switch_info = None
        error = None
        session = async_create_clientsession(
            self.hass,
            verify_ssl=user_input[CONF_VERIFY_SSL],
            auto_cleanup=False,
            cookie_jar=aiohttp.CookieJar(unsafe=True),
        )
        api = TpLinkApi(
            host=user_input[CONF_HOST],
            port=user_input[CONF_PORT],
            use_ssl=user_input[CONF_SSL],
            user=user_input[CONF_USERNAME],
            password=user_input[CONF_PASSWORD],
            verify_ssl=user_input[CONF_VERIFY_SSL],
            session=session,
        )
        try:
            await api.authenticate()
            switch_info = await api.get_device_info()
            if not switch_info.mac:
                raise DataFormatError("The switch did not return a MAC address")
        except AuthenticationError as ex:
            error = ex.reason_code or "auth_general"
        except DataFormatError:
            error = "invalid_response"
        except Exception as ex:
            _LOGGER.warning("Connection validation failed: %s", ex)
            error = "auth_general"
        finally:
            await api.disconnect()
        return switch_info, error

    # ---------------------------
    #   _show_config_form
    # ---------------------------
    def _show_config_form(self, step_id, user_input, errors=None):
        """Show the configuration form to edit data."""
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=user_input[CONF_NAME]): str,
                    vol.Required(CONF_HOST, default=user_input[CONF_HOST]): vol.All(
                        str, vol.Length(min=1)
                    ),
                    vol.Required(CONF_USERNAME, default=user_input[CONF_USERNAME]): str,
                    vol.Required(CONF_PASSWORD, default=user_input[CONF_PASSWORD]): str,
                    vol.Required(CONF_PORT, default=user_input[CONF_PORT]): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=65535)
                    ),
                    vol.Required(CONF_SSL, default=user_input[CONF_SSL]): bool,
                    vol.Required(
                        CONF_VERIFY_SSL, default=user_input[CONF_VERIFY_SSL]
                    ): bool,
                }
            ),
            errors=errors,
        )


# ---------------------------
#   TpLinkControllerOptionsFlowHandler
# ---------------------------
class TpLinkControllerOptionsFlowHandler(OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.options = dict(config_entry.options)
        self._local_config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        return await self.async_step_basic_options(user_input)

    async def async_step_basic_options(self, user_input=None):
        """Manage the basic options options."""
        if user_input is not None:
            self.options.update(user_input)
            return await self.async_step_features_select()

        return self.async_show_form(
            step_id="basic_options",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self._local_config_entry.options.get(
                            CONF_SCAN_INTERVAL,
                            self._local_config_entry.data.get(
                                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                            ),
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                    vol.Required(
                        OPT_ESTIMATED_PACKET_SIZE,
                        default=self._local_config_entry.options.get(
                            OPT_ESTIMATED_PACKET_SIZE,
                            DEFAULT_ESTIMATED_PACKET_SIZE,
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_ESTIMATED_PACKET_SIZE,
                            max=MAX_ESTIMATED_PACKET_SIZE,
                        ),
                    ),
                }
            ),
        )

    async def async_step_features_select(self, user_input=None):
        """Manage the controls select options."""
        if user_input is not None:
            self.options.update(user_input)
            return self.async_create_entry(title="", data=self.options)

        return self.async_show_form(
            step_id="features_select",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        OPT_PORT_STATE_SWITCHES,
                        default=self._local_config_entry.options.get(
                            OPT_PORT_STATE_SWITCHES, DEFAULT_PORT_STATE_SWITCHES
                        ),
                    ): bool,
                    vol.Required(
                        OPT_POE_STATE_SWITCHES,
                        default=self._local_config_entry.options.get(
                            OPT_POE_STATE_SWITCHES, DEFAULT_POE_STATE_SWITCHES
                        ),
                    ): bool,
                },
            ),
        )
