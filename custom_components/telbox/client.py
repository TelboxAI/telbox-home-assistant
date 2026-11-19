"""Owner-approved Telbox text proposals through Home Assistant's MCP client."""
import asyncio
from uuid import UUID

import aiohttp
from homeassistant.helpers import oauth2
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from homeassistant.components.mcp.coordinator import mcp_client
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_entry_oauth2_flow as oauth

DOMAIN = "telbox"
API = "https://api.telbox.ai"
RESOURCE = API + "/mcp"
SCOPE = "messages:write"
PROPOSAL_STATES = ("pending_approval", "approved", "executed", "rejected", "expired")


class TelboxOAuth(oauth.LocalOAuth2ImplementationWithPkce):
    """Use a fresh verifier for each connection flow and bind both grants to MCP."""

    def __init__(self, hass, client_id):
        super().__init__(hass, DOMAIN, client_id, API + "/v1/oauth/authorize", API + "/v1/oauth/token")

    @property
    def redirect_uri(self):
        return oauth.MY_AUTH_CALLBACK_PATH

    @property
    def extra_authorize_data(self):
        return {**super().extra_authorize_data, "scope": SCOPE, "resource": RESOURCE}

    async def _token_request(self, data):
        return await oauth2.async_token_request(
            self.hass, self.token_url, {**data, "resource": RESOURCE, "client_id": self.client_id},
            domain=self.service_domain, allow_redirects=False,
        )


async def revoke(hass, client_id, token):
    """Revoke the grant family at Telbox before discarding its local credential."""
    try:
        async with asyncio.timeout(15), async_get_clientsession(hass).post(
            API + "/v1/oauth/revoke", data={"client_id": client_id, "token": token},
            allow_redirects=False,
        ) as response:
            if response.status != 200:
                raise HomeAssistantError("Revoke this connection in Telbox Connected apps.")
    except (aiohttp.ClientError, TimeoutError) as err:
        raise HomeAssistantError("Telbox is unreachable. Revoke access in Telbox Connected apps.") from err


def identifier(data, key):
    try:
        return str(UUID(data[key]))
    except (KeyError, ValueError, TypeError, AttributeError) as err:
        raise HomeAssistantError("Telbox returned an incomplete receipt.") from err


async def tool(session, name, arguments):
    result = await session.call_tool(name, arguments)
    if result.is_error or not isinstance(result.structured_content, dict):
        raise HomeAssistantError(f"Telbox could not complete {name}.")
    return result.structured_content


class InboxSetupRequired(HomeAssistantError):
    """Telbox supplied a setup step for the receiving owner."""


async def inbox(session):
    result = await tool(session, "get_my_inbox", {})
    if result.get("destination", "Notes to Self") != "Notes to Self" or result.get("owner_approval_required") is not True:
        raise HomeAssistantError("Telbox returned an unexpected inbox.")
    if result.get("status") == "setup_required" and "thread_id" in result and result["thread_id"] is None:
        step = result.get("next_step")
        if isinstance(step, str) and step.strip():
            raise InboxSetupRequired(step.strip())
    if result.get("status") != "ready":
        raise HomeAssistantError("Notes to Self is unavailable for this account.")
    return identifier(result, "thread_id")


async def read_inbox(hass, token_manager):
    async with asyncio.timeout(30), mcp_client(hass, RESOURCE, token_manager) as (session, _):
        return await inbox(session)


async def propose(hass, token_manager, expected_thread, notice, event_id):
    async with asyncio.timeout(30), mcp_client(hass, RESOURCE, token_manager) as (session, _):
        thread = await inbox(session)
        if thread != expected_thread:
            raise HomeAssistantError("The connected Notes to Self account has changed.")
        result = await tool(session, "send_message", {
            "thread_id": thread, "content": notice, "client_message_id": "ha-" + event_id,
        })
    status = result.get("status")
    if status not in PROPOSAL_STATES:
        raise HomeAssistantError("Telbox returned an unknown proposal status.")
    return {"status": status, "draft_id": identifier(result, "draft_id"),
            "approval_request_id": identifier(result, "approval_request_id")}


async def message_status(hass, token_manager, draft_id):
    async with asyncio.timeout(30), mcp_client(hass, RESOURCE, token_manager) as (session, _):
        result = await tool(session, "get_message_status", {"draft_id": draft_id})
    if identifier(result, "draft_id") != draft_id or result.get("status") not in PROPOSAL_STATES:
        raise HomeAssistantError("Telbox returned an unexpected status receipt.")
    acknowledgments = ("owner_device_delivery", "owner_device_read")
    if any(result.get(key) not in ("acknowledged", "unconfirmed") for key in acknowledgments):
        raise HomeAssistantError("Telbox returned an incomplete device receipt.")
    return {
        "draft_id": draft_id,
        "status": result["status"],
        "message_id": identifier(result, "message_id") if result.get("message_id") else None,
        **{key: result[key] for key in acknowledgments},
    }
