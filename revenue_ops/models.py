from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, TypeVar
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


T = TypeVar("T", bound="Record")


class Record:
    id: str

    @classmethod
    def fieldnames(cls) -> list[str]:
        return [item.name for item in fields(cls)]  # type: ignore[arg-type]

    @classmethod
    def from_dict(cls: type[T], row: dict[str, Any]) -> T:
        clean = {}
        for item in fields(cls):  # type: ignore[arg-type]
            value = row.get(item.name, "")
            if item.type in (int, "int"):
                clean[item.name] = int(value or 0)
            elif item.type in (float, "float"):
                clean[item.name] = float(value or 0.0)
            elif item.type in (bool, "bool"):
                clean[item.name] = str(value).lower() in {"1", "true", "yes", "y"}
            else:
                clean[item.name] = value
        return cls(**clean)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Lead(Record):
    id: str = field(default_factory=lambda: new_id("lead"))
    name: str = ""
    company: str = ""
    email: str = ""
    profile_url: str = ""
    niche: str = ""
    country: str = ""
    review_count: int = 0
    source: str = "manual"
    status: str = "new"
    need: str = ""
    budget: str = ""
    notes: str = ""
    score: int = 0
    followup_attempts: int = 0
    last_contacted_at: str = ""
    next_followup_at: str = ""
    hot: bool = False
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class Message(Record):
    id: str = field(default_factory=lambda: new_id("msg"))
    lead_id: str = ""
    channel: str = "manual"
    direction: str = "outbound"
    subject: str = ""
    body: str = ""
    purpose: str = "outreach"
    attempt_no: int = 1
    review_required: bool = True
    status: str = "draft"
    sent_at: str = ""
    response_at: str = ""
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class Event(Record):
    id: str = field(default_factory=lambda: new_id("evt"))
    lead_id: str = ""
    kind: str = ""
    detail: str = ""
    occurred_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class Feedback(Record):
    id: str = field(default_factory=lambda: new_id("fb"))
    lead_id: str = ""
    message_id: str = ""
    did_proposal_sound_like_you: str = ""
    what_would_make_better: str = ""
    would_pay_9_month: str = ""
    notes: str = ""
    rating: int = 0
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class Metric(Record):
    id: str = field(default_factory=lambda: new_id("met"))
    date: str = ""
    name: str = ""
    value: float = 0.0
    created_at: str = field(default_factory=utc_now)
