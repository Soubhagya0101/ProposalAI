from __future__ import annotations

import smtplib
import json
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Any

from .config import RevenueOpsConfig


def format_daily_report(report: dict[str, Any]) -> str:
    metrics = report.get("metrics", {})
    lines = [
        f"ProposalAI Daily Revenue Report - {report.get('date', '')}",
        "",
        f"Leads found: {metrics.get('leads_found', 0)}",
        f"Messages ready: {metrics.get('messages_ready', 0)}",
        f"Messages sent: {metrics.get('messages_sent', 0)}",
        f"Replies received: {metrics.get('replies_received', 0)}",
        f"Hot leads: {metrics.get('hot_leads', 0)}",
        f"Free users: {metrics.get('free_users', 0)}",
        f"Paying users: {metrics.get('paying_users', 0)}",
        "",
        f"Lead -> message rate: {metrics.get('lead_to_message_rate', 0)}%",
        f"Message -> reply rate: {metrics.get('message_to_reply_rate', 0)}%",
        f"Free -> paid rate: {metrics.get('free_to_paid_rate', 0)}%",
        "",
        "Hot leads:",
    ]
    hot_leads = report.get("hot_leads", [])
    if hot_leads:
        lines.extend(f"- {lead.get('name') or 'Unknown'} ({lead.get('company') or 'No company'}) score {lead.get('score', 0)}" for lead in hot_leads)
    else:
        lines.append("- None yet")
    lines.extend(["", f"Local report: {report.get('local_report_path', '')}"])
    return "\n".join(lines)


def deliver_daily_report(report: dict[str, Any], config: RevenueOpsConfig) -> dict[str, str]:
    body = format_daily_report(report)
    subject = f"ProposalAI daily revenue report - {report.get('date', '')}"
    if config.report_email and config.brevo_enabled:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = formataddr((config.email_from_name, config.brevo_from_email or config.brevo_email or ""))
        if config.brevo_reply_to_email:
            message["Reply-To"] = config.brevo_reply_to_email
        message["To"] = config.report_email
        message.set_content(body)
        try:
            _send_brevo_smtp(message, config)
        except smtplib.SMTPAuthenticationError as exc:
            if config.brevo_api_key and b"Unauthorized IP" in (exc.smtp_error or b""):
                _send_brevo_api(message, config)
            else:
                raise
        return {"status": "sent", "to": config.report_email}

    reports_dir = Path(config.data_dir) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    draft_path = reports_dir / f"daily-email-{report.get('date', 'unknown')}.txt"
    draft_path.write_text(f"Subject: {subject}\n\n{body}\n", encoding="utf-8")
    return {"status": "drafted", "path": str(draft_path)}


def _send_brevo_smtp(message: EmailMessage, config: RevenueOpsConfig) -> None:
    if not config.brevo_email or not config.brevo_smtp_key:
        if config.brevo_api_key:
            _send_brevo_api(message, config)
            return
        raise RuntimeError("Brevo SMTP credentials are missing.")
    with smtplib.SMTP(config.brevo_smtp_host, config.brevo_smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(config.brevo_email or "", config.brevo_smtp_key or "")
        smtp.send_message(message)


def _send_brevo_api(message: EmailMessage, config: RevenueOpsConfig) -> None:
    if not config.brevo_api_key:
        raise RuntimeError("Brevo API key is missing.")
    sender_email = config.brevo_from_email or config.brevo_reply_to_email or config.brevo_email
    payload = {
        "sender": {"name": config.email_from_name, "email": sender_email},
        "to": [{"email": message["To"]}],
        "subject": message["Subject"],
        "textContent": message.get_content(),
    }
    if config.brevo_reply_to_email:
        payload["replyTo"] = {"email": config.brevo_reply_to_email}
    request = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={"accept": "application/json", "api-key": config.brevo_api_key, "content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status >= 300:
                raise RuntimeError(f"Brevo API returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Brevo API returned HTTP {exc.code}: {body[:500]}") from exc
