"""SQLAlchemy ORM models for the LaFrieda ERP testbed database."""

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, Integer, String, Text,
    ForeignKey, func,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Product(Base):
    __tablename__ = "products"

    sku_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    short_description = Column(String)
    category = Column(String, nullable=False)       # BEEF, PORK, POULTRY, LAMB_VEAL, BLEND, CHARCUTERIE
    subcategory = Column(String)                     # STEAK, ROAST, GROUND, etc.
    usda_grade = Column(String)                      # PRIME, CHOICE, SELECT, WAGYU, N/A
    breed = Column(String)
    primal_cut = Column(String)

    # Catch weight
    is_catch_weight = Column(Boolean, default=True)
    base_uom = Column(String, nullable=False)        # LB, EACH, CASE
    catch_weight_uom = Column(String)
    nominal_weight = Column(Float)
    weight_tolerance_pct = Column(Float, default=0.10)
    case_pack_qty = Column(Integer)
    case_weight_lbs = Column(Float)

    # Pricing
    list_price_per_lb = Column(Float)
    cost_per_lb = Column(Float)
    target_margin_pct = Column(Float)

    # Attributes
    aging_type = Column(String)                      # DRY, WET, FRESH, N/A
    aging_days_min = Column(Integer)
    aging_days_max = Column(Integer)
    shelf_life_days = Column(Integer, nullable=False)
    storage_temp_min_f = Column(Float)
    storage_temp_max_f = Column(Float)
    requires_freezing = Column(Boolean, default=False)
    allergens = Column(Text)                         # JSON array

    # Business flags
    is_active = Column(Boolean, default=True)
    is_seasonal = Column(Boolean, default=False)
    seasonal_months = Column(Text)                   # JSON array
    min_order_qty = Column(Float)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())

    # Relationships
    lots = relationship("Lot", back_populates="product")
    invoice_line_items = relationship("InvoiceLineItem", back_populates="product")
    inventory_records = relationship("Inventory", back_populates="product")
    pricing_records = relationship("Pricing", back_populates="product")


class Customer(Base):
    __tablename__ = "customers"

    customer_id = Column(String, primary_key=True)
    business_name = Column(String, nullable=False)
    dba_name = Column(String)
    customer_type = Column(String, nullable=False)   # RESTAURANT, HOTEL, CATERING, RETAIL
    cuisine_type = Column(String)
    segment = Column(String)                         # FINE_DINING, CASUAL, FAST_CASUAL, QSR, HOTEL_FB

    # Tier
    tier = Column(String, default="STANDARD")        # WHALE, ENTERPRISE, STANDARD, SMALL
    annual_volume_estimate = Column(Float)
    account_status = Column(String, default="ACTIVE")

    # Location
    address_line1 = Column(String)
    address_line2 = Column(String)
    city = Column(String, nullable=False)
    state = Column(String, default="NY")
    zip_code = Column(String)
    borough = Column(String)
    delivery_zone = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)

    # Business details
    num_locations = Column(Integer, default=1)
    owner_name = Column(String)
    primary_contact_name = Column(String)
    primary_contact_email = Column(String)
    primary_contact_phone = Column(String)

    # Credit and payment
    credit_limit = Column(Float)
    credit_terms = Column(String, default="NET30")
    credit_terms_days = Column(Integer, default=30)
    credit_rating = Column(String)
    tax_exempt = Column(Boolean, default=False)
    tax_id = Column(String)

    # Cari-specific
    cari_enrolled = Column(Boolean, default=False)
    cari_enrollment_date = Column(Date)
    cari_reward_tier = Column(String)
    cari_points_balance = Column(Integer, default=0)

    # Engagement metrics
    first_order_date = Column(Date)
    last_order_date = Column(Date)
    total_lifetime_orders = Column(Integer, default=0)
    total_lifetime_revenue = Column(Float, default=0)
    avg_order_value = Column(Float)
    order_frequency_days = Column(Float)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())

    # Relationships
    invoices = relationship("Invoice", back_populates="customer")
    payments = relationship("Payment", back_populates="customer")
    ar_aging_records = relationship("ARaging", back_populates="customer")


class Supplier(Base):
    __tablename__ = "suppliers"

    supplier_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    supplier_type = Column(String)                   # RANCH, PACKER, IMPORTER, CO_OP

    city = Column(String)
    state = Column(String)
    country = Column(String, default="US")
    region = Column(String)

    primary_products = Column(Text)                  # JSON array
    certifications = Column(Text)                    # JSON array
    usda_grades_available = Column(Text)             # JSON array
    breeds_available = Column(Text)                  # JSON array

    quality_rating = Column(Float)
    delivery_reliability_pct = Column(Float)
    avg_lead_time_days = Column(Integer)
    min_order_lbs = Column(Float)

    payment_terms = Column(String, default="NET30")
    is_preferred = Column(Boolean, default=False)
    contract_end_date = Column(Date)

    lot_tracking_capable = Column(Boolean, default=True)
    haccp_compliant = Column(Boolean, default=True)
    last_audit_date = Column(Date)
    audit_score = Column(Float)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    lots = relationship("Lot", back_populates="supplier")
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")


class Lot(Base):
    __tablename__ = "lots"

    lot_id = Column(String, primary_key=True)
    lot_number = Column(String, unique=True, nullable=False)
    sku_id = Column(String, ForeignKey("products.sku_id"), nullable=False)
    supplier_id = Column(String, ForeignKey("suppliers.supplier_id"))

    production_date = Column(Date)
    received_date = Column(Date, nullable=False)
    expiration_date = Column(Date, nullable=False)
    sell_by_date = Column(Date)

    initial_quantity_lbs = Column(Float, nullable=False)
    current_quantity_lbs = Column(Float, nullable=False)
    units_received = Column(Integer)

    usda_grade = Column(String)
    grade_stamp_id = Column(String)
    country_of_origin = Column(String, default="US")
    farm_source = Column(String)

    storage_location = Column(String)
    storage_temp_f = Column(Float)

    aging_start_date = Column(Date)
    aging_target_days = Column(Integer)
    aging_actual_days = Column(Integer)

    status = Column(String, default="AVAILABLE")     # AVAILABLE, RESERVED, DEPLETED, EXPIRED, HOLD
    hold_reason = Column(String)

    inspection_status = Column(String, default="PASSED")
    inspection_date = Column(Date)
    inspection_notes = Column(String)

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    product = relationship("Product", back_populates="lots")
    supplier = relationship("Supplier", back_populates="lots")
    inventory_records = relationship("Inventory", back_populates="lot")
    line_items = relationship("InvoiceLineItem", back_populates="lot")


class Inventory(Base):
    __tablename__ = "inventory"

    inventory_id = Column(String, primary_key=True)
    sku_id = Column(String, ForeignKey("products.sku_id"), nullable=False)
    lot_id = Column(String, ForeignKey("lots.lot_id"))

    location = Column(String, nullable=False)
    zone = Column(String)
    bin_location = Column(String)

    quantity_on_hand = Column(Float, nullable=False)
    weight_on_hand_lbs = Column(Float)
    quantity_reserved = Column(Float, default=0)
    quantity_available = Column(Float)

    unit_cost = Column(Float)
    total_value = Column(Float)

    days_in_inventory = Column(Integer)
    days_until_expiry = Column(Integer)
    freshness_score = Column(Float)

    last_count_date = Column(Date)
    last_movement_date = Column(Date)
    snapshot_date = Column(Date, nullable=False)

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    product = relationship("Product", back_populates="inventory_records")
    lot = relationship("Lot", back_populates="inventory_records")


class Invoice(Base):
    __tablename__ = "invoices"

    invoice_id = Column(String, primary_key=True)
    invoice_number = Column(String, unique=True, nullable=False)
    customer_id = Column(String, ForeignKey("customers.customer_id"), nullable=False)

    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    ship_date = Column(Date)
    delivery_date = Column(Date)

    status = Column(String, default="OPEN")          # DRAFT, OPEN, PARTIAL, PAID, OVERDUE, DISPUTED, VOID

    subtotal = Column(Float, nullable=False)
    tax_amount = Column(Float, default=0)
    freight_amount = Column(Float, default=0)
    total_amount = Column(Float, nullable=False)
    amount_paid = Column(Float, default=0)
    balance_due = Column(Float)

    payment_terms = Column(String)
    payment_terms_days = Column(Integer)

    route_id = Column(String, ForeignKey("routes.route_id"))
    delivery_address = Column(String)
    po_number = Column(String)

    # Cari integration
    cari_eligible = Column(Boolean, default=False)
    cari_cashback_pct = Column(Float)
    cari_points_earned = Column(Integer, default=0)
    cari_payment_window = Column(String)
    cari_payment_method = Column(String)

    notes = Column(Text)
    dispute_reason = Column(String)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now())

    # Relationships
    customer = relationship("Customer", back_populates="invoices")
    route = relationship("Route", back_populates="invoices")
    line_items = relationship("InvoiceLineItem", back_populates="invoice")
    payments = relationship("Payment", back_populates="invoice")


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    line_item_id = Column(String, primary_key=True)
    invoice_id = Column(String, ForeignKey("invoices.invoice_id"), nullable=False)
    line_number = Column(Integer, nullable=False)

    sku_id = Column(String, ForeignKey("products.sku_id"), nullable=False)
    description = Column(String)

    quantity = Column(Float, nullable=False)
    uom = Column(String)
    catch_weight_lbs = Column(Float)
    price_per_unit = Column(Float)

    line_subtotal = Column(Float, nullable=False)
    line_tax = Column(Float, default=0)
    discount_pct = Column(Float, default=0)
    discount_amount = Column(Float, default=0)
    line_total = Column(Float, nullable=False)

    lot_id = Column(String, ForeignKey("lots.lot_id"))

    cari_cashback_pct = Column(Float)
    cari_points = Column(Float, default=0)

    category = Column(String)
    gl_code = Column(String)

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    invoice = relationship("Invoice", back_populates="line_items")
    product = relationship("Product", back_populates="invoice_line_items")
    lot = relationship("Lot", back_populates="line_items")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    po_id = Column(String, primary_key=True)
    po_number = Column(String, unique=True, nullable=False)
    supplier_id = Column(String, ForeignKey("suppliers.supplier_id"), nullable=False)

    status = Column(String, default="DRAFT")
    order_date = Column(Date, nullable=False)
    expected_delivery_date = Column(Date)
    actual_delivery_date = Column(Date)

    subtotal = Column(Float)
    freight = Column(Float, default=0)
    total_amount = Column(Float)

    receiving_location = Column(String)
    notes = Column(Text)

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    supplier = relationship("Supplier", back_populates="purchase_orders")
    line_items = relationship("POLineItem", back_populates="purchase_order")


class POLineItem(Base):
    __tablename__ = "po_line_items"

    po_line_id = Column(String, primary_key=True)
    po_id = Column(String, ForeignKey("purchase_orders.po_id"), nullable=False)
    line_number = Column(Integer)

    sku_id = Column(String, ForeignKey("products.sku_id"), nullable=False)
    quantity_ordered = Column(Float, nullable=False)
    quantity_received = Column(Float, default=0)
    uom = Column(String)
    catch_weight_ordered_lbs = Column(Float)
    catch_weight_received_lbs = Column(Float)
    cost_per_lb = Column(Float)
    line_total = Column(Float)

    lot_id = Column(String)

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    purchase_order = relationship("PurchaseOrder", back_populates="line_items")


class Payment(Base):
    __tablename__ = "payments"

    payment_id = Column(String, primary_key=True)
    invoice_id = Column(String, ForeignKey("invoices.invoice_id"), nullable=False)
    customer_id = Column(String, ForeignKey("customers.customer_id"), nullable=False)

    payment_date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    payment_method = Column(String)

    is_cari_payment = Column(Boolean, default=False)
    cari_payment_window = Column(String)
    cari_reward_pct = Column(Float)
    cari_points_earned = Column(Integer, default=0)
    cari_fee_pct = Column(Float)
    days_to_payment = Column(Integer)

    settlement_date = Column(Date)
    settlement_amount = Column(Float)

    reference_number = Column(String)
    notes = Column(String)

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    invoice = relationship("Invoice", back_populates="payments")
    customer = relationship("Customer", back_populates="payments")


class Route(Base):
    __tablename__ = "routes"

    route_id = Column(String, primary_key=True)
    route_name = Column(String, nullable=False)

    zone = Column(String)
    subzone = Column(String)

    delivery_days = Column(Text)                     # JSON array
    departure_time = Column(String)
    estimated_stops = Column(Integer)
    estimated_duration_hours = Column(Float)

    driver_name = Column(String)
    truck_id = Column(String)
    truck_type = Column(String)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    invoices = relationship("Invoice", back_populates="route")


class Pricing(Base):
    __tablename__ = "pricing"

    pricing_id = Column(String, primary_key=True)
    sku_id = Column(String, ForeignKey("products.sku_id"), nullable=False)
    customer_id = Column(String, ForeignKey("customers.customer_id"))

    price_type = Column(String, nullable=False)      # LIST, CONTRACT, VOLUME, PROMOTIONAL
    price_per_lb = Column(Float, nullable=False)

    effective_date = Column(Date, nullable=False)
    expiration_date = Column(Date)

    min_quantity_lbs = Column(Float)
    max_quantity_lbs = Column(Float)

    market_basis = Column(String)
    basis_adjustment = Column(Float)

    notes = Column(String)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    product = relationship("Product", back_populates="pricing_records")


class QualityRecord(Base):
    __tablename__ = "quality_records"

    record_id = Column(String, primary_key=True)
    record_type = Column(String, nullable=False)     # HACCP_CHECK, TEMP_LOG, GRADE_VERIFY, COMPLAINT

    lot_id = Column(String, ForeignKey("lots.lot_id"))
    sku_id = Column(String, ForeignKey("products.sku_id"))
    location = Column(String)

    check_datetime = Column(DateTime, nullable=False)
    checked_by = Column(String)

    temperature_f = Column(Float)
    temp_in_range = Column(Boolean)

    usda_grade_verified = Column(String)
    grade_matches_expected = Column(Boolean)

    haccp_point = Column(String)
    critical_limit = Column(String)
    actual_value = Column(String)
    corrective_action = Column(String)

    status = Column(String, default="PASS")
    notes = Column(Text)

    created_at = Column(DateTime, server_default=func.now())


class Campaign(Base):
    __tablename__ = "campaigns"

    campaign_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    campaign_type = Column(String, nullable=False)

    # Cari Reward API fields
    condition_type = Column(String)                  # ANY, INVOICE_TOTAL_OVER, DAYS_BEFORE, etc.
    condition_value = Column(Text)                   # JSON
    reward_type = Column(String)                     # FIXED, PERCENTAGE, PERCENTAGE_OF_ITEMS
    reward_value = Column(Text)                      # JSON

    participant_type = Column(String, default="ALL_CUSTOMERS")
    eligible_customers = Column(Text)                # JSON array
    eligible_skus = Column(Text)                     # JSON array

    tiered = Column(Boolean, default=False)
    tiers = Column(Text)                             # JSON
    stackable = Column(Boolean, default=True)
    validity_days = Column(Integer)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date)

    budget_total = Column(Float)
    budget_spent = Column(Float, default=0)
    budget_remaining = Column(Float)

    status = Column(String, default="ACTIVE")

    created_at = Column(DateTime, server_default=func.now())


class ARaging(Base):
    __tablename__ = "ar_aging"

    snapshot_id = Column(String, primary_key=True)
    snapshot_date = Column(Date, nullable=False)
    customer_id = Column(String, ForeignKey("customers.customer_id"), nullable=False)

    current_amount = Column(Float, default=0)
    days_31_60 = Column(Float, default=0)
    days_61_90 = Column(Float, default=0)
    days_over_90 = Column(Float, default=0)
    total_outstanding = Column(Float, default=0)

    weighted_avg_days = Column(Float)

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    customer = relationship("Customer", back_populates="ar_aging_records")


class MarginSummary(Base):
    __tablename__ = "margin_summary"

    summary_id = Column(String, primary_key=True)
    period_date = Column(Date, nullable=False)

    customer_id = Column(String, ForeignKey("customers.customer_id"))
    category = Column(String)
    sku_id = Column(String, ForeignKey("products.sku_id"))

    revenue = Column(Float, nullable=False)
    cogs = Column(Float, nullable=False)
    gross_margin = Column(Float)
    gross_margin_pct = Column(Float)

    volume_lbs = Column(Float)
    num_invoices = Column(Integer)
    avg_price_per_lb = Column(Float)
    avg_cost_per_lb = Column(Float)

    created_at = Column(DateTime, server_default=func.now())
