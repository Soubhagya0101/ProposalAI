from __future__ import annotations

from pathlib import Path
from typing import Generic, TypeVar

from .models import Event, Feedback, Lead, Message, Metric, Record
from .storage import RevenueStore


T = TypeVar("T", bound=Record)


class GoogleSheetsUnavailable(RuntimeError):
    pass


class GoogleSheetTable(Generic[T]):
    def __init__(self, worksheet, model: type[T], headers: list[str] | None = None, fieldnames: list[str] | None = None) -> None:
        self.worksheet = worksheet
        self.model = model
        self._fieldnames = fieldnames or self.model.fieldnames()
        self._headers = headers or self._fieldnames
        self._ensure_header()

    def all(self) -> list[T]:
        records = []
        for row in self.worksheet.get_all_records():
            normalized = {}
            for header, fieldname in zip(self._headers, self._fieldnames):
                normalized[fieldname] = row.get(header, "")
            records.append(self.model.from_dict(normalized))
        return records

    def append(self, record: T) -> T:
        self.worksheet.append_row([record.to_dict().get(name, "") for name in self._fieldnames])
        return record

    def upsert(self, record: T) -> T:
        rows = self.worksheet.get_all_records()
        for index, row in enumerate(rows, start=2):
            row_id = row.get("id") or row.get("Lead ID") or row.get("message_id") or row.get("Message ID")
            if row_id == record.id:
                values = [record.to_dict().get(name, "") for name in self._fieldnames]
                self.worksheet.update(f"A{index}:{self._column_letter(len(self._fieldnames))}{index}", [values])
                return record
        return self.append(record)

    def _ensure_header(self) -> None:
        expected = self._headers
        current = self.worksheet.row_values(1)
        if current != expected:
            self.worksheet.update("A1", [expected])

    @staticmethod
    def _column_letter(number: int) -> str:
        result = ""
        while number:
            number, remainder = divmod(number - 1, 26)
            result = chr(65 + remainder) + result
        return result


def build_google_store(sheet_id: str, credentials_file: Path) -> RevenueStore:
    try:
        import gspread
    except ImportError as exc:
        raise GoogleSheetsUnavailable("Install gspread and google-auth to enable Google Sheets sync.") from exc

    if not credentials_file.exists():
        raise GoogleSheetsUnavailable(f"Google credentials file not found: {credentials_file}")

    client = gspread.service_account(filename=str(credentials_file))
    spreadsheet = client.open_by_key(sheet_id)

    def worksheet(title: str):
        try:
            return spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            return spreadsheet.add_worksheet(title=title, rows=1000, cols=30)

    lead_fields = [
        "name",
        "email",
        "niche",
        "country",
        "source",
        "created_at",
        "status",
        "id",
        "company",
        "profile_url",
        "review_count",
        "need",
        "budget",
        "notes",
        "score",
        "followup_attempts",
        "last_contacted_at",
        "next_followup_at",
        "hot",
        "updated_at",
    ]
    lead_headers = [
        "Name",
        "Email",
        "Niche",
        "Country",
        "Source",
        "Date Added",
        "Status",
        "Lead ID",
        "Company",
        "Profile URL",
        "Review Count",
        "Need",
        "Budget",
        "Notes",
        "Score",
        "Attempts",
        "Last Contacted",
        "Next Follow-Up",
        "Hot",
        "Updated At",
    ]

    return RevenueStore(
        leads=GoogleSheetTable(worksheet("Leads"), Lead, headers=lead_headers, fieldnames=lead_fields),
        messages=GoogleSheetTable(worksheet("OutreachQueue"), Message),
        events=GoogleSheetTable(worksheet("Events"), Event),
        feedback=GoogleSheetTable(worksheet("Feedback"), Feedback),
        metrics=GoogleSheetTable(worksheet("Metrics"), Metric),
    )
