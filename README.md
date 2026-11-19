# Telbox for Home Assistant

Send a sensor alert to your Telbox Notes to Self. Home Assistant proposes the message, and you approve it in Telbox on your iPhone. A stable source event ID lets your automation retry a proposal without creating another approval.

## Install

In HACS, open **Custom repositories**, add `https://github.com/TelboxAI/telbox-home-assistant`, and select the **Integration** category. Download Telbox and restart Home Assistant. You can also copy `custom_components/telbox` to your Home Assistant configuration directory and restart.

Open **Settings → Devices & services → Add integration → Telbox**. Follow the account and OAuth instructions in the [setup guide](SETUP.md). This preview was exercised with Home Assistant Core 2026.11.1 and a private Telbox account. The [example automation](telbox_text_qa.yaml) shows how to send a sensor event.
