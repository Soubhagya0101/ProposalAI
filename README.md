# ProposalAI

ProposalAI is a clean website-only freelancer proposal generator.

It has one browser app and one Python server:

- `public/index.html` collects your freelancer profile and job description.
- `server.py` serves the website and calls GitHub Models from the backend.
- `render.yaml` deploys the app as a single Render Python Web Service.

No lead finder, no scheduler, no Brevo, no Google Sheets dependency, and no browser-side API key field.

## Required Render Environment Variable

Set this in Render manually:

```text
GITHUB_MODELS_TOKEN=your GitHub Models PAT
```

The token must have GitHub Models access. Do not commit your real `.env` file to GitHub.

Optional model override:

```text
GITHUB_MODELS_MODEL=openai/gpt-4o-mini
```

## Local Run

```bash
python server.py
```

Then open:

```text
http://localhost:8000
```

Health check:

```text
http://localhost:8000/health
```

GitHub Models smoke test:

```text
http://localhost:8000/api/generate-proposal?test=1
```

## Render Deploy

Deploy from the `render.yaml` Blueprint or create a Python Web Service using:

```bash
python server.py
```

Important: do not deploy this as a Static Site. A Static Site can show HTML, but it cannot run `/api/generate-proposal`.

Live URL:

```text
https://proposalai-6qch.onrender.com
```
