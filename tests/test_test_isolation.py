from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from rag_esocial.config import (
    TestIsolationError,
    corpus_storage_path_for_environment,
    database_url_for_environment,
    get_settings,
    validate_test_isolation,
)
from rag_esocial.db import assert_test_session, ensure_test_database, session_factory


def test_test_database_is_created_idempotently_and_selected_in_a_new_session():
    ensure_test_database()
    fresh = session_factory()()
    try:
        database = fresh.execute(text("SELECT current_database()")).scalar_one()
        assert database == "esocial_test"
        assert_test_session(fresh)
    finally:
        fresh.close()


def test_test_environment_uses_dedicated_database_and_corpus_storage():
    settings = get_settings()
    assert database_url_for_environment(settings) == settings.test_database_url
    assert corpus_storage_path_for_environment(settings).resolve() == (
        Path(settings.test_corpus_storage_path).resolve()
    )
    assert settings.test_corpus_storage_path != settings.corpus_storage_path


def test_development_environment_uses_runtime_database_url():
    settings = SimpleNamespace(
        database_url="postgresql+psycopg://user:pass@db:5432/esocial",
        test_database_url="postgresql+psycopg://user:pass@db:5432/esocial_test",
        corpus_storage_path="/app/data/corpus",
        test_corpus_storage_path="/app/data/test-corpus",
        environment="development",
    )
    assert database_url_for_environment(settings) == settings.database_url


def test_test_isolation_fails_closed_for_runtime_database_target():
    unsafe = SimpleNamespace(
        database_url="postgresql+psycopg://user:pass@db:5432/esocial",
        test_database_url="postgresql+psycopg://user:pass@db:5432/esocial",
        corpus_storage_path="/app/data/corpus",
        test_corpus_storage_path="/app/data/test-corpus",
        environment="test",
    )
    with pytest.raises(TestIsolationError, match="exactly"):
        validate_test_isolation(unsafe)


def test_test_isolation_fails_closed_when_urls_are_identical():
    unsafe = SimpleNamespace(
        database_url="postgresql+psycopg://user:pass@db:5432/esocial_test",
        test_database_url="postgresql+psycopg://user:pass@db:5432/esocial_test",
        corpus_storage_path="/app/data/corpus",
        test_corpus_storage_path="/app/data/test-corpus",
        environment="test",
    )
    with pytest.raises(TestIsolationError, match="must not target"):
        validate_test_isolation(unsafe)


def test_test_isolation_fails_closed_for_runtime_corpus_storage():
    unsafe = SimpleNamespace(
        database_url="postgresql+psycopg://user:pass@db:5432/esocial",
        test_database_url="postgresql+psycopg://user:pass@db:5432/esocial_test",
        corpus_storage_path="/app/data/corpus",
        test_corpus_storage_path="/app/data/corpus",
        environment="test",
    )
    with pytest.raises(TestIsolationError, match="separate"):
        validate_test_isolation(unsafe)


class _UnexpectedSession:
    def execute(self, statement):
        del statement
        raise AssertionError("database lookup must not happen without test environment")


def test_destructive_guard_fails_before_query_outside_test_environment(monkeypatch):
    monkeypatch.setenv("ESOCIAL_ENVIRONMENT", "development")
    get_settings.cache_clear()
    try:
        with pytest.raises(TestIsolationError, match="requires"):
            assert_test_session(_UnexpectedSession())
    finally:
        monkeypatch.setenv("ESOCIAL_ENVIRONMENT", "test")
        get_settings.cache_clear()


class _ScalarResult:
    def scalar_one(self):
        return "esocial"


class _RuntimeDatabaseSession:
    def execute(self, statement):
        del statement
        return _ScalarResult()


def test_cleanup_refuses_a_session_connected_to_runtime_database():
    from test_mos_integration import cleanup

    with pytest.raises(TestIsolationError, match="database 'esocial'"):
        cleanup(_RuntimeDatabaseSession(), {})
