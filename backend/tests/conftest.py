import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="logmind_test_")
os.environ.update(DATABASE_URL=f"sqlite:///{_tmp}/test.db", UPLOAD_DIR=f"{_tmp}/uploads", CACHE_DIR=f"{_tmp}/cache", DATASET_DIR=f"{_tmp}/datasets",
                  EMBEDDINGS_ENABLED="false", RATE_LIMIT_PER_MINUTE="0", LLM_PROVIDER="", LLM_API_KEY="")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def sample_dir():
    return SAMPLE
