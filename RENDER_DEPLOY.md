# Deploy ProposalAI Revenue Ops To Render Free

This deployment uses one free Render Docker web service. It runs:

- a small HTTP server for `/health`
- the private dashboard at `/?secret=...`
- Brevo webhook endpoints
- the revenue scheduler loop in the background

Render's free web services can spin down after inactivity, and Render background workers are not the right free-tier shape for this app. To keep the scheduler awake without paying, add a free uptime monitor that pings `/health`.

## What You Need

- GitHub repo containing this project
- Render account
- Brevo keys
- Hunter API key
- Sender physical mailing address
- Report email
- Strongly recommended: Google Sheets service-account JSON for persistent state

## Step 1: Push This Project To GitHub

Make sure these files are in the repo:

```text
Dockerfile
render.yaml
revenue_ops/
requirements.txt
```

Do not commit `.env` or `revenue_ops_data/`.

## Step 2: Create A Render Blueprint

1. Go to Render.
2. Click **New +**.
3. Choose **Blueprint**.
4. Connect the GitHub repo.
5. Render should detect `render.yaml`.
6. Select the `proposalai-revenue-ops` service.
7. Keep the plan as **Free**.

The service command is:

```bash
python -m revenue_ops render-service
```

## Step 3: Add Environment Variables

Render will ask for values marked `sync: false`.

Required:

```text
HUNTER_API_KEY
BREVO_EMAIL
BREVO_FROM_EMAIL
BREVO_SMTP_KEY
BREVO_API_KEY
BREVO_REPLY_TO_EMAIL
PROPOSALAI_PHYSICAL_ADDRESS
PROPOSALAI_REPORT_EMAIL
```

Recommended for persistence:

```text
PROPOSALAI_GOOGLE_SHEET_ID
GOOGLE_SERVICE_ACCOUNT_JSON
```

`GOOGLE_SERVICE_ACCOUNT_JSON` should be the full service-account JSON pasted as one Render environment variable. The app writes it to a temporary file inside the container at startup.

Render auto-generates:

```text
BREVO_WEBHOOK_SECRET
PROPOSALAI_DASHBOARD_SECRET
```

Keep `BREVO_PREFER_API=true`; Render Free should use Brevo's HTTPS API, not SMTP port `587`.

## Step 4: Deploy

Click **Apply** / **Deploy**.

After deploy, open:

```text
https://YOUR-RENDER-SERVICE.onrender.com/health
```

Expected:

```json
{"ok": true, "service": "proposalai-revenue-ops"}
```

## Step 5: Open The Dashboard

In Render, copy `PROPOSALAI_DASHBOARD_SECRET` from environment variables.

Open:

```text
https://YOUR-RENDER-SERVICE.onrender.com/?secret=YOUR_PROPOSALAI_DASHBOARD_SECRET
```

## Step 6: Keep It Awake For Free

Create a free uptime monitor with UptimeRobot, cron-job.org, or a similar free tool.

Ping this every 5 minutes:

```text
https://YOUR-RENDER-SERVICE.onrender.com/health
```

Without this, Render Free can sleep and the background scheduler will not run while asleep.

## Step 7: Configure Brevo Webhooks

In Brevo, configure transactional event webhooks:

```text
https://YOUR-RENDER-SERVICE.onrender.com/brevo/events?secret=YOUR_BREVO_WEBHOOK_SECRET
```

If you set up Brevo inbound parse for replies:

```text
https://YOUR-RENDER-SERVICE.onrender.com/brevo/inbound?secret=YOUR_BREVO_WEBHOOK_SECRET
```

## Step 8: Important Free-Tier Caveats

- Free Render web services can sleep without incoming traffic.
- Free Render has no persistent disk for this service.
- Use Google Sheets credentials if you want durable lead/message tracking.
- If you do not configure Google Sheets, local CSV state can reset after redeploys/restarts.
- Keep daily volume conservative until replies prove demand.

## Schedule

All times are IST:

- After 9:00 AM: lead finder + email queue + send
- After 10:00 AM: follow-up queue + send
- Business hours: reply checks and hourly email retry
- After 8:00 PM: daily summary
- After 8:30 PM: backup summary if needed
