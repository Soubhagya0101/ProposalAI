from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .brevo_webhooks import BrevoWebhookProcessor
from .config import RevenueOpsConfig
from .workflow import RevenueAgent


class BrevoWebhookHandler(BaseHTTPRequestHandler):
    server_version = "ProposalAIBrevoWebhook/0.1"

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/health":
            self._send_json({"ok": True})
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
        print("[%s] %s" % (self.log_date_time_string(), format % args))

    def _authorized(self, query: str) -> bool:
        secret = self.server.config.brevo_webhook_secret  # type: ignore[attr-defined]
        if not secret:
            return True
        query_secret = (parse_qs(query).get("secret") or [""])[0]
        header_secret = self.headers.get("X-ProposalAI-Webhook-Secret", "")
        return secret in {query_secret, header_secret}

    def _send_json(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(config: RevenueOpsConfig) -> None:
    agent = RevenueAgent(config)
    processor = BrevoWebhookProcessor(config, agent.store)
    server = ThreadingHTTPServer((config.webhook_host, config.webhook_port), BrevoWebhookHandler)
    server.config = config  # type: ignore[attr-defined]
    server.processor = processor  # type: ignore[attr-defined]
    print(f"ProposalAI Brevo webhook server running at http://{config.webhook_host}:{config.webhook_port}")
    print("Endpoints: POST /brevo/events and POST /brevo/inbound")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping webhook server.")
    finally:
        server.server_close()
