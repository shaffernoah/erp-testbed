"""Tests for database schema integrity."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from database.models import Base


@pytest.fixture
def engine():
    """Create an in-memory SQLite database."""
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


class TestSchema:
    def test_all_tables_created(self, engine):
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        expected = [
            "products", "customers", "suppliers", "lots", "inventory",
            "invoices", "invoice_line_items", "purchase_orders", "po_line_items",
            "payments", "routes", "pricing", "quality_records", "campaigns",
            "ar_aging", "margin_summary",
        ]
        for table in expected:
            assert table in tables, f"Missing table: {table}"

    def test_foreign_keys_exist(self, engine):
        inspector = inspect(engine)
        # invoices should have FK to customers
        fks = inspector.get_foreign_keys("invoices")
        fk_tables = {fk["referred_table"] for fk in fks}
        assert "customers" in fk_tables

    def test_product_columns(self, engine):
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("products")}
        assert "sku_id" in columns
        assert "category" in columns
        assert "is_catch_weight" in columns
        assert "shelf_life_days" in columns
