from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .config import RevenueOpsConfig
from .emailer import deliver_daily_report
from .google_sheets import GoogleSheetsUnavailable, build_google_store
from .importers import CsvLeadImporter
from .messages import generate_followup, generate_outreach, word_count
from .models import Event, Feedback, Lead, Message, Metric, utc_now
from .reports import build_daily_report
from .storage import LocalJsonReports, RevenueStore


HOT_EVENT_KINDS = {"reply", "meeting_booked", "proposal_requested", "positive_feedback"}


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class RevenueAgent:
    def __init__(self, config: RevenueOpsConfig, store: RevenueStore | None = None) -> None:
        self.config = config
        self.store = store or self._build_store(config)
        self.reports = LocalJsonReports(config.data_dir)

    def add_lead(self, lead: Lead) -> Lead:
        lead.hot = self.is_hot(lead)
        lead.updated_at = utc_now()
        return self.store.leads.upsert(lead)

    def draft_outreach(self, lead_id: str, purpose: str = "outreach") -> Message:
        lead = self.get_lead(lead_id)
        body = generate_followup(lead, self.config.sender_name) if purpose == "followup" else generate_outreach(lead, self.config.sender_name)
        if word_count(body) >= 100:
            raise ValueError("Generated message must stay under 100 words.")
        message = Message(
            lead_id=lead.id,
            subject="Free ProposalAI access for your freelance proposals",
            body=body,
            purpose=purpose,
            attempt_no=min(lead.followup_attempts + 1, self.config.max_followups),
            status="draft",
        )
        return self.store.messages.append(message)

    def record_manual_contact(self, lead_id: str, message_id: str | None = None) -> Lead:
        lead = self.get_lead(lead_id)
        if lead.followup_attempts >= self.config.max_followups:
            raise ValueError(f"Max contact attempts reached for lead {lead.id}.")
        now = datetime.now(timezone.utc).replace(microsecond=0)
        lead.last_contacted_at = now.isoformat()
        lead.next_followup_at = (now + timedelta(days=self.config.followup_interval_days)).isoformat()
        lead.followup_attempts += 1
        lead.status = "contacted"
        lead.updated_at = utc_now()
        if message_id:
            message = self.get_message(message_id)
            message.status = "sent"
            message.sent_at = now.isoformat()
            self.store.messages.upsert(message)
        self.store.events.append(Event(lead_id=lead.id, kind="manual_contact", detail=message_id or ""))
        return self.store.leads.upsert(lead)

    def record_event(self, lead_id: str, kind: str, detail: str = "") -> Event:
        lead = self.get_lead(lead_id)
        event = self.store.events.append(Event(lead_id=lead.id, kind=kind, detail=detail))
        lead.hot = self.is_hot(lead, [event])
        lead.status = "hot" if lead.hot else lead.status
        lead.updated_at = utc_now()
        self.store.leads.upsert(lead)
        return event

    def record_feedback(
        self,
        lead_id: str,
        message_id: str,
        rating: int,
        notes: str = "",
        did_sound_like_you: str = "",
        what_would_make_better: str = "",
        would_pay_9_month: str = "",
    ) -> Feedback:
        lead = self.get_lead(lead_id)
        feedback = self.store.feedback.append(
            Feedback(
                lead_id=lead.id,
                message_id=message_id,
                did_proposal_sound_like_you=did_sound_like_you,
                what_would_make_better=what_would_make_better,
                would_pay_9_month=would_pay_9_month,
                rating=rating,
                notes=notes,
            )
        )
        if rating >= 4:
            lead.hot = True
            lead.status = "hot"
            lead.updated_at = utc_now()
            self.store.leads.upsert(lead)
        return feedback

    def import_csv(self, path: str) -> dict:
        added = []
        skipped = []
        existing_urls = {lead.profile_url for lead in self.store.leads.all() if lead.profile_url}
        for lead in CsvLeadImporter(path).iter_leads():
            if lead.profile_url and lead.profile_url in existing_urls:
                skipped.append(lead.profile_url)
                continue
            if 0 <= lead.review_count < 10:
                saved = self.add_lead(lead)
                added.append(saved.to_dict())
                existing_urls.add(saved.profile_url)
            else:
                skipped.append(lead.profile_url or lead.name)
        return {"added": added, "skipped": skipped, "added_count": len(added), "skipped_count": len(skipped)}

    def due_followups(self) -> list[Lead]:
        now = datetime.now(timezone.utc)
        due = []
        for lead in self.store.leads.all():
            next_at = parse_time(lead.next_followup_at)
            if lead.status in {"won", "lost", "unsubscribed"}:
                continue
            if lead.followup_attempts >= self.config.max_followups:
                continue
            if next_at and next_at <= now:
                due.append(lead)
        return due

    def run_daily(self) -> dict:
        lead_import = None
        if self.config.lead_import_csv and self.config.lead_import_csv.exists():
            lead_import = self.import_csv(str(self.config.lead_import_csv))
        drafts = []
        for lead in self.due_followups():
            if self._has_followup_draft_today(lead.id):
                continue
            drafts.append(self.draft_outreach(lead.id, purpose="followup").to_dict())
        report = build_daily_report(self.store, drafts)
        report["lead_import"] = lead_import or {"status": "not_configured"}
        self._save_metrics(report)
        path = self.reports.write_daily(report)
        report["local_report_path"] = str(path)
        report["email_delivery"] = deliver_daily_report(report, self.config)
        return report

    def get_lead(self, lead_id: str) -> Lead:
        for lead in self.store.leads.all():
            if lead.id == lead_id:
                return lead
        raise KeyError(f"Lead not found: {lead_id}")

    def get_message(self, message_id: str) -> Message:
        for message in self.store.messages.all():
            if message.id == message_id:
                return message
        raise KeyError(f"Message not found: {message_id}")

    def is_hot(self, lead: Lead, new_events: list[Event] | None = None) -> bool:
        events = [event for event in self.store.events.all() if event.lead_id == lead.id]
        events.extend(new_events or [])
        has_hot_event = any(event.kind in HOT_EVENT_KINDS for event in events)
        return lead.score >= self.config.hot_score_threshold or has_hot_event

    def _save_metrics(self, report: dict) -> None:
        for name, value in report["metrics"].items():
            self.store.metrics.append(Metric(date=report["date"], name=name, value=float(value)))

    def _has_followup_draft_today(self, lead_id: str) -> bool:
        today = datetime.now(timezone.utc).date().isoformat()
        for message in self.store.messages.all():
            if message.lead_id != lead_id or message.purpose != "followup":
                continue
            if message.created_at.startswith(today):
                return True
        return False

    @staticmethod
    def _build_store(config: RevenueOpsConfig) -> RevenueStore:
        if config.google_enabled:
            try:
                return build_google_store(config.google_sheet_id or "", config.google_credentials_file)  # type: ignore[arg-type]
            except GoogleSheetsUnavailable:
                pass
        return RevenueStore.local(config.data_dir)
