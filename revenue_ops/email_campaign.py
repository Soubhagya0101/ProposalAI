from __future__ import annotations

import email
import imaplib
import json
import random
import re
import smtplib
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid, parsedate_to_datetime
from typing import Iterable

from .config import RevenueOpsConfig
from .models import Event, Lead, Message, utc_now
from .notifications import notify_hot_reply
from .storage import RevenueStore
from .time_utils import is_business_hours_ist, now_ist, today_ist


SUBJECT_VARIATIONS = [
    "Quick question about your {niche} proposals",
    "Found something that might save you time",
    "Free tool for {niche} freelancers",
    "How long does writing proposals take you?",
    "Built this for freelancers like you",
]
POSITIVE_WORDS = ("interested", "yes", "how", "tell me more", "sure")
NEGATIVE_WORDS = ("no thanks", "unsubscribe", "remove me")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
GENERIC_NAMES = {
    "admin",
    "contact",
    "hello",
    "hi",
    "info",
    "mail",
    "office",
    "sales",
    "support",
    "team",
}


class TemporaryEmailDeliveryError(RuntimeError):
    """Retryable provider/network failure."""


@dataclass(slots=True)
class EmailRunResult:
    attempted: int = 0
    sent: int = 0
    skipped: int = 0
    errors: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "attempted": self.attempted,
            "sent": self.sent,
            "skipped": self.skipped,
            "errors": self.errors or [],
        }


class EmailCampaign:
    def __init__(self, config: RevenueOpsConfig, store: RevenueStore) -> None:
        self.config = config
        self.store = store

    def queue_new_outreach(self) -> dict:
        queued: list[dict] = []
        skipped = 0
        for lead in self.store.leads.all():
            if not self._can_email_lead(lead):
                skipped += 1
                continue
            if self._has_any_email_attempt(lead):
                skipped += 1
                continue
            message = self._create_message(lead, purpose="cold_email", attempt_no=1)
            queued.append(message.to_dict())
        return {"queued_count": len(queued), "skipped_count": skipped, "queued": queued}

    def send_queued(self, max_to_send: int | None = None, dry_run: bool = False, no_delay: bool = False) -> dict:
        if not is_business_hours_ist(self.config.email_business_start_hour_ist, self.config.email_business_end_hour_ist):
            return {"status": "outside_business_hours", "sent": 0, "business_hours": "9AM-6PM IST"}
        if not self.config.send_enabled and not dry_run:
            return {"status": "missing_brevo_credentials", "sent": 0}
        if not self.config.physical_address and not dry_run:
            return {"status": "missing_physical_address", "sent": 0, "reason": "Commercial email needs an opt-out and sender address."}

        remaining = self._daily_remaining()
        limit = min(max_to_send or remaining, remaining)
        if limit <= 0:
            return {"status": "daily_limit_reached", "sent": 0}

        messages = [message for message in self.store.messages.all() if message.channel == "email" and message.status == "queued"]
        result = EmailRunResult(errors=[])
        for message in messages[:limit]:
            result.attempted += 1
            lead = self._lead_for_message(message)
            if not lead or not self._can_email_lead(lead) or self._email_already_sent(lead.email):
                message.status = "skipped"
                self.store.messages.upsert(message)
                result.skipped += 1
                continue
            try:
                if dry_run:
                    message.status = "dry_run"
                else:
                    self._send_email(lead, message)
                    message.status = "sent"
                    message.sent_at = utc_now()
                    lead.status = "emailed"
                    lead.last_contacted_at = message.sent_at
                    lead.followup_attempts = max(lead.followup_attempts, message.attempt_no)
                    lead.next_followup_at = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0).isoformat()
                    lead.updated_at = utc_now()
                    self.store.leads.upsert(lead)
                    self.store.events.append(Event(lead_id=lead.id, kind="email_sent", detail=json.dumps({"email": lead.email, "message_id": message.id, "attempt": message.attempt_no})))
                self.store.messages.upsert(message)
                result.sent += 1
                if not no_delay and not dry_run and result.sent < limit:
                    time.sleep(random.randint(self.config.email_min_delay_seconds, self.config.email_max_delay_seconds))
            except TemporaryEmailDeliveryError as exc:
                message.status = "queued"
                self.store.messages.upsert(message)
                detail = f"{lead.email if lead else message.lead_id}: {exc}"
                self.store.events.append(Event(lead_id=message.lead_id, kind="email_retry_scheduled", detail=detail))
                result.errors.append(detail)
                break
            except Exception as exc:  # noqa: BLE001
                message.status = "error"
                self.store.messages.upsert(message)
                detail = f"{lead.email if lead else message.lead_id}: {exc}"
                self.store.events.append(Event(lead_id=message.lead_id, kind="email_error", detail=detail))
                result.errors.append(detail)
        return result.to_dict()

    def queue_followups(self) -> dict:
        queued: list[dict] = []
        for lead in self.store.leads.all():
            if not lead.email or lead.status in {"replied", "hot", "not_interested", "unsubscribed", "closed", "won", "lost"}:
                continue
            if lead.followup_attempts >= 2:
                lead.status = "closed"
                lead.updated_at = utc_now()
                self.store.leads.upsert(lead)
                continue
            next_followup = self._parse_time(lead.next_followup_at)
            if not next_followup or next_followup > datetime.now(timezone.utc):
                continue
            if self._has_followup_for_attempt(lead, 2):
                continue
            queued.append(self._create_message(lead, purpose="followup_email", attempt_no=2).to_dict())
        return {"queued_count": len(queued), "queued": queued}

    def check_replies(self) -> dict:
        if not self.config.imap_enabled:
            return {
                "status": "brevo_webhook_mode",
                "checked": 0,
                "message": "No IMAP inbox configured. Replies are captured through Brevo inbound parse webhooks.",
            }
        checked = replies = hot = not_interested = 0
        with imaplib.IMAP4_SSL(self.config.imap_host, self.config.imap_port) as imap:
            imap.login(self.config.imap_address or "", self.config.imap_password or "")
            imap.select("INBOX")
            for lead in self.store.leads.all():
                if not lead.email or lead.status in {"not_interested", "unsubscribed"}:
                    continue
                if not self._email_already_sent(lead.email) or self._has_reply_event(lead):
                    continue
                checked += 1
                for mail in self._search_replies(imap, lead):
                    replies += 1
                    classification = self._classify_reply(mail["body"])
                    self._mark_reply(lead, mail, classification)
                    if classification == "hot":
                        hot += 1
                    if classification == "not_interested":
                        not_interested += 1
                    break
        return {"status": "ok", "checked": checked, "replies": replies, "hot": hot, "not_interested": not_interested}

    def send_summary_email(self) -> dict:
        if not self.config.send_enabled:
            return {"status": "missing_brevo_credentials"}
        to_email = self.config.report_email or self.config.brevo_email
        if not to_email:
            return {"status": "missing_report_email"}
        report = self._summary_text()
        msg = EmailMessage()
        msg["Subject"] = f"ProposalAI daily summary - {today_ist()}"
        msg["From"] = formataddr((self.config.email_from_name, self.config.brevo_from_email or self.config.brevo_email or ""))
        if self.config.brevo_reply_to_email:
            msg["Reply-To"] = self.config.brevo_reply_to_email
        msg["To"] = to_email
        msg.set_content(report)
        self._deliver_message(msg)
        self.store.events.append(Event(lead_id="", kind="daily_summary_sent", detail=to_email))
        return {"status": "sent", "to": to_email}

    def run_pipeline(self, send: bool = True, dry_run: bool = False, no_delay: bool = False) -> dict:
        queued = self.queue_new_outreach()
        sent = self.send_queued(dry_run=dry_run, no_delay=no_delay) if send else {"status": "send_skipped"}
        return {"queued": queued, "sent": sent}

    def _create_message(self, lead: Lead, purpose: str, attempt_no: int) -> Message:
        if purpose == "followup_email":
            subject = "Still want free ProposalAI access?"
            body = self._followup_body(lead)
        else:
            variant = random.randrange(len(SUBJECT_VARIATIONS))
            niche = lead.niche or "freelance"
            subject = SUBJECT_VARIATIONS[variant].format(niche=niche)
            body = self._cold_body(lead)
        message = Message(
            lead_id=lead.id,
            channel="email",
            subject=subject,
            body=body,
            purpose=purpose,
            attempt_no=attempt_no,
            review_required=False,
            status="queued",
        )
        return self.store.messages.append(message)

    def _cold_body(self, lead: Lead) -> str:
        name = self._greeting_name(lead)
        niche = lead.niche or "freelance"
        return (
            f"Hi {name},\n\n"
            f"I saw you do {niche} freelancing. Quick question - how long does writing a new proposal usually take you?\n\n"
            "I built ProposalAI - paste any job description and get a ready proposal in 30 seconds, in your own voice.\n\n"
            "It's free to try. No signup, no credit card.\n\n"
            "Want me to send you the link?\n\n"
            f"{self.config.email_signature}"
        )

    def _followup_body(self, lead: Lead) -> str:
        name = self._greeting_name(lead)
        return (
            f"Hi {name},\n\n"
            "Just checking if my last message landed okay.\n\n"
            "Still happy to give you free access to ProposalAI if you'd like to try it.\n\n"
            f"No worries if not - just let me know!\n\n{self.config.email_signature}"
        )

    @staticmethod
    def _greeting_name(lead: Lead) -> str:
        name = (lead.name or "").strip()
        if not name:
            return "there"
        normalized = re.sub(r"[^a-z]", "", name.lower())
        return "there" if normalized in GENERIC_NAMES else name

    def _send_email(self, lead: Lead, message: Message) -> None:
        msg = EmailMessage()
        msg["Subject"] = message.subject
        msg["From"] = formataddr((self.config.email_from_name, self.config.brevo_from_email or self.config.brevo_email or ""))
        if self.config.brevo_reply_to_email:
            msg["Reply-To"] = self.config.brevo_reply_to_email
        msg["To"] = lead.email
        msg["Message-ID"] = make_msgid(idstring=f"proposalai-{message.id}")
        msg["X-ProposalAI-Lead-ID"] = lead.id
        body = self._with_compliance_footer(message.body)
        msg.set_content(body)
        self._deliver_message(msg)

    def _deliver_message(self, msg: EmailMessage) -> None:
        if self.config.brevo_prefer_api and self.config.brevo_api_key:
            self._deliver_via_api(msg)
            return
        try:
            self._deliver_via_smtp(msg)
        except smtplib.SMTPAuthenticationError as exc:
            if self.config.brevo_api_key and b"Unauthorized IP" in (exc.smtp_error or b""):
                self._deliver_via_api(msg)
                return
            raise
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, TimeoutError) as exc:
            raise TemporaryEmailDeliveryError(str(exc)) from exc

    def _deliver_via_smtp(self, msg: EmailMessage) -> None:
        if not self.config.brevo_email or not self.config.brevo_smtp_key:
            if self.config.brevo_api_key:
                self._deliver_via_api(msg)
                return
            raise RuntimeError("Brevo SMTP credentials are missing.")
        with smtplib.SMTP(self.config.brevo_smtp_host, self.config.brevo_smtp_port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(self.config.brevo_email or "", self.config.brevo_smtp_key or "")
            smtp.send_message(msg)

    def _deliver_via_api(self, msg: EmailMessage) -> None:
        if not self.config.brevo_api_key:
            raise RuntimeError("Brevo API key is missing.")
        sender_email = self.config.brevo_from_email or self.config.brevo_reply_to_email or self.config.brevo_email
        payload = {
            "sender": {"name": self.config.email_from_name, "email": sender_email},
            "to": [{"email": msg["To"]}],
            "subject": msg["Subject"],
            "textContent": msg.get_content(),
        }
        if self.config.brevo_reply_to_email:
            payload["replyTo"] = {"email": self.config.brevo_reply_to_email}
        request = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "accept": "application/json",
                "api-key": self.config.brevo_api_key,
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status >= 300:
                    raise RuntimeError(f"Brevo API returned HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            lowered = body.lower()
            if exc.code == 429 or exc.code >= 500 or "unrecognised ip" in lowered or "unauthorized ip" in lowered:
                raise TemporaryEmailDeliveryError(f"Brevo API returned HTTP {exc.code}: {body[:500]}") from exc
            raise RuntimeError(f"Brevo API returned HTTP {exc.code}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            raise TemporaryEmailDeliveryError(f"Brevo API network error: {exc.reason}") from exc
        except TimeoutError as exc:
            raise TemporaryEmailDeliveryError("Brevo API network timeout") from exc

    def _with_compliance_footer(self, body: str) -> str:
        footer = (
            "\n\n--\n"
            "You are receiving this because your public/business contact appeared relevant to freelance proposal tools. "
            "Reply 'remove me' and I will not contact you again.\n"
            f"{self.config.physical_address or ''}"
        )
        return f"{body}{footer}"

    def _can_email_lead(self, lead: Lead) -> bool:
        return bool(lead.email and EMAIL_RE.fullmatch(lead.email) and lead.status not in {"unsubscribed", "not_interested", "closed", "won", "lost"})

    def _has_any_email_attempt(self, lead: Lead) -> bool:
        return any(message.lead_id == lead.id and message.channel == "email" for message in self.store.messages.all())

    def _has_followup_for_attempt(self, lead: Lead, attempt_no: int) -> bool:
        return any(message.lead_id == lead.id and message.channel == "email" and message.attempt_no == attempt_no for message in self.store.messages.all())

    def _email_already_sent(self, email_address: str) -> bool:
        target = email_address.lower()
        for event in self.store.events.all():
            if event.kind != "email_sent":
                continue
            try:
                detail = json.loads(event.detail)
            except json.JSONDecodeError:
                detail = {"email": event.detail}
            if str(detail.get("email", "")).lower() == target:
                return True
        return False

    def _daily_remaining(self) -> int:
        today = today_ist()
        sent_today = 0
        for message in self.store.messages.all():
            if message.channel != "email" or message.status != "sent" or not message.sent_at:
                continue
            sent_at = self._parse_time(message.sent_at)
            if sent_at and sent_at.astimezone(now_ist().tzinfo).date().isoformat() == today:
                sent_today += 1
        return max(0, self.config.email_daily_limit - sent_today)

    def _lead_for_message(self, message: Message) -> Lead | None:
        for lead in self.store.leads.all():
            if lead.id == message.lead_id:
                return lead
        return None

    def _search_replies(self, imap: imaplib.IMAP4_SSL, lead: Lead) -> Iterable[dict[str, str]]:
        since = self._imap_since(lead.last_contacted_at)
        status, data = imap.search(None, "FROM", f'"{lead.email}"', "SINCE", since)
        if status != "OK":
            return []
        messages = []
        for message_id in data[0].split():
            status, fetched = imap.fetch(message_id, "(RFC822)")
            if status != "OK" or not fetched:
                continue
            raw = fetched[0][1]
            parsed = email.message_from_bytes(raw)
            received = parsedate_to_datetime(parsed.get("Date")) if parsed.get("Date") else datetime.now(timezone.utc)
            body = self._extract_body(parsed)
            messages.append({"message_id": message_id.decode(), "received_at": received.isoformat(), "body": body[:2000]})
        return messages

    def _mark_reply(self, lead: Lead, mail: dict[str, str], classification: str) -> None:
        lead.status = classification if classification in {"hot", "not_interested"} else "replied"
        lead.hot = classification == "hot"
        lead.updated_at = utc_now()
        if classification == "not_interested":
            lead.status = "unsubscribed"
        self.store.leads.upsert(lead)
        self.store.events.append(Event(lead_id=lead.id, kind="reply", detail=json.dumps(mail)))
        if classification == "hot":
            self.store.events.append(Event(lead_id=lead.id, kind="hot_lead", detail=lead.email))
            notify_hot_reply(self.config, f"Hot ProposalAI reply from {lead.name or lead.email}: {lead.email}")
        elif classification == "not_interested":
            self.store.events.append(Event(lead_id=lead.id, kind="suppressed", detail=lead.email))

    @staticmethod
    def _classify_reply(body: str) -> str:
        lowered = body.lower()
        if any(word in lowered for word in NEGATIVE_WORDS):
            return "not_interested"
        if any(word in lowered for word in POSITIVE_WORDS):
            return "hot"
        return "replied"

    @staticmethod
    def _extract_body(message: email.message.Message) -> str:
        if message.is_multipart():
            parts = []
            for part in message.walk():
                if part.get_content_type() == "text/plain" and not part.get_filename():
                    payload = part.get_payload(decode=True)
                    if payload:
                        parts.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
            return "\n".join(parts)
        payload = message.get_payload(decode=True)
        return payload.decode(message.get_content_charset() or "utf-8", errors="replace") if payload else ""

    def _has_reply_event(self, lead: Lead) -> bool:
        return any(event.lead_id == lead.id and event.kind == "reply" for event in self.store.events.all())

    @staticmethod
    def _parse_time(value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _imap_since(value: str) -> str:
        parsed = EmailCampaign._parse_time(value)
        return (parsed or datetime.now(timezone.utc) - timedelta(days=14)).strftime("%d-%b-%Y")

    def _summary_text(self) -> str:
        leads = self.store.leads.all()
        messages = self.store.messages.all()
        events = self.store.events.all()
        today = today_ist()
        sent_today = [message for message in messages if message.sent_at and (self._parse_time(message.sent_at) or datetime.now(timezone.utc)).astimezone(now_ist().tzinfo).date().isoformat() == today]
        replies_today = [event for event in events if event.kind == "reply" and event.occurred_at.startswith(today)]
        hot_leads = [lead for lead in leads if lead.hot]
        followups = [lead for lead in leads if lead.next_followup_at and lead.status not in {"unsubscribed", "closed", "won", "lost"}]
        return "\n".join(
            [
                f"ProposalAI Daily Summary - {today}",
                "",
                f"Leads found today: {sum(1 for lead in leads if lead.created_at.startswith(today))}",
                f"Emails sent today: {len(sent_today)} / {self.config.email_daily_limit}",
                f"Replies received: {len(replies_today)}",
                f"Hot leads: {len(hot_leads)}",
                "",
                "What runs tomorrow:",
                "- 9:00 AM: lead finder and outreach queue",
                "- 10:00 AM: follow-up queue",
                "- Every 2 hours: reply detector",
                "- 8:00 PM: daily summary",
                "",
                "Next follow-ups:",
                *[f"- {lead.name or lead.email}: {lead.next_followup_at}" for lead in followups[:10]],
            ]
        )
