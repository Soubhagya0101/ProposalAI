# Deploy ProposalAI To Render

ProposalAI is now a website-only Docker service with Google Sheets feedback collection. It does not run email automation, scraping, scheduled jobs, or a revenue dashboard.

## Deploy

1. Push this repository to GitHub.
2. In Render, create a **Blueprint** from the repository using `render.yaml`, or create a **Web Service** using the included `Dockerfile`.
3. Do not create a Static Site. The app needs the Python API route.
4. Add only the Groq generation environment variables:

```text
GROQ_API_KEY
GROQ_MODEL_ID=llama-3.3-70b-versatile
```

Do not set GitHub Models, BlueMinds, OpenRouter, `GENERATION_API_*`, or other generation-provider variables. ProposalAI intentionally uses Groq only right now.

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

6. Deploy.

## Verify

Health endpoint:

```text
https://YOUR-SERVICE.onrender.com/health
```

Expected:

```json
{"ok": true, "service": "proposalai"}
```

Groq connection test:

```text
https://YOUR-SERVICE.onrender.com/api/generate-proposal?test=1
```

Expected:

```json
{"ok": true, "model": "llama-3.3-70b-versatile", "response": "ProposalAI Groq connection works."}
```

The response text may vary slightly by provider, but the status should be `200` and the `model` should match the configured Groq model.

The app loads at the Render service root:

```text
https://YOUR-SERVICE.onrender.com/
```

After generating a proposal, submit feedback and confirm a row appears in the `Feedback` tab.
