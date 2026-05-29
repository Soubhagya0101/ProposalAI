from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "public" / "index.html"
SOURCE = HTML.read_text(encoding="utf-8")


def test_frontend_defines_20_second_generation_cooldown():
    assert "const GENERATION_COOLDOWN_MS = 20000;" in SOURCE
    assert "let generationCooldownUntil = 0;" in SOURCE


def test_generate_button_state_respects_generating_and_cooldown():
    assert "function isGenerationCoolingDown()" in SOURCE
    assert "function remainingCooldownSeconds()" in SOURCE
    assert "function updateGenerateButtonState()" in SOURCE
    assert "function setGenerating(generating)" in SOURCE
    assert "isGenerating = generating;" in SOURCE
    assert "generateBtn.disabled = isGenerating || isCoolingDown || count < MIN_JOB_CHARS;" in SOURCE


def test_successful_generation_starts_cooldown_and_shows_wait_message():
    assert "startGenerationCooldown();" in SOURCE
    assert "Wait ${remainingCooldownSeconds()}s before generating again." in SOURCE
    assert "generateStatus.textContent.includes(\"before generating again\")" in SOURCE
    assert "window.setInterval" in SOURCE
