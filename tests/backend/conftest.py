import os

import pytest

from app.database import DB_PATH, init_db
from app.routes.upload import jobs


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def fresh_db():
    """Reset the database and in-memory state before each test."""
    if DB_PATH.exists():
        os.remove(DB_PATH)
    jobs.clear()
    init_db()
    yield
    if DB_PATH.exists():
        os.remove(DB_PATH)
