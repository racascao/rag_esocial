from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

TEST_DATABASE_NAME = "esocial_test"


class TestIsolationError(RuntimeError):
    """Raised when a test run is not provably isolated from production data."""

    __test__ = False


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
    test_corpus_storage_path: str = "/app/data/test-corpus"


def validate_test_isolation(settings: Settings) -> None:
    """Fail closed unless the configured test targets are dedicated resources."""
    production = make_url(settings.database_url)
    test = make_url(settings.test_database_url)
    if test.database != TEST_DATABASE_NAME:
        raise TestIsolationError(
            "test database must be exactly "
            f"{TEST_DATABASE_NAME!r}, got {test.database!r}"
        )
    if production.database == test.database:
        raise TestIsolationError(
            "test database URL must not target the runtime database"
        )
    production_storage = Path(settings.corpus_storage_path).resolve()
    test_storage = Path(settings.test_corpus_storage_path).resolve()
    if production_storage == test_storage or production_storage in test_storage.parents:
        raise TestIsolationError(
            "test corpus storage must be separate from runtime corpus storage"
        )
    if "test" not in test_storage.name:
        raise TestIsolationError(
            "test corpus storage path must be explicitly test-scoped"
        )


def database_url_for_environment(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if settings.environment == "test":
        validate_test_isolation(settings)
        return settings.test_database_url
    return settings.database_url


def corpus_storage_path_for_environment(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    if settings.environment == "test":
        validate_test_isolation(settings)
        return Path(settings.test_corpus_storage_path)
    return Path(settings.corpus_storage_path)


@lru_cache
def get_settings() -> Settings:
    return Settings()
