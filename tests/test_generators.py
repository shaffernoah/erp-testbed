"""Tests for data generation correctness."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, Product, Customer, Supplier, Route
from generators.products import generate_products
from generators.suppliers import generate_suppliers
from generators.customers import generate_customers
from generators.routes import generate_routes


@pytest.fixture
def session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


class TestProductGenerator:
    def test_generates_products(self, session):
        products = generate_products(session)
        session.flush()
        assert len(products) >= 200  # Should be ~300

    def test_products_have_required_fields(self, session):
        products = generate_products(session)
        session.flush()
        for p in products[:10]:
            assert p.sku_id is not None
            assert p.name is not None
            assert p.category in ("BEEF", "PORK", "POULTRY", "LAMB_VEAL", "BLEND", "CHARCUTERIE")
            assert p.shelf_life_days > 0
            assert p.list_price_per_lb > 0
            assert p.cost_per_lb > 0
            assert p.list_price_per_lb > p.cost_per_lb  # Positive margin

    def test_unique_sku_ids(self, session):
        products = generate_products(session)
        session.flush()
        sku_ids = [p.sku_id for p in products]
        assert len(sku_ids) == len(set(sku_ids))


class TestSupplierGenerator:
    def test_generates_suppliers(self, session):
        suppliers = generate_suppliers(session)
        session.flush()
        assert len(suppliers) == 20

    def test_suppliers_have_required_fields(self, session):
        suppliers = generate_suppliers(session)
        session.flush()
        for s in suppliers:
            assert s.supplier_id is not None
            assert s.name is not None
            assert s.quality_rating >= 3.0
            assert s.haccp_compliant is True


class TestCustomerGenerator:
    def test_generates_customers(self, session):
        customers = generate_customers(session)
        session.flush()
        assert len(customers) == 1000

    def test_tier_distribution(self, session):
        customers = generate_customers(session)
        session.flush()
        tiers = [c.tier for c in customers]
        whales = tiers.count("WHALE")
        assert 10 <= whales <= 30  # ~2% of 1000

    def test_cari_enrollment(self, session):
        customers = generate_customers(session)
        session.flush()
        enrolled = sum(1 for c in customers if c.cari_enrolled)
        assert 200 <= enrolled <= 500  # ~30% of 1000


class TestRouteGenerator:
    def test_generates_routes(self, session):
        routes = generate_routes(session)
        session.flush()
        assert len(routes) >= 20

    def test_routes_have_zones(self, session):
        routes = generate_routes(session)
        session.flush()
        zones = {r.zone for r in routes}
        assert "MANHATTAN" in zones
        assert "BROOKLYN" in zones
