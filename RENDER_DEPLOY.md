# Deploy ProposalAI To Render

ProposalAI is now a website-only Docker service. It does not run email automation, scraping, scheduled jobs, or a revenue dashboard.

## Deploy

1. Push this repository to GitHub.
2. In Render, create a **Blueprint** from the repository using `render.yaml`, or create a **Web Service** using the included `Dockerfile`.
3. Do not create a Static Site. The app needs the Python API route.
4. Add the only required environment variable:

```text
GITHUB_MODELS_TOKEN
```

5. Deploy.

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
