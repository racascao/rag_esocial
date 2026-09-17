from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ESOCIAL_", env_file=".env")
    environment: str = "development"
    database_url: str = "postgresql+psycopg://esocial:esocial@db:5432/esocial"
    test_database_url: str = "postgresql+psycopg://esocial:esocial@db:5432/esocial_test"
    log_level: str = "INFO"
    app_name: str = "rag-esocial"
    app_version: str = "0.1.0"
    llm_model: str = "gemma4:12b"
    ollama_base_url: str = "http://ollama:11434"
    ollama_host_url: str = "http://localhost:11436"
    corpus_storage_path: str = "/app/data/corpus"


@lru_cache
def get_settings() -> Settings:
    return Settings()
