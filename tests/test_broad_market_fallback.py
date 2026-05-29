import server


BOOKKEEPER_PROFILE = {
    "fullName": "Elena",
    "niche": "Bookkeeper",
    "experience": "8",
    "tone": "Calm",
    "skills": ["QuickBooks Online", "bank reconciliation", "monthly reports"],
    "pastWin": "Cleaned up 18 months of QuickBooks records for a consulting firm before tax season",
    "rate": "$40/hour",
}

BOOKKEEPER_JOB = (
    "Small agency needs monthly bookkeeping in QuickBooks Online. Tasks include bank reconciliation, "
    "categorizing expenses, invoices, and a monthly profit and loss report."
)

EMAIL_PROFILE = {
    "fullName": "Asha",
    "niche": "Email copywriter",
    "experience": "4",
    "tone": "Warm",
    "skills": ["email sequences", "launch copy", "customer research"],
    "pastWin": "Rewrote a 5-email launch sequence that brought in $18k in sales",
    "rate": "$45/hour",
}

EMAIL_JOB = (
    "We sell an online yoga course and need a 5-email welcome sequence for new subscribers. "
    "The emails should explain the course, build trust, and invite people to book a trial class."
)


def test_bookkeeping_fallback_uses_current_job_not_dashboard_template():
    relevant_win = server.select_relevant_win(BOOKKEEPER_PROFILE["pastWin"], BOOKKEEPER_JOB)
    proposal = server.build_rule_based_proposal(BOOKKEEPER_JOB, relevant_win, "quick")

    lowered = proposal.lower()
    assert "quickbooks" in lowered or "bookkeeping" in lowered or "reconciliation" in lowered
    assert "driver dashboard" not in lowered
    assert "filtered view" not in lowered

    findings = server.proposal_violations(proposal, BOOKKEEPER_PROFILE, BOOKKEEPER_JOB, relevant_win, "quick")
    assert not server.blocking_violations(proposal, findings)


def test_provider_failure_can_return_valid_rule_based_draft(monkeypatch):
    monkeypatch.setattr(server, "github_models_token", lambda: "test-token")
    monkeypatch.setattr(
        server,
        "request_github_models",
        lambda *args, **kwargs: server.error(server.USER_RETRY_MESSAGE, 503),
    )

    result = server.generate_proposal(
        {"profile": EMAIL_PROFILE, "jobDescription": EMAIL_JOB, "style": "quick"}
    )

    assert result.status == 200
    proposal = result.payload["proposal"]
    assert "email" in proposal.lower() or "sequence" in proposal.lower() or "subscribers" in proposal.lower()
    assert result.payload.get("fallback") == "rule_based_provider_failure"
