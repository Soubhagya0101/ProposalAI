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
MODEL_ID = "openai/gpt-4o-mini"
USER_RETRY_MESSAGE = "Taking longer than usual - please try again."
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
    token = github_models_token()
    if not token:
        print("[ProposalAI] Generation token is not configured.", flush=True)
        return error(USER_RETRY_MESSAGE, 503)

    if test_mode:
        result = request_github_models(
            token,
            "Reply with exactly this sentence: ProposalAI GitHub Models connection works.",
            temperature=0,
            max_tokens=80,
        )
        if result.status != 200:
            return result
        return ApiResult(200, {"ok": True, "model": MODEL_ID, "response": result.payload["proposal"]})

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

    relevant_win = select_relevant_win(profile["pastWin"], job_description)
    guidance = situation_guidance(job_description, style)
    prompt = build_prompt(profile, job_description, relevant_win, guidance, style)
    result = request_github_models(token, prompt, temperature=0.42, max_tokens=620 if style == "detailed" else 320)
    if result.status != 200:
        return result

    proposal = clean_proposal(str(result.payload["proposal"]))
    findings = proposal_violations(proposal, profile, job_description, relevant_win, style)
    blockers = blocking_violations(proposal, findings)
    if blockers:
        result = request_github_models(
            token,
            "\n".join(
                [
                    "Rewrite this freelance proposal to comply with every rule below.",
                    f"Fix these blocking issues: {', '.join(blockers)}.",
                    "- Open immediately with a concrete detail from the client's job, not a greeting or an introduction about the freelancer.",
                    "- The opening must add an observation the client did not write but will immediately recognize as true. Never merely restate the brief.",
                    "- State facts and actions. Do not explain that the project is important, beneficial, impactful, or engaging.",
                    "- Every sentence must state the client's concrete need, the allowed proof point, a deliverable/action, or a necessary next-step decision.",
                    "- Expand only the concrete execution and testing approach for the requested task; do not invent scope, client facts, or outcomes.",
                    "- Use short paragraphs and short sentences. Natural colleague-to-colleague language.",
                    "- Use one relevant past win in one sentence only, or omit it when it is not relevant.",
                    (
                        f"- The only allowed past-result claim is: {relevant_win}"
                        if relevant_win
                        else "- No relevant past win is supplied for this job. Do not claim any previous result, project, or metric."
                    ),
                    "- Do not invent clients, industries, metrics, timelines, or outcomes.",
                    "- Do not borrow facts from the style example; use only the job description and allowed past win.",
                    "- Do not mention years of experience. Use concrete proof or a concrete approach instead.",
                    "- Ask at most one question and only when the answer changes the work.",
                    "- Do not ask broad discovery questions such as what topics, features, or issues the client wants.",
                    "- A question is permitted only if it identifies a technical decision such as platform or migration.",
                    f"- Never use any of these phrases: {', '.join(FORBIDDEN_PHRASES)}.",
                    f"- Avoid generic filler such as: {', '.join(GENERIC_FILLER)}.",
                    "- End with a useful next step, one essential question, or confident availability.",
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
            return result
        proposal = clean_proposal(str(result.payload["proposal"]))
        findings = proposal_violations(proposal, profile, job_description, relevant_win, style)
        blockers = blocking_violations(proposal, findings)

    if blockers:
        result = request_github_models(
            token,
            build_fallback_prompt(profile, job_description, relevant_win, guidance, style),
            temperature=0.2,
            max_tokens=620 if style == "detailed" else 220,
        )
        if result.status != 200:
            return result
        proposal = clean_proposal(str(result.payload["proposal"]))
        findings = proposal_violations(proposal, profile, job_description, relevant_win, style)
        blockers = blocking_violations(proposal, findings)
    if blockers:
        print(f"[ProposalAI] Draft blocked: {'; '.join(blockers)}.", flush=True)
        return error(USER_RETRY_MESSAGE, 502)

    warnings = [finding for finding in findings if finding not in blockers]
    if warnings:
        print(f"[ProposalAI] Draft accepted with warnings: {'; '.join(warnings)}.", flush=True)

    return ApiResult(200, {"model": MODEL_ID, "style": style, "proposal": proposal.strip(), "wordCount": word_count(proposal)})


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


def request_github_models(token: str, prompt: str, temperature: float = 0.7, max_tokens: int = 1300) -> ApiResult:
    payload = {
        "model": MODEL_ID,
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
    request = urllib.request.Request(
        GITHUB_MODELS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=70) as response:
            raw = response.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        exc.read()
        print(f"[ProposalAI] Generation provider returned HTTP {exc.code}.", flush=True)
        return error(USER_RETRY_MESSAGE, 503)
    except urllib.error.URLError as exc:
        print(f"[ProposalAI] Generation network request failed: {type(exc.reason).__name__}.", flush=True)
        return error(USER_RETRY_MESSAGE, 503)
    except TimeoutError:
        print("[ProposalAI] Generation request timed out.", flush=True)
        return error(USER_RETRY_MESSAGE, 503)
    except json.JSONDecodeError:
        print("[ProposalAI] Generation provider returned invalid JSON.", flush=True)
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
        profile_lines.append(f"The only relevant past win you may mention: {relevant_win}")
    else:
        profile_lines.append("Relevant past win: none. Do not invent or mention prior outcomes.")
    if profile["rate"]:
        profile_lines.append(f"Rate: {profile['rate']}")
    return "\n".join(
        [
            "Write a ready-to-send proposal for this freelance job.",
            style_rules(style),
            "",
            "Non-negotiable rules:",
            "- The first sentence must be about the client's most specific need, deadline, tool, industry, or problem. Start there immediately.",
            "- The first sentence must add an insight the client did not state: a consequence, tradeoff, common failure, or useful constraint. Never echo the brief.",
            "- The first sentence must not contain I, I'm, my, or me. Do not begin with a greeting or a description of the freelancer.",
            "- State the problem and useful action directly. Do not say the work is important, beneficial, engaging, effective, impressive, or a success.",
            "- Every sentence must state a concrete need from the brief, an allowed proof point, a deliverable/action, or a necessary next-step decision.",
            "- Expand only the concrete execution and testing approach for the requested task; do not invent scope, client facts, or vague benefits.",
            "- Include only one past win, in one sentence, and only if it directly supports this job. Skip it when it is not relevant.",
            "- Never invent a past result, number, client, industry, timeline, or outcome.",
            "- Do not mention years of experience. A short proposal has no room for background padding.",
            "- Use I only for a concrete action or the supplied proof point. Prefer active voice: 'I fixed' rather than 'a past project involved.'",
            "- Ask no question unless its answer genuinely changes the work. Maximum one question. Avoid broad questions about topics, features, or issues.",
            f"- Do not use these words or phrases: {', '.join(FORBIDDEN_PHRASES)}.",
            f"- Avoid hollow filler such as: {', '.join(GENERIC_FILLER)}.",
            "- Use short paragraphs and short sentences. Natural colleague-to-colleague language.",
            "- Prefer contractions such as I'll. Avoid phrases like 'the immediate action is', 'detailed review', or 'solution'.",
            "- Do not include a rate unless the client specifically requests pricing or it resolves a stated budget.",
            "- Never include bracket placeholders or generic salutations.",
            "- End with a specific next step, one essential question, or confident availability.",
            "- Prefer ending with one practical question whose answer changes the approach. Never ask for confirmation or permission to proceed.",
            "- Return only the proposal text.",
            "",
            "Style example to match for directness and humanity:",
            "Two weeks before launch with a broken checkout is the worst possible timing. I fixed a similar checkout that was losing orders at payment.",
            "",
            "What platform is the checkout on?",
            "",
            "For recurring content, the cadence should sound like:",
            "Weekly LinkedIn posts, long term: the hard part is keeping the voice consistent without recycling the same angle. Send one post or page that captures the tone and I can draft the first week.",
            "",
            "For a simple software tool, the cadence should sound like:",
            "Invoice generators are usually overkill or too basic. I can build a lightweight web version around the fields you use. Do invoices need PDF downloads or email sending?",
            "These examples demonstrate tone only. Do not reuse their facts, features, timing, or metrics.",
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
        f"You may use this one proof sentence only: {relevant_win}."
        if relevant_win
        else "No past proof is relevant. Do not mention prior results, clients, or metrics."
    )
    format_instructions = (
        [
            "Paragraph 1: open with a useful truth about the client's situation, then use the allowed proof when relevant.",
            "Paragraph 2: give concrete steps for this exact job, including checks or handoff details that matter.",
            "Paragraph 3: end with one technical decision question whose answer changes the work.",
            "Do not compress this into a quick pitch; the detailed word range is mandatory.",
        ]
        if style == "detailed"
        else [
            "Sentence 1: name the most concrete task, deadline, or constraint in the client's brief.",
            "Sentence 1 must add a recognized truth or tradeoff, not repeat the brief.",
            "Sentence 2: state one concrete action you can take, or include the allowed proof.",
            "Optional final sentence: ask one technical decision question only when required; otherwise state availability.",
        ]
    )
    return "\n".join(
        [
            "Write a human freelance message in the requested style.",
            style_rules(style),
            *format_instructions,
            "No greeting. No adjectives about value. No general benefits. No invented deliverables. No years of experience.",
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
        if not 120 <= count <= 150:
            violations.append(f"detailed draft has {count} words; required range is 120 to 150")
    elif not 50 <= count <= 80:
        violations.append(f"quick draft has {count} words; required range is 50 to 80")
    used = [phrase for phrase in FORBIDDEN_PHRASES if phrase in lowered]
    if used:
        violations.append(f"banned wording used: {', '.join(used)}")
    filler = [phrase for phrase in GENERIC_FILLER if phrase in lowered]
    if filler:
        violations.append(f"generic filler used: {', '.join(filler)}")
    if re.search(r"\byears?\s+of\b.*\bexperience\b", lowered):
        violations.append("years-of-experience padding used")
    if "[" in proposal or "]" in proposal:
        violations.append("bracket placeholder present")
    paragraphs = [chunk.strip() for chunk in re.split(r"\n\s*\n", proposal) if chunk.strip()]
    if style == "detailed" and len(paragraphs) != 3:
        violations.append("detailed draft must have exactly 3 short paragraphs")
    if style == "quick" and len(paragraphs) > 3:
        violations.append("more than 3 paragraphs")
    if proposal.count("?") > 1:
        violations.append("more than one question")
    if any(re.search(pattern, lowered) for pattern in BROAD_QUESTION_PATTERNS):
        violations.append("broad forced question used instead of a decision-specific question")
    if any(phrase in lowered for phrase in CONFIRMATION_ENDINGS):
        violations.append("confirmation-style ending used")
    opening = re.sub(r"^\s*(?:hi|hello|dear)\b[^\n,]{0,70},\s*", "", proposal, flags=re.I)
    if re.match(r"^\s*(?:i\b|i[' ]?m\b|i am\b|my\b|as a\b|with \d+)", opening, flags=re.I):
        violations.append("opening is about the freelancer instead of the client")
    first_sentence = re.split(r"(?<=[.!?])\s+", opening.strip(), maxsplit=1)[0]
    if re.search(r"\b(?:i|i'm|i am|me|my)\b", first_sentence, flags=re.I):
        violations.append("first sentence mentions the freelancer")
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
        allowed_source = "\n".join([job_description, relevant_win, profile.get("experience", ""), profile.get("rate", "")])
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
            or finding == "bracket placeholder present"
            or finding.startswith("unsupported numeric claim:")
            or finding.startswith("unsupported timing claim:")
            or finding == "past win is unrelated to this job and must be omitted"
        ):
            blockers.append(finding)
    return list(dict.fromkeys(blockers))


def select_relevant_win(past_win: str, job_description: str) -> str:
    if not past_win:
        return ""
    win_category = classify_proof_category(past_win)
    job_category = classify_proof_category(job_description)
    return past_win if win_category and win_category == job_category else ""


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
    profile_text = " ".join(
        [profile.get("niche", ""), " ".join(profile.get("skills", [])), profile.get("pastWin", "")]
    )
    profile_domains = detect_domains(profile_text)
    job_domains = detect_domains(job_description)
    if not profile_domains or not job_domains or profile_domains.intersection(job_domains):
        return None
    job_domain = sorted(job_domains)[0]
    labels = {"development": "development", "writing": "writing", "design": "design", "video": "video editing"}
    return {"job_label": labels.get(job_domain, job_domain)}


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
                "Explain concrete checks: reproduce with a qualifying and non-qualifying cart, inspect the coupon rule "
                "and total-calculation hooks or plugins, compare subtotal, discount, tax and final total, fix the "
                "override, then retest valid, invalid and edge-value coupons before payment. End by asking whether a "
                "coupon plugin or custom checkout hook is involved."
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
                "In the middle paragraph, explain a specific approach: reproduce the failed checkout path, inspect "
                "browser errors and failed network requests, inspect gateway responses, check whether cart state, "
                "discounts, tax, or shipping changes trigger the break, isolate whether failure happens before or "
                "during payment, patch the fault, verify totals and gateway handoff, test successful and declined "
                "payments, then rerun guest and mobile checkout against the launch build. Avoid reassurance phrases. "
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
                "Follow with a direct offer to build around the fields and calculations they actually use; do not promise "
                "time savings, reduced frustration, or other general benefits. "
                "In the middle paragraph, explain a specific approach: capture only their invoice fields and calculation rules, "
                "define invoice numbering, line items, totals, currency and tax handling, build input and editing first, "
                "leave customer-detail storage as a decision unless they ask for it, validate calculations and empty-field behavior, "
                "test that saved and revised invoices reopen with unchanged totals, and explain that PDF or email changes "
                "the version-one data and layout decisions without promising either feature. "
                "End by asking whether PDF downloads or email sending are required. Do not promise security, easy outcomes, "
                "generic fit, or optional features before that question. A strong cadence for this brief is: invoice tools "
                "get messy when features are chosen before calculation rules; map invoice number, client details, item rows, "
                "tax, currency, total and due-date rules; build create/edit and missing-value validation; test saved and "
                "revised invoices reopen with unchanged totals; explain PDF affects layout and email affects sending setup; "
                "ask which is needed in the first version."
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
            "Explain how you would define the report fields, connect the "
            "driver data, test filters against export rows, and check totals for the same date range. End by asking "
            "where the driver data currently lives."
        )
    if category == "landing_page":
        return (
            "Open with an implementation truth: a launch-page Figma can look finished while the built hero and signup "
            "flow still lose the intended message or action. Explain how you would translate layout responsively, build "
            "the hero and signup interaction, check mobile spacing and form states, and preserve the supplied design. "
            "Avoid claims about engagement, visual appeal, or a seamless experience. End by asking what stack the page "
            "must be added to."
        )
    if category == "api":
        return (
            "Open with a subscription truth: monthly and yearly billing usually breaks at state transitions, not at the "
            "first checkout button. Explain how you would map the Stripe products and prices, create the Node endpoint, "
            "verify webhook events and subscription state, and test plan selection and renewal paths. End by asking "
            "whether Stripe products and webhook handling already exist."
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
            "Style: DETAILED. Draft toward 140 to 150 words; anything below 120 words will be rejected. "
            "Use exactly 3 paragraphs. Paragraph 1 should be about 30 to 40 words: open with client insight and "
            "include one relevant proof point only if supplied. Paragraph 2 should be about 95 to 105 words and use "
            "nine short sentences: each sentence states one concrete action or check and what it resolves for this "
            "job. Do not collapse the actions into a list and do not pad with sales language. Paragraph 3 should be "
            "about 15 to 20 words and end with exactly one practical question whose "
            "answer changes the approach. Before returning, silently count the words; if fewer than 120, add useful "
            "implementation or testing detail to paragraph 2 until the range is met. Add no status-update promises, "
            "sales reassurance, or claims that the work guarantees success just to reach the word count. The final "
            "question mark must be the final character; do not add a sentence after the question."
        )
    return (
        "Style: QUICK. Write 50 to 80 words in no more than 3 sentences. "
        "Keep only the insight, one relevant proof point when available, and one practical next step or question."
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
    for name in ("GITHUB_MODELS_TOKEN", "GITHUB_PAT", "GITHUB_TOKEN"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


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
