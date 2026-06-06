import server


DENTAL_PROFILE = {
    "fullName": "Maya",
    "niche": "WordPress designer",
    "experience": "5 years",
    "tone": "Direct",
    "skills": ["WordPress redesign", "online booking", "mobile pages"],
    "pastWin": "Completed 3 healthcare websites with mobile-friendly booking flows",
    "rate": "$45/hr",
}

DENTAL_JOB = (
    "Local dental clinic needs a WordPress redesign with online booking, SEO, "
    "mobile-friendly pages, 4-week launch, and budget $2,500."
)


def test_detailed_prompt_treats_plan_b_as_full_proposal_with_job_constraints():
    relevant_win = server.select_relevant_win(DENTAL_PROFILE["pastWin"], DENTAL_JOB)
    guidance = server.situation_guidance(DENTAL_JOB, "detailed")
    prompt = server.build_prompt(DENTAL_PROFILE, DENTAL_JOB, relevant_win, guidance, "detailed")
    lowered = prompt.lower()

    assert "style: detailed" in lowered
    assert "scope" in lowered or "finished outcome" in lowered
    assert "timeline/deadline mentioned: 4-week" in lowered
    assert "budget mentioned: $2,500" in lowered
    assert "booking flow is part of the scope" in lowered
    assert "seo must be preserved or improved" in lowered
    assert "mobile experience matters" in lowered
    assert "figma" not in guidance.lower()


def test_wordpress_redesign_guidance_does_not_invent_figma_when_job_does_not_say_figma():
    guidance = server.situation_guidance(DENTAL_JOB, "detailed")

    assert "wordpress redesign" in guidance.lower()
    assert "figma" not in guidance.lower()
    assert "booking/seo/mobile" in guidance.lower()


def test_extract_client_constraints_captures_budget_timeline_and_scope_facts():
    constraints = server.extract_client_constraints(DENTAL_JOB)

    assert "Timeline/deadline mentioned: 4-week" in constraints
    assert "Budget mentioned: $2,500" in constraints
    assert "Booking flow is part of the scope" in constraints
    assert "SEO must be preserved or improved" in constraints
    assert "Mobile experience matters" in constraints
    assert "WordPress is the platform" in constraints
