"""Connect automations to the owner's Notes to Self."""
import httpx2
import probatio
from mcp import MCPError
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session

from .client import DOMAIN, TelboxOAuth, identifier, message_status, propose, revoke

SERVICE = "propose_message"
SCHEMA = probatio.Schema({
    probatio.Required("notice"): probatio.All(str, probatio.Length(min=1, max=8192)),
    probatio.Required("source_event_id"): probatio.All(str, probatio.Match(r"^[A-Za-z0-9_-]{1,60}\Z")),
})


async def async_setup_entry(hass, entry):
    session = OAuth2Session(hass, entry, TelboxOAuth(hass, entry.data["client_id"]))

    async def token_manager():
        await session.async_ensure_token_valid()
        return session.token["access_token"]

    async def handle(call):
        try:
            if call.service == "message_status":
                return await message_status(hass, token_manager, identifier(call.data, "draft_id"))
            if not call.data["notice"].strip():
                raise HomeAssistantError("Enter a nonempty notice.")
            return await propose(hass, token_manager, entry.data["thread_id"],
                                 call.data["notice"], call.data["source_event_id"])
        except httpx2.HTTPStatusError as err:
            if err.response.status_code == 401:
                entry.async_start_reauth_if_available(hass)
                raise HomeAssistantError("Reconnect Telbox in Home Assistant.") from err
            raise HomeAssistantError("Telbox could not process the proposal.") from err
        except MCPError as err:
            # The MCP client preserves Telbox's JSON-RPC error on a non-2xx response.
            data = err.error.data
            code = data.get("error_code") if isinstance(data, dict) else None
            if code == "invalid_bearer_token":
                entry.async_start_reauth_if_available(hass)
                raise HomeAssistantError("Reconnect Telbox in Home Assistant.") from err
            if code in ("assistant_provisioning_consent_required", "assistant_disabled"):
                raise HomeAssistantError(
                    "Open Executive assistant settings in Telbox to enable message approvals, "
                    "then run the original event again. No draft was created."
                ) from err
            raise HomeAssistantError("Telbox could not complete the request. Check the proposal before retrying.") from err
        except (TimeoutError, httpx2.HTTPError) as err:
            raise HomeAssistantError("Telbox is unavailable. Retry with the same source event ID.") from err

    hass.services.async_register(DOMAIN, SERVICE, handle, schema=SCHEMA,
                                 supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, "message_status", handle,
                                 schema=probatio.Schema({probatio.Required("draft_id"): str}),
                                 supports_response=SupportsResponse.ONLY)
    return True


async def async_unload_entry(hass, entry):
    hass.services.async_remove(DOMAIN, SERVICE)
    hass.services.async_remove(DOMAIN, "message_status")
    return True


async def async_remove_entry(hass, entry):
    await revoke(hass, entry.data["client_id"], entry.data["token"]["access_token"])
