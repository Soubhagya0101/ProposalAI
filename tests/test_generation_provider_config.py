import urllib.error
from email.message import Message

import server


def clear_generation_env(monkeypatch):
    for name in (
        "BLUESMINDS_API_KEY",
        "GENERATION_API_KEY",
        "GENERATION_API_URL",
        "GENERATION_MODEL_ID",
        "GROQ_API_KEY",
        "GROQ_MODEL_ID",
        "GITHUB_MODELS_TOKEN",
        "GITHUB_PAT",
        "GITHUB_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)


def test_only_groq_key_is_used_for_generation_token(monkeypatch):
    clear_generation_env(monkeypatch)
    monkeypatch.setenv("BLUESMINDS_API_KEY", "blue-test-key")
    monkeypatch.setenv("GENERATION_API_KEY", "custom-test-key")
    monkeypatch.setenv("GITHUB_MODELS_TOKEN", "github-test-key")

    assert server.github_models_token() == ""

    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    assert server.github_models_token() == "groq-test-key"


def test_groq_provider_is_always_selected(monkeypatch):
    clear_generation_env(monkeypatch)
    monkeypatch.setenv("GENERATION_API_URL", "https://example.com/v1/chat/completions")
    monkeypatch.setenv("GENERATION_MODEL_ID", "custom-model")
    monkeypatch.setenv("GROQ_MODEL_ID", "llama-test-model")

    assert server.generation_provider_config() == (
        "groq",
        server.GROQ_MODELS_URL,
        "llama-test-model",
    )


def test_provider_request_sets_user_agent_and_uses_one_attempt(monkeypatch):
    captured_headers = {}
    calls = {"count": 0}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}]}'

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        captured_headers.update(dict(request.header_items()))
        return FakeResponse()

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")

    result = server.request_github_models("groq-test-key", "Say ok", temperature=0, max_tokens=10)

    assert result.status == 200
    assert calls["count"] == 1
    assert captured_headers["User-agent"] == "ProposalAI/1.0"


def test_provider_http_error_does_not_retry(monkeypatch):
    calls = {"count": 0}

    def fake_urlopen(request, timeout):
        calls["count"] += 1
        raise urllib.error.HTTPError(request.full_url, 429, "rate limited", Message(), None)

    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")

    result = server.request_github_models("groq-test-key", "Say ok", temperature=0, max_tokens=10)

    assert result.status == 503
    assert calls["count"] == 1


def test_missing_groq_key_returns_configuration_error(monkeypatch):
    clear_generation_env(monkeypatch)
    result = server.generate_proposal(
        {
            "profile": {
                "fullName": "Asha",
                "niche": "Email copywriter",
                "experience": "4",
                "tone": "Warm",
                "skills": ["email sequences"],
                "pastWin": "",
                "rate": "$45/hour",
            },
            "jobDescription": "Need a 5-email welcome sequence for new subscribers to explain the course and book a trial class.",
            "style": "quick",
        }
    )

    assert result.status == 503
    assert result.payload["code"] == "MISSING_GROQ_API_KEY"
    assert result.payload["provider"] == "groq"
