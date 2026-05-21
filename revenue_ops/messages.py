from __future__ import annotations

import re

from .models import Lead


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def shorten_to_under_100_words(text: str) -> str:
    words = text.split()
    if len(words) <= 99:
        return text
    return " ".join(words[:96]).rstrip(".,;:") + "..."


def generate_outreach(lead: Lead, sender_name: str = "ProposalAI") -> str:
    greeting = f"Hi {lead.name}," if lead.name else "Hi there,"
    niche = lead.niche or lead.need or "freelance work"
    country = f" from {lead.country}" if lead.country else ""
    proof = "ProposalAI helps new freelancers write sharper proposals in their own voice"
    body = (
        f"{greeting} I noticed you're building momentum as a {niche}{country}. {proof} "
        "without sounding templated. I'm opening a few free early-access spots this week. "
        f"If you'd like, I can share access and you can test it on one real job post. - {sender_name}"
    )
    return shorten_to_under_100_words(body)


def generate_followup(lead: Lead, sender_name: str = "ProposalAI") -> str:
    greeting = f"Hi {lead.name}," if lead.name else "Hi there,"
    niche = lead.niche or lead.need or "freelance work"
    body = (
        f"{greeting} quick follow-up. For a {niche}, ProposalAI can turn a pasted job post "
        "into a client-ready proposal in under 30 seconds. Happy to give you free access "
        f"if you want to try it once. No pressure either way. - {sender_name}"
    )
    return shorten_to_under_100_words(body)
