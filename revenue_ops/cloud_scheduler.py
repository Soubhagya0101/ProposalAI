from __future__ import annotations

import json
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Any

from .config import RevenueOpsConfig
from .email_campaign import EmailCampaign
from .lead_finder import LeadFinder
from .models import Event
from .time_utils import is_business_hours_ist, now_ist, today_ist
from .workflow import RevenueAgent


class CloudScheduler:
    """Small always-on scheduler for a VPS/container deployment."""

    def __init__(self, config: RevenueOpsConfig) -> None:
        self.config = config
        self.agent = RevenueAgent(config)
        self.email_campaign = EmailCampaign(config, self.agent.store)
        self.lead_finder = LeadFinder(config, self.agent.store)
        self.state_path = config.data_dir / "cloud_scheduler_state.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def run_forever(self, poll_seconds: int = 60) -> None:
        print("ProposalAI cloud scheduler started.", flush=True)
        print("Schedule timezone: Asia/Kolkata.", flush=True)
        while True:
            try:
                self.run_pending()
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            time.sleep(poll_seconds)

    def run_pending(self) -> list[dict[str, Any]]:
        current = now_ist()
        results: list[dict[str, Any]] = []

        if self._automation_stopped():
            return [
                {
                    "task": "automation_stop",
                    "status": "stopped",
                    "stop_date": self.config.automation_stop_date,
                }
            ]

        if current.hour >= 9:
            results.append(
                self._run_once_per_day(
                    "lead_finder",
                    lambda: {"found": self.lead_finder.run_all()},
                )
            )
            results.append(
                self._run_once_per_hour(
                    "outreach_queue",
                    lambda: self.email_campaign.queue_new_outreach(),
                )
            )

        if current.hour >= 10:
            results.append(
                self._run_once_per_day(
                    "followups",
                    lambda: {
                        "queued": self.email_campaign.queue_followups(),
                    },
                )
            )

        if is_business_hours_ist(self.config.email_business_start_hour_ist, self.config.email_business_end_hour_ist):
            results.append(self._run_once_per_hour("email_sender", lambda: self.email_campaign.send_queued()))
            if current.hour in {9, 11, 13, 15, 17}:
                results.append(self._run_once_per_hour("check_replies", lambda: self.email_campaign.check_replies()))

        if current.hour >= 20 and not self._summary_sent_today():
            results.append(self._run_once_per_day("daily_summary_20", lambda: self.email_campaign.send_summary_email()))

        if current.hour > 20 or (current.hour == 20 and current.minute >= 30):
            if not self._summary_sent_today():
                results.append(self._run_once_per_day("daily_summary_backup_2030", lambda: self.email_campaign.send_summary_email()))

        return [result for result in results if result.get("status") != "already_ran"]

    def _automation_stopped(self) -> bool:
        if not self.config.automation_stop_date:
            return False
        try:
            stop_date = datetime.strptime(self.config.automation_stop_date, "%Y-%m-%d").date()
        except ValueError:
            return False
        return now_ist().date() > stop_date

    def _run_once_per_day(self, name: str, action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        return self._run_once(f"{today_ist()}:{name}", name, action)

    def _run_once_per_hour(self, name: str, action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        current = now_ist()
        return self._run_once(f"{current.date().isoformat()}:{current.hour:02d}:{name}", name, action)

    def _run_once(self, key: str, name: str, action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        state = self._load_state()
        if key in state or self._task_event_exists(key):
            return {"task": name, "status": "already_ran"}
        print(f"[{now_ist().isoformat(timespec='seconds')}] Running {name}", flush=True)
        try:
            result = action()
            state[key] = {"status": "ok", "ran_at": now_ist().isoformat(timespec="seconds"), "result": result}
            self._save_state(state)
            self.agent.store.events.append(Event(lead_id="", kind="cloud_task_ok", detail=json.dumps({"task": name, "key": key})))
            print(f"[{now_ist().isoformat(timespec='seconds')}] Finished {name}: {json.dumps(result)[:600]}", flush=True)
            return {"task": name, "status": "ok", "result": result}
        except Exception as exc:  # noqa: BLE001
            state[key] = {"status": "error", "ran_at": now_ist().isoformat(timespec="seconds"), "error": str(exc)}
            self._save_state(state)
            self.agent.store.events.append(Event(lead_id="", kind="cloud_task_error", detail=json.dumps({"task": name, "key": key, "error": str(exc)})))
            print(f"[{now_ist().isoformat(timespec='seconds')}] Failed {name}: {exc}", flush=True)
            traceback.print_exc()
            return {"task": name, "status": "error", "error": str(exc)}

    def _task_event_exists(self, key: str) -> bool:
        for event in self.agent.store.events.all():
            if event.kind not in {"cloud_task_ok", "cloud_task_error"}:
                continue
            try:
                detail = json.loads(event.detail)
            except json.JSONDecodeError:
                continue
            if detail.get("key") == key:
                return True
        return False

    def _summary_sent_today(self) -> bool:
        today = today_ist()
        for event in self.agent.store.events.all():
            if event.kind == "daily_summary_sent" and _date_prefix(event.occurred_at) == today:
                return True
        return False

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            backup = self.state_path.with_suffix(f".broken-{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
            self.state_path.replace(backup)
            return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _date_prefix(value: str) -> str:
    return value[:10] if value else ""
