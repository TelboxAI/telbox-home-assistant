# Telbox for Home Assistant

Home Assistant Core 2026.11.1 and a Telbox account with Notes to Self and message approvals enabled. Telbox reviews each new public client.

1. Extract custom_components/telbox into the Home Assistant configuration folder and restart Home Assistant.
2. [Open Telbox setup in Home Assistant](https://my.home-assistant.io/redirect/config_flow_start/?domain=telbox). Select your instance and register the installation once. Continue when Telbox approves the client.
3. Check the receiving account and messaging permission in Telbox. On the My Home Assistant page, choose Link account to finish. If you decline access, choose Notify Home Assistant of rejection to return that decision to your instance.
4. Use the Telbox: Propose a Notes to Self message action with a notice and a stable source_event_id. Review the proposal in Telbox.

Home Assistant Core 2026.11.1 completed private Telbox consent, renewal, replay and revocation. One approved text was stored for the synthetic account. Production and iPhone delivery remain open.

## Account setup
1. Extract the setup ZIP into your Home Assistant configuration directory so the manifest is at `custom_components/telbox/manifest.json`. Restart Home Assistant. The integration was tested with Home Assistant Core 2026.11.1.
2. Open **Settings → Devices & services → Add integration → Telbox**. Register the installation. Setup keeps its public client ID across restarts. If Telbox client review is pending, give that ID to the Telbox administrator who reviews registrations. Leave the replacement checkbox clear when resuming an existing registration.
3. Continue to Telbox, check the signed-in account and approve **Send messages on your behalf**. On My Home Assistant, confirm the instance URL and choose **Link account**. If you decline in Telbox, select **Notify Home Assistant of rejection** to close the pending setup in your instance. If Home Assistant shows **Finish setting up Notes to Self**, follow the account instruction shown there. Continue from that screen to authorize the same installation again.
4. In an automation, choose **Telbox → Propose a Notes to Self message**. Supply the text and a stable source event ID. In Telbox, approve the text to place it in Notes to Self.

```yaml
- action: telbox.propose_message
  data:
    notice: "The utility-room leak sensor needs attention."
    source_event_id: "{{ trigger.to_state.context.id }}"
  response_variable: telbox_receipt
```

This example assumes a Home Assistant state trigger. Reuse the originating event’s ID for retries. A changed message needs its own event ID. Use the **Check a message proposal** action with the returned `draft_id` to read its status without sending again. A pending approval can be rejected or expire. A replay can return the existing decision, including execution. Removing the integration asks Telbox to revoke its grant. If the home is offline during removal, revoke it in Telbox **Connected apps**.

If Telbox asks you to reconnect, open the integration’s reauthentication prompt in Home Assistant and select the original Telbox account. Choosing another account discards its new grant and keeps the existing inbox. When Telbox asks for Executive assistant setup, the receiving owner enables message approvals in Telbox before running the original event again. [First-message setup](https://docs.telbox.ai/guides/authentication/#send-your-first-message-to-notes-to-self)
