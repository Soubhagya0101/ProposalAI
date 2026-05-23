from __future__ import annotations

import json
import mimetypes
import os
import re
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"
MODEL = os.getenv("GITHUB_MODELS_MODEL", "openai/gpt-4o-mini")
GITHUB_MODELS_URL = "https://models.github.ai/inference/chat/completions"


def github_models_token() -> str:
    for name in ("GITHUB_MODELS_TOKEN", "PROPOSALAI_GITHUB_MODELS_TOKEN", "GITHUB_PAT", "GITHUB_TOKEN"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def send_github_models(messages: list[dict[str, str]], *, temperature: float = 0.72, max_tokens: int = 900) -> str:
    token = github_models_token()
    if not token:
        raise RuntimeError("GITHUB_MODELS_TOKEN is not configured in Render Environment.")

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        GITHUB_MODELS_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=75) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GitHub Models HTTP {exc.code}: {details}") from exc

    proposal = extract_model_text(data).strip()
    if not proposal:
        raise RuntimeError("GitHub Models returned an empty proposal.")
    return proposal


def extract_model_text(data: object) -> str:
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
                chunks: list[str] = []
                for item in content:
                    if isinstance(item, str):
                        chunks.append(item)
                    elif isinstance(item, dict):
                        text = item.get("text") or item.get("content")
                        if isinstance(text, str):
                            chunks.append(text)
                return "\n".join(chunks)
        text = choice.get("text") if isinstance(choice, dict) else ""
        if isinstance(text, str):
            return text

    output_text = data.get("output_text")
    return output_text if isinstance(output_text, str) else ""


def build_messages(profile: dict, job_description: str) -> list[dict[str, str]]:
    full_name = clean(profile.get("fullName")) or "the freelancer"
    niche = clean(profile.get("niche")) or "freelancer"
    experience = clean(profile.get("experience")) or "relevant"
    tone = clean(profile.get("tone")) or "Professional"
    rate = clean(profile.get("rate")) or "not specified"
    past_win = clean(profile.get("pastWin")) or "a relevant past project success"
    skills = profile.get("skills") if isinstance(profile.get("skills"), list) else []
    skills_text = ", ".join(clean(skill) for skill in skills if clean(skill)) or "relevant freelance skills"

    system = (
        "You are ProposalAI, a practical freelance proposal writer. "
        "Write ready-to-send proposals that sound human, specific, and useful. "
        "Do not use bracket placeholders. Do not invent fake metrics or fake client names."
    )
    user = f"""
Freelancer profile:
- Name: {full_name}
- Niche: {niche}
- Experience: {experience} years
- Skills: {skills_text}
- Past win: {past_win}
- Rate: {rate}
- Tone: {tone}

Client job description:
{job_description}

Write a 300-400 word proposal.
Structure:
1. Warm greeting. If a real client/company name is visible in the job description, use it. Otherwise use "Hi there,".
2. Short opening showing understanding of the project.
3. 3-5 bullets explaining how the freelancer will help.
4. Mention relevant skills and the past win naturally.
5. Close with a clear next step.

Keep it direct, confident, and ready to paste into Upwork, Fiverr, LinkedIn, or email.
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def clean(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


class ProposalAIHandler(SimpleHTTPRequestHandler):
    server_version = "ProposalAI/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            self.send_json({"ok": True, "service": "proposalai", "model": MODEL})
            return

        if path == "/api/generate-proposal":
            if (parse_qs(parsed.query).get("test") or [""])[0] == "1":
                self.send_json({"ok": True, "model": MODEL, "tokenConfigured": bool(github_models_token())})
                return
            self.send_json({"error": "Use POST for /api/generate-proposal."}, status=405)
            return

        if path in {"/", "/index.html", "/public/index.html"}:
            self.send_file(PUBLIC_DIR / "index.html", "text/html; charset=utf-8")
            return

        requested = (PUBLIC_DIR / unquote(path.lstrip("/"))).resolve()
        if PUBLIC_DIR in requested.parents and requested.is_file():
            content_type = mimetypes.guess_type(str(requested))[0] or "application/octet-stream"
            self.send_file(requested, content_type)
            return

        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/generate-proposal":
            self.send_error(404, "Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0

        try:
            body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(body or "{}")
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON payload."}, status=400)
            return

        profile = payload.get("profile") if isinstance(payload.get("profile"), dict) else {}
        job_description = clean(payload.get("jobDescription"))
        if len(job_description) < 50:
            self.send_json({"error": "Job description must be at least 50 characters."}, status=400)
            return

        try:
            proposal = send_github_models(build_messages(profile, job_description))
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=502)
            return

        self.send_json({"proposal": proposal})

    def send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, content_type: str) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404, "File not found")
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    with ThreadingHTTPServer(("0.0.0.0", port), ProposalAIHandler) as server:
        print(f"ProposalAI running on port {port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
