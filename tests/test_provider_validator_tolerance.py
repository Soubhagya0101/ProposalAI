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
