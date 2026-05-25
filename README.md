# ProposalAI

ProposalAI is a simple web app for freelancers. A user saves their profile once, pastes a job description, selects a proposal style, and gets a client-first proposal written in their tone.

This repo is now website-only:

- no email automation
- no lead scraping
- no Brevo
- no Hunter
- no Google Sheets
- no scheduler
- no Netlify functions

## Runtime

The browser never sees the GitHub token. The frontend calls the local server endpoint:

```text
POST /api/generate-proposal
```

The server calls GitHub Models:

```text
openai/gpt-4o-mini
```

Proposal style rules are applied server-side: an insightful client-first opening, one relevant win at most, profile/job-fit protection, and at most one essential question. Past wins are only supplied when their work category matches the job, so an ecommerce result is not inserted into dashboard, landing-page, or API work.

- `Quick` (default): 50-80 words, at most three sentences.
- `Detailed`: 120-150 words with a concrete approach paragraph and one closing question.

Minor wording or length findings are logged without hiding a usable draft. The server still blocks direct job-description echo openings, bracket placeholders, unsupported numeric/timing claims, unrelated past-result claims, or drafts containing three or more banned/filler phrases. Transient generation failures are shown to users as a simple retry message rather than raw provider errors.

## Local Run

Create `.env` locally:

```text
GITHUB_MODELS_TOKEN=your-github-models-token
PORT=10000
```

Start the app:

```powershell
python server.py
```

Open:

```text
http://127.0.0.1:10000/
```

Smoke test:

```text
http://127.0.0.1:10000/api/generate-proposal?test=1
```

## Render

Use this repo as a Docker Web Service. Do not deploy it as a Static Site, because Static Sites cannot run `/api/generate-proposal`.

Render needs only one environment variable:

```text
GITHUB_MODELS_TOKEN
```

Health check:

```text
/health
```
