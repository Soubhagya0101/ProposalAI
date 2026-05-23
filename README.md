# ProposalAI

ProposalAI is a single-page freelancer proposal generator that uses GitHub Models (`openai/gpt-4o-mini`) through the Render Python service.

## How it works

1. Save a freelancer profile in the browser.
2. Paste a job description.
3. Generate a 300-400 word proposal in the selected tone.

The GitHub Models token is stored as a server environment variable named `GITHUB_MODELS_TOKEN`. The browser never shows or stores the token.

Live Render URL:
https://proposalai-6qch.onrender.com

Render must be deployed as the Docker web service/Blueprint in `render.yaml`, not as a Static Site. If `/public/index.html` loads but `/health` is 404, the Python API is not running yet.

## Revenue Ops

The revenue system lives in `revenue_ops/`.

Run the founder command:

```powershell
.\run_revenue_ops.bat
```

It initializes tracking, runs the daily agent cycle, and opens the live local dashboard at `http://127.0.0.1:8765`.

The Google Sheets dashboard template is:
https://docs.google.com/spreadsheets/d/1m2syNh-oDujGYPVo-Fd3-ZFPJFy6wJmruH9moKYA-88

Latest live-data snapshot:
https://docs.google.com/spreadsheets/d/1CGfj6k3idqc8k8OZB1r-natQu2cM6X0IkKrrrs2JYsU

Full email automation is configured through `.env`:

```powershell
copy .env.example .env
.\install_email_automation_tasks.ps1
```

Local `.env` is ignored by Git. On Render, add the same values in the service Environment tab; Render does not read your laptop's `.env` file.

The automation uses Hunter, Reddit public JSON, CSV imports, Brevo SMTP/API fallback, Brevo webhooks/inbound parse for reply tracking, and the existing dashboard/store.

Google Sheets continuous sync requires a service-account JSON path in `GOOGLE_APPLICATION_CREDENTIALS`. Until that is added, the system writes live data to `revenue_ops_data/*.csv` and can export/upload snapshots.

## Reliable Cloud Worker

For real automation, run the revenue ops worker on a small Ubuntu VPS with a fixed IPv4. See `CLOUD_DEPLOY.md`.

For a no-paid Render deployment, use the Render blueprint in `render.yaml` and follow `RENDER_DEPLOY.md`.

Cloud services included:

- `scheduler`: always-on daily lead finder, sender, follow-ups, retries, and summary
- `webhook`: Brevo inbound/event receiver
- `app`: public ProposalAI generator at the Render root URL
- `dashboard`: private revenue dashboard at `/ops?secret=...`
