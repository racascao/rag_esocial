from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import sessionmaker

from .config import (
    TEST_DATABASE_NAME,
    TestIsolationError,
    database_url_for_environment,
    get_settings,
    validate_test_isolation,
)


def get_engine():
    return create_engine(database_url_for_environment(), pool_pre_ping=True)


def check_connection() -> bool:
    with get_engine().connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one() == 1


def session_factory():
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def assert_test_session(session) -> None:
    """Protect destructive test helpers before they can mutate any table."""
    settings = get_settings()
    if settings.environment != "test":
        raise TestIsolationError(
            "destructive test operation requires ESOCIAL_ENVIRONMENT=test"
        )
    validate_test_isolation(settings)
    database = session.execute(text("SELECT current_database()")).scalar_one()
    if database != TEST_DATABASE_NAME:
        raise TestIsolationError(
            f"destructive test operation refused for database {database!r}"
        )


def ensure_test_database() -> None:
    """Create only the dedicated test database, idempotently, via postgres."""
    settings = get_settings()
    if settings.environment != "test":
        raise TestIsolationError(
            "test database bootstrap requires ESOCIAL_ENVIRONMENT=test"
        )
    validate_test_isolation(settings)
    admin_url = make_url(settings.test_database_url).set(database="postgres")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DATABASE_NAME},
            ).scalar_one_or_none()
            if exists is None:
                try:
                    connection.execute(text("CREATE DATABASE esocial_test"))
                except ProgrammingError:
                    # A concurrent test process may have created it after the check.
                    if (
                        connection.execute(
                            text("SELECT 1 FROM pg_database WHERE datname = :name"),
                            {"name": TEST_DATABASE_NAME},
                        ).scalar_one_or_none()
                        is None
                    ):
                        raise
    finally:
        engine.dispose()
