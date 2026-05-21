# ProposalAI Revenue Ops Dashboard

Lightweight local dashboard for agent activity and revenue automation metrics.

## Run

```powershell
cd "C:\Users\ksoub\OneDrive\Desktop\New folder\All Data\Personal\Project\ProposalAI"
python .\revenue_ops\dashboard\server.py
```

Then open http://127.0.0.1:8765.

To point at the core workflow store explicitly:

```powershell
$env:PROPOSALAI_REVENUE_STORE = "C:\path\to\revenue_store.json"
python .\revenue_ops\dashboard\server.py --port 8765
```

The adapter checks JSON and SQLite stores in common `revenue_ops` locations. If none exists, it creates a compatible sample JSON store at `revenue_ops\dashboard\data\revenue_store.json`.

## Expected Store Shape

JSON stores can include any of these top-level arrays:

- `leads`
- `messages`
- `replies`
- `users`
- `events`
- `followups`

SQLite stores are read from matching table names when present.
