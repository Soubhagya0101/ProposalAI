from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Protocol

from .models import Lead


class LeadImporter(Protocol):
    """Safe extension point for approved APIs or user-provided exports."""

    def iter_leads(self) -> Iterable[Lead]:
        ...


class UpworkImportStub:
    """Placeholder for official Upwork API or manual CSV exports.

    This package intentionally does not scrape Upwork or send automated proposals.
    Implement this class only with an approved API integration or a user-exported file.
    """

    def iter_leads(self) -> Iterable[Lead]:
        return []


class CsvLeadImporter:
    """Import allowed lead exports with common ProposalAI/Upwork-like columns."""

    def __init__(self, path: str | Path, default_source: str = "csv_import") -> None:
        self.path = Path(path)
        self.default_source = default_source

    def iter_leads(self) -> Iterable[Lead]:
        with self.path.open("r", newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                yield Lead(
                    name=self._get(row, "name", "full_name", "freelancer_name"),
                    profile_url=self._get(row, "profile_url", "url", "upwork_url"),
                    niche=self._get(row, "niche", "title", "category", "skill"),
                    country=self._get(row, "country", "location"),
                    review_count=self._int(self._get(row, "review_count", "reviews", "total_feedback_count")),
                    source=self._get(row, "source") or self.default_source,
                    need=self._get(row, "need", "notes", "headline"),
                    notes=self._get(row, "notes", "summary", "description"),
                    score=self._int(self._get(row, "score", "fit_score")),
                )

    @staticmethod
    def _get(row: dict[str, str], *names: str) -> str:
        normalized = {key.strip().lower(): value.strip() for key, value in row.items() if key}
        for name in names:
            value = normalized.get(name)
            if value:
                return value
        return ""

    @staticmethod
    def _int(value: str) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0
