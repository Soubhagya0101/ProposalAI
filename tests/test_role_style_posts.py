import server


MARKETING_MANAGER_JOB = """Marketing Manager:

Responsibilities: Develop and implement marketing strategies to increase brand awareness. Manage marketing campaigns and analyze their performance. Collaborate with sales and product teams to align marketing efforts.
Requirements: Bachelor’s degree in Marketing or related field. Proven experience in marketing or related roles. Strong analytical skills and proficiency in marketing software and tools."""

MARKETING_PROFILE = {
    "fullName": "Asha",
    "niche": "Marketing consultant",
    "experience": "5",
    "tone": "Direct",
    "skills": ["marketing strategy", "campaign analysis", "brand awareness"],
    "pastWin": "Helped a small B2B team improve campaign reporting and align sales follow-up with marketing messages.",
    "rate": "$50/hr",
}


def test_detects_responsibilities_requirements_role_style_post():
    assert server.is_role_style_post(MARKETING_MANAGER_JOB)
    assert server.role_post_title(MARKETING_MANAGER_JOB) == "Marketing Manager"


def test_role_style_prompt_switches_to_applicant_voice_rules():
    relevant_win = server.select_relevant_win(MARKETING_PROFILE["pastWin"], MARKETING_MANAGER_JOB)
    prompt = server.build_prompt(
        MARKETING_PROFILE,
        MARKETING_MANAGER_JOB,
        relevant_win,
        server.situation_guidance(MARKETING_MANAGER_JOB, "detailed"),
        "detailed",
    ).lower()

    assert "role-style post detected" in prompt
    assert "application/proposal for the marketing manager role" in prompt
    assert "never write 'you'll have a marketing manager'" in prompt
    assert "first-person freelancer/applicant voice" in prompt


def test_role_style_validator_blocks_job_description_summary_voice():
    bad_proposal = """Without a solid understanding of the target audience, marketing strategies often fall flat. Usually, this lack of insight leads to wasted resources and missed opportunities, still leaving the company struggling to increase brand awareness.

The company needs a marketing manager who can develop effective strategies and collaborate with other teams.

You'll have a marketing manager who can analyze campaign performance and adjust strategies accordingly, and who can work closely with sales and product teams to align marketing efforts. You'll also have a clear understanding of how marketing campaigns are impacting the company's overall goals.

What specific marketing software and tools does the company currently use?"""

    relevant_win = server.select_relevant_win(MARKETING_PROFILE["pastWin"], MARKETING_MANAGER_JOB)
    findings = server.proposal_violations(
        bad_proposal,
        MARKETING_PROFILE,
        MARKETING_MANAGER_JOB,
        relevant_win,
        "detailed",
    )

    assert "role-style post answered as a job-description summary instead of an applicant proposal" in findings
    assert "role-style post answered as a job-description summary instead of an applicant proposal" in server.blocking_violations(bad_proposal, findings)


def test_role_style_applicant_proposal_passes_validator():
    good_proposal = """Brand awareness campaigns often fall flat when the team can see activity but not which audience, channel, or message is actually creating useful demand.

Helped a small B2B team improve campaign reporting and align sales follow-up with marketing messages.

I can help plan and manage campaigns around the audience you want to reach, then turn performance data into decisions sales and product can use. The proposal would stay tied to campaign results instead of repeating a generic marketing calendar.

Which marketing tools are you currently using for campaign tracking and reporting?"""

    relevant_win = server.select_relevant_win(MARKETING_PROFILE["pastWin"], MARKETING_MANAGER_JOB)
    findings = server.proposal_violations(
        good_proposal,
        MARKETING_PROFILE,
        MARKETING_MANAGER_JOB,
        relevant_win,
        "detailed",
    )

    assert not server.blocking_violations(good_proposal, findings)


def test_role_style_provider_summary_fails_visible_without_retry_or_fallback(monkeypatch):
    calls = {"count": 0}

    def fake_provider(*args, **kwargs):
        calls["count"] += 1
        return server.ApiResult(
            200,
            {
                "proposal": """Without a solid understanding of the target audience, marketing strategies often fall flat. Usually, this lack of insight leads to wasted resources and missed opportunities, still leaving the company struggling to increase brand awareness.

The company needs a marketing manager who can develop effective strategies and collaborate with other teams.

You'll have a marketing manager who can analyze campaign performance and adjust strategies accordingly, and who can work closely with sales and product teams to align marketing efforts. You'll also have a clear understanding of how marketing campaigns are impacting the company's overall goals.

What specific marketing software and tools does the company currently use?"""
            },
        )

    monkeypatch.setattr(server, "github_models_token", lambda: "test-token")
    monkeypatch.setattr(server, "request_github_models", fake_provider)

    result = server.generate_proposal(
        {"profile": MARKETING_PROFILE, "jobDescription": MARKETING_MANAGER_JOB, "style": "detailed"}
    )

    assert result.status == 502
    assert result.payload["code"] == "GROQ_VALIDATOR_BLOCKED"
    assert result.payload.get("fallback") is None
    assert calls["count"] == 1
