from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .brevo_webhooks import BrevoWebhookProcessor
from .cloud_scheduler import CloudScheduler
from .config import RevenueOpsConfig
from .dashboard.adapter import load_dashboard_payload
from .time_utils import is_business_hours_ist, now_ist
from .workflow import RevenueAgent


DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"
STATIC_DIR = DASHBOARD_DIR / "static"
TEMPLATE_DIR = DASHBOARD_DIR / "templates"


class RenderServiceHandler(BaseHTTPRequestHandler):
    server_version = "ProposalAIRenderService/0.1"

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path in {"/", "/index.html"}:
            if not self._dashboard_authorized(parsed.query):
                self.send_error(401, "Unauthorized")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_error(404, "Not found")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/health":
            self._send_json({"ok": True, "service": "proposalai-revenue-ops"})
            return
        if path in {"/", "/index.html"}:
            if not self._dashboard_authorized(parsed.query):
                self.send_error(401, "Unauthorized")
                return
            self._send_file(TEMPLATE_DIR / "index.html", "text/html; charset=utf-8")
            return
        if path == "/api/summary":
            if not self._dashboard_authorized(parsed.query):
                self.send_error(401, "Unauthorized")
                return
            self._send_json(load_dashboard_payload())
            return
        if path == "/api/debug":
            if not self._dashboard_authorized(parsed.query):
                self.send_error(401, "Unauthorized")
                return
            self._send_json(self._debug_payload())
            return
        if path.startswith("/static/"):
            requested = (STATIC_DIR / path.removeprefix("/static/")).resolve()
            if STATIC_DIR.resolve() in requested.parents and requested.exists():
                self._send_file(requested)
                return
        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in {"/brevo/events", "/brevo/inbound"}:
            self.send_error(404, "Not found")
            return
        if not self._authorized(parsed.query):
            self.send_error(401, "Unauthorized")
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return
        kind = "inbound" if parsed.path.endswith("/inbound") else "event"
        result = self.server.processor.process_payload(payload, kind=kind)  # type: ignore[attr-defined]
        self._send_json(result)

    def log_message(self, format: str, *args: object) -> None:
        print("[%s] %s" % (self.log_date_time_string(), format % args), flush=True)

    def _authorized(self, query: str) -> bool:
        secret = self.server.config.brevo_webhook_secret  # type: ignore[attr-defined]
        if not secret:
            return True
        query_secret = (parse_qs(query).get("secret") or [""])[0]
        header_secret = self.headers.get("X-ProposalAI-Webhook-Secret", "")
        return secret in {query_secret, header_secret}

    def _dashboard_authorized(self, query: str) -> bool:
        secret = os.getenv("PROPOSALAI_DASHBOARD_SECRET", "").strip()
        if not secret:
            return True
        query_secret = (parse_qs(query).get("secret") or [""])[0]
        header_secret = self.headers.get("X-ProposalAI-Dashboard-Secret", "")
        return secret in {query_secret, header_secret}

    def _send_json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str | None = None) -> None:
        if not path.exists():
            self.send_error(404, "Not found")
            return
        body = path.read_bytes()
        guessed_type = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", guessed_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _debug_payload(self) -> dict:
        config = self.server.config  # type: ignore[attr-defined]
        agent = RevenueAgent(config)
        leads = agent.store.leads.all()
        messages = agent.store.messages.all()
        events = agent.store.events.all()
        current = now_ist()
        queued = [message for message in messages if message.channel == "email" and message.status == "queued"]
        sent = [message for message in messages if message.channel == "email" and message.status == "sent"]
        errored = [message for message in messages if message.channel == "email" and message.status == "error"]
        valid_email_leads = [lead for lead in leads if lead.email]
        return {
            "now_ist": current.isoformat(timespec="seconds"),
            "inside_business_hours": is_business_hours_ist(
                config.email_business_start_hour_ist,
                config.email_business_end_hour_ist,
            ),
            "store": {
                "data_dir": str(config.data_dir),
                "google_sheets_enabled": config.google_enabled,
            },
            "config_ready": {
                "send_enabled": config.send_enabled,
                "brevo_api_enabled": bool(config.brevo_api_key),
                "brevo_smtp_enabled": bool(config.brevo_email and config.brevo_smtp_key),
                "brevo_prefer_api": config.brevo_prefer_api,
                "physical_address_set": bool(config.physical_address),
                "report_email_set": bool(config.report_email),
                "hunter_configured": bool(config.hunter_api_key),
                "imap_enabled": config.imap_enabled,
            },
            "counts": {
                "leads": len(leads),
                "leads_with_email": len(valid_email_leads),
                "email_messages": len([message for message in messages if message.channel == "email"]),
                "queued": len(queued),
                "sent": len(sent),
                "errored": len(errored),
                "events": len(events),
            },
            "recent_events": [
                {
                    "time": event.occurred_at,
                    "kind": event.kind,
                    "detail": _redact_event_detail(event.detail),
                }
                for event in events[-12:]
            ],
        }


def run_render_service() -> None:
    config = RevenueOpsConfig.from_env()
    port = int(os.getenv("PORT", str(config.webhook_port or 8770)))
    scheduler = CloudScheduler(config)
    scheduler_thread = threading.Thread(target=scheduler.run_forever, name="proposalai-scheduler", daemon=True)
    scheduler_thread.start()

    agent = RevenueAgent(config)
    processor = BrevoWebhookProcessor(config, agent.store)
    server = ThreadingHTTPServer(("0.0.0.0", port), RenderServiceHandler)
    server.config = config  # type: ignore[attr-defined]
    server.processor = processor  # type: ignore[attr-defined]
    print(f"ProposalAI Render service listening on 0.0.0.0:{port}", flush=True)
    print("Routes: /health, /, /api/summary, /brevo/events, /brevo/inbound", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _redact_event_detail(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[email]", text, flags=re.IGNORECASE)
    text = re.sub(r"(api[_-]?key|smtp[_-]?key|password|secret|token)[^,}\s]*", r"\1=[redacted]", text, flags=re.IGNORECASE)
    return text[:220]
