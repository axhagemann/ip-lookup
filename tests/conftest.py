import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture(autouse=True)
def _clear_geo_cache():
    main._geo_cache.clear()
    yield
    main._geo_cache.clear()


@pytest.fixture
def client():
    return TestClient(main.app)
