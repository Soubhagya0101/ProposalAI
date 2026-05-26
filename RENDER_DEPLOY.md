# Deploy ProposalAI To Render

ProposalAI is now a website-only Docker service with proposal feedback collection. It does not run outreach email automation, scraping, or a revenue dashboard.

## Deploy

1. Push this repository to GitHub.
2. In Render, create a **Blueprint** from the repository using `render.yaml`, or create a **Web Service** using the included `Dockerfile`.
3. Do not create a Static Site. The app needs the Python API route.
4. Add the generation environment variable:

```text
GITHUB_MODELS_TOKEN
```

5. To retain feedback on Render, create a `Feedback` tab in a Google Sheet and share it with a Google service account. Add:

```text
PROPOSALAI_FEEDBACK_SHEET_ID
GOOGLE_SERVICE_ACCOUNT_JSON
```

Optional custom range values:

```text
PROPOSALAI_FEEDBACK_SHEET_RANGE=Feedback!A:I
PROPOSALAI_FEEDBACK_HEADER_RANGE=Feedback!A1:I1
```

Do not rely on the local feedback log in a free Render service. Free services lose filesystem changes when they spin down or restart.

6. For the daily feedback summary email, add these Render environment variables:

```text
FEEDBACK_SUMMARY_SECRET
BREVO_API_KEY
BREVO_FROM_EMAIL
PROPOSALAI_REPORT_EMAIL
```

`BREVO_REPLY_TO_EMAIL` is optional. Use a verified Brevo sender for `BREVO_FROM_EMAIL`. This uses Brevo's HTTPS API because Render free services block SMTP port `587`.

7. In the private GitHub repository, add Actions secrets:

```text
PROPOSALAI_RENDER_URL=https://YOUR-SERVICE.onrender.com
FEEDBACK_SUMMARY_SECRET=the-same-secret-used-on-render
```

The included workflow calls Render daily at `20:00 IST` and can also be run manually from GitHub Actions.

8. Deploy.

## Verify

Health endpoint:

```text
https://YOUR-SERVICE.onrender.com/health
```

Expected:

```json
{"ok": true, "service": "proposalai"}
```

GitHub Models connection test:

```text
https://YOUR-SERVICE.onrender.com/api/generate-proposal?test=1
```

Expected:

```json
{"ok": true, "model": "openai/gpt-4o-mini", "response": "ProposalAI GitHub Models connection works."}
```

The app loads at the Render service root:

```text
https://YOUR-SERVICE.onrender.com/
```

After generating a proposal, submit feedback and confirm a row appears in the `Feedback` tab.

To test the summary endpoint manually without putting its secret in a URL:

```bash
curl -X POST "https://YOUR-SERVICE.onrender.com/api/feedback-summary/send" \
  -H "Authorization: Bearer YOUR_FEEDBACK_SUMMARY_SECRET" \
  -H "Content-Type: application/json" \
  --data "{}"
```
