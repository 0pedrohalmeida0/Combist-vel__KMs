"""Fixtures compartilhadas pelos testes."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
