from __future__ import annotations

import csv
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .config import RevenueOpsConfig
from .models import Event, Lead
from .storage import RevenueStore


NICHE_KEYWORDS = {
    "web design": ["web design", "web designer", "webflow", "wordpress", "framer"],
    "copywriting": ["copywriter", "copywriting", "content writer", "sales page", "email copy"],
    "video editing": ["video editor", "video editing", "shorts", "reels", "youtube editor"],
    "development": ["developer", "development", "frontend", "backend", "full stack", "react", "python"],
}
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s)>\]]+|(?:www\.)[^\s)>\]]+", re.IGNORECASE)
OFFER_PATTERNS = ("[for hire]", "for hire", "hire me", "available for", "freelance", "portfolio")


@dataclass(slots=True)
class LeadFinderResult:
    source: str
    found: int = 0
    added: int = 0
    skipped: int = 0
    errors: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "found": self.found,
            "added": self.added,
            "skipped": self.skipped,
            "errors": self.errors or [],
        }


class LeadFinder:
    def __init__(self, config: RevenueOpsConfig, store: RevenueStore) -> None:
        self.config = config
        self.store = store

    def run_all(self) -> dict:
        results = [
            self._run_source("csv", self.import_csv_if_configured),
            self._run_source("hunter", self.find_hunter_leads),
            self._run_source("reddit", self.find_reddit_leads),
        ]
        return {"results": [result.to_dict() for result in results]}

    def _run_source(self, source: str, runner) -> LeadFinderResult:
        try:
            return runner()
        except Exception as exc:  # noqa: BLE001
            detail = f"{source} failed: {exc}"
            self.store.events.append(Event(lead_id="", kind=f"{source}_error", detail=detail))
            return LeadFinderResult(source=source, errors=[detail])

    def import_csv_if_configured(self) -> LeadFinderResult:
        if not self.config.lead_import_csv or not self.config.lead_import_csv.exists():
            return LeadFinderResult(source="csv", errors=["PROPOSALAI_LEADS_CSV not configured"])
        return self._save_leads("csv", self._iter_csv_leads(self.config.lead_import_csv))

    def find_hunter_leads(self) -> LeadFinderResult:
        if not self.config.hunter_api_key:
            return LeadFinderResult(source="hunter", errors=["HUNTER_API_KEY not configured"])

        searches_left = self._hunter_searches_left_this_month()
        if searches_left <= 0:
            return LeadFinderResult(source="hunter", errors=["monthly Hunter search limit reached"])

        if self.config.hunter_domains_csv and self.config.hunter_domains_csv.exists():
            domains = self._read_domains(self.config.hunter_domains_csv)
        else:
            domains = self._hunter_discover_domains(searches_left)
            if not domains:
                return LeadFinderResult(source="hunter", errors=["Hunter Discover returned no domains"])
        leads: list[Lead] = []
        errors: list[str] = []
        for domain in domains[:searches_left]:
            try:
                leads.extend(self._hunter_domain_search(domain))
                self.store.events.append(Event(lead_id="", kind="hunter_search", detail=domain))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{domain}: {exc}")
                self.store.events.append(Event(lead_id="", kind="hunter_error", detail=f"{domain}: {exc}"))
        result = self._save_leads("hunter", leads)
        result.errors = errors
        return result

    def find_reddit_leads(self) -> LeadFinderResult:
        subreddits = []
        for item in self.config.reddit_subreddits.split(","):
            cleaned = item.strip()
            if cleaned.lower().startswith("r/"):
                cleaned = cleaned[2:]
            if cleaned:
                subreddits.append(cleaned)
        leads: list[Lead] = []
        errors: list[str] = []
        for subreddit in subreddits:
            try:
                leads.extend(self._reddit_subreddit_posts(subreddit))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"r/{subreddit}: {exc}")
                self.store.events.append(Event(lead_id="", kind="reddit_error", detail=f"r/{subreddit}: {exc}"))
        result = self._save_leads("reddit", leads)
        result.errors = errors
        return result

    def _save_leads(self, source: str, leads: Iterable[Lead]) -> LeadFinderResult:
        existing_emails = {lead.email.lower() for lead in self.store.leads.all() if lead.email}
        existing_urls = {lead.profile_url.lower() for lead in self.store.leads.all() if lead.profile_url}
        found = added = skipped = 0
        for lead in leads:
            found += 1
            email_key = lead.email.lower()
            url_key = lead.profile_url.lower()
            if (email_key and email_key in existing_emails) or (url_key and url_key in existing_urls):
                skipped += 1
                continue
            lead.source = lead.source or source
            lead.status = "new" if lead.email else "needs_email"
            lead.updated_at = lead.updated_at
            saved = self.store.leads.upsert(lead)
            self.store.events.append(Event(lead_id=saved.id, kind="lead_found", detail=source))
            if saved.email:
                existing_emails.add(saved.email.lower())
            if saved.profile_url:
                existing_urls.add(saved.profile_url.lower())
            added += 1
        return LeadFinderResult(source=source, found=found, added=added, skipped=skipped)

    def _iter_csv_leads(self, path: Path) -> Iterable[Lead]:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                yield Lead(
                    name=self._get(row, "Name", "name", "full_name"),
                    email=self._get(row, "Email", "email"),
                    niche=self._guess_niche(" ".join(row.values())),
                    country=self._get(row, "Country", "country", "location"),
                    profile_url=self._get(row, "profile_url", "Profile URL", "url"),
                    source=self._get(row, "Source", "source") or "csv",
                    notes=self._get(row, "notes", "Notes"),
                )

    def _hunter_domain_search(self, domain: str) -> list[Lead]:
        query = urllib.parse.urlencode({"domain": domain, "api_key": self.config.hunter_api_key})
        payload = self._get_json(f"https://api.hunter.io/v2/domain-search?{query}")
        data = payload.get("data") or {}
        company = data.get("organization") or data.get("domain") or domain
        country = data.get("country") or ""
        leads: list[Lead] = []
        for email_data in data.get("emails", []):
            email = (email_data.get("value") or "").strip()
            if not email:
                continue
            first = email_data.get("first_name") or ""
            last = email_data.get("last_name") or ""
            lead_text = " ".join(str(value) for value in email_data.values() if value)
            niche = self._guess_niche(f"{company} {lead_text}")
            if niche:
                leads.append(
                    Lead(
                        name=f"{first} {last}".strip() or email.split("@")[0],
                        company=company,
                        email=email,
                        profile_url=f"https://{domain}",
                        niche=niche,
                        country=country,
                        source="hunter",
                        notes=f"Hunter domain search for {domain}",
                    )
                )
        return leads

    def _hunter_discover_domains(self, limit: int) -> list[str]:
        domains: list[str] = []
        queries = [query.strip() for query in self.config.hunter_discover_queries.split(",") if query.strip()]
        for query_text in queries:
            if len(domains) >= limit:
                break
            query = urllib.parse.urlencode({"api_key": self.config.hunter_api_key})
            payload = self._post_json(
                f"https://api.hunter.io/v2/discover?{query}",
                {"query": query_text},
            )
            data = payload.get("data") or []
            companies = data.get("companies") if isinstance(data, dict) else data
            companies = companies or []
            if isinstance(companies, dict):
                companies = companies.get("items") or companies.get("results") or []
            for company in companies:
                domain = self._clean_domain(str(company.get("domain") or company.get("website") or ""))
                if domain and domain not in domains:
                    domains.append(domain)
                if len(domains) >= limit:
                    break
        return domains[:limit]

    def _reddit_subreddit_posts(self, subreddit: str) -> list[Lead]:
        limit = max(1, min(self.config.reddit_posts_per_subreddit, 100))
        url = f"https://www.reddit.com/r/{urllib.parse.quote(subreddit)}/new.json?limit={limit}"
        payload = self._get_json(url)
        leads: list[Lead] = []
        for child in ((payload.get("data") or {}).get("children") or []):
            post = child.get("data") or {}
            title = post.get("title") or ""
            body = post.get("selftext") or ""
            text = f"{title}\n{body}"
            if not self._looks_like_freelancer_offer(text):
                continue
            email = self._first_match(EMAIL_RE, text)
            website = self._first_match(URL_RE, text)
            niche = self._guess_niche(text)
            if not niche:
                continue
            username = post.get("author") or ""
            permalink = post.get("permalink") or ""
            leads.append(
                Lead(
                    name=username,
                    email=email,
                    profile_url=f"https://www.reddit.com{permalink}" if permalink else website,
                    niche=niche,
                    source="reddit",
                    notes=f"Public Reddit post in r/{subreddit}; website={website}",
                )
            )
        return leads

    def _hunter_searches_left_this_month(self) -> int:
        now = datetime.now(timezone.utc)
        prefix = now.strftime("%Y-%m")
        used = sum(1 for event in self.store.events.all() if event.kind == "hunter_search" and event.occurred_at.startswith(prefix))
        return max(0, self.config.hunter_monthly_search_limit - used)

    @staticmethod
    def _read_domains(path: Path) -> list[str]:
        domains: list[str] = []
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
            if rows and rows[0]:
                for row in rows:
                    value = row.get("domain") or row.get("website") or row.get("url") or next(iter(row.values()), "")
                    domain = LeadFinder._clean_domain(value)
                    if domain:
                        domains.append(domain)
            else:
                handle.seek(0)
                for line in handle:
                    domain = LeadFinder._clean_domain(line)
                    if domain:
                        domains.append(domain)
        return domains

    @staticmethod
    def _clean_domain(value: str) -> str:
        value = (value or "").strip()
        value = re.sub(r"^https?://", "", value, flags=re.I)
        value = value.split("/", 1)[0].strip()
        return value.lower()

    @staticmethod
    def _get(row: dict[str, str], *names: str) -> str:
        normalized = {key.strip().lower(): value.strip() for key, value in row.items() if key}
        for name in names:
            value = normalized.get(name.lower())
            if value:
                return value
        return ""

    @staticmethod
    def _get_json(url: str) -> dict:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "ProposalAIRevenueOps/1.0 (+https://proposalai-generator.netlify.app)"},
        )
        return LeadFinder._open_json(request)

    @staticmethod
    def _post_json(url: str, payload: dict) -> dict:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ProposalAIRevenueOps/1.0 (+https://proposalai-generator.netlify.app)",
            },
            method="POST",
        )
        return LeadFinder._open_json(request)

    @staticmethod
    def _open_json(request: urllib.request.Request) -> dict:
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {body[:240]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"network error: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError("network timeout") from exc

    @staticmethod
    def _looks_like_freelancer_offer(text: str) -> bool:
        lowered = text.lower()
        return any(pattern in lowered for pattern in OFFER_PATTERNS)

    @staticmethod
    def _guess_niche(text: str) -> str:
        lowered = text.lower()
        for niche, keywords in NICHE_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                return niche
        return ""

    @staticmethod
    def _first_match(pattern: re.Pattern[str], text: str) -> str:
        match = pattern.search(text)
        return match.group(0).strip(".,;:") if match else ""
