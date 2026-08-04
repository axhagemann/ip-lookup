import pytest
from fastapi.testclient import TestClient

import geo
import main


@pytest.fixture(autouse=True)
def _clear_geo_cache():
    geo._geo_cache.clear()
    yield
    geo._geo_cache.clear()


@pytest.fixture
def client():
    return TestClient(main.app)
