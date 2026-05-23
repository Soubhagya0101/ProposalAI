from __future__ import annotations

import os
import base64
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class RevenueOpsConfig:
    """Runtime settings for local or Google Sheets-backed revenue ops."""

    data_dir: Path
    google_sheet_id: str | None = None
    google_credentials_file: Path | None = None
    lead_import_csv: Path | None = None
    hunter_api_key: str | None = None
    hunter_domains_csv: Path | None = None
    hunter_discover_queries: str = "web design agency,copywriting studio,video editing agency,development studio"
    hunter_monthly_search_limit: int = 25
    reddit_subreddits: str = "forhire,freelance,slavelabour"
    reddit_posts_per_subreddit: int = 25
    imap_address: str | None = None
    imap_password: str | None = None
    imap_host: str = ""
    imap_port: int = 993
    brevo_email: str | None = None
    brevo_smtp_key: str | None = None
    brevo_api_key: str | None = None
    brevo_from_email: str | None = None
    brevo_smtp_host: str = "smtp-relay.brevo.com"
    brevo_smtp_port: int = 587
    brevo_prefer_api: bool = False
    brevo_reply_to_email: str | None = None
    brevo_webhook_secret: str | None = None
    webhook_host: str = "127.0.0.1"
    webhook_port: int = 8770
    email_daily_limit: int = 40
    email_min_delay_seconds: int = 120
    email_max_delay_seconds: int = 300
    email_business_start_hour_ist: int = 9
    email_business_end_hour_ist: int = 18
    email_from_name: str = "Soubhagya Parida"
    email_signature: str = "Soubhagya"
    physical_address: str | None = None
    proposalai_url: str = "https://proposalai-revenue-ops.onrender.com"
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_whatsapp: str | None = None
    twilio_to_whatsapp: str | None = None
    sender_name: str = "ProposalAI"
    report_email: str | None = None
    automation_stop_date: str | None = None
    max_followups: int = 2
    followup_interval_days: int = 3
    hot_score_threshold: int = 75

    @classmethod
    def from_env(cls, data_dir: str | Path | None = None) -> "RevenueOpsConfig":
        load_dotenv()
        base_dir = Path(data_dir or os.getenv("PROPOSALAI_REVENUE_DATA_DIR", "revenue_ops_data"))
        base_dir.mkdir(parents=True, exist_ok=True)
        credentials = clean_env("GOOGLE_APPLICATION_CREDENTIALS") or clean_env("PROPOSALAI_GOOGLE_CREDENTIALS")
        if not credentials:
            credentials = _credentials_file_from_env(base_dir)
        brevo_email = clean_env("BREVO_EMAIL")
        brevo_reply_to = clean_env("BREVO_REPLY_TO_EMAIL") or brevo_email
        return cls(
            data_dir=base_dir,
            google_sheet_id=clean_env("PROPOSALAI_GOOGLE_SHEET_ID"),
            google_credentials_file=Path(credentials) if credentials else None,
            lead_import_csv=Path(clean_env("PROPOSALAI_LEADS_CSV")) if clean_env("PROPOSALAI_LEADS_CSV") else None,
            hunter_api_key=clean_env("HUNTER_API_KEY"),
            hunter_domains_csv=Path(clean_env("HUNTER_DOMAINS_CSV")) if clean_env("HUNTER_DOMAINS_CSV") else None,
            hunter_discover_queries=os.getenv("HUNTER_DISCOVER_QUERIES", "web design agency,copywriting studio,video editing agency,development studio"),
            hunter_monthly_search_limit=int(os.getenv("HUNTER_MONTHLY_SEARCH_LIMIT", "25")),
            reddit_subreddits=os.getenv("REDDIT_SUBREDDITS", "forhire,freelance,slavelabour"),
            reddit_posts_per_subreddit=int(os.getenv("REDDIT_POSTS_PER_SUBREDDIT", "25")),
            imap_address=clean_env("IMAP_ADDRESS") or clean_env("GMAIL_ADDRESS"),
            imap_password=clean_env("IMAP_PASSWORD") or clean_env("GMAIL_APP_PASSWORD"),
            imap_host=clean_env("IMAP_HOST") or clean_env("GMAIL_IMAP_HOST") or "",
            imap_port=int(os.getenv("IMAP_PORT") or os.getenv("GMAIL_IMAP_PORT") or "993"),
            brevo_email=brevo_email,
            brevo_smtp_key=clean_env("BREVO_SMTP_KEY"),
            brevo_api_key=clean_env("BREVO_API_KEY"),
            brevo_from_email=clean_env("BREVO_FROM_EMAIL") or clean_env("BREVO_REPLY_TO_EMAIL") or brevo_email,
            brevo_smtp_host="smtp-relay.brevo.com",
            brevo_smtp_port=587,
            brevo_prefer_api=_truthy(os.getenv("BREVO_PREFER_API", "false")),
            brevo_reply_to_email=brevo_reply_to,
            brevo_webhook_secret=clean_env("BREVO_WEBHOOK_SECRET"),
            webhook_host=os.getenv("PROPOSALAI_WEBHOOK_HOST", "127.0.0.1"),
            webhook_port=int(os.getenv("PROPOSALAI_WEBHOOK_PORT", "8770")),
            email_daily_limit=int(os.getenv("EMAIL_DAILY_LIMIT", "40")),
            email_min_delay_seconds=int(os.getenv("EMAIL_MIN_DELAY_SECONDS", "120")),
            email_max_delay_seconds=int(os.getenv("EMAIL_MAX_DELAY_SECONDS", "300")),
            email_business_start_hour_ist=int(os.getenv("EMAIL_BUSINESS_START_HOUR_IST", "9")),
            email_business_end_hour_ist=int(os.getenv("EMAIL_BUSINESS_END_HOUR_IST", "18")),
            email_from_name=os.getenv("EMAIL_FROM_NAME", "Soubhagya Parida"),
            email_signature=os.getenv("EMAIL_SIGNATURE", "Soubhagya"),
            physical_address=clean_env("PROPOSALAI_PHYSICAL_ADDRESS"),
            proposalai_url=os.getenv("PROPOSALAI_URL", "https://proposalai-revenue-ops.onrender.com"),
            twilio_account_sid=clean_env("TWILIO_ACCOUNT_SID"),
            twilio_auth_token=clean_env("TWILIO_AUTH_TOKEN"),
            twilio_from_whatsapp=clean_env("TWILIO_FROM_WHATSAPP"),
            twilio_to_whatsapp=clean_env("TWILIO_TO_WHATSAPP"),
            sender_name=os.getenv("PROPOSALAI_SENDER_NAME", "ProposalAI"),
            report_email=clean_env("PROPOSALAI_REPORT_EMAIL"),
            automation_stop_date=clean_env("PROPOSALAI_AUTOMATION_STOP_DATE"),
            max_followups=int(os.getenv("PROPOSALAI_MAX_FOLLOWUPS", "2")),
            followup_interval_days=int(os.getenv("PROPOSALAI_FOLLOWUP_INTERVAL_DAYS", "3")),
            hot_score_threshold=int(os.getenv("PROPOSALAI_HOT_SCORE_THRESHOLD", "75")),
        )

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_sheet_id and self.google_credentials_file)

    @property
    def imap_enabled(self) -> bool:
        """True when IMAP credentials are available (reply detection)."""
        return bool(self.imap_address and self.imap_password and self.imap_host)

    @property
    def brevo_enabled(self) -> bool:
        """True when Brevo SMTP credentials are available (outbound sending)."""
        return bool((self.brevo_email and self.brevo_smtp_key) or self.brevo_api_key)

    @property
    def send_enabled(self) -> bool:
        """True when any outbound SMTP provider is configured."""
        return self.brevo_enabled


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
        if key not in os.environ or not os.environ[key].strip():
            os.environ[key] = value


def clean_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    cleaned = value.strip().strip('"').strip("'")
    lowered = cleaned.lower()
    placeholder_markers = (
        "your-",
        "your_",
        "example.com",
        "choose-a-",
        "c:\\path\\",
        "/path/",
        "xxxxxxxx",
    )
    if not cleaned or any(marker in lowered for marker in placeholder_markers):
        return None
    return cleaned


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _credentials_file_from_env(base_dir: Path) -> str | None:
    raw = clean_env("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        return None
    content = raw
    if not raw.lstrip().startswith("{"):
        try:
            content = base64.b64decode(raw).decode("utf-8")
        except Exception:
            content = raw
    try:
        json.loads(content)
    except json.JSONDecodeError:
        return None
    target = base_dir / "google-service-account.json"
    target.write_text(content, encoding="utf-8")
    return str(target)
