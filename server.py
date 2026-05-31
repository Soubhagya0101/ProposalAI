from __future__ import annotations

import json
import mimetypes
import os
import re
import threading
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse


ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"
GITHUB_MODELS_URL = "https://models.github.ai/inference/chat/completions"
BLUESMINDS_MODELS_URL = "https://api.bluesminds.com/v1/chat/completions"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/chat/completions"
GITHUB_MODEL_ID = "openai/gpt-4o-mini"
BLUESMINDS_MODEL_ID = "gpt-4o-mini"
GROQ_MODEL_ID = "llama-3.3-70b-versatile"
MODEL_ID = BLUESMINDS_MODEL_ID
USER_RETRY_MESSAGE = "Taking longer than usual - please try again."
PROVIDER_MAX_ATTEMPTS = 3
PROVIDER_TIMEOUT_SECONDS = 45
IST = timezone(timedelta(hours=5, minutes=30))
FEEDBACK_TYPES = {
    "human": "This sounds human",
    "robotic": "Still sounds robotic",
    "needs_something": "Good but needs something",
}
FEEDBACK_HEADERS = [
    "Timestamp IST",
    "Date IST",
    "Feedback",
    "Comment",
    "Proposal Style",
    "Words",
    "Niche",
    "Job Category",
    "Feedback ID",
]
FEEDBACK_LOCK = threading.Lock()
FORBIDDEN_PHRASES = (
    "passionate",
    "dedicated",
    "excited to",
    "leverage",
    "utilize",
    "synergy",
    "results-driven",
    "hard-working",
    "detail-oriented",
    "i would love to",
    "looking forward",
    "i am confident",
    "rest assured",
    "i guarantee",
    "seamlessly",
    "drive engagement",
    "significantly",
    "first i will",
    "next i will",
    "then i will",
    "finally i will",
    "lastly i will",
    "this resolves",
    "this addresses",
    "this helps",
    "this ensures",
    "this will ensure",
    "engagement",
    "conversion rates",
    "lost sales",
)
GENERIC_FILLER = (
    "please confirm if you want to proceed",
    "proceed with this approach",
    "understanding your brand's tone will guide the content creation process",
    "the immediate action is",
    "detailed review of the current",
    "addressing this issue promptly",
    "crucial",
    "seamless",
    "regular updates",
    "keep you informed",
    "necessary adjustments",
    "it's important",
    "tailor the fix",
    "functioning properly",
    "ensure reliability",
    "save time",
    "reduce frustration",
    "ensure clarity",
    "based on your needs",
    "protect sensitive information",
    "ensure everything functions correctly",
    "based on your requirements",
    "allow easy",
    "stored securely",
    "easily",
    "ensure functionality",
    "works as expected",
    "exact needs",
    "aligned with your requirements",
    "everything works as intended",
    "unnecessary complexity",
    "this approach keeps",
    "streamline your process",
    "ensure accuracy",
    "meet your needs",
    "what you require",
    "i have worked on similar projects",
    "worked on similar projects",
    "similar projects",
    "technical specification",
    "this improvement",
    "can lead to",
    "smooth experience",
    "fully functional",
)
BROAD_QUESTION_PATTERNS = (
    r"(?:what|which|do you have|are there|could you|can you)[^?]{0,48}\b(?:issues?|bugs?|features?|functionalit(?:y|ies)|themes?|topics?)",
    r"tell me more about",
)
CONFIRMATION_ENDINGS = (
    "please confirm",
    "want to proceed",
    "proceed with this approach",
    "discuss the details",
    "share your requirements",
    "get started",
)
INSIGHT_MARKERS = (
    "worst",
    "tight",
    "risk",
    "risky",
    "overkill",
    "too basic",
    "without",
    "hard part",
    "usually",
    "often",
    "extra admin",
    "lost",
    "lose",
    "break",
    "fail",
    "fails",
    "failure",
    "disagree",
    "mismatch",
    "drift",
    "transition",
)
DOMAIN_KEYWORDS = {
    "development": {
        "api",
        "app",
        "checkout",
        "code",
        "css",
        "dashboard",
        "developer",
        "development",
        "frontend",
        "generator",
        "html",
        "invoice",
        "integration",
        "landing",
        "node",
        "node.js",
        "shopify",
        "software",
        "stripe",
        "tool",
        "web",
        "website",
        "woocommerce",
    },
    "writing": {
        "article",
        "blog",
        "content",
        "copy",
        "copywriter",
        "linkedin",
        "post",
        "posts",
        "writer",
        "writing",
    },
    "design": {"brand", "designer", "design", "figma", "graphic", "logo", "ui", "ux"},
    "video": {"editing", "editor", "premiere", "reel", "video", "youtube"},
}
PROOF_CATEGORIES = {
    "ecommerce": ("shopify", "woocommerce", "cart", "checkout", "payment"),
    "dashboard": ("dashboard", "analytics", "export", "report", "driver"),
    "landing_page": ("landing", "hero", "figma", "saas launch", "signup"),
    "api": ("stripe", "api", "integration", "webhook", "node.js", "node"),
}
CONTROLLED_CONTEXT_TERMS = (
    "figma",
    "signup flow",
    "sign-up flow",
    "signup",
    "sign-up",
    "crm",
    "stripe",
    "dashboard",
    "mobile app",
    "web app",
    "wordpress",
    "woocommerce",
    "shopify",
)
RELEVANCE_STOPWORDS = {
    "a",
    "an",
    "and",
    "build",
    "built",
    "create",
    "created",
    "fixed",
    "for",
    "from",
    "helped",
    "in",
    "project",
    "reduced",
    "the",
    "that",
    "this",
    "tool",
    "website",
    "with",
}
@dataclass(slots=True)
class ApiResult:
    status: int
    payload: dict[str, Any]


class ProposalAIHandler(BaseHTTPRequestHandler):
    server_version = "ProposalAI/1.0"

    def do_HEAD(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path == "/health":
            self._send_empty(200, "application/json; charset=utf-8")
            return
        if path in {"/", "/index.html", "/public/index.html"}:
            self._send_file_head(PUBLIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        self.send_error(404, "Not found")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/health":
            self._send_json({"ok": True, "service": "proposalai"})
            return
        if path == "/api/generate-proposal":
            if (parse_qs(parsed.query).get("test") or [""])[0] == "1":
                result = generate_proposal({}, test_mode=True)
                self._send_json(result.payload, result.status)
                return
            self._send_json({"error": "Use POST for /api/generate-proposal."}, 405)
            return
        if path in {"/", "/index.html", "/public/index.html"}:
            self._send_file(PUBLIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        path = unquote(urlparse(self.path).path)
        if path not in {"/api/generate-proposal", "/api/feedback"}:
            self.send_error(404, "Not found")
            return

        payload = self._read_json_payload()
        if payload is None:
            return

        if path == "/api/generate-proposal":
            result = generate_proposal(payload)
        else:
            result = save_feedback(payload)
        self._send_json(result.payload, result.status)

    def log_message(self, format: str, *args: object) -> None:
        print("[%s] %s" % (self.log_date_time_string(), format % args), flush=True)

    def _read_json_payload(self) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            self._send_json({"error": f"Invalid JSON request: {exc.msg}."}, 400)
            return None
        if not isinstance(payload, dict):
            self._send_json({"error": "Request body must be a JSON object."}, 400)
            return None
        return payload

    def _send_empty(self, status: int, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file_head(self, path: Path, content_type: str | None = None) -> None:
        if not path.exists():
            self.send_error(404, "Not found")
            return
        self._send_empty(200, content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream")

    def _send_file(self, path: Path, content_type: str | None = None) -> None:
        if not path.exists():
            self.send_error(404, "Not found")
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def generate_proposal(body: dict[str, Any], test_mode: bool = False) -> ApiResult:
    if test_mode:
        token = github_models_token()
        if not token:
            print("[ProposalAI] Generation token is not configured.", flush=True)
            return error(USER_RETRY_MESSAGE, 503)
        result = request_github_models(
            token,
            "Reply with exactly this sentence: ProposalAI GitHub Models connection works.",
            temperature=0,
            max_tokens=80,
        )
        if result.status != 200:
            return result
        return ApiResult(200, {"ok": True, "model": generation_model_id(), "response": result.payload["proposal"]})

    profile = normalize_profile(body.get("profile"))
    job_description = trim(body.get("jobDescription"))
    style = normalize_style(body.get("style"))

    if not profile:
        return error("Complete and save your profile first.", 400)
    if len(job_description) < 50:
        return error("Paste a job description with at least 50 characters.", 400)

    mismatch = profile_mismatch(profile, job_description)
    if mismatch:
        return ApiResult(
            422,
            {
                "code": "PROFILE_MISMATCH",
                "error": (
                    f"Profile mismatch: this job asks for {mismatch['job_label']} work, "
                    f"but the saved profile is {profile['niche']}. Edit the profile before generating "
                    "a proposal for this role."
                ),
            },
        )

    token = github_models_token()
    relevant_win = select_relevant_win(profile["pastWin"], job_description)
    guidance = situation_guidance(job_description, style)
    if not token:
        print("[ProposalAI] Generation token is not configured; using rule-based draft.", flush=True)
        fallback = build_rule_based_proposal(job_description, relevant_win, style)
        fallback_findings = proposal_violations(fallback, profile, job_description, relevant_win, style)
        fallback_blockers = blocking_violations(fallback, fallback_findings)
        if fallback_blockers:
            print(f"[ProposalAI] Rule-based draft blocked without token: {'; '.join(fallback_blockers)}.", flush=True)
            return error(USER_RETRY_MESSAGE, 503)
        return ApiResult(
            200,
            {
                "model": generation_model_id(),
                "style": style,
                "proposal": fallback.strip(),
                "wordCount": word_count(fallback),
                "fallback": "rule_based_missing_token",
            },
        )

    prompt = build_prompt(profile, job_description, relevant_win, guidance, style)
    result = request_github_models(token, prompt, temperature=0.42, max_tokens=620 if style == "detailed" else 320)
    if result.status != 200:
        fallback = build_rule_based_proposal(job_description, relevant_win, style)
        fallback_findings = proposal_violations(fallback, profile, job_description, relevant_win, style)
        fallback_blockers = blocking_violations(fallback, fallback_findings)
        if fallback_blockers:
            print(f"[ProposalAI] Provider failed and rule-based draft blocked: {'; '.join(fallback_blockers)}.", flush=True)
            return result
        print(f"[ProposalAI] Provider failed with {result.status}; using rule-based draft.", flush=True)
        return ApiResult(
            200,
            {
                "model": generation_model_id(),
                "style": style,
                "proposal": fallback.strip(),
                "wordCount": word_count(fallback),
                "fallback": "rule_based_provider_failure",
            },
        )

    proposal = clean_proposal(str(result.payload["proposal"]))
    findings = proposal_violations(proposal, profile, job_description, relevant_win, style)
    blockers = blocking_violations(proposal, findings)
    provider_repair_failed = False
    if blockers:
        result = request_github_models(
            token,
            "\n".join(
                [
                    "Rewrite this freelance proposal to comply with every rule below.",
                    f"Fix these blocking issues: {', '.join(blockers)}.",
                    "- Open immediately with a concrete detail from the client's job, not a greeting or an introduction about the freelancer.",
                    "- The opening must add an observation the client did not write but will immediately recognize as true. Never merely restate the brief.",
                    "- State facts and outcomes. Do not explain that the project is important, beneficial, impactful, or engaging.",
                    "- Every sentence must state client insight, allowed proof, the finished outcome, or one necessary decision question.",
                    "- For detailed mode, add depth about why the problem exists, what it is costing them, and what outcome they get. Do not list your methodology.",
                    "- Past win rule: If the freelancer profile includes a past win/success story, compare it to the job description. When it is relevant to the job's platform, service, skill, industry, or outcome, include it naturally as one short proof sentence. Do not force it if unrelated. If relevant, mention the concrete outcome/metric from the past win.",
                    "- If an allowed past win exists, include it naturally once as a proof sentence. If no allowed past win exists, skip proof completely.",
                    (
                        f"- Relevant past win to weave in naturally: {relevant_win}"
                        if relevant_win
                        else "- No past win is supplied for this job. Do not claim any previous result, similar project, client, or metric."
                    ),
                    "- Do not invent clients, industries, metrics, timelines, or outcomes.",
                    "- Only mention tools, platforms, or features that appear explicitly in the job description or the freelancer profile. Never invent context.",
                    "- If a tool, platform, or feature is not explicitly present, speak generally instead of naming it.",
                    "- Do not borrow facts from the style example; use only the job description and allowed past win.",
                    "- Do not mention years of experience. Use concrete proof or a concrete approach instead.",
                    "- Ask at most one question and only when the answer changes the work.",
                    "- Do not ask broad discovery questions such as what topics, features, or issues the client wants.",
                    "- A question is permitted only if it identifies a technical decision such as platform or migration.",
                    f"- Never use any of these phrases: {', '.join(FORBIDDEN_PHRASES)}.",
                    f"- Avoid generic filler such as: {', '.join(GENERIC_FILLER)}.",
                    "- End with one specific practical question.",
                    "- Do not ask for confirmation or say 'proceed with this approach.'",
                    style_rules(style),
                    "Return only the revised proposal text.",
                    "Never include bracket placeholders.",
                    "",
                    "Job description:",
                    job_description,
                    "",
                    "Situation guidance:",
                    guidance,
                    "",
                    "Draft to revise:",
                    proposal,
                ]
            ),
            temperature=0.35,
            max_tokens=620 if style == "detailed" else 320,
        )
        if result.status != 200:
            print(f"[ProposalAI] Provider repair failed with {result.status}; using rule-based draft.", flush=True)
            provider_repair_failed = True
        else:
            proposal = clean_proposal(str(result.payload["proposal"]))
            findings = proposal_violations(proposal, profile, job_description, relevant_win, style)
            blockers = blocking_violations(proposal, findings)

    if blockers and not provider_repair_failed:
        result = request_github_models(
            token,
            build_fallback_prompt(profile, job_description, relevant_win, guidance, style),
            temperature=0.2,
            max_tokens=620 if style == "detailed" else 220,
        )
        if result.status != 200:
            print(f"[ProposalAI] Provider fallback prompt failed with {result.status}; using rule-based draft.", flush=True)
        else:
            proposal = clean_proposal(str(result.payload["proposal"]))
            findings = proposal_violations(proposal, profile, job_description, relevant_win, style)
            blockers = blocking_violations(proposal, findings)
    if blockers:
        fallback = build_rule_based_proposal(job_description, relevant_win, style)
        fallback_findings = proposal_violations(fallback, profile, job_description, relevant_win, style)
        fallback_blockers = blocking_violations(fallback, fallback_findings)
        if fallback_blockers:
            print(f"[ProposalAI] Draft blocked: {'; '.join(fallback_blockers)}.", flush=True)
            return error(USER_RETRY_MESSAGE, 502)
        proposal = fallback
        findings = fallback_findings

    warnings = [finding for finding in findings if finding not in blockers]
    if warnings:
        print(f"[ProposalAI] Draft accepted with warnings: {'; '.join(warnings)}.", flush=True)

    return ApiResult(200, {"model": generation_model_id(), "style": style, "proposal": proposal.strip(), "wordCount": word_count(proposal)})


def save_feedback(body: dict[str, Any]) -> ApiResult:
    feedback_type = trim(body.get("feedbackType")).lower()
    if feedback_type not in FEEDBACK_TYPES:
        return error("Choose one feedback option before submitting.", 400)

    comment = trim(body.get("comment"))[:800]
    style = normalize_style(body.get("style"))
    niche = trim(body.get("niche"))[:100]
    job_category = classify_proof_category(trim(body.get("jobDescription"))) or "other"
    try:
        words = max(0, min(int(body.get("wordCount", 0) or 0), 1000))
    except (TypeError, ValueError):
        words = 0
    timestamp = datetime.now(IST)
    record = {
        "timestampIst": timestamp.isoformat(timespec="seconds"),
        "dateIst": timestamp.date().isoformat(),
        "feedbackType": feedback_type,
        "feedbackLabel": FEEDBACK_TYPES[feedback_type],
        "comment": comment,
        "style": style,
        "wordCount": words,
        "niche": niche,
        "jobCategory": job_category,
        "id": uuid.uuid4().hex,
    }

    try:
        storage = append_feedback(record)
    except Exception as exc:
        print(f"[ProposalAI] Feedback storage failed: {type(exc).__name__}.", flush=True)
        return error("Feedback could not be saved. Please try again.", 503)
    return ApiResult(201, {"ok": True, "message": "Thanks - your feedback is saved.", "storage": storage})


def append_feedback(record: dict[str, Any]) -> str:
    load_dotenv()
    if google_sheet_enabled():
        append_feedback_to_google_sheet(record)
        return "google_sheet"

    if os.getenv("ALLOW_LOCAL_FEEDBACK_LOG", "").strip().lower() not in {"1", "true", "yes"}:
        raise RuntimeError("Google Sheets feedback storage is not configured")

    path = feedback_log_path()
    with FEEDBACK_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
    print("[ProposalAI] Feedback saved to local development storage.", flush=True)
    return "local_log"


def feedback_log_path() -> Path:
    configured = os.getenv("PROPOSALAI_FEEDBACK_LOG_PATH", "").strip()
    return Path(configured) if configured else ROOT / "feedback_data" / "feedback.jsonl"


def google_sheet_enabled() -> bool:
    sheet_id = os.getenv("PROPOSALAI_FEEDBACK_SHEET_ID", "").strip()
    credentials = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if bool(sheet_id) != bool(credentials):
        raise RuntimeError("Incomplete Google Sheets configuration")
    return bool(sheet_id and credentials)


def google_sheet_range() -> str:
    return os.getenv("PROPOSALAI_FEEDBACK_SHEET_RANGE", "Feedback!A:I").strip() or "Feedback!A:I"


def google_sheet_header_range() -> str:
    return os.getenv("PROPOSALAI_FEEDBACK_HEADER_RANGE", "Feedback!A1:I1").strip() or "Feedback!A1:I1"


def google_access_token() -> str:
    try:
        from google.auth.transport.requests import Request as GoogleRequest
        from google.oauth2 import service_account
    except ImportError as exc:
        raise RuntimeError("google-auth is not installed") from exc

    try:
        service_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise RuntimeError("Invalid Google service account configuration") from exc
    credentials = service_account.Credentials.from_service_account_info(
        service_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    credentials.refresh(GoogleRequest())
    return str(credentials.token)


def google_sheet_request(method: str, cell_range: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    sheet_id = quote(os.environ["PROPOSALAI_FEEDBACK_SHEET_ID"].strip(), safe="")
    encoded_range = quote(cell_range, safe="!:")
    parameters = ""
    if method == "POST":
        parameters = "?" + urlencode({"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"})
    elif method == "PUT":
        parameters = "?" + urlencode({"valueInputOption": "RAW"})
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{encoded_range}"
    if method == "POST":
        url += ":append"
    url += parameters
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {google_access_token()}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        exc.read()
        raise RuntimeError(f"Google Sheets returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("Google Sheets request failed") from exc


def append_feedback_to_google_sheet(record: dict[str, Any]) -> None:
    row = [
        record["timestampIst"],
        record["dateIst"],
        record["feedbackLabel"],
        record["comment"],
        record["style"],
        record["wordCount"],
        record["niche"],
        record["jobCategory"],
        record["id"],
    ]
    with FEEDBACK_LOCK:
        first_row = google_sheet_request("GET", google_sheet_header_range())
        if not first_row.get("values"):
            google_sheet_request(
                "PUT",
                google_sheet_header_range(),
                {"majorDimension": "ROWS", "values": [FEEDBACK_HEADERS]},
            )
        google_sheet_request(
            "POST",
            google_sheet_range(),
            {"majorDimension": "ROWS", "values": [row]},
        )


def build_rule_based_proposal(job_description: str, relevant_win: str, style: str) -> str:
    lowered = job_description.lower()
    if "landing" in lowered and ("shopify" in lowered or "hero" in lowered or "mobile" in lowered):
        product = "eco-friendly water bottles" if "water bottle" in lowered else "the product"
        question = "Should the main call to action send shoppers to the product page, cart, or checkout?"
        if "shopify" in lowered:
            opener = (
                "A Shopify landing page can look clean and still lose buyers when the hero, benefits, "
                "and mobile call to action fight for attention."
            )
        else:
            opener = (
                "A landing page can look clean and still lose buyers when the hero, benefits, "
                "and mobile call to action fight for attention."
            )
        outcome = (
            f"You'll have a page for {product} where the offer is clear, the benefits sell the product, "
            "and the mobile action is easy to take."
        )
        proof = f"{relevant_win}." if relevant_win else ""
        if style == "detailed":
            proof_block = f"\n\n{proof}" if proof else ""
            return (
                f"{opener} If those pieces compete, visitors understand the product but hesitate before acting."
                f"{proof_block}\n\n"
                f"{outcome} The draft should stay focused on the offer in the brief instead of adding extra flows or tools.\n\n"
                f"{question}"
            )
        proof_or_outcome = f"{relevant_win}, so {outcome[0].lower()}{outcome[1:]}" if relevant_win else outcome
        return f"{opener} {proof_or_outcome} {question}"

    if "checkout" in lowered and ("launch" in lowered or "week" in lowered or "deadline" in lowered):
        deadline = re.search(r"\b(\d+)\s*weeks?\b", lowered)
        opener = (
            f"{deadline.group(1)} weeks before launch with a broken checkout is the worst possible timing."
            if deadline
            else "Close to launch with a broken checkout is the worst possible timing."
        )
        insight_2 = (
            "Every failed payment hides the real launch signal because visitors leave before you know whether "
            "the offer, pricing, or payment path caused the drop."
        )
        question = "Which platform is the checkout on?"
        if style == "detailed":
            proof = f"\n\n{relevant_win}." if relevant_win else ""
            return (
                f"{opener} {insight_2}"
                f"{proof}\n\n"
                "You'll have a checkout customers can complete without the payment path breaking at the moment buyers are ready to pay. "
                "The launch can be judged on real orders and customer intent, not panic over a cart that blocks people before payment.\n\n"
                f"{question}"
            )
        proof_or_outcome = (
            f"{relevant_win}, so I know how fragile checkout issues get when payment and cart logic collide this close to launch."
            if relevant_win
            else "You'll have a checkout customers can complete before launch traffic reaches the payment step."
        )
        quick_insight = f"{opener.rstrip('.')} — {insight_2[0].lower()}{insight_2[1:]}"
        return f"{quick_insight} {proof_or_outcome} {question}"

    if ("wordpress" in lowered or "website" in lowered or "pages" in lowered) and (
        "slow" in lowered or "speed" in lowered or "seconds" in lowered or "load" in lowered
    ):
        question = "Is the site on shared hosting or managed WordPress hosting?"
        if style == "detailed":
            return (
                "An 8-second WordPress load time means visitors are deciding whether to leave before your page has a fair chance to make its case. "
                "Slow pages usually come from a few heavy assets, plugin choices, or render-blocking files that make the whole site feel heavier than it is.\n\n"
                "You'll have a site that feels ready when people land, with the heavy page drag removed from the initial impression. "
                "That means visitors can judge the offer itself instead of waiting around for the page to catch up.\n\n"
                f"{question}"
            )
        return (
            "The risk with a slow WordPress mobile load is that visitors decide whether to leave before the page has a fair chance to make its case. "
            "You'll have a faster site that feels ready when people land, with the heavy page drag removed from the initial impression. "
            f"{question}"
        )

    if "invoice" in lowered and ("generator" in lowered or "tool" in lowered):
        question = "Do invoices need PDF downloads or email sending in the first version?"
        if style == "detailed":
            proof = f"\n\n{relevant_win}." if relevant_win else ""
            return (
                "Invoice tools become painful when they are either too bloated or too limited for how a small business bills. "
                "The real risk is building fields and totals that do not match the invoices already being sent."
                f"{proof}\n\n"
                "You'll have a lightweight tool shaped around the invoice details and totals the business actually uses. "
                "The result should feel like their billing workflow, not another generic finance app.\n\n"
                f"{question}"
            )
        proof_or_outcome = (
            f"{relevant_win}, so the first version can stay tied to a real billing problem."
            if relevant_win
            else "You'll have a lightweight tool shaped around the invoice details and totals the business actually uses."
        )
        return (
            "Invoice tools become painful when they are either too bloated or too limited for how a small business bills. "
            f"{proof_or_outcome} {question}"
        )

    if any(term in lowered for term in ("copywriter", "copywriting", "website copy", "rewrite", "rewriting", "seo-friendly", "seo friendly")):
        question = "Could you share the existing website link and page list?"
        if style == "detailed":
            proof = f"\n\n{relevant_win}." if relevant_win else ""
            return (
                "Website rewrites can go wrong when the new copy sounds polished but drifts away from the original business message. "
                "The hard part is keeping the meaning intact while making each section clearer and easier to read."
                f"{proof}\n\n"
                "You'll have clean, SEO-friendly website copy that keeps the original intent and reads naturally after manual editing. "
                "The first version can stay tight enough for a quick review without turning the rewrite into a bigger branding project.\n\n"
                f"{question}"
            )
        proof_or_outcome = (
            f"{relevant_win}, so I can keep the rewrite tied to a real content outcome instead of polishing words for their own sake."
            if relevant_win
            else "I can turn the existing pages into clean, SEO-friendly copy while keeping the meaning intact and manually editing the final text so it reads naturally."
        )
        return (
            "Website rewrites can go wrong when the new copy sounds polished but drifts away from the original business message. "
            f"{proof_or_outcome} {question}"
        )

    focus_terms = job_focus_terms(job_description)
    primary = focus_terms[0] if focus_terms else "the work"
    question = practical_question_for_job(job_description, focus_terms)
    opener = f"The hard part with {primary} work is turning a busy brief into one clear finished result."
    outcome = (
        "You'll have a draft that focuses on the client's actual outcome, keeps the scope tight, "
        "and avoids adding details that were never mentioned in the brief or making the client sort through extra assumptions."
    )
    proof = (
        f"{relevant_win.strip().rstrip('.!?')}. I would keep the message grounded in the result the client actually needs without padding it with unrelated claims."
        if relevant_win
        else ""
    )
    if style == "detailed":
        proof_block = f"\n\n{proof}" if relevant_win else ""
        return (
            f"{opener} A proposal should show the brief was understood without stuffing in every keyword the client wrote."
            f"{proof_block}\n\n"
            f"{outcome} That makes the message specific enough to feel human without inventing platforms, tools, or proof.\n\n"
            f"{question}"
        )
    proof_or_outcome = proof if relevant_win else outcome
    return f"{opener} {proof_or_outcome} {question}"


def job_focus_terms(job_description: str) -> list[str]:
    lowered = job_description.lower()
    terms = meaningful_tokens(job_description) - {
        "need",
        "needs",
        "want",
        "wants",
        "looking",
        "someone",
        "include",
        "includes",
        "should",
        "explain",
        "build",
        "trust",
        "invite",
        "people",
        "tasks",
        "work",
        "project",
        "freelancer",
        "full",
        "stack",
        "developer",
        "manage",
        "small",
        "agency",
        "monthly",
        "online",
        "current",
        "better",
        "sell",
        "about",
    }
    ordered: list[str] = []
    if "crm" in lowered:
        ordered.append("crm")
    if "sequence" in lowered or ("email" in lowered and any(term in lowered for term in ("welcome", "campaign", "newsletter", "copy", "subscribers"))):
        for priority in ("email", "emails", "sequence"):
            if priority in terms and priority not in ordered:
                ordered.append(priority)
    priority_terms = (
        "crm",
        "customer support",
        "support",
        "quickbooks",
        "bookkeeping",
        "reconciliation",
        "video",
        "youtube",
        "illustrator",
        "illustration",
        "react",
        "native",
        "firebase",
        "dashboard",
        "looker",
        "wordpress",
        "shopify",
    )
    for priority in priority_terms:
        if priority in terms and priority not in ordered:
            ordered.append(priority)
    for token in re.findall(r"[a-z][a-z0-9+.-]+", job_description.lower()):
        cleaned = token.strip(".-")
        if cleaned in terms and cleaned not in ordered:
            ordered.append(cleaned)
    return ordered[:5]


def practical_question_for_job(job_description: str, focus_terms: list[str]) -> str:
    lowered = job_description.lower()
    if "sequence" in lowered or ("email" in lowered and any(term in lowered for term in ("welcome", "campaign", "newsletter", "copy", "subscribers"))):
        return "What action should the final email ask readers to take?"
    if "video" in lowered or "youtube" in lowered:
        return "Should the edit prioritize retention, Shorts, or captions first?"
    if "customer support" in lowered or "support" in lowered:
        return "Which support replies need the strictest tone match first?"
    if "quickbooks" in lowered or "bookkeeping" in lowered or "reconciliation" in lowered:
        return "Which month should the first reconciliation and report cover?"
    if "illustration" in lowered or "illustrator" in lowered or "book" in lowered:
        return "Should the first sketch focus on the main character or one full scene?"
    if "react native" in lowered or "firebase" in lowered or "notification" in lowered:
        return "Which bug is blocking users most right now?"
    if "crm" in lowered:
        return "Which CRM task should be handled first?"
    if "dashboard" in lowered or "looker" in lowered or "report" in lowered:
        return "Which metric has to be trusted first in the report?"
    if focus_terms:
        return f"Which part of {focus_terms[0]} should be handled first?"
    return "What constraint matters most for the first draft?"


def request_github_models(token: str, prompt: str, temperature: float = 0.7, max_tokens: int = 1300) -> ApiResult:
    provider_name, api_url, model_id = generation_provider_config()
    payload = {
        "model": model_id,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write winning freelance proposals that sound like one human messaging another. "
                    "The client is scanning many pitches, so specificity and brevity matter more than formality. "
                    "Never introduce the freelancer first. Never use generic corporate filler. "
                    "Never invent a past result, number, client, or project that is not supplied. "
                    "Prefer plain facts and a practical next step over claims about importance or benefit. "
                    "Follow all user-supplied proposal rules exactly."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "ProposalAI/1.0",
    }
    if provider_name == "github":
        headers["Accept"] = "application/vnd.github+json"
        headers["X-GitHub-Api-Version"] = "2022-11-28"

    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    data: Any = {}
    for attempt in range(1, PROVIDER_MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=PROVIDER_TIMEOUT_SECONDS) as response:
                raw = response.read().decode("utf-8", errors="replace")
                data = json.loads(raw) if raw.strip() else {}
                break
        except urllib.error.HTTPError as exc:
            exc.read()
            print(f"[ProposalAI] Generation provider returned HTTP {exc.code} on attempt {attempt}.", flush=True)
            if attempt == PROVIDER_MAX_ATTEMPTS:
                return error(USER_RETRY_MESSAGE, 503)
        except urllib.error.URLError as exc:
            print(
                f"[ProposalAI] Generation network request failed on attempt {attempt}: {type(exc.reason).__name__}.",
                flush=True,
            )
            if attempt == PROVIDER_MAX_ATTEMPTS:
                return error(USER_RETRY_MESSAGE, 503)
        except TimeoutError:
            print(f"[ProposalAI] Generation request timed out on attempt {attempt}.", flush=True)
            if attempt == PROVIDER_MAX_ATTEMPTS:
                return error(USER_RETRY_MESSAGE, 503)
        except json.JSONDecodeError:
            print(f"[ProposalAI] Generation provider returned invalid JSON on attempt {attempt}.", flush=True)
            if attempt == PROVIDER_MAX_ATTEMPTS:
                return error(USER_RETRY_MESSAGE, 503)

    proposal = extract_text(data)
    if not proposal.strip():
        print("[ProposalAI] Generation provider returned no proposal text.", flush=True)
        return error(USER_RETRY_MESSAGE, 503)
    return ApiResult(200, {"proposal": proposal.strip()})


def normalize_profile(profile: Any) -> dict[str, Any] | None:
    if not isinstance(profile, dict):
        return None
    skills = profile.get("skills")
    if not isinstance(skills, list):
        skills = [profile.get("skill1"), profile.get("skill2"), profile.get("skill3")]
    normalized = {
        "fullName": trim(profile.get("fullName")),
        "niche": trim(profile.get("niche")),
        "experience": trim(profile.get("experience")),
        "skills": [trim(skill) for skill in skills if trim(skill)][:3],
        "pastWin": trim(profile.get("pastWin")),
        "tone": trim(profile.get("tone")) or "Professional",
        "rate": trim(profile.get("rate")),
    }
    if not normalized["fullName"] or not normalized["niche"] or not normalized["experience"]:
        return None
    return normalized


def build_prompt(profile: dict[str, Any], job_description: str, relevant_win: str, guidance: str, style: str) -> str:
    profile_lines = [
        f"Name: {profile['fullName']}",
        f"Niche: {profile['niche']}",
        f"Years of experience: {profile['experience']}",
        f"Preferred tone: {profile['tone']}",
    ]
    if profile["skills"]:
        profile_lines.append(f"Skills: {', '.join(profile['skills'])}")
    if relevant_win:
        profile_lines.append(f"Relevant past win: {relevant_win}")
    else:
        profile_lines.append("Past win: none. Skip proof completely. Do not invent prior work.")
    if profile["rate"]:
        profile_lines.append(f"Rate: {profile['rate']}")
    return "\n".join(
        [
            "Write a proposal draft to edit for this freelance job.",
            style_rules(style),
            "",
            "Non-negotiable rules:",
            "- Never begin with a greeting, freelancer introduction, years of experience, or profile summary.",
            "- The first sentence must say something the client did not write but will immediately recognize as true.",
            "- The opener must show you understand the situation: why this problem exists, what it is costing them, or what constraint matters.",
            "- Never restate the job description as the opening line.",
            "- The first sentence must not contain I, I'm, my, or me. Do not begin with a greeting or a description of the freelancer.",
            "- Only mention tools, platforms, or features that appear explicitly in the job description or the freelancer profile. Never invent context.",
            "- Ground every specific claim in either the job description or the freelancer profile. If a tool, platform, or feature is not explicitly present, speak generally instead of naming it.",
            "- Do not add examples like Figma, signup flow, CRM, Stripe, dashboards, apps, etc. unless present in the input.",
            "- Past win rule: If the freelancer profile includes a past win/success story, compare it to the job description. When it is relevant to the job's platform, service, skill, industry, or outcome, include it naturally as one short proof sentence. Do not force it if unrelated. Do not copy the past win as a separate case study; weave it into the proposal. If relevant, mention the concrete outcome/metric from the past win.",
            "- If no relevant past win is provided, skip the proof sentence completely.",
            "- Never write 'I have worked on similar projects' or invent a replacement proof point.",
            "- Never invent a past result, number, client, industry, timeline, or outcome that is not in the profile.",
            "- Do not mention years of experience. A short proposal has no room for background padding.",
            "- Use I only for the supplied proof point or a direct outcome statement.",
            "- Ask no question unless its answer genuinely changes the work. Maximum one question. Avoid broad questions about topics, features, or issues.",
            f"- Do not use these words or phrases: {', '.join(FORBIDDEN_PHRASES)}.",
            f"- Avoid hollow filler such as: {', '.join(GENERIC_FILLER)}.",
            "- Use short paragraphs and short sentences. Natural colleague-to-colleague language.",
            "- Prefer contractions such as I'll. Avoid phrases like 'the immediate action is', 'detailed review', or 'solution'.",
            "- In detailed mode, do not write First, Next, Then, Finally, or Lastly.",
            "- In detailed mode, never list process steps, explain your methodology, or write a technical specification.",
            "- Detailed mode means more depth about the client's situation and the outcome, not a longer process explanation.",
            "- Do not include a rate unless the client specifically requests pricing or it resolves a stated budget.",
            "- Never include bracket placeholders or generic salutations.",
            "- End with exactly one specific practical question whose answer changes the approach.",
            "- Never end with looking forward to hearing from you, please confirm if you want to proceed, I hope to work with you, or any confirmation request.",
            "- Return only the proposal text.",
            "",
            "Perfect detailed example to match for depth and structure only:",
            "Two weeks before launch with a broken checkout is the worst possible timing — every hour it stays broken is a test user who bounces and doesn't come back.",
            "",
            "Fixed Shopify checkout, reduced drop-offs by 40%.",
            "",
            "You'll have a fully tested checkout — guest, mobile, and declined card flows — before your launch date.",
            "",
            "What platform is the checkout on?",
            "",
            "Do not reuse example facts, platform, timing, flows, or metrics unless they appear in the current profile or job.",
            "",
            "Freelancer profile:",
            *profile_lines,
            "",
            "Job description:",
            job_description,
            "",
            "Situation guidance:",
            guidance,
        ]
    )


def build_fallback_prompt(
    profile: dict[str, Any],
    job_description: str,
    relevant_win: str,
    guidance: str,
    style: str,
) -> str:
    proof_rule = (
        f"Use this relevant past win naturally as one short proof sentence, keeping its concrete metric/outcome when possible: {relevant_win}"
        if relevant_win
        else "No past win is supplied. Skip proof completely. Do not mention similar projects, prior results, clients, or metrics."
    )
    format_instructions = (
        [
            "Detailed mode is 90 to 130 words.",
            "Paragraph 1: exactly 2 sentences with an insight about why the client's situation is risky or costly.",
            "Paragraph 2: 1 to 2 sentences of relevant past-win proof only if supplied; otherwise omit this paragraph.",
            "Paragraph 3: exactly 2 sentences describing the finished outcome the client will have.",
            "Closing: one specific practical question.",
            "Do not list steps, explain methodology, or write a technical specification.",
        ]
        if style == "detailed"
        else [
            "Quick mode is 50 to 80 words and at most 3 sentences.",
            "Sentence 1: one insight about the client's situation, not a restatement of the brief.",
            "Sentence 2: exact proof if supplied, otherwise the specific outcome they will get.",
            "Sentence 3: one specific practical question.",
        ]
    )
    return "\n".join(
        [
            "Write a human freelance message in the requested style.",
            style_rules(style),
            *format_instructions,
            "No greeting. No general benefits. No invented deliverables. No years of experience.",
            "Only mention tools, platforms, or features that appear explicitly in the job description or the freelancer profile. Never invent context.",
            "If a tool, platform, or feature is not explicitly present, speak generally instead of naming it.",
            f"Never use: {', '.join(FORBIDDEN_PHRASES + GENERIC_FILLER)}.",
            proof_rule,
            "Return only the message.",
            "",
            "Profile niche:",
            profile["niche"],
            "",
            "Client brief:",
            job_description,
            "",
            "Situation guidance:",
            guidance,
        ]
    )


def clean_proposal(text: str) -> str:
    cleaned = re.sub(r"\[[^\]]+\]", "", text or "")
    cleaned = re.sub(r"^\s*(?:proposal|draft)\s*:\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"^\s*(?:hi|hello|dear)\b[^\n,]{0,70},\s*", "", cleaned, flags=re.I)
    cleaned = cleaned.strip().strip('"').strip()
    cleaned = re.sub(r"\bI will\b", "I'll", cleaned)
    cleaned = re.sub(r"\bI would\b", "I'd", cleaned)
    cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return cleaned


def proposal_violations(
    proposal: str,
    profile: dict[str, Any] | None = None,
    job_description: str = "",
    relevant_win: str = "",
    style: str = "quick",
) -> list[str]:
    violations: list[str] = []
    lowered = proposal.lower()
    count = word_count(proposal)
    if style == "detailed":
        if not 90 <= count <= 130:
            violations.append(f"detailed draft has {count} words; required range is 90 to 130")
    elif not 50 <= count <= 80:
        violations.append(f"quick draft has {count} words; required range is 50 to 80")
    job_description_lower = job_description.lower()
    used = [phrase for phrase in FORBIDDEN_PHRASES if phrase in lowered and phrase not in job_description_lower]
    if used:
        violations.append(f"banned wording used: {', '.join(used)}")
    filler = [phrase for phrase in GENERIC_FILLER if phrase in lowered and phrase not in job_description_lower]
    if filler:
        violations.append(f"generic filler used: {', '.join(filler)}")
    if re.search(r"\byears?\s+of\b.*\bexperience\b", lowered):
        violations.append("years-of-experience padding used")
    if "[" in proposal or "]" in proposal:
        violations.append("bracket placeholder present")
    paragraphs = [chunk.strip() for chunk in re.split(r"\n\s*\n", proposal) if chunk.strip()]
    if style == "detailed" and relevant_win and len(paragraphs) != 4:
        violations.append("detailed draft with proof must have insight, proof, outcome, and closing paragraphs")
    if style == "detailed" and not relevant_win and len(paragraphs) != 3:
        violations.append("detailed draft without proof must have insight, outcome, and closing paragraphs")
    if style == "quick" and len(paragraphs) > 3:
        violations.append("more than 3 paragraphs")
    if proposal.count("?") > 1:
        violations.append("more than one question")
    if any(re.search(pattern, lowered) for pattern in BROAD_QUESTION_PATTERNS):
        violations.append("broad forced question used instead of a decision-specific question")
    if any(phrase in lowered for phrase in CONFIRMATION_ENDINGS):
        violations.append("confirmation-style ending used")
    if style == "detailed" and re.search(r"\b(?:first|next|then|finally|lastly)\b", lowered):
        violations.append("detailed draft lists process steps")
    if style == "detailed" and re.search(r"\b(?:i'll|i will|we will)\b[^.!?]{0,80}\b(?:check|inspect|build|test|fix|create|set up|optimize|audit)\b", lowered):
        violations.append("detailed draft explains methodology instead of client depth")
    opening = re.sub(r"^\s*(?:hi|hello|dear)\b[^\n,]{0,70},\s*", "", proposal, flags=re.I)
    if re.match(r"^\s*(?:i\b|i[' ]?m\b|i am\b|my\b|as a\b|with \d+)", opening, flags=re.I):
        violations.append("opening is about the freelancer instead of the client")
    first_sentence = re.split(r"(?<=[.!?])\s+", opening.strip(), maxsplit=1)[0]
    if generic_freelancer_first_opener(first_sentence):
        violations.append("generic freelancer-first opener used")
    if re.search(r"\b(?:i|i'm|i am|me|my)\b", first_sentence, flags=re.I):
        violations.append("first sentence mentions the freelancer")
    if job_description and not first_sentence_has_job_specific_noun(first_sentence, job_description):
        violations.append("first sentence lacks a job-specific noun")
    if opening_echoes_brief(first_sentence, job_description):
        violations.append("opening only echoes the job description instead of adding insight")
    lowered_job = job_description.lower()
    sentence_count = len([chunk for chunk in re.split(r"(?<=[.!?])\s+", proposal.strip()) if chunk.strip()])
    if style == "quick" and sentence_count > 3:
        violations.append("quick draft must contain at most 3 sentences")
    if style == "quick" and "checkout" in lowered_job and "launch" in lowered_job and sentence_count > 3:
        violations.append("checkout pitch should contain only the insight, proof, and platform question")
    if style == "detailed" and (proposal.count("?") != 1 or not proposal.rstrip().endswith("?")):
        violations.append("detailed draft must end with one specific question")
    if "invoice" in lowered_job and re.match(r"^\s*invoice (?:tools|generators?)\s+can\s+(?:often\s+)?be\b", lowered):
        violations.append("passive invoice opener used instead of a direct observation")
    if profile is not None:
        allowed_source = "\n".join([job_description, profile.get("niche", ""), " ".join(profile.get("skills", [])), relevant_win, profile.get("experience", ""), profile.get("rate", "")])
        invented_context = [
            term
            for term in CONTROLLED_CONTEXT_TERMS
            if category_marker_present(term, lowered) and not category_marker_present(term, allowed_source.lower())
        ]
        if invented_context:
            violations.append(f"invented tool/platform/feature: {', '.join(invented_context)}")
        generated_numbers = numeric_tokens(proposal)
        allowed_numbers = numeric_tokens(allowed_source)
        unsupported_numbers = sorted(generated_numbers - allowed_numbers)
        if unsupported_numbers:
            violations.append(f"unsupported numeric claim: {', '.join(unsupported_numbers)}")
        timing_claims = re.findall(r"\b(?:recent|recently|last\s+(?:day|week|month|year)|yesterday|today)\b", lowered)
        unsupported_timing = [claim for claim in timing_claims if claim not in allowed_source.lower()]
        if unsupported_timing:
            violations.append(f"unsupported timing claim: {', '.join(unsupported_timing)}")
        if profile.get("pastWin") and not relevant_win and claims_unrelated_past_win(proposal, profile["pastWin"]):
            violations.append("past win is unrelated to this job and must be omitted")
        if relevant_win and not past_win_covered(proposal, relevant_win):
            violations.append("relevant past win is missing")
        if not relevant_win and re.search(r"\b(?:similar projects?|worked on similar|past projects?|previous projects?|previously worked)\b", lowered):
            violations.append("invented similar-project proof used without a past win")
    return violations


def blocking_violations(proposal: str, findings: list[str]) -> list[str]:
    blockers: list[str] = []
    lowered = proposal.lower()
    banned_count = len(
        {
            phrase
            for phrase in (*FORBIDDEN_PHRASES, *GENERIC_FILLER)
            if phrase in lowered
        }
    )
    if banned_count >= 3:
        blockers.append(f"draft contains {banned_count} banned or filler phrases")
    for finding in findings:
        if (
            finding == "opening only echoes the job description instead of adding insight"
            or finding == "generic freelancer-first opener used"
            or finding == "first sentence lacks a job-specific noun"
            or finding == "bracket placeholder present"
            or finding.startswith("banned wording used:")
            or finding.startswith("unsupported numeric claim:")
            or finding.startswith("invented tool/platform/feature:")
            or finding.startswith("unsupported timing claim:")
            or finding.startswith("quick draft has ")
            or finding.startswith("detailed draft has ")
            or finding == "past win is unrelated to this job and must be omitted"
            or finding == "relevant past win is missing"
            or finding == "invented similar-project proof used without a past win"
            or finding == "detailed draft lists process steps"
            or finding == "detailed draft explains methodology instead of client depth"
        ):
            blockers.append(finding)
    return list(dict.fromkeys(blockers))


def select_relevant_win(past_win: str, job_description: str) -> str:
    if not past_win:
        return ""
    win_category = classify_proof_category(past_win)
    job_category = classify_proof_category(job_description)
    if win_category and job_category and win_category == job_category:
        return past_win
    # Also allow proof when the win and job share explicit platform/service/skill/outcome words.
    # This catches cases like a Shopify checkout win for a Shopify landing-page job even when
    # the specific task categories differ.
    shared_terms = meaningful_tokens(past_win).intersection(meaningful_tokens(job_description))
    return past_win if shared_terms else ""


def classify_proof_category(text: str) -> str | None:
    lowered = text.lower()
    scores: dict[str, int] = {}
    for category, markers in PROOF_CATEGORIES.items():
        score = sum(1 for marker in markers if category_marker_present(marker, lowered))
        if score:
            scores[category] = score
    if not scores:
        return None
    return max(scores, key=lambda category: scores[category])


def category_marker_present(marker: str, text: str) -> bool:
    if " " in marker or "." in marker:
        return marker in text
    return bool(re.search(rf"\b{re.escape(marker)}\b", text))


def profile_mismatch(profile: dict[str, Any], job_description: str) -> dict[str, str] | None:
    """Avoid hard-blocking broad public tests by category.

    Freelancers often test across adjacent services, and the market is much
    wider than a few fixed labels. A wrong block is worse than a slightly rough
    draft, especially while ProposalAI is collecting public feedback. Keep this
    hook for future warnings, but do not reject generation here.
    """
    return None


def claims_unrelated_past_win(proposal: str, past_win: str) -> bool:
    win_category = classify_proof_category(past_win)
    if not win_category:
        return False
    mentions_win_category = any(
        category_marker_present(marker, proposal.lower())
        for marker in PROOF_CATEGORIES[win_category]
    )
    past_claim = bool(
        re.search(
            r"\b(?:(?:i|i've|i have)\s+(?:fixed|built|created|improved|reduced|resolved|handled|delivered)"
            r"|(?:previously|recently|before)\s+(?:fixed|built|created|improved|resolved|handled))\b",
            proposal.lower(),
        )
    )
    return mentions_win_category and past_claim


def meaningful_tokens(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-z][a-z0-9-]{3,}", text.lower()))
    return tokens - RELEVANCE_STOPWORDS


def past_win_covered(proposal: str, past_win: str) -> bool:
    proposal_lower = proposal.lower()
    win_lower = past_win.lower()
    if win_lower in proposal_lower:
        return True
    win_numbers = numeric_tokens(past_win)
    if win_numbers and not win_numbers.issubset(numeric_tokens(proposal)):
        return False
    win_terms = meaningful_tokens(past_win)
    proposal_terms = meaningful_tokens(proposal)
    shared_terms = win_terms.intersection(proposal_terms)
    return bool(shared_terms) and (not win_numbers or win_numbers.issubset(numeric_tokens(proposal)))


def generic_freelancer_first_opener(first_sentence: str) -> bool:
    return bool(
        re.match(
            r"^\s*(?:hi\b[^.!?]{0,80})?(?:i\s+can\s+help|i[' ]?m\s+(?:an?\s+)?(?:experienced|skilled|professional)|i\s+have\s+\d+|with\s+\d+\s+years|as\s+an?\s+)",
            first_sentence,
            flags=re.I,
        )
    )


def first_sentence_has_job_specific_noun(first_sentence: str, job_description: str) -> bool:
    sentence_terms = meaningful_tokens(first_sentence)
    job_terms = meaningful_tokens(job_description) - {
        "need",
        "needs",
        "want",
        "wants",
        "looking",
        "someone",
        "help",
        "improve",
        "redesign",
        "section",
        "benefits",
        "layout",
        "action",
        "description",
    }
    short_job_terms = {term for term in ("api", "crm", "seo", "ui", "ux") if category_marker_present(term, job_description.lower())}
    short_sentence_terms = {
        term for term in short_job_terms if category_marker_present(term, first_sentence.lower())
    }
    return bool(sentence_terms.intersection(job_terms) or short_sentence_terms)


def detect_domains(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-z][a-z0-9-]+", text.lower()))
    return {domain for domain, keywords in DOMAIN_KEYWORDS.items() if tokens.intersection(keywords)}


def opening_echoes_brief(first_sentence: str, job_description: str) -> bool:
    lowered = first_sentence.lower()
    if any(marker in lowered for marker in INSIGHT_MARKERS):
        return False
    echo_shapes = (
        r"^(?:the|a|an)\s+.+\s+(?:is|are)\s+(?:needed|required)\b",
        r"^(?:the|a|an)\s+.+\s+needs?\s+(?:fixing|to be|a)\b",
        r"^(?:weekly\s+)?linkedin posts\s+(?:are|need|require)\b",
        r"^(?:a|an|the)\s+(?:simple\s+)?invoice generator\b",
    )
    if any(re.search(pattern, lowered) for pattern in echo_shapes):
        return True
    opening_tokens = meaningful_tokens(first_sentence)
    job_tokens = meaningful_tokens(job_description)
    return bool(opening_tokens) and len(opening_tokens.intersection(job_tokens)) >= 3 and not any(
        marker in lowered for marker in INSIGHT_MARKERS
    )


def numeric_tokens(text: str) -> set[str]:
    return set(re.findall(r"(?<!\w)(?:\$?\d+(?:[.,]\d+)?%?)(?!\w)", text.lower()))


def situation_guidance(job_description: str, style: str) -> str:
    lowered = job_description.lower()
    coupon_zero_checkout = (
        "woocommerce" in lowered
        and "coupon" in lowered
        and "checkout" in lowered
        and bool(re.search(r"(?:\$\s*0(?:\.00)?\b|zero\s+(?:total|checkout)|total\s+(?:becomes|shows|goes\s+to|is)\s+\$?\s*0)", lowered))
    )
    if coupon_zero_checkout:
        if style == "detailed":
            return (
                'Start exactly with: "A coupon sending a payable WooCommerce cart to $0 usually means an override is '
                'replacing the total instead of discounting it." Use the supplied ecommerce proof once if available. '
                "Add depth around the cost: every bad coupon path can create a free order, a failed payment, or a "
                "support problem. Describe the finished outcome as a cart total that keeps discounts, tax, shipping, "
                "and payment handoff consistent. End by asking whether a coupon plugin or custom checkout hook is involved."
            )
        return (
            "Lead with the $0 coupon symptom: a discount override is probably replacing the payable WooCommerce total. "
            "Say you'll trace the coupon calculation, fix the override, and ask whether a plugin or custom hook handles coupons."
        )
    if "checkout" in lowered and ("launch" in lowered or "week" in lowered or "deadline" in lowered):
        deadline = re.search(r"\b(\d+)\s*weeks?\b", lowered)
        opener = (
            f"{deadline.group(1)} weeks before launch with a broken checkout is the worst possible timing."
            if deadline
            else "Close to launch with a broken checkout is the worst possible timing."
        )
        if style == "detailed":
            return (
                f'Open with this human observation: "{opener}" Use the supplied checkout proof once. '
                "Add depth around the cost: checkout bugs this close to launch turn every test visit into a lost signal "
                "because nobody knows whether the product or the payment path failed. Describe the finished outcome "
                "as a checkout that can be trusted before launch, with the platform-specific failure removed. "
                "End only by asking which platform the checkout is on."
            )
        return (
            f'Open with this human observation: "{opener}" '
            "Use the supplied checkout proof once, then end only by asking which platform the checkout is on."
        )
    if "invoice" in lowered and ("generator" in lowered or "tool" in lowered):
        if style == "detailed":
            return (
                "Surface the real tradeoff: invoice tools are often overbuilt or too limited. "
                "Add depth around the cost: small businesses lose time when invoice fields, totals, and delivery options "
                "do not match how they actually bill. Describe the finished outcome as a lightweight tool that fits "
                "their invoices instead of forcing them into bloated software. End by asking whether PDF downloads or "
                "email sending are required."
            )
        return (
            "Surface the real tradeoff: invoice tools are often overbuilt or too limited. "
            "Say directly that you'll build a lightweight web version, then ask whether PDF downloads or email sending are needed. "
            "Do not use passive language."
        )
    category = classify_proof_category(job_description)
    if category == "dashboard":
        return (
            'Start exactly with: "Driver dashboards lose trust when the filtered view and exported report disagree." '
            "Add depth around the cost of mismatched operational numbers: teams stop using dashboards when exports "
            "tell a different story. Describe the finished outcome as one view that matches the exported report. "
            "End by asking where the driver data currently lives."
        )
    if category == "landing_page":
        return (
            "Open with an implementation truth: a landing page can look finished while the hero, benefits, and call "
            "to action still point in different directions. Describe the finished outcome using only the platform, "
            "product, sections, and constraints named in the brief. Do not mention Figma, signup flows, dashboards, "
            "apps, or any other tool or feature unless the brief or profile says it. End with one practical question "
            "about the call to action, product page, mobile layout, or page stack."
        )
    if category == "api":
        return (
            "Open with a subscription truth: monthly and yearly billing usually breaks at state transitions, not at the "
            "first checkout button. Describe the finished outcome as billing that stays correct when customers switch "
            "plans, renew, or hit webhook-driven state changes. End by asking whether Stripe products and webhook "
            "handling already exist."
        )
    if ("wordpress" in lowered or "website" in lowered or "pages" in lowered) and (
        "slow" in lowered or "speed" in lowered or "seconds" in lowered or "load" in lowered
    ):
        if style == "detailed":
            return (
                "Open with this truth: an 8-second page load is not just slow, it makes visitors decide before the "
                "site gets a chance to sell. Add depth around the cost: speed problems usually come from a few heavy "
                "assets, plugins, or render-blocking choices rather than one magical fix. Describe the finished "
                "outcome as a site that feels immediate enough for visitors to stay. End by asking whether the site "
                "is on shared hosting or managed WordPress hosting."
            )
        return (
            "Open with the 8-second load as the cost: visitors decide before the site gets a chance to sell. "
            "Describe the outcome as a WordPress site that feels fast enough to stay on. Ask whether hosting is shared or managed WordPress."
        )
    return (
        "Infer one practical truth the client will recognize immediately. "
        "Do not repeat their request or add invented project details."
    )


def normalize_style(value: Any) -> str:
    return "detailed" if trim(value).lower() == "detailed" else "quick"


def style_rules(style: str) -> str:
    if style == "detailed":
        return (
            "Style: DETAILED. Write 90 to 130 words. Detailed means more depth about the client's situation, "
            "not more process. Paragraph 1 must have 2 sentences: show why the problem exists, what it is costing "
            "them, or what hidden constraint matters. Paragraph 2 must have 1 to 2 sentences and must use the relevant "
            "past win naturally only if supplied; omit this paragraph entirely when no past win is supplied. Paragraph 3 must "
            "have 2 sentences describing the specific finished outcome the client will have. Closing must be one "
            "specific practical question. Never use First, Next, Then, Finally, or Lastly. Never list process steps, "
            "explain how you will do the work, write 'This resolves' or 'This addresses', or write a technical "
            "specification. The final question mark must be the final character."
        )
    return (
        "Style: QUICK. Write 50 to 80 words in no more than 3 sentences. "
        "Sentence 1 is one client-situation insight. Sentence 2 is the relevant proof if supplied, otherwise the "
        "specific finished outcome. Sentence 3 is one specific practical question."
    )


def extract_text(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0] if isinstance(choices[0], dict) else {}
        message = choice.get("message") if isinstance(choice, dict) else {}
        if isinstance(message, dict):
            content = message.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, str):
                        parts.append(item)
                    elif isinstance(item, dict):
                        value = item.get("text") or item.get("content")
                        if isinstance(value, str):
                            parts.append(value)
                return "\n".join(parts)
        text = choice.get("text") if isinstance(choice, dict) else ""
        if isinstance(text, str):
            return text
    output_text = data.get("output_text")
    return output_text if isinstance(output_text, str) else ""


def github_models_token() -> str:
    load_dotenv()
    for name in (
        "GENERATION_API_KEY",
        "GROQ_API_KEY",
        "BLUESMINDS_API_KEY",
        "GITHUB_MODELS_TOKEN",
        "GITHUB_PAT",
        "GITHUB_TOKEN",
    ):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def generation_provider_config() -> tuple[str, str, str]:
    """Return provider name, OpenAI-compatible chat completions URL, and model id.

    Explicit GENERATION_* env vars take priority for hosted-provider testing.
    Groq is supported directly because its free tier has more useful public-test
    limits than GitHub Models or OpenRouter free models. BlueMinds and GitHub
    remain fallbacks so older Render env vars keep working.
    """
    load_dotenv()
    explicit_url = os.getenv("GENERATION_API_URL", "").strip()
    explicit_model = os.getenv("GENERATION_MODEL_ID", "").strip()
    if explicit_url:
        return "custom", explicit_url, explicit_model or MODEL_ID
    if os.getenv("GROQ_API_KEY", "").strip():
        return "groq", GROQ_MODELS_URL, explicit_model or GROQ_MODEL_ID
    if os.getenv("BLUESMINDS_API_KEY", "").strip() or os.getenv("GENERATION_API_KEY", "").strip():
        return "bluesminds", BLUESMINDS_MODELS_URL, explicit_model or BLUESMINDS_MODEL_ID
    return "github", GITHUB_MODELS_URL, explicit_model or GITHUB_MODEL_ID


def generation_model_id() -> str:
    return generation_provider_config()[2]


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = value.strip().strip('"').strip("'")
        if key and (key not in os.environ or not os.environ[key].strip()):
            os.environ[key] = value


def trim(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def word_count(text: str) -> int:
    return len([word for word in re.split(r"\s+", text.strip()) if word])


def error(message: str, status: int) -> ApiResult:
    return ApiResult(status, {"error": message})


def main() -> None:
    load_dotenv()
    port = int(os.getenv("PORT", "10000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), ProposalAIHandler)
    print(f"ProposalAI listening on 0.0.0.0:{port}", flush=True)
    print("Routes: /, /health, /api/generate-proposal, /api/feedback", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
