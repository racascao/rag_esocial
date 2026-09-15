from sqlalchemy import create_engine, text

from .config import get_settings


def get_engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def check_connection() -> bool:
    with get_engine().connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one() == 1
