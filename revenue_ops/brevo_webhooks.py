from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import RevenueOpsConfig
from .email_campaign import NEGATIVE_WORDS, POSITIVE_WORDS
from .models import Event, Lead, utc_now
from .notifications import notify_hot_reply
from .storage import RevenueStore


EVENT_KIND_MAP = {
    "sent": "email_sent_event",
    "delivered": "email_delivered",
    "opened": "email_opened",
    "unique_opened": "email_opened",
    "proxy_open": "email_opened",
    "click": "email_clicked",
    "clicked": "email_clicked",
    "soft_bounce": "email_soft_bounced",
    "hard_bounce": "email_hard_bounced",
    "blocked": "email_blocked",
    "spam": "email_complaint",
    "complaint": "email_complaint",
    "unsubscribed": "email_unsubscribed",
    "invalid_email": "email_invalid",
    "error": "email_error_event",
}


class BrevoWebhookProcessor:
    def __init__(self, config: RevenueOpsConfig, store: RevenueStore) -> None:
        self.config = config
        self.store = store

    def process_file(self, path: str | Path, kind: str = "auto") -> dict:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return self.process_payload(payload, kind=kind)

    def process_payload(self, payload: Any, kind: str = "auto") -> dict:
        if isinstance(payload, list):
            results = [self.process_payload(item, kind=kind) for item in payload]
            return {"status": "ok", "processed": len(results), "results": results}
        if not isinstance(payload, dict):
            return {"status": "ignored", "reason": "payload must be an object or list"}

        detected = kind
        if detected == "auto":
            detected = "inbound" if self._looks_like_inbound(payload) else "event"
        if detected == "inbound":
            return self._process_inbound(payload)
        return self._process_event(payload)

    def _process_inbound(self, payload: dict[str, Any]) -> dict:
        sender = self._extract_sender(payload)
        body = self._extract_body(payload)
        if not sender:
            return {"status": "ignored", "reason": "no sender found"}
        lead = self._lead_by_email(sender)
        if not lead:
            self.store.events.append(Event(lead_id="", kind="reply_unmatched", detail=json.dumps(self._compact(payload))))
            return {"status": "unmatched_reply", "from": sender}

        classification = self._classify_reply(body)
        if classification == "not_interested":
            lead.status = "unsubscribed"
            lead.hot = False
        elif classification == "hot":
            lead.status = "hot"
            lead.hot = True
        else:
            lead.status = "replied"
        lead.updated_at = utc_now()
        self.store.leads.upsert(lead)
        self.store.events.append(Event(lead_id=lead.id, kind="reply", detail=json.dumps({"from": sender, "classification": classification, "body": body[:2000]})))
        if classification == "hot":
            self.store.events.append(Event(lead_id=lead.id, kind="hot_lead", detail=sender))
            notify_hot_reply(self.config, f"Hot ProposalAI reply from {lead.name or sender}: {sender}")
        if classification == "not_interested":
            self.store.events.append(Event(lead_id=lead.id, kind="suppressed", detail=sender))
        return {"status": "reply_recorded", "lead_id": lead.id, "classification": classification}

    def _process_event(self, payload: dict[str, Any]) -> dict:
        event_name = str(self._first(payload, "event", "Event", "type", "Type") or "").lower()
        email_address = str(self._first(payload, "email", "recipient", "to", "Email") or "").lower()
        kind = EVENT_KIND_MAP.get(event_name, f"brevo_{event_name or 'event'}")
        lead = self._lead_by_email(email_address) if email_address else None
        detail = json.dumps(self._compact(payload))
        self.store.events.append(Event(lead_id=lead.id if lead else "", kind=kind, detail=detail))
        if lead and kind in {"email_hard_bounced", "email_blocked", "email_invalid", "email_complaint", "email_unsubscribed"}:
            lead.status = "unsubscribed" if kind == "email_unsubscribed" else "closed"
            lead.hot = False
            lead.updated_at = utc_now()
            self.store.leads.upsert(lead)
        return {"status": "event_recorded", "event": event_name, "kind": kind, "lead_id": lead.id if lead else ""}

    @staticmethod
    def _looks_like_inbound(payload: dict[str, Any]) -> bool:
        keys = {key.lower() for key in payload}
        return bool(keys & {"from", "sender", "text", "textbody", "html", "attachments"}) and not bool(keys & {"event", "type"})

    @staticmethod
    def _classify_reply(body: str) -> str:
        lowered = body.lower()
        if any(word in lowered for word in NEGATIVE_WORDS):
            return "not_interested"
        if any(word in lowered for word in POSITIVE_WORDS):
            return "hot"
        return "replied"

    def _lead_by_email(self, email_address: str) -> Lead | None:
        target = email_address.lower()
        for lead in self.store.leads.all():
            if lead.email.lower() == target:
                return lead
        return None

    def _extract_sender(self, payload: dict[str, Any]) -> str:
        sender = self._first(payload, "from", "sender", "From", "Sender")
        if isinstance(sender, dict):
            return str(self._first(sender, "email", "address", "mail") or "").lower()
        if isinstance(sender, list) and sender:
            first = sender[0]
            if isinstance(first, dict):
                return str(self._first(first, "email", "address", "mail") or "").lower()
            return str(first).lower()
        return str(sender or self._first(payload, "from_email", "sender_email", "email") or "").lower()

    def _extract_body(self, payload: dict[str, Any]) -> str:
        body = self._first(payload, "text", "TextBody", "textBody", "body", "Body", "html", "HtmlBody", "subject", "Subject")
        if isinstance(body, (dict, list)):
            return json.dumps(body)
        return str(body or "")

    @staticmethod
    def _first(payload: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in payload and payload[key] not in (None, ""):
                return payload[key]
        lowered = {key.lower(): value for key, value in payload.items()}
        for key in keys:
            value = lowered.get(key.lower())
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _compact(payload: dict[str, Any]) -> dict[str, Any]:
        compact = {}
        for key, value in payload.items():
            if isinstance(value, str):
                compact[key] = value[:1200]
            elif isinstance(value, (int, float, bool)) or value is None:
                compact[key] = value
            else:
                compact[key] = str(value)[:1200]
        return compact
