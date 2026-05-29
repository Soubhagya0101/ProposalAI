import server


PROFILE = {
    "fullName": "Test User",
    "niche": "Shopify developer",
    "experience": "5",
    "tone": "Professional",
    "skills": ["Shopify", "landing pages", "conversion copy"],
    "pastWin": "Fixed Shopify checkout flow and reduced drop-offs by 40%",
    "rate": "$50/hour",
}

JOB = (
    "We need a Shopify landing page redesign for eco-friendly water bottles. "
    "Improve the hero section, product benefits, mobile layout, and call to action."
)


def test_quick_draft_blocks_i_can_help_opener():
    proposal = (
        "I can help with this project and make sure the page is clear for shoppers. "
        "Fixed Shopify checkout flow and reduced drop-offs by 40%, so the page can stay tied to the offer. "
        "Should the main call to action send shoppers to the product page, cart, or checkout?"
    )

    findings = server.proposal_violations(
        proposal,
        PROFILE,
        JOB,
        PROFILE["pastWin"],
        "quick",
    )

    assert "generic freelancer-first opener used" in findings
    assert "generic freelancer-first opener used" in server.blocking_violations(proposal, findings)


def test_quick_draft_blocks_first_line_without_job_specific_noun():
    proposal = (
        "This kind of work can look fine and still fail when the main message is unclear. "
        "Fixed Shopify checkout flow and reduced drop-offs by 40%, so the page can stay tied to the offer. "
        "Should the main call to action send shoppers to the product page, cart, or checkout?"
    )

    findings = server.proposal_violations(
        proposal,
        PROFILE,
        JOB,
        PROFILE["pastWin"],
        "quick",
    )

    assert "first sentence lacks a job-specific noun" in findings
    assert "first sentence lacks a job-specific noun" in server.blocking_violations(proposal, findings)


def test_quick_draft_accepts_job_specific_client_first_opener():
    proposal = (
        "A Shopify landing page can look clean and still lose buyers when the hero, benefits, and mobile call to action fight for attention. "
        "Fixed Shopify checkout flow and reduced drop-offs by 40%, so you'll have a page for eco-friendly water bottles where the offer is clear and the mobile action is easy to take. "
        "Should the main call to action send shoppers to the product page, cart, or checkout?"
    )

    findings = server.proposal_violations(
        proposal,
        PROFILE,
        JOB,
        PROFILE["pastWin"],
        "quick",
    )

    assert "generic freelancer-first opener used" not in findings
    assert "first sentence lacks a job-specific noun" not in findings
