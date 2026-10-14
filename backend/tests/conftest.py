import os
import tempfile
from pathlib import Path

import pytest

# Point the app at a throwaway database before anything imports app.db.
_TMP = Path(tempfile.mkdtemp(prefix="forecast-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["OLLAMA_URL"] = "http://127.0.0.1:9"  # nothing listens here: LLM is "offline" in tests


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:  # runs startup: create tables + seed demo data
        yield c
