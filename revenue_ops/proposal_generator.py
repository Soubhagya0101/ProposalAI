from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


GITHUB_MODELS_URL = "https://models.github.ai/inference/chat/completions"
MODEL_ID = "openai/gpt-4o-mini"


@dataclass(slots=True)
class ProposalResult:
    status: int
    payload: dict[str, Any]


def generate_proposal_response(body: dict[str, Any], test_mode: bool = False) -> ProposalResult:
    token = _github_models_token()
    if not token:
        return _error("GitHub Models token is not configured on the server.", 500)

    if test_mode:
        result = _request_github_models(
            token,
            "Reply with exactly this sentence: ProposalAI GitHub Models connection works.",
            temperature=0,
            max_tokens=80,
        )
        if result.status != 200:
            return result
        return ProposalResult(200, {"ok": True, "model": MODEL_ID, "response": result.payload["proposal"]})

    profile = _normalize_profile(body.get("profile"))
    job_description = _safe_trim(body.get("jobDescription"))

    if not profile:
        return _error("Complete the freelancer profile first.", 400)
    if not job_description:
        return _error("Paste a job description first.", 400)

    greeting = extract_client_greeting(job_description)
    prompt = _build_prompt(profile, job_description, greeting)
    result = _request_github_models(token, prompt)
    if result.status != 200:
        return result

    proposal = remove_bracket_placeholders(str(result.payload["proposal"]), greeting)
    count = _word_count(proposal)

    for _ in range(3):
        if 300 <= count <= 400:
            break
        length_instruction = (
            f"The current proposal is {count} words, which is too short. Expand it to 340 to 370 words by adding concrete "
            "understanding of the client's project, your working approach, expected collaboration steps, and a stronger call to action."
            if count < 300
            else f"The current proposal is {count} words, which is too long. Tighten it to 340 to 370 words while preserving specificity, credibility, and the call to action."
        )
        result = _request_github_models(
            token,
            "\n".join(
                [
                    length_instruction,
                    "The final answer must be 300 to 400 words. Do not use bullets.",
                    "Keep it ready to send, natural, specific, and client-focused.",
                    "Keep the same tone and call to action.",
                    f"Start exactly with: {greeting},",
                    "Never include bracket placeholders.",
                    "Return only the revised proposal text.",
                    "",
                    proposal,
                ]
            ),
            temperature=0.35,
        )
        if result.status != 200:
            return result
        proposal = remove_bracket_placeholders(str(result.payload["proposal"]), greeting)
        count = _word_count(proposal)

    return ProposalResult(200, {"model": MODEL_ID, "proposal": proposal.strip()})


def extract_client_greeting(job_description: str) -> str:
    patterns = [
        re.compile(r"\b(?:client|company|brand|business|organization)\s*(?:name\s*[:=-]?|is\s*|[:=-])\s*([A-Z][A-Za-z0-9&'. -]{1,60})", re.I),
        re.compile(r"\b(?:we are|we're)\s+([A-Z][A-Za-z0-9&'. -]{1,60})", re.I),
        re.compile(r"\bfor\s+([A-Z][A-Za-z0-9&'. -]{1,60})\b"),
    ]

    for pattern in patterns:
        match = pattern.search(job_description)
        if not match:
            continue
        candidate = re.split(r"[.\n,;|]", match.group(1))[0]
        candidate = re.split(r"\b(?:and|is|that|who|which|needs?|looking|hiring|seeking|searching|building)\b", candidate, flags=re.I)[0]
        candidate = re.sub(r"[.,;:!?]+$", "", candidate.strip())
        if candidate and len(candidate) <= 60 and not re.search(r"\b(?:looking|hiring|seeking|need|searching|building)\b", candidate, re.I):
            return f"Hi {candidate}"

    return "Hi there"


def remove_bracket_placeholders(text: str, greeting: str) -> str:
    cleaned = re.sub(r"\[[^\]]+\]", "", text)
    cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()

    expected_start = f"{greeting},"
    if cleaned.lower().startswith(expected_start.lower()):
        return cleaned

    comma_index = cleaned.find(",")
    first_comma_is_greeting = comma_index > -1 and comma_index < 80 and re.match(r"^(hi|hello|dear)\b", cleaned, re.I)
    if first_comma_is_greeting:
        cleaned = cleaned[comma_index + 1 :].strip()

    return f"{expected_start}\n\n{cleaned}".strip()


def _request_github_models(token: str, prompt: str, temperature: float = 0.7, max_tokens: int = 1300) -> ProposalResult:
    payload = {
        "model": MODEL_ID,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "system",
                "content": "You are an expert freelance proposal writer. You write credible, client-focused proposals that feel personal and specific. Follow requested word counts carefully.",
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
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            data = {}
        detail = data.get("message") if isinstance(data, dict) else None
        detail = detail or raw.strip() or exc.reason or "No response body returned."
        return _error(f"GitHub Models request failed ({exc.code}): {detail}", exc.code)
    except urllib.error.URLError as exc:
        return _error(f"GitHub Models network error: {exc.reason}", 502)
    except TimeoutError:
        return _error("GitHub Models request timed out.", 504)
    except json.JSONDecodeError:
        return _error("GitHub Models returned invalid JSON.", 502)

    proposal = _extract_proposal_text(data)
    if not isinstance(proposal, str) or not proposal.strip():
        return _error(_empty_response_message(data), 502)
    return ProposalResult(200, {"proposal": proposal.strip()})


def _extract_proposal_text(data: Any) -> str:
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
                chunks = []
                for item in content:
                    if isinstance(item, dict):
                        text = item.get("text") or item.get("content")
                        if isinstance(text, str):
                            chunks.append(text)
                    elif isinstance(item, str):
                        chunks.append(item)
                return "\n".join(chunks)
        text = choice.get("text") if isinstance(choice, dict) else ""
        if isinstance(text, str):
            return text

    output_text = data.get("output_text")
    if isinstance(output_text, str):
        return output_text
    return ""


def _empty_response_message(data: Any) -> str:
    if not isinstance(data, dict):
        return "GitHub Models returned an empty or unrecognized response."
    choices = data.get("choices")
    finish_reason = ""
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        finish_reason = str(choices[0].get("finish_reason") or "")
    response_id = str(data.get("id") or "")
    details = []
    if finish_reason:
        details.append(f"finish_reason={finish_reason}")
    if response_id:
        details.append(f"response_id={response_id}")
    suffix = f" ({', '.join(details)})" if details else ""
    return f"GitHub Models returned an empty proposal{suffix}."


def _normalize_profile(profile: Any) -> dict[str, Any] | None:
    if not isinstance(profile, dict):
        return None
    normalized = {
        "fullName": _safe_trim(profile.get("fullName")),
        "niche": _safe_trim(profile.get("niche")),
        "experience": _safe_trim(profile.get("experience")),
        "tone": _safe_trim(profile.get("tone")) or "Professional",
        "skills": [_safe_trim(skill) for skill in profile.get("skills", []) if _safe_trim(skill)][:3]
        if isinstance(profile.get("skills"), list)
        else [],
        "pastWin": _safe_trim(profile.get("pastWin")),
        "rate": _safe_trim(profile.get("rate")),
    }
    if (
        not normalized["fullName"]
        or not normalized["niche"]
        or not normalized["experience"]
        or len(normalized["skills"]) != 3
        or not normalized["pastWin"]
        or not normalized["rate"]
    ):
        return None
    return normalized


def _build_prompt(profile: dict[str, Any], job_description: str, greeting: str) -> str:
    return "\n".join(
        [
            "Write a ready-to-send freelance proposal for the job description below.",
            "",
            "Requirements:",
            f"- Start exactly with: {greeting},",
            "- Never use bracket placeholders such as [Client's Name], [Your Name], or [Company].",
            "- If the client name is unclear, use exactly: Hi there,",
            "- 300 to 400 words. This is mandatory; target 330 to 370 words.",
            "- Use 5 to 7 short paragraphs, not bullets.",
            f"- Tone: {profile['tone']}.",
            "- Sound natural, specific, and human.",
            "- Reference the freelancer's skills and past win naturally, without forcing them.",
            "- Include the rate only if it feels appropriate and non-pushy.",
            "- End with a clear call to action.",
            "- Return only the proposal text. Do not include notes, markdown labels, or analysis.",
            "",
            "Freelancer profile:",
            f"Name: {profile['fullName']}",
            f"Niche: {profile['niche']}",
            f"Experience: {profile['experience']} years",
            f"Top skills: {', '.join(profile['skills'])}",
            f"Past win: {profile['pastWin']}",
            f"Rate: {profile['rate']}",
            "",
            "Job description:",
            job_description,
        ]
    )


def _safe_trim(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _word_count(text: str) -> int:
    return len([word for word in re.split(r"\s+", text.strip()) if word])


def _github_models_token() -> str:
    try:
        from .config import load_dotenv

        load_dotenv()
    except Exception:
        pass
    for name in ("GITHUB_MODELS_TOKEN", "PROPOSALAI_GITHUB_MODELS_TOKEN", "GITHUB_TOKEN", "GITHUB_PAT"):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _error(message: str, status: int) -> ProposalResult:
    return ProposalResult(status, {"error": message})
