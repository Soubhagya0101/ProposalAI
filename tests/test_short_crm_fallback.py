import server

CRM_PROFILE = {
    "fullName": "SK",
    "niche": "Full stack developer",
    "experience": "3",
    "tone": "Professional",
    "skills": ["React", "Node.js", "CRM automation"],
    "pastWin": "Built a CRM dashboard that helped a sales team track leads faster",
    "rate": "$25/hour",
}

CRM_JOB = "We need a full stack developer to manage our CRM.."


def test_short_crm_job_fallback_still_returns_valid_quick_proposal():
    relevant_win = server.select_relevant_win(CRM_PROFILE["pastWin"], CRM_JOB)
    proposal = server.build_rule_based_proposal(CRM_JOB, relevant_win, "quick")

    assert 50 <= server.word_count(proposal) <= 80
    assert "crm" in proposal.lower()
    assert "Which" in proposal and proposal.endswith("?")

    findings = server.proposal_violations(proposal, CRM_PROFILE, CRM_JOB, relevant_win, "quick")
    assert not server.blocking_violations(proposal, findings)


def test_provider_failure_returns_valid_crm_fallback(monkeypatch):
    monkeypatch.setattr(server, "github_models_token", lambda: "test-token")
    monkeypatch.setattr(
        server,
        "request_github_models",
        lambda *args, **kwargs: server.error(server.USER_RETRY_MESSAGE, 503),
    )

    result = server.generate_proposal(
        {"profile": CRM_PROFILE, "jobDescription": CRM_JOB, "style": "quick"}
    )

    assert result.status == 200
    assert result.payload["fallback"] == "rule_based_provider_failure"
    assert "crm" in result.payload["proposal"].lower()
