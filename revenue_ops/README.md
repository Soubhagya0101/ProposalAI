# ProposalAI Revenue Ops

Safe revenue automation primitives for ProposalAI.

## Run

Fastest founder command:

```powershell
.\run_revenue_ops.bat
```

This initializes storage, runs today's daily agent cycle, and opens the live dashboard at `http://127.0.0.1:8765`.

Manual commands:

```powershell
python -m revenue_ops init
python -m revenue_ops add-lead --name "Asha" --profile-url "https://www.upwork.com/freelancers/example" --niche "copywriter" --country "India" --review-count 3 --score 82
python -m revenue_ops import-csv revenue_ops\leads_template.csv
python -m revenue_ops list-leads
python -m revenue_ops draft-outreach lead_xxxxxxxxxxxx
python -m revenue_ops record-contact lead_xxxxxxxxxxxx --message-id msg_xxxxxxxxxxxx
python -m revenue_ops record-feedback lead_xxxxxxxxxxxx msg_xxxxxxxxxxxx --rating 5 --sounded-like-you "Yes" --make-better "More niche examples" --would-pay-9 "Yes"
python -m revenue_ops daily
python -m revenue_ops dashboard
```

Local fallback data is written to `revenue_ops_data/` by default. Override it with:

```powershell
$env:PROPOSALAI_REVENUE_DATA_DIR="C:\path\to\data"
```

Daily lead import from an approved export:

```powershell
$env:PROPOSALAI_LEADS_CSV="C:\path\to\allowed-upwork-export.csv"
```

The importer filters for `review_count` under 10 and skips duplicate `profile_url` values.

## Google Sheets Sync

Set both environment variables to use Google Sheets instead of local CSV storage:

```powershell
$env:PROPOSALAI_GOOGLE_SHEET_ID="your-sheet-id"
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\service-account.json"
pip install gspread google-auth
```

If configuration or dependencies are missing, the package falls back to local CSV/JSON.

## Daily Reports

The daily command writes a JSON report and an email-ready text draft in `revenue_ops_data/reports/`.
To send automatically through Brevo SMTP, set:

```powershell
$env:PROPOSALAI_REPORT_EMAIL="you@example.com"
$env:BREVO_EMAIL="your-brevo-login@example.com"
$env:BREVO_SMTP_KEY="your-brevo-smtp-key"
```

Install a Windows daily task at 9 AM:

```powershell
.\install_daily_task.ps1
```

## Full Email Automation

Copy `.env.example` to `.env`, then add:

- `BREVO_EMAIL`
- `BREVO_SMTP_KEY`
- `BREVO_API_KEY`
- `BREVO_REPLY_TO_EMAIL`
- `BREVO_WEBHOOK_SECRET`
- `HUNTER_API_KEY`
- `HUNTER_DOMAINS_CSV`
- `PROPOSALAI_PHYSICAL_ADDRESS`
- optional Twilio WhatsApp credentials

Commands:

```powershell
python -m revenue_ops find-leads
python -m revenue_ops queue-emails
python -m revenue_ops send-emails
python -m revenue_ops check-replies
python -m revenue_ops send-followups
python -m revenue_ops send-summary
python -m revenue_ops email-pipeline
```

Install the email automation schedule:

```powershell
.\install_email_automation_tasks.ps1
```

Schedule:

- 9:00 AM IST: lead finder + cold email queue + sender
- 9:05 AM IST: local Brevo webhook receiver
- 10:00 AM IST: follow-up sender
- Every 2 hours during the workday: optional IMAP fallback detector
- 8:00 PM IST: daily summary email
- Hourly retry window: sends any queued mail if Brevo failed earlier

Sending rules:

- 40 emails/day maximum
- 2-5 minute randomized delay between sends
- 9 AM-6 PM IST only
- never sends to the same email twice
- detects unsubscribe/remove/no-thanks replies and suppresses the lead
- requires `PROPOSALAI_PHYSICAL_ADDRESS` before sending commercial email

## Brevo Reply Tracking Without Gmail

Gmail is no longer required. Replies should be captured with Brevo Inbound Parse:

1. Configure a Brevo inbound parse domain or subdomain.
2. Set `BREVO_REPLY_TO_EMAIL` to an address on that inbound domain.
3. Expose the local webhook server with a tunnel, or deploy an equivalent public endpoint.
4. In Brevo, send inbound parse webhooks to:

```text
https://YOUR-PUBLIC-WEBHOOK/brevo/inbound?secret=YOUR_BREVO_WEBHOOK_SECRET
```

Transactional event webhooks for delivery/open/click/bounce should go to:

```text
https://YOUR-PUBLIC-WEBHOOK/brevo/events?secret=YOUR_BREVO_WEBHOOK_SECRET
```

Local webhook server command:

```powershell
python -m revenue_ops brevo-webhook-server
```

You can test with a saved payload:

```powershell
python -m revenue_ops process-brevo-webhook sample.json --kind inbound
```

## Safety Boundaries

- Messages are generated as drafts under 100 words.
- Follow-ups are limited to 2 attempts, 3 days apart by default.
- The CLI records manual contact; it does not send messages.
- Upwork support is an import extension point only. Use official APIs or user-provided exports, not scraping or spam automation.
