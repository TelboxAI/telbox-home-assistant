"""Register one public client per installation and request explicit Telbox consent."""
import asyncio
import logging
from uuid import UUID

import aiohttp
import httpx2
from mcp import MCPError
import probatio
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_entry_oauth2_flow as oauth
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .client import API, DOMAIN, SCOPE, InboxSetupRequired, TelboxOAuth, read_inbox, revoke


class TelboxFlow(oauth.AbstractOAuth2FlowHandler, domain=DOMAIN):
    DOMAIN = DOMAIN
    VERSION = 1
    logger = logging.getLogger(__name__)

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors = {}
        store = Store(self.hass, 1, "telbox.public_registration")
        current = await store.async_load()
        if user_input is not None:
            callback = oauth.MY_AUTH_CALLBACK_PATH
            if not current or user_input.get("replace_client"):
                current = None
                try:
                    async with asyncio.timeout(20), async_get_clientsession(self.hass).post(
                        API + "/v1/oauth/register", allow_redirects=False, json={
                            "client_name": "Home Assistant", "redirect_uris": [callback],
                            "grant_types": ["authorization_code", "refresh_token"],
                            "response_types": ["code"], "token_endpoint_auth_method": "none",
                            "scope": SCOPE, "application_type": "web",
                        },
                    ) as response:
                        if response.status != 201:
                            raise ValueError("Registration unsuccessful")
                        info = await response.json()
                        if info.get("redirect_uris") != [callback] or info.get("scope") != SCOPE:
                            raise ValueError("Unexpected client registration")
                        current = {"client_id": str(UUID(info["client_id"]))}
                    await store.async_save(current)
                except (aiohttp.ClientError, TimeoutError, KeyError, ValueError, TypeError):
                    errors["base"] = "registration_failed"
            if current:
                self.flow_impl = TelboxOAuth(self.hass, current["client_id"])
                return await self.async_step_review()
        fields = {probatio.Optional("replace_client", default=False): bool} if current else {}
        return self.async_show_form(step_id="user", data_schema=probatio.Schema(fields), errors=errors)

    async def async_step_review(self, user_input=None):
        if user_input is not None:
            return await self.async_step_auth()
        return self.async_show_form(step_id="review", data_schema=probatio.Schema({}),
                                    description_placeholders={"client_id": self.flow_impl.client_id})

    async def async_step_reauth(self, entry_data):
        self.flow_impl = TelboxOAuth(self.hass, entry_data["client_id"])
        return await self.async_step_review()

    async def async_step_owner_setup(self, user_input=None):
        if user_input is None:
            return self.async_show_form(
                step_id="owner_setup", data_schema=probatio.Schema({}),
                description_placeholders={"next_step": self.owner_setup_instruction},
            )
        self.flow_impl = TelboxOAuth(self.hass, self.flow_impl.client_id)
        return await self.async_step_auth()

    async def async_oauth_create_entry(self, data):
        async def token_manager():
            return data["token"]["access_token"]

        try:
            thread = await read_inbox(self.hass, token_manager)
        except InboxSetupRequired as err:
            await revoke(self.hass, self.flow_impl.client_id, data["token"]["access_token"])
            self.owner_setup_instruction = str(err)
            return await self.async_step_owner_setup()
        except (OSError, TimeoutError, HomeAssistantError, httpx2.HTTPError, MCPError):
            await revoke(self.hass, self.flow_impl.client_id, data["token"]["access_token"])
            return self.async_abort(reason="inbox_unavailable")
        data = {**data, "client_id": self.flow_impl.client_id, "thread_id": thread}
        if self.source == SOURCE_REAUTH:
            entry = self._get_reauth_entry()
            if thread != entry.data["thread_id"]:
                await revoke(self.hass, self.flow_impl.client_id, data["token"]["access_token"])
                return self.async_abort(reason="wrong_account")
            return self.async_update_reload_and_abort(entry, data=data)
        return self.async_create_entry(title="Telbox · Notes to Self", data=data)
