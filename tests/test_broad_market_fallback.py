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

WEBSITE_COPY_PROFILE = {
    "fullName": "Ravi",
    "niche": "Website copywriter",
    "experience": "4 years",
    "tone": "Direct",
    "skills": ["website rewrites", "SEO-friendly copy", "manual editing"],
    "pastWin": "",
    "rate": "$25/hr",
}

WEBSITE_COPY_JOB = (
    "Need a detail-oriented website copywriter to rewrite existing website content for a new site. "
    "The copy should be SEO-friendly, professional, and match the original business message. "
    "Future projects available if this goes well. Estimated 1-3 hours, budget $10. "
    "You can use AI tools like ChatGPT, Claude, or Gemini but final text must read naturally."
)

DATA_RESEARCH_PROFILE = {
    "fullName": "Ishan",
    "niche": "Data research freelancer",
    "experience": "3 years",
    "tone": "Direct",
    "skills": ["web research", "data collection", "spreadsheet cleanup"],
    "pastWin": "",
    "rate": "$20/hr",
}

DATA_RESEARCH_JOB = (
    "We are looking for freelancers who gather data from online sources. "
    "If you use software will be faster and cleaner data; otherwise, manual is also fine."
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


def test_validator_allows_banned_wording_when_it_came_from_job_description():
    profile = WEBSITE_COPY_PROFILE
    job = WEBSITE_COPY_JOB
    proposal = (
        "Website rewrites can lose the original business message when the new copy only sounds polished. "
        "I can rewrite the existing pages into clean, SEO-friendly copy while keeping the meaning intact and manually editing the final text for better website readability. "
        "Could you share the existing website link and page list?"
    )

    findings = server.proposal_violations(proposal, profile, job, "", "quick")

    assert not any(finding.startswith("banned wording used:") for finding in findings)
    assert not server.blocking_violations(proposal, findings)


def test_website_copywriting_fallback_sounds_human_for_long_real_job():
    proposal = server.build_rule_based_proposal(WEBSITE_COPY_JOB, "", "quick")
    lowered = proposal.lower()

    assert "copywriter, rewrite, existing" not in lowered
    assert "treated as separate pieces" not in lowered
    assert "website rewrites can go wrong" in lowered
    assert "seo-friendly" in lowered
    assert "manually editing" in lowered

    findings = server.proposal_violations(proposal, WEBSITE_COPY_PROFILE, WEBSITE_COPY_JOB, "", "quick")
    assert not server.blocking_violations(proposal, findings)


def test_clean_proposal_repairs_provider_punctuation_after_past_win():
    proposal = server.clean_proposal(
        "Website rewrites can go wrong when the copy drifts from the original message. "
        "Rewrote a service page that lifted consultation bookings by 18%., so I can keep the rewrite tied to a real content outcome. "
        "could you share the existing website link and page list?"
    )

    assert "%. ," not in proposal
    assert "%.," not in proposal
    assert "18%. So I can" in proposal
    assert "Could you share" in proposal


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


def test_blocked_provider_draft_uses_rule_based_without_extra_provider_calls(monkeypatch):
    profile = {
        "fullName": "Maya",
        "niche": "Customer support specialist",
        "experience": "5 years",
        "tone": "Direct",
        "skills": ["refund replies", "shipping questions", "conversation tagging"],
        "pastWin": "Reduced unresolved weekend tickets for a small ecommerce store.",
        "rate": "$35/hr",
    }
    job = (
        "Ecommerce brand needs weekend customer support help. Reply to refund, shipping, "
        "and product questions using our tone guide and tag conversations correctly."
    )
    calls = {"count": 0}

    def fake_provider(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return server.ApiResult(200, {"proposal": "Hello, I am passionate and detail-oriented."})
        return server.error(server.USER_RETRY_MESSAGE, 503)

    monkeypatch.setattr(server, "github_models_token", lambda: "test-token")
    monkeypatch.setattr(server, "request_github_models", fake_provider)

    result = server.generate_proposal({"profile": profile, "jobDescription": job, "style": "quick"})

    assert result.status == 200
    assert result.payload.get("fallback") == "rule_based_validator_block"
    assert "customer" in result.payload["proposal"].lower() or "support" in result.payload["proposal"].lower()
    assert ".," not in result.payload["proposal"]
    assert calls["count"] == 1


def test_broad_public_test_does_not_block_adjacent_freelance_categories(monkeypatch):
    profile = {
        "fullName": "SK Test",
        "niche": "Freelance operator across web, content, automation, and business support",
        "experience": "5 years",
        "tone": "Friendly",
        "skills": ["Client communication", "Project execution", "Fast research"],
        "pastWin": "Helped clients turn unclear requirements into practical deliverables.",
        "rate": "$40/hr",
    }
    jobs = [
        "Need a short-form video editor for 20 reels from podcast clips. Add captions, hooks, simple b-roll, and deliver in vertical format.",
        "Looking for a UI designer to redesign our SaaS onboarding flow in Figma, improve empty states, and make mobile screens cleaner.",
        "Ecommerce brand needs weekend customer support help. Reply to refund, shipping, and product questions using our tone guide.",
    ]
    monkeypatch.setattr(server, "github_models_token", lambda: "test-token")
    monkeypatch.setattr(
        server,
        "request_github_models",
        lambda *args, **kwargs: server.error(server.USER_RETRY_MESSAGE, 503),
    )

    for job in jobs:
        result = server.generate_proposal({"profile": profile, "jobDescription": job, "style": "quick"})
        assert result.status == 200
        assert result.payload.get("fallback") == "rule_based_provider_failure"


def test_prompt_uses_real_freelancer_buyer_psychology_rules():
    prompt = server.build_prompt(EMAIL_PROFILE, EMAIL_JOB, EMAIL_PROFILE["pastWin"], "", "quick")

    lowered = prompt.lower()
    assert "client is skimming a pile of proposals" in lowered
    assert "do not try to prove the freelancer is impressive" in lowered
    assert "one relevant proof point" in lowered
    assert "practical next step or decision question" in lowered


def test_generic_fallback_reflects_real_freelancer_commentary_without_skill_dump():
    profile = {
        "fullName": "Nora",
        "niche": "Translator",
        "experience": "3 years",
        "tone": "Direct",
        "skills": ["translation", "localization", "proofreading"],
        "pastWin": "",
        "rate": "$18/hr",
    }
    job = (
        "Need a translator to localize onboarding emails from English to Spanish, keep the tone casual, "
        "and flag phrases that would sound awkward to native readers."
    )

    proposal = server.build_rule_based_proposal(job, "", "quick")
    lowered = proposal.lower()

    assert "not proving you can do everything" in lowered
    assert "exact part of the brief" in lowered
    assert "long generic" in lowered
    assert "similar projects" not in lowered
    assert "years of experience" not in lowered

    findings = server.proposal_violations(proposal, profile, job, "", "quick")
    assert not server.blocking_violations(proposal, findings)


def test_virtual_assistant_fallback_uses_admin_reality_not_awkward_focus_term():
    profile = {
        "fullName": "Mina",
        "niche": "Virtual assistant",
        "experience": "3 years",
        "tone": "Direct",
        "skills": ["admin support", "data entry", "calendar cleanup"],
        "pastWin": "",
        "rate": "$18/hr",
    }
    job = (
        "Need a virtual assistant to clean up a messy spreadsheet, organize meeting notes, "
        "update contact records, and flag missing details before Friday."
    )

    proposal = server.build_rule_based_proposal(job, "", "quick")
    lowered = proposal.lower()

    assert "messy admin work" in lowered
    assert "unclear fields flagged" in lowered
    assert "which part of virtual" not in lowered
    assert "the spreadsheet, notes, or contact records" in lowered

    findings = server.proposal_violations(proposal, profile, job, "", "quick")
    assert not server.blocking_violations(proposal, findings)


def test_data_research_fallback_understands_online_data_gathering_not_freelancers():
    proposal = server.build_rule_based_proposal(DATA_RESEARCH_JOB, "", "quick")
    lowered = proposal.lower()

    assert "online data gathering" in lowered
    assert "online sources" in lowered
    assert "clean spreadsheet" in lowered
    assert "i can collect the data" in lowered
    assert "software" in lowered
    assert "manually check entries" in lowered
    assert "you'll get" not in lowered
    assert "which part of freelancers" not in lowered
    assert "freelancers work" not in lowered
    assert proposal.endswith("?")
    assert "target sources" in lowered or "fields" in lowered

    findings = server.proposal_violations(proposal, DATA_RESEARCH_PROFILE, DATA_RESEARCH_JOB, "", "quick")
    assert not server.blocking_violations(proposal, findings)


def test_wordpress_laravel_client_history_blob_generates_relevant_quick_and_detailed_fallback(monkeypatch):
    profile = {
        "fullName": "Dev Test",
        "niche": "WordPress Laravel Developer",
        "experience": "5 years",
        "tone": "Direct",
        "skills": ["WordPress", "Laravel", "SEO", "site migration"],
        "pastWin": "",
        "rate": "$25/hr",
    }
    job = (
        "Corporate Lawyer Needed – NDA & Agreement Drafting for Game Development Project\n"
        "Mar 2026 - Apr 2026\n"
        "Fixed-price $5.00\n"
        "Other open jobs by this Client (2)\n"
        "Experienced Laravel Developer Needed – Convert Existing WordPress Website to Laravel\n"
        "Fixed-price\n"
        "AI-Powered WordPress SEO & Social Media Marketing Expert (Lead Generation Focus)\n"
        "Fixed-price"
    )
    monkeypatch.setattr(server, "github_models_token", lambda: "test-token")
    monkeypatch.setattr(
        server,
        "request_github_models",
        lambda *args, **kwargs: server.error(server.USER_RETRY_MESSAGE, 503),
    )

    for style in ("quick", "detailed"):
        result = server.generate_proposal({"profile": profile, "jobDescription": job, "style": style})
        assert result.status == 200
        assert result.payload.get("fallback") == "rule_based_provider_failure"
        proposal = result.payload["proposal"]
        lowered = proposal.lower()
        assert "wordpress" in lowered
        assert "laravel" in lowered
        assert "slow wordpress mobile load" not in lowered
        assert "shared hosting" not in lowered
        findings = server.proposal_violations(proposal, profile, job, "", style)
        assert not server.blocking_violations(proposal, findings)


def test_detailed_validator_allows_non_step_words_like_first_reply():
    proposal = (
        "Onboarding emails usually fail when the wording is technically correct but native readers feel the phrasing was carried over too directly. "
        "Clients often judge the first reply by whether the freelancer notices that tone risk, not by a long language list.\n\n"
        "I can localize the onboarding emails so the meaning stays intact and the casual tone reads naturally in Spanish. "
        "The finished copy should feel written for the reader, not transferred from English sentence by sentence.\n\n"
        "Should the Spanish version stay casual across every email, or only in the welcome message?"
    )
    job = "Need a translator to localize onboarding emails from English to Spanish and keep the tone casual."
    profile = {"niche": "Translator", "skills": ["translation", "localization"], "pastWin": "", "experience": "3 years", "rate": "$18/hr"}

    findings = server.proposal_violations(proposal, profile, job, "", "detailed")

    assert "detailed draft lists process steps" not in findings
    assert not server.blocking_violations(proposal, findings)


def test_validator_block_fallback_is_visible_to_frontend(monkeypatch):
    calls = {"count": 0}

    def fake_provider(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return server.ApiResult(200, {"proposal": "Hello, I am passionate and detail-oriented."})
        return server.error(server.USER_RETRY_MESSAGE, 503)

    monkeypatch.setattr(server, "github_models_token", lambda: "test-token")
    monkeypatch.setattr(server, "request_github_models", fake_provider)

    result = server.generate_proposal(
        {"profile": DATA_RESEARCH_PROFILE, "jobDescription": DATA_RESEARCH_JOB, "style": "quick"}
    )

    assert result.status == 200
    assert result.payload.get("fallback") == "rule_based_validator_block"
    lowered = result.payload["proposal"].lower()
    assert "online data gathering" in lowered
    assert "which part of freelancers" not in lowered
    assert calls["count"] == 1


def test_figma_wordpress_revamp_data_migration_does_not_become_laravel(monkeypatch):
    profile = {
        "fullName": "Asha",
        "niche": "WordPress designer and developer",
        "experience": "5",
        "tone": "clear",
        "skills": ["Figma", "WordPress", "website redesign", "data migration"],
        "pastWin": "",
        "rate": "$35/hour",
    }
    job = (
        "Need a person who can Revamp and Redesign our website.\n\n"
        "I need a dedicated person to design a figam file for our website.\n\n"
        "Also, have to convert the same to wordpress and migrate our data to new wordpress\n\n"
        "Check our website memedownload.in -- Make sure to tell me the timeline with no. of pages etc."
    )
    monkeypatch.setattr(server, "github_models_token", lambda: "test-token")
    monkeypatch.setattr(
        server,
        "request_github_models",
        lambda *args, **kwargs: server.error(server.USER_RETRY_MESSAGE, 503),
    )

    for style in ("quick", "detailed"):
        result = server.generate_proposal({"profile": profile, "jobDescription": job, "style": style})
        assert result.status == 200
        proposal = result.payload["proposal"]
        lowered = proposal.lower()
        assert "figma" in lowered
        assert "wordpress" in lowered
        assert "memedownload.in" in lowered
        assert "page" in lowered or "pages" in lowered
        assert "timeline" in lowered
        assert "laravel" not in lowered
        findings = server.proposal_violations(proposal, profile, job, "", style)
        assert not server.blocking_violations(proposal, findings)
