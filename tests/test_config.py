from rag_esocial.config import Settings, get_settings


def test_defaults(monkeypatch) -> None:
    monkeypatch.delenv("ESOCIAL_ENVIRONMENT", raising=False)
    get_settings.cache_clear()
    settings = Settings()
    assert settings.environment == "development"
    assert settings.llm_model == "gemma4:12b"
