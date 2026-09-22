"""Global PostgreSQL and corpus isolation for the test suite."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

# This is intentionally set before pytest imports test modules that import services.
os.environ["ESOCIAL_ENVIRONMENT"] = "test"

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _clear_test_corpus() -> None:
    from rag_esocial.config import (
        TestIsolationError,
        corpus_storage_path_for_environment,
        get_settings,
    )

    settings = get_settings()
    root = corpus_storage_path_for_environment(settings).resolve()
    runtime_root = Path(settings.corpus_storage_path).resolve()
    if root == runtime_root or runtime_root in root.parents or "test" not in root.name:
        raise TestIsolationError("refusing to clean a non-test corpus storage path")
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)


def pytest_sessionstart(session: pytest.Session) -> None:
    del session
    from rag_esocial.config import get_settings, validate_test_isolation
    from rag_esocial.db import (
        assert_test_session,
        ensure_test_database,
        session_factory,
    )

    get_settings.cache_clear()
    validate_test_isolation(get_settings())
    ensure_test_database()
    subprocess.run(
        [str(Path(sys.executable).parent / "alembic"), "upgrade", "head"],
        check=True,
        cwd=PROJECT_ROOT,
        env=os.environ.copy(),
    )
    database_session = session_factory()()
    try:
        assert_test_session(database_session)
        database = database_session.execute(
            text("SELECT current_database()")
        ).scalar_one()
        assert database == "esocial_test"
    finally:
        database_session.close()
    _clear_test_corpus()
