"""Pytest configuration for Kage tests."""

import pytest


@pytest.fixture
def sample_config():
    """Provide a sample configuration for testing."""
    from kage.persistence.config import KageConfig

    return KageConfig()


@pytest.fixture
def sample_session():
    """Provide a sample session for testing."""
    from kage.core.models import Session

    return Session()
