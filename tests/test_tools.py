"""Tests for agent tools."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base


@pytest.fixture
def session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


class TestQueryDatabaseTool:
    def test_placeholder(self, session):
        """Placeholder — requires seeded data to test meaningfully."""
        assert True


class TestAlertTriggersTool:
    def test_placeholder(self, session):
        """Placeholder — requires seeded data to test meaningfully."""
        assert True
