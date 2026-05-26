# ProposalAI

ProposalAI is a simple web app for freelancers. A user saves their profile once, pastes a job description, selects a proposal style, and gets a client-first proposal written in their tone.

This repo is now website-only:

- no lead scraping
- no Hunter
- no Netlify functions

It has one narrow feedback workflow: users can rate a generated proposal, responses can be stored in Google Sheets, and a daily feedback summary can be emailed through the Brevo HTTPS API. It does not send outreach emails.

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

## Feedback

After a proposal is generated, the user can select `This sounds human`, `Still sounds robotic`, or `Good but needs something` and optionally say what should improve.

The app stores only the selection, optional note, proposal style, word count, freelance niche, and detected job category. It does not store the job description or the generated proposal.

For local development with no feedback environment variables, responses are appended to the ignored file `feedback_data/feedback.jsonl`. For Render deployment, configure Google Sheets storage: Render free web services lose local files when they spin down, restart, or redeploy.

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

Proposal generation requires:

```text
GITHUB_MODELS_TOKEN
```

To retain feedback and send the daily feedback report, also configure:

```text
PROPOSALAI_FEEDBACK_SHEET_ID
GOOGLE_SERVICE_ACCOUNT_JSON
FEEDBACK_SUMMARY_SECRET
BREVO_API_KEY
BREVO_FROM_EMAIL
PROPOSALAI_REPORT_EMAIL
```

Optional values:

```text
PROPOSALAI_FEEDBACK_SHEET_RANGE=Feedback!A:I
PROPOSALAI_FEEDBACK_HEADER_RANGE=Feedback!A1:I1
BREVO_REPLY_TO_EMAIL
```

Create a `Feedback` tab and share the spreadsheet with the `client_email` in the Google service-account JSON. The app creates its column headers on the first feedback response.

Daily summary email uses Brevo's HTTPS transactional email API, not SMTP. Render free web services block outbound SMTP ports, including port `587`.

The included GitHub Actions workflow requests a summary at `20:00 IST` each day. Add these secrets to the private repository:

```text
PROPOSALAI_RENDER_URL=https://YOUR-SERVICE.onrender.com
FEEDBACK_SUMMARY_SECRET=the-same-secret-set-on-render
```

Health check:

```text
/health
```
