from __future__ import annotations

import os
import tempfile

import pytest

# Configure an isolated SQLite DB + artifact root before importing app modules.
_TMP = tempfile.mkdtemp(prefix="appforge-test-")
os.environ["APPFORGE_DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["APPFORGE_STORAGE_ROOT"] = f"{_TMP}/artifacts"
os.environ["APPFORGE_DISCOVERY_TOP_N_PER_NICHE"] = "6"
os.environ["APPFORGE_OPERATOR_TOKEN"] = ""

from appforge.db import SessionLocal, engine  # noqa: E402
from appforge.models import Base  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def session():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    finally:
        s.close()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from appforge.main import app

    with TestClient(app) as c:
        yield c
