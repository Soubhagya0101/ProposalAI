from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from .storage import RevenueStore


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def build_daily_report(store: RevenueStore, drafted_followups: list[dict] | None = None) -> dict:
    leads = store.leads.all()
    messages = store.messages.all()
    events = store.events.all()
    feedback = store.feedback.all()
    status_counts = Counter(lead.status for lead in leads)
    event_counts = Counter(event.kind for event in events)
    hot_leads = [lead for lead in leads if lead.hot]
    replies = event_counts.get("reply", 0)
    outbound = len([message for message in messages if message.direction == "outbound"])
    ready = len([message for message in messages if message.status in {"draft", "ready", "queued", "approved"}])
    sent = len([message for message in messages if message.status in {"sent", "delivered", "opened", "replied"}])
    free_users = status_counts.get("free", 0) + status_counts.get("trial", 0)
    paying_users = status_counts.get("paid", 0) + status_counts.get("won", 0) + status_counts.get("customer", 0)
    response_rate = round((replies / outbound) * 100, 2) if outbound else 0.0

    return {
        "date": today(),
        "metrics": {
            "leads_found": len(leads),
            "messages_ready": ready,
            "messages_sent": sent,
            "replies_received": replies,
            "hot_leads": len(hot_leads),
            "free_users": free_users,
            "paying_users": paying_users,
            "lead_to_message_rate": round((ready / len(leads)) * 100, 2) if leads else 0.0,
            "message_to_reply_rate": round((replies / sent) * 100, 2) if sent else 0.0,
            "free_to_paid_rate": round((paying_users / free_users) * 100, 2) if free_users else 0.0,
            "leads_total": len(leads),
            "messages_total": len(messages),
            "outbound_messages": outbound,
            "events_total": len(events),
            "feedback_total": len(feedback),
            "response_rate_percent": response_rate,
            "due_followup_drafts": len(drafted_followups or []),
        },
        "lead_status_counts": dict(status_counts),
        "event_counts": dict(event_counts),
        "hot_leads": [{"id": lead.id, "name": lead.name, "company": lead.company, "score": lead.score} for lead in hot_leads],
        "drafted_followups": drafted_followups or [],
    }
