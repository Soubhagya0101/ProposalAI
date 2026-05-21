from __future__ import annotations

import base64
import subprocess
import urllib.parse
import urllib.request

from .config import RevenueOpsConfig


def notify_hot_reply(config: RevenueOpsConfig, message: str) -> dict:
    if config.twilio_account_sid and config.twilio_auth_token and config.twilio_from_whatsapp and config.twilio_to_whatsapp:
        return _twilio_whatsapp(config, message)
    return _desktop_notification(message)


def _twilio_whatsapp(config: RevenueOpsConfig, message: str) -> dict:
    url = f"https://api.twilio.com/2010-04-01/Accounts/{config.twilio_account_sid}/Messages.json"
    body = urllib.parse.urlencode(
        {
            "From": config.twilio_from_whatsapp or "",
            "To": config.twilio_to_whatsapp or "",
            "Body": message,
        }
    ).encode("utf-8")
    token = base64.b64encode(f"{config.twilio_account_sid}:{config.twilio_auth_token}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(url, data=body, headers={"Authorization": f"Basic {token}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return {"status": "sent_twilio", "code": response.status}


def _desktop_notification(message: str) -> dict:
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        f"[System.Windows.Forms.MessageBox]::Show('{_escape_ps(message)}','ProposalAI Hot Lead') | Out-Null"
    )
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script])
        return {"status": "desktop_notification"}
    except OSError as exc:
        return {"status": "notification_failed", "error": str(exc)}


def _escape_ps(value: str) -> str:
    return value.replace("'", "''")[:900]
