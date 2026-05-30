import os

import server


def clear_generation_env(monkeypatch):
    for name in (
        "BLUESMINDS_API_KEY",
        "GENERATION_API_KEY",
        "GENERATION_API_URL",
        "GENERATION_MODEL_ID",
        "GROQ_API_KEY",
        "GITHUB_MODELS_TOKEN",
        "GITHUB_PAT",
        "GITHUB_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)


def test_bluesminds_key_selects_bluesminds_provider(monkeypatch):
    clear_generation_env(monkeypatch)
    monkeypatch.setenv("BLUESMINDS_API_KEY", "blue-test-key")

    assert server.github_models_token() == "blue-test-key"
    assert server.generation_provider_config() == (
        "bluesminds",
        server.BLUESMINDS_MODELS_URL,
        server.BLUESMINDS_MODEL_ID,
    )


def test_groq_key_selects_groq_provider(monkeypatch):
    clear_generation_env(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")

    assert server.github_models_token() == "groq-test-key"
    assert server.generation_provider_config() == (
        "groq",
        server.GROQ_MODELS_URL,
        server.GROQ_MODEL_ID,
    )


def test_github_token_still_uses_github_fallback(monkeypatch):
    clear_generation_env(monkeypatch)
    monkeypatch.setenv("GITHUB_MODELS_TOKEN", "github-test-key")

    assert server.github_models_token() == "github-test-key"
    assert server.generation_provider_config() == (
        "github",
        server.GITHUB_MODELS_URL,
        server.GITHUB_MODEL_ID,
    )


def test_explicit_generation_api_url_overrides_provider(monkeypatch):
    clear_generation_env(monkeypatch)
    monkeypatch.setenv("GENERATION_API_KEY", "custom-test-key")
    monkeypatch.setenv("GENERATION_API_URL", "https://example.com/v1/chat/completions")
    monkeypatch.setenv("GENERATION_MODEL_ID", "custom-model")

    assert server.github_models_token() == "custom-test-key"
    assert server.generation_provider_config() == (
        "custom",
        "https://example.com/v1/chat/completions",
        "custom-model",
    )
