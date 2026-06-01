from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "public" / "index.html"
SOURCE = HTML.read_text(encoding="utf-8")


def test_frontend_retries_transient_generation_failures_three_times():
    assert "const MAX_GENERATION_ATTEMPTS = 3;" in SOURCE


def test_frontend_defines_20_second_generation_cooldown():
    assert "const GENERATION_COOLDOWN_MS = 20000;" in SOURCE
    assert "let generationCooldownUntil = 0;" in SOURCE


def test_generate_button_state_respects_generating_and_cooldown():
    assert "function isGenerationCoolingDown()" in SOURCE
    assert "function remainingCooldownSeconds()" in SOURCE
    assert "function updateGenerateButtonState()" in SOURCE
    assert "function setGenerating(generating)" in SOURCE
    assert "isGenerating = generating;" in SOURCE
    assert "generateBtn.disabled = isGenerating || isCoolingDown;" in SOURCE


def test_profile_form_uses_app_validation_not_native_required_popups():
    assert 'id="profileForm" novalidate' in SOURCE
    assert 'setStatus(profileStatus, `Complete: ${missing.join(", ")}.`, "error");' in SOURCE


def test_generate_button_can_show_short_job_error_instead_of_dead_click():
    assert "if (job.length < MIN_JOB_CHARS)" in SOURCE
    assert 'setStatus(generateStatus, "Add at least 50 characters.", "error");' in SOURCE
    assert "generateBtn.disabled = isGenerating || isCoolingDown;" in SOURCE


def test_frontend_shows_server_errors_instead_of_generic_retry_only():
    assert "const error = new Error(data.error || RETRY_MESSAGE);" in SOURCE
    assert "setStatus(generateStatus, message || RETRY_MESSAGE, \"error\");" in SOURCE


def test_successful_generation_starts_cooldown_and_shows_wait_message():
    assert "startGenerationCooldown();" in SOURCE
    assert "Wait ${remainingCooldownSeconds()}s before generating again." in SOURCE
    assert "generateStatus.textContent.includes(\"before generating again\")" in SOURCE
    assert "window.setInterval" in SOURCE
