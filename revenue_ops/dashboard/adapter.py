from __future__ import annotations

import csv
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = Path(__file__).resolve().parent
SAMPLE_STORE = DASHBOARD_DIR / "data" / "revenue_store.json"


@dataclass(frozen=True)
class StoreSource:
    path: Path
    kind: str
    created: bool = False


def load_dashboard_payload() -> dict[str, Any]:
    _load_env()
    source = _find_or_create_store()
    if source.kind == "json":
        raw = _load_json(source.path)
    elif source.kind == "csv_dir":
        raw = _load_csv_dir(source.path)
    else:
        raw = _load_sqlite(source.path)
    normalized = _normalize_store(raw)
    normalized["source"] = {
        "path": str(source.path),
        "kind": source.kind,
        "created": source.created,
        "loaded_at": _now_iso(),
    }
    return normalized


def _find_or_create_store() -> StoreSource:
    env_path = os.environ.get("PROPOSALAI_REVENUE_STORE")
    candidates: list[tuple[Path, str]] = []

    if env_path:
        path = Path(env_path).expanduser()
        candidates.append((path, _kind_for(path)))

    data_dir = os.environ.get("PROPOSALAI_REVENUE_DATA_DIR")
    if data_dir:
        candidates.append((Path(data_dir).expanduser(), "csv_dir"))

    candidates.extend(
        [
            (ROOT / "revenue_ops" / "data" / "revenue_store.json", "json"),
            (ROOT / "revenue_ops" / "revenue_store.json", "json"),
            (ROOT / "data" / "revenue_ops.json", "json"),
            (ROOT / "revenue_ops_data", "csv_dir"),
            (ROOT / "revenue_ops" / "dashboard" / "data" / "revenue_store.json", "json"),
            (ROOT / "revenue_ops" / "data" / "revenue_ops.db", "sqlite"),
            (ROOT / "revenue_ops" / "revenue_ops.db", "sqlite"),
            (ROOT / "proposalai_revenue.db", "sqlite"),
        ]
    )

    for path, kind in candidates:
        if path.exists() and (kind != "csv_dir" or (path / "leads.csv").exists()):
            return StoreSource(path=path, kind=kind)

    SAMPLE_STORE.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE_STORE.write_text(json.dumps(_sample_store(), indent=2), encoding="utf-8")
    return StoreSource(path=SAMPLE_STORE, kind="json", created=True)


def _kind_for(path: Path) -> str:
    if path.is_dir() or path.suffix == "":
        return "csv_dir"
    return "sqlite" if path.suffix.lower() in {".db", ".sqlite", ".sqlite3"} else "json"


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_csv_dir(path: Path) -> dict[str, list[dict[str, Any]]]:
    data = {
        "leads": _read_csv(path / "leads.csv"),
        "messages": _read_csv(path / "messages.csv"),
        "events": _read_csv(path / "events.csv"),
        "feedback": _read_csv(path / "feedback.csv"),
        "metrics": _read_csv(path / "metrics.csv"),
    }
    data["replies"] = [event for event in data["events"] if _lower(event.get("kind")) == "reply"]
    data["followups"] = [
        {
            "lead": lead.get("company") or lead.get("name") or lead.get("email"),
            "due_at": lead.get("next_followup_at"),
            "action": "Send follow-up draft",
            "priority": "high" if _lower(lead.get("hot")) in {"1", "true", "yes", "y"} else "normal",
        }
        for lead in data["leads"]
        if lead.get("next_followup_at") and _lower(lead.get("status")) not in {"won", "lost", "unsubscribed"}
    ]
    return data


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _load_sqlite(path: Path) -> dict[str, list[dict[str, Any]]]:
    data: dict[str, list[dict[str, Any]]] = {}
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        tables = [
            row["name"]
            for row in conn.execute(
                "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
            )
        ]
        for table in tables:
            if table.lower() in {"leads", "messages", "replies", "users", "events", "followups"}:
                rows = conn.execute(f'select * from "{table}" order by rowid desc limit 200').fetchall()
                data[table.lower()] = [dict(row) for row in rows]
    return data


def _normalize_store(raw: Any) -> dict[str, Any]:
    if isinstance(raw, list):
        raw = {"events": raw}
    if not isinstance(raw, dict):
        raw = {}

    leads = _list(raw, "leads", "prospects", "contacts")
    messages = _list(raw, "messages", "outreach", "drafts")
    replies = _list(raw, "replies", "responses")
    users = _list(raw, "users", "accounts", "customers")
    events = _list(raw, "events", "activity", "activities")
    followups = _list(raw, "followups", "follow_ups", "tasks")
    metrics_rows = _list(raw, "metrics")
    today = datetime.now(timezone.utc).astimezone().date().isoformat()

    inferred_replies = [lead for lead in leads if _lower(lead.get("status")) in {"replied", "reply", "responded"}]
    event_replies = [event for event in events if _lower(event.get("kind")) == "reply"]
    total_replies = len(replies) if replies else len(event_replies) or len(inferred_replies)

    free_users = [user for user in users if _is_free_user(user)]
    paying_users = [user for user in users if _is_paying_user(user)]
    free_leads = [lead for lead in leads if _lower(lead.get("status")) in {"free", "trial", "freemium"}]
    paying_leads = [lead for lead in leads if _lower(lead.get("status")) in {"paid", "won", "converted", "customer"}]
    sent_messages = [msg for msg in messages if _lower(msg.get("status")) in {"sent", "delivered", "opened", "replied"}]
    sent_today = [
        msg
        for msg in sent_messages
        if _date_prefix(_first(msg, "sent_at", "updated_at", "created_at")) == today
    ]
    manual_contacts = [event for event in events if _lower(event.get("kind")) in {"manual_contact", "message_sent"}]
    opened_events = [event for event in events if _lower(event.get("kind")) == "email_opened"]
    clicked_events = [event for event in events if _lower(event.get("kind")) == "email_clicked"]
    bounced_events = [event for event in events if _lower(event.get("kind")) in {"email_hard_bounced", "email_soft_bounced", "email_blocked", "email_invalid"}]
    ready_messages = [
        msg
        for msg in messages
        if _lower(msg.get("status")) in {"ready", "queued", "approved", "drafted", "draft"}
    ]

    activity = _recent_activity(events, leads, messages, replies, users)
    hot_leads = _hot_leads(leads)
    next_followups = _next_followups(followups, leads)

    metrics = {
        "leads_found": len(leads),
        "messages_ready": len(ready_messages),
        "messages_sent": len(sent_messages) or len(manual_contacts),
        "emails_sent_today": len(sent_today),
        "email_daily_limit": int(os.environ.get("EMAIL_DAILY_LIMIT", "40")),
        "open_rate": _percent(len(opened_events), len(sent_messages) or len(manual_contacts)),
        "click_rate": _percent(len(clicked_events), len(sent_messages) or len(manual_contacts)),
        "bounces": len(bounced_events),
        "replies": total_replies,
        "reply_rate": _percent(total_replies, len(sent_messages) or len(manual_contacts)),
        "free_users": len(free_users) or int(_latest_metric(metrics_rows, "free_users", 0)) or len(free_leads),
        "paying_users": len(paying_users) or int(_latest_metric(metrics_rows, "paying_users", 0)) or len(paying_leads),
        "lead_reply_rate": _percent(total_replies, len(leads)),
        "free_to_paid_rate": _percent(
            len(paying_users) or int(_latest_metric(metrics_rows, "paying_users", 0)) or len(paying_leads),
            (len(free_users) or int(_latest_metric(metrics_rows, "free_users", 0)) or len(free_leads))
            + (len(paying_users) or int(_latest_metric(metrics_rows, "paying_users", 0)) or len(paying_leads)),
        ),
        "lead_to_paid_rate": _percent(
            len(paying_users) or int(_latest_metric(metrics_rows, "paying_users", 0)) or len(paying_leads),
            len(leads),
        ),
        "hot_leads_count": len(hot_leads),
        "followups_scheduled": len(next_followups),
    }

    return {
        "metrics": metrics,
        "recent_activity": activity[:12],
        "hot_leads": hot_leads[:8],
        "next_followups": next_followups[:8],
        "next_scheduled_runs": _next_scheduled_runs(),
        "counts": {
            "leads": len(leads),
            "messages": len(messages),
            "replies": len(replies),
            "users": len(users),
            "events": len(events),
            "followups": len(followups),
            "metrics": len(metrics_rows),
        },
    }


def _list(raw: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _recent_activity(
    events: list[dict[str, Any]],
    leads: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    replies: list[dict[str, Any]],
    users: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    activity = [_activity_item(event) for event in events]

    if not activity:
        activity.extend(_activity_from_items(leads, "Lead found", "company", "created_at"))
        activity.extend(_activity_from_items(messages, "Message updated", "subject", "updated_at"))
        activity.extend(_activity_from_items(replies, "Reply received", "from", "created_at"))
        activity.extend(_activity_from_items(users, "User updated", "email", "updated_at"))

    return sorted(activity, key=lambda item: item.get("time") or "", reverse=True)


def _activity_item(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "time": _first(event, "time", "timestamp", "occurred_at", "created_at", "updated_at"),
        "type": _first(event, "type", "event", "kind", "action") or "activity",
        "title": _first(event, "title", "summary", "name") or _first(event, "type", "event", "kind") or "Activity",
        "detail": _first(event, "detail", "description", "message") or "",
    }


def _activity_from_items(items: list[dict[str, Any]], title: str, label_key: str, time_key: str) -> list[dict[str, Any]]:
    return [
        {
            "time": _first(item, time_key, "created_at", "updated_at", "time", "timestamp") or "",
            "type": title.lower().replace(" ", "_"),
            "title": title,
            "detail": str(_first(item, label_key, "name", "email", "id") or "Unknown"),
        }
        for item in items
    ]


def _hot_leads(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hot = []
    for lead in leads:
        score = _score(lead)
        status = _lower(lead.get("status"))
        intent = _lower(lead.get("intent"))
        hot_flag = _lower(lead.get("hot")) in {"1", "true", "yes", "y"}
        if hot_flag or score >= 75 or status in {"hot", "qualified", "priority"} or intent in {"high", "buyer", "urgent"}:
            hot.append(
                {
                    "name": _first(lead, "name", "contact", "email") or "Unknown lead",
                    "company": _first(lead, "company", "account", "organization") or "Unknown company",
                    "score": score,
                    "stage": _first(lead, "stage", "status", "intent") or "new",
                    "value": _first(lead, "value", "deal_value", "revenue") or "",
                }
            )
    return sorted(hot, key=lambda item: item["score"], reverse=True)


def _next_followups(followups: list[dict[str, Any]], leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for followup in followups:
        if _lower(followup.get("status")) in {"done", "completed", "sent"}:
            continue
        items.append(
            {
                "due": _first(followup, "due_at", "due", "scheduled_at", "next_follow_up") or "",
                "lead": _first(followup, "lead", "lead_name", "company", "email") or "Follow-up",
                "action": _first(followup, "action", "task", "message", "note") or "Follow up",
                "priority": _first(followup, "priority", "status") or "normal",
            }
        )

    for lead in leads:
        due = _first(lead, "next_followup_at", "next_follow_up", "next_followup", "follow_up_at", "followup_at")
        if due and _lower(lead.get("status")) not in {"converted", "paid", "closed_won"}:
            items.append(
                {
                    "due": due,
                    "lead": _first(lead, "name", "company", "email") or "Lead",
                    "action": _first(lead, "next_action", "follow_up_note") or "Follow up",
                    "priority": _first(lead, "priority", "intent") or "normal",
                }
            )
    return sorted(items, key=lambda item: item.get("due") or "9999")


def _sample_store() -> dict[str, Any]:
    return {
        "leads": [
            {
                "name": "Maya Chen",
                "company": "Northstar Ops",
                "status": "hot",
                "score": 92,
                "intent": "high",
                "value": "$2,400/mo",
                "created_at": "2026-05-19T07:05:00+05:30",
                "next_follow_up": "2026-05-19T14:00:00+05:30",
                "next_action": "Send custom ROI breakdown",
            },
            {
                "name": "Ravi Menon",
                "company": "Tenderly Studio",
                "status": "qualified",
                "score": 81,
                "value": "$900/mo",
                "created_at": "2026-05-19T06:50:00+05:30",
            },
            {
                "name": "Avery Brooks",
                "company": "GrantPilot",
                "status": "new",
                "score": 63,
                "created_at": "2026-05-18T18:30:00+05:30",
            },
        ],
        "messages": [
            {"subject": "ProposalAI ROI intro", "status": "ready", "updated_at": "2026-05-19T07:12:00+05:30"},
            {"subject": "Follow-up: bid response automation", "status": "sent", "sent_at": "2026-05-19T06:59:00+05:30", "updated_at": "2026-05-19T06:59:00+05:30"},
            {"subject": "Founder note", "status": "draft", "updated_at": "2026-05-18T21:20:00+05:30"},
        ],
        "replies": [
            {"from": "maya@northstar.example", "created_at": "2026-05-19T07:22:00+05:30", "message": "Asked for pricing."}
        ],
        "users": [
            {"email": "trial1@example.com", "plan": "free", "created_at": "2026-05-18T09:00:00+05:30"},
            {"email": "ops@northstar.example", "plan": "paid", "updated_at": "2026-05-19T07:30:00+05:30"},
        ],
        "followups": [
            {
                "lead": "Northstar Ops",
                "due_at": "2026-05-19T14:00:00+05:30",
                "action": "Send custom ROI breakdown",
                "priority": "high",
            },
            {
                "lead": "Tenderly Studio",
                "due_at": "2026-05-20T10:00:00+05:30",
                "action": "Check whether founder wants a done-for-you setup",
                "priority": "medium",
            },
        ],
        "events": [
            {
                "timestamp": "2026-05-19T07:30:00+05:30",
                "type": "conversion",
                "title": "Paying user added",
                "detail": "Northstar Ops moved from free to paid.",
            },
            {
                "timestamp": "2026-05-19T07:22:00+05:30",
                "type": "reply",
                "title": "Reply received",
                "detail": "Maya asked for pricing and implementation timing.",
            },
        ],
    }


def _is_free_user(user: dict[str, Any]) -> bool:
    plan = _lower(_first(user, "plan", "tier", "status"))
    return plan in {"free", "trial", "freemium"} or bool(user.get("is_free"))


def _is_paying_user(user: dict[str, Any]) -> bool:
    plan = _lower(_first(user, "plan", "tier", "status"))
    return plan in {"paid", "pro", "starter", "team", "enterprise", "subscribed"} or bool(user.get("is_paying"))


def _latest_metric(rows: list[dict[str, Any]], name: str, default: float) -> float:
    matches = [row for row in rows if row.get("name") == name]
    if not matches:
        return default
    latest = sorted(matches, key=lambda row: row.get("created_at") or row.get("date") or "")[-1]
    try:
        return float(latest.get("value") or default)
    except (TypeError, ValueError):
        return default


def _first(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _score(item: dict[str, Any]) -> int:
    value = _first(item, "score", "lead_score", "priority_score")
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _percent(part: int, total: int) -> float:
    return round((part / total) * 100, 1) if total else 0.0


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _date_prefix(value: Any) -> str:
    text = str(value or "")
    return text[:10] if len(text) >= 10 else ""


def _next_scheduled_runs() -> list[dict[str, str]]:
    return [
        {"name": "Lead finder + cold email queue", "time": "Daily 9:00 AM IST"},
        {"name": "Brevo webhook receiver", "time": "Daily 9:05 AM IST"},
        {"name": "Follow-up sender", "time": "Daily 10:00 AM IST"},
        {"name": "Reply detector", "time": "Every 2 hours"},
        {"name": "Email retry sender", "time": "Hourly during workday"},
        {"name": "Daily summary email", "time": "Daily 8:00 PM IST"},
    ]


def _load_env(path: Path | None = None) -> None:
    env_path = path or ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = value.strip().strip('"').strip("'")
        if key not in os.environ or not os.environ[key].strip():
            os.environ[key] = value
