from rag_esocial.config import Settings


def test_defaults() -> None:
    settings = Settings()
    assert settings.environment == "development"
    assert settings.llm_model == "gemma4:12b"
