import server


def test_quick_provider_draft_under_fifty_words_can_pass_when_specific():
    profile = {
        "fullName": "Asha",
        "niche": "Email copywriter",
        "experience": "4",
        "tone": "warm",
        "skills": ["welcome emails", "course launch emails"],
        "pastWin": "",
        "rate": "$45/hour",
    }
    job = (
        "Need a 5-email welcome sequence for new subscribers to explain our online course, "
        "handle common doubts, and book a trial class. The emails should sound personal, "
        "not pushy, and help people understand whether the course fits them."
    )
    proposal = (
        "New subscribers often drop off if they don't quickly understand the value of an online course. "
        "The welcome sequence will help people decide if the course fits them. "
        "What's the main doubt or concern you've heard from potential students that the emails should address?"
    )

    findings = server.proposal_violations(proposal, profile, job, "", "quick")

    assert server.word_count(proposal) == 44
    assert not server.blocking_violations(proposal, findings)


def test_figma_wordpress_scope_opener_is_not_treated_as_echo():
    first_sentence = (
        "A redesign is not just about visuals when it involves Figma design, "
        "WordPress build, and data migration - the scope is broader and more complex."
    )
    job = (
        "Need a person who can revamp and redesign our website, design a Figma file, "
        "convert the same to WordPress, and migrate our data to new WordPress."
    )

    assert not server.opening_echoes_brief(first_sentence, job)


def test_clean_proposal_rewrites_common_provider_filler():
    proposal = (
        "The number of pages will significantly impact the timeline, making a seamless transition crucial."
    )

    cleaned = server.clean_proposal(proposal)

    assert "significantly" not in cleaned.lower()
    assert "seamless transition" not in cleaned.lower()
    assert "crucial" not in cleaned.lower()
    assert "shape the timeline" in cleaned.lower()
