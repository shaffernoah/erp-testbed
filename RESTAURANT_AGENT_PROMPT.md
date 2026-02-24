# Restaurant ERP Intelligence Agent — Comprehensive Build Prompt

> **Purpose**: Give this prompt to an LLM coding agent to build a self-contained Python testbed for evaluating AI agent capabilities against realistic restaurant ERP data, modeled on Restaurant365 (R365) data structures.

---

## 1. PROJECT OVERVIEW

Build a Python application that simulates a multi-unit restaurant operation sitting on top of Restaurant365-style ERP data. The system should:

1. **Generate ~1M rows of synthetic restaurant ERP data** across 15+ tables covering sales, inventory, purchasing, labor, recipes, menu items, GL accounts, vendors, and more.
2. **Provide 3 AI agent personas** (Restaurant Operations Manager, Restaurant Financial Controller, Restaurant Group Buyer/Purchaser) with deep domain expertise encoded in system prompts.
3. **Expose 10+ callable tools** the agents can invoke to query data, analyze operations, generate recommendations, and execute micro-actions.
4. **Serve a Flask web UI** (port 5001) for interactive chat with streaming agent responses and a KPI dashboard.
5. **Support both Anthropic and OpenAI** as LLM providers via a unified client.

The system embodies a **"micro-actions" philosophy**: every interaction should identify specific, quantified operational or financial opportunities and recommend concrete actions with dollar impact.

---

## 2. ARCHITECTURE

```
restaurant-erp-agent/
├── app.py                          # Flask web app entry point (port 5001)
├── requirements.txt                # Dependencies
├── .env.example                    # API key template
│
├── config/
│   ├── settings.py                 # Global constants, DB path, LLM config, data generation scale
│   └── restaurant_profile.py       # Business domain constants (menu items, categories, pricing)
│
├── database/
│   ├── models.py                   # SQLAlchemy ORM models (15+ tables)
│   ├── connection.py               # Session management, SQLite connection
│   └── seed.py                     # Data generation orchestration
│
├── generators/                     # Synthetic data generation modules
│   ├── base.py                     # Base generator with seeded random
│   ├── locations.py                # Restaurant locations
│   ├── gl_accounts.py              # Chart of accounts
│   ├── vendors.py                  # Supplier/vendor records
│   ├── purchased_items.py          # Raw ingredient items
│   ├── recipes.py                  # Recipe items with sub-recipes
│   ├── menu_items.py               # POS menu items mapped to recipes
│   ├── sales.py                    # Daily sales summaries + line items
│   ├── labor.py                    # Labor details (hours, wages, tips)
│   ├── inventory.py                # Inventory counts and on-hand
│   ├── purchasing.py               # AP invoices, POs, credit memos
│   ├── payments.py                 # Payment records
│   └── gl_transactions.py          # Journal entries, GL transactions
│
├── agents/
│   ├── agent_runner.py             # Core ReAct agentic loop (tool calling, streaming)
│   ├── tool_registry.py            # Tool registration and dispatch
│   │
│   ├── prompts/
│   │   ├── ops_manager_agent.py    # Operations manager persona
│   │   ├── financial_controller_agent.py  # Financial controller persona
│   │   └── group_buyer_agent.py    # Purchasing/buyer persona
│   │
│   └── tools/
│       ├── query_database.py       # SQL SELECT against ERP (read-only)
│       ├── alert_triggers.py       # Expiry, waste, labor, sales anomalies
│       ├── food_cost_analyzer.py   # Actual vs theoretical food cost
│       ├── menu_engineering.py     # Menu mix analysis (stars/puzzles/plowhorses/dogs)
│       ├── inventory_variance.py   # Count variance, waste tracking, shrinkage
│       ├── labor_optimizer.py      # Labor cost %, scheduling efficiency
│       ├── vendor_scorecard.py     # Vendor performance analysis
│       ├── purchase_optimizer.py   # Order optimization, par level management
│       ├── sales_forecaster.py     # Demand forecasting by daypart/day-of-week
│       ├── prime_cost_tracker.py   # Prime cost (food + labor) analysis
│       └── cash_flow_analyzer.py   # AP aging, cash position, payment timing
│
├── analysis/                       # LLM-powered analyzers
│   ├── llm_client.py              # Multi-provider client (Anthropic/OpenAI)
│   ├── context_builder.py         # Build domain context from database
│   ├── prompt_builder.py          # Build LLM prompts with JSON schemas
│   └── analyzers/
│       ├── sales_trend.py         # Sales trend analysis and forecasting
│       ├── menu_profitability.py  # Menu item margin analysis
│       ├── labor_efficiency.py    # Labor productivity metrics
│       ├── vendor_analysis.py     # Vendor price comparison
│       ├── waste_prediction.py    # Waste/spoilage prediction
│       └── budget_variance.py     # Budget vs actual analysis
│
├── scenarios/                      # Predefined test scenarios
│   ├── ops_scenarios.py
│   ├── finance_scenarios.py
│   └── purchasing_scenarios.py
│
├── tests/
│   ├── test_generators.py
│   ├── test_schema.py
│   └── test_tools.py
│
└── static/
    ├── app.js                      # Frontend chat UI
    └── dashboard.js                # KPI dashboard
```

---

## 3. DATA MODEL — Based on Restaurant365 Schema

### Design Philosophy

The data model mirrors Restaurant365's entity structure. R365 uses these core concepts:
- **Company** → Legal entity (the restaurant group)
- **Location** → Individual restaurant, commissary, or accounting entity
- **Daily Sales Summary (DSS)** → POS-imported daily sales rolled into journal entries
- **Three Item Types**: Purchased Items (raw ingredients), Recipe Items (formulas), Sales/Menu Items (POS items)
- **GL Accounts** grouped by GL Types for P&L and Balance Sheet reporting
- **Vendors** → Suppliers with AP Invoices, Credit Memos, Purchase Orders

### SQLAlchemy Models (database/models.py)

Implement these tables:

```python
# ── ORGANIZATIONAL ──

class Company(Base):
    """Legal entity / restaurant group"""
    __tablename__ = 'companies'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)          # e.g., "Urban Plate Restaurant Group"
    entity_type = Column(String)                    # LLC, Corp, etc.
    tax_id = Column(String)
    created_at = Column(DateTime)

class Location(Base):
    """Individual restaurant location"""
    __tablename__ = 'locations'
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('companies.id'))
    name = Column(String, nullable=False)           # "Downtown Flagship"
    location_number = Column(String, unique=True)   # "LOC-001"
    location_type = Column(String)                  # RESTAURANT, COMMISSARY, ACCOUNTING_ENTITY
    concept = Column(String)                        # FINE_DINING, CASUAL, FAST_CASUAL, QSR, BAR_GRILL
    cuisine_type = Column(String)                   # AMERICAN, ITALIAN, MEXICAN, ASIAN, SEAFOOD, STEAKHOUSE
    square_footage = Column(Integer)
    seat_count = Column(Integer)
    date_established = Column(Date)
    manager_name = Column(String)
    address = Column(String)
    city = Column(String)
    state = Column(String)
    zip_code = Column(String)
    sales_tax_rate = Column(Float)                  # e.g., 0.0875
    is_active = Column(Boolean, default=True)
    # Relationships
    daily_sales = relationship("DailySalesSummary", back_populates="location")
    inventory_counts = relationship("InventoryCount", back_populates="location")
    labor_details = relationship("LaborDetail", back_populates="location")

# ── CHART OF ACCOUNTS ──

class GLType(Base):
    """GL Type groupings for financial reporting"""
    __tablename__ = 'gl_types'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)           # "Revenue", "COGS", "Labor", "Occupancy", etc.
    category = Column(String)                       # REVENUE, EXPENSE, ASSET, LIABILITY, EQUITY
    display_order = Column(Integer)

class GLAccount(Base):
    """Chart of accounts"""
    __tablename__ = 'gl_accounts'
    id = Column(Integer, primary_key=True)
    account_number = Column(String, unique=True)    # "4000", "5100", "6200"
    account_name = Column(String, nullable=False)   # "Food Sales", "Food Cost - Meat", "Hourly Labor"
    gl_type_id = Column(Integer, ForeignKey('gl_types.id'))
    description = Column(String)
    default_budget_amount = Column(Float)
    is_active = Column(Boolean, default=True)

# ── ITEMS & RECIPES ──

class ItemCategory(Base):
    """3-level hierarchical item categorization (R365 style)"""
    __tablename__ = 'item_categories'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)           # "Meat", "Beef", "Ground Beef"
    level = Column(Integer)                         # 1, 2, or 3
    parent_id = Column(Integer, ForeignKey('item_categories.id'))

class PurchasedItem(Base):
    """Raw ingredients bought from vendors"""
    __tablename__ = 'purchased_items'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)  # "Ground Beef 80/20 10lb"
    item_number = Column(String)
    description = Column(String)
    category_id = Column(Integer, ForeignKey('item_categories.id'))
    measure_type = Column(String)                   # WEIGHT, VOLUME, EACH
    reporting_uom = Column(String)                  # lb, oz, gal, each, case
    inventory_uom = Column(String)
    pack_size = Column(String)                      # "4x5lb", "1x10lb", "50lb case"
    par_level = Column(Float)                       # Minimum stock level
    cost_update_method = Column(String)             # WEIGHTED_AVG_LAST_COUNT, LAST_INVOICE, MANUAL
    current_cost = Column(Float)                    # Current unit cost
    cost_account_id = Column(Integer, ForeignKey('gl_accounts.id'))     # COGS GL account
    inventory_account_id = Column(Integer, ForeignKey('gl_accounts.id'))
    waste_account_id = Column(Integer, ForeignKey('gl_accounts.id'))
    shelf_life_days = Column(Integer)
    storage_temp = Column(String)                   # REFRIGERATED, FROZEN, DRY, AMBIENT
    is_active = Column(Boolean, default=True)
    # Relationships
    vendor_items = relationship("VendorItem", back_populates="purchased_item")
    recipe_ingredients = relationship("RecipeIngredient", back_populates="purchased_item")

class RecipeItem(Base):
    """Recipes / sub-recipes / prep items"""
    __tablename__ = 'recipe_items'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)           # "House Burger Patty", "Marinara Sauce"
    recipe_number = Column(String)
    recipe_type = Column(String)                    # RECIPE, SUB_RECIPE, PREP, BATCH
    yield_qty = Column(Float)                       # Batch yield quantity
    yield_uom = Column(String)                      # Batch yield unit
    portion_size = Column(Float)                    # Single portion size
    portion_uom = Column(String)
    portion_cost = Column(Float)                    # Calculated cost per portion
    batch_cost = Column(Float)                      # Total batch cost
    prep_time_minutes = Column(Integer)
    shelf_life_hours = Column(Integer)              # Prep item shelf life
    instructions = Column(Text)
    is_active = Column(Boolean, default=True)
    # Relationships
    ingredients = relationship("RecipeIngredient", back_populates="recipe")

class RecipeIngredient(Base):
    """Line items in a recipe"""
    __tablename__ = 'recipe_ingredients'
    id = Column(Integer, primary_key=True)
    recipe_id = Column(Integer, ForeignKey('recipe_items.id'))
    purchased_item_id = Column(Integer, ForeignKey('purchased_items.id'), nullable=True)
    sub_recipe_id = Column(Integer, ForeignKey('recipe_items.id'), nullable=True)
    quantity = Column(Float, nullable=False)
    uom = Column(String, nullable=False)
    waste_percent = Column(Float, default=0.0)      # Trim/prep waste %
    cost_per_unit = Column(Float)
    extended_cost = Column(Float)                   # quantity * cost_per_unit * (1 + waste_percent)
    # Relationships
    recipe = relationship("RecipeItem", foreign_keys=[recipe_id], back_populates="ingredients")
    purchased_item = relationship("PurchasedItem", back_populates="recipe_ingredients")

class MenuItem(Base):
    """POS menu items mapped to recipes"""
    __tablename__ = 'menu_items'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)           # "Classic Burger", "Ribeye 12oz"
    pos_item_id = Column(String)                    # POS system ID
    menu_category = Column(String)                  # APPETIZER, ENTREE, DESSERT, BEVERAGE, SIDE
    menu_section = Column(String)                   # "Burgers", "Steaks", "Pasta", "Salads"
    selling_price = Column(Float, nullable=False)
    recipe_id = Column(Integer, ForeignKey('recipe_items.id'))
    food_cost_target = Column(Float)                # Target food cost % (e.g., 0.30)
    actual_food_cost_pct = Column(Float)            # Calculated actual food cost %
    is_active = Column(Boolean, default=True)
    is_modifiable = Column(Boolean, default=True)
    # Relationships
    recipe = relationship("RecipeItem")
    sales_details = relationship("SalesDetail", back_populates="menu_item")

# ── VENDORS & PURCHASING ──

class Vendor(Base):
    """Suppliers / purveyors"""
    __tablename__ = 'vendors'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    vendor_number = Column(String, unique=True)
    category = Column(String)                       # PROTEIN, PRODUCE, DAIRY, DRY_GOODS, BEVERAGE, SMALLWARES, SERVICES
    contact_name = Column(String)
    contact_email = Column(String)
    contact_phone = Column(String)
    payment_terms = Column(String)                  # NET15, NET30, NET45, COD
    lead_time_days = Column(Integer)
    minimum_order = Column(Float)
    delivery_days = Column(String)                  # JSON: ["MON","WED","FRI"]
    quality_rating = Column(Float)                  # 1-5 scale
    on_time_pct = Column(Float)                     # Delivery reliability
    fill_rate_pct = Column(Float)                   # Order fill rate
    is_active = Column(Boolean, default=True)

class VendorItem(Base):
    """Vendor-specific item records (same item, different vendor pricing)"""
    __tablename__ = 'vendor_items'
    id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer, ForeignKey('vendors.id'))
    purchased_item_id = Column(Integer, ForeignKey('purchased_items.id'))
    vendor_item_number = Column(String)             # Vendor's SKU
    vendor_item_name = Column(String)               # Vendor's name for item
    unit_cost = Column(Float, nullable=False)
    uom = Column(String)
    pack_size = Column(String)
    is_preferred = Column(Boolean, default=False)   # Primary supplier flag
    last_order_date = Column(Date)
    # Relationships
    vendor = relationship("Vendor")
    purchased_item = relationship("PurchasedItem", back_populates="vendor_items")

class PurchaseOrder(Base):
    """Purchase orders to vendors"""
    __tablename__ = 'purchase_orders'
    id = Column(Integer, primary_key=True)
    po_number = Column(String, unique=True)
    vendor_id = Column(Integer, ForeignKey('vendors.id'))
    location_id = Column(Integer, ForeignKey('locations.id'))
    order_date = Column(Date, nullable=False)
    expected_delivery_date = Column(Date)
    actual_delivery_date = Column(Date)
    status = Column(String)                         # DRAFT, SUBMITTED, RECEIVED, PARTIAL, CLOSED, CANCELLED
    total_amount = Column(Float)
    notes = Column(Text)
    # Relationships
    line_items = relationship("PurchaseOrderLineItem", back_populates="purchase_order")
    vendor = relationship("Vendor")

class PurchaseOrderLineItem(Base):
    __tablename__ = 'po_line_items'
    id = Column(Integer, primary_key=True)
    purchase_order_id = Column(Integer, ForeignKey('purchase_orders.id'))
    purchased_item_id = Column(Integer, ForeignKey('purchased_items.id'))
    quantity_ordered = Column(Float, nullable=False)
    quantity_received = Column(Float)
    unit_cost = Column(Float, nullable=False)
    extended_cost = Column(Float)
    uom = Column(String)
    # Relationships
    purchase_order = relationship("PurchaseOrder", back_populates="line_items")

class APInvoice(Base):
    """Accounts payable invoices from vendors — mirrors R365 APInvoices endpoint"""
    __tablename__ = 'ap_invoices'
    id = Column(Integer, primary_key=True)
    invoice_number = Column(String)
    vendor_id = Column(Integer, ForeignKey('vendors.id'))
    location_id = Column(Integer, ForeignKey('locations.id'))
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date)
    gl_date = Column(Date)
    invoice_type = Column(String)                   # AP_INVOICE, AP_CREDIT_MEMO
    total_amount = Column(Float, nullable=False)
    status = Column(String)                         # OPEN, APPROVED, PAID, VOIDED, DISPUTED
    payment_date = Column(Date)
    payment_method = Column(String)                 # CHECK, ACH, CREDIT_CARD, WIRE
    po_id = Column(Integer, ForeignKey('purchase_orders.id'), nullable=True)
    notes = Column(Text)
    # Relationships
    line_items = relationship("APInvoiceLineItem", back_populates="invoice")
    vendor = relationship("Vendor")

class APInvoiceLineItem(Base):
    """Invoice line items — mirrors R365 APInvoices product-level fields"""
    __tablename__ = 'ap_invoice_line_items'
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey('ap_invoices.id'))
    purchased_item_id = Column(Integer, ForeignKey('purchased_items.id'))
    gl_account_id = Column(Integer, ForeignKey('gl_accounts.id'))
    quantity = Column(Float, nullable=False)
    unit_cost = Column(Float, nullable=False)
    extended_cost = Column(Float, nullable=False)
    uom = Column(String)
    description = Column(String)
    # Relationships
    invoice = relationship("APInvoice", back_populates="line_items")

# ── SALES (POS-Sourced, mirrors R365 DSS pipeline) ──

class DailySalesSummary(Base):
    """Daily sales summary — R365's core POS import entity"""
    __tablename__ = 'daily_sales_summaries'
    id = Column(Integer, primary_key=True)
    location_id = Column(Integer, ForeignKey('locations.id'))
    business_date = Column(Date, nullable=False)
    gross_sales = Column(Float)
    discounts = Column(Float)
    comps = Column(Float)
    net_sales = Column(Float)
    tax_collected = Column(Float)
    tips = Column(Float)
    guest_count = Column(Integer)
    transaction_count = Column(Integer)
    average_check = Column(Float)
    # Daypart breakdowns
    lunch_sales = Column(Float)
    dinner_sales = Column(Float)
    bar_sales = Column(Float)
    takeout_sales = Column(Float)
    delivery_sales = Column(Float)
    catering_sales = Column(Float)
    # Relationships
    location = relationship("Location", back_populates="daily_sales")
    sales_details = relationship("SalesDetail", back_populates="daily_summary")

class SalesDetail(Base):
    """Sales line item detail — mirrors R365 SalesDetail OData entity"""
    __tablename__ = 'sales_details'
    id = Column(Integer, primary_key=True)
    daily_summary_id = Column(Integer, ForeignKey('daily_sales_summaries.id'))
    location_id = Column(Integer, ForeignKey('locations.id'))
    business_date = Column(Date, nullable=False)
    menu_item_id = Column(Integer, ForeignKey('menu_items.id'))
    quantity_sold = Column(Integer, nullable=False)
    gross_amount = Column(Float)
    discount_amount = Column(Float)
    net_amount = Column(Float)
    daypart = Column(String)                        # LUNCH, DINNER, LATE_NIGHT, BRUNCH, BREAKFAST
    order_type = Column(String)                     # DINE_IN, TAKEOUT, DELIVERY, CATERING, BAR
    # Relationships
    daily_summary = relationship("DailySalesSummary", back_populates="sales_details")
    menu_item = relationship("MenuItem", back_populates="sales_details")

class SalesPayment(Base):
    """Payment method breakdown — mirrors R365 SalesPayment OData entity"""
    __tablename__ = 'sales_payments'
    id = Column(Integer, primary_key=True)
    daily_summary_id = Column(Integer, ForeignKey('daily_sales_summaries.id'))
    location_id = Column(Integer, ForeignKey('locations.id'))
    business_date = Column(Date, nullable=False)
    payment_type = Column(String)                   # CASH, CREDIT_CARD, DEBIT, GIFT_CARD, COMP, THIRD_PARTY
    amount = Column(Float, nullable=False)
    transaction_count = Column(Integer)
    tip_amount = Column(Float)

# ── LABOR (mirrors R365 LaborDetail OData entity) ──

class Employee(Base):
    """Employee master records"""
    __tablename__ = 'employees'
    id = Column(Integer, primary_key=True)
    employee_number = Column(String, unique=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    location_id = Column(Integer, ForeignKey('locations.id'))
    job_title_id = Column(Integer, ForeignKey('job_titles.id'))
    hire_date = Column(Date)
    hourly_rate = Column(Float)
    salary = Column(Float)                          # For salaried employees
    employment_type = Column(String)                # FULL_TIME, PART_TIME, SEASONAL
    is_active = Column(Boolean, default=True)

class JobTitle(Base):
    """Job title reference data"""
    __tablename__ = 'job_titles'
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)          # "Line Cook", "Server", "Bartender", "GM"
    department = Column(String)                     # BOH, FOH, MANAGEMENT
    is_tipped = Column(Boolean, default=False)
    default_hourly_rate = Column(Float)

class LaborDetail(Base):
    """Labor detail records — mirrors R365 LaborDetail OData entity"""
    __tablename__ = 'labor_details'
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey('employees.id'))
    location_id = Column(Integer, ForeignKey('locations.id'))
    job_title_id = Column(Integer, ForeignKey('job_titles.id'))
    business_date = Column(Date, nullable=False)
    clock_in = Column(DateTime)
    clock_out = Column(DateTime)
    regular_hours = Column(Float)
    overtime_hours = Column(Float)
    break_hours = Column(Float)
    hourly_rate = Column(Float)
    regular_pay = Column(Float)
    overtime_pay = Column(Float)
    total_pay = Column(Float)
    tips = Column(Float)
    declared_tips = Column(Float)

# ── INVENTORY ──

class InventoryCount(Base):
    """Periodic inventory counts"""
    __tablename__ = 'inventory_counts'
    id = Column(Integer, primary_key=True)
    location_id = Column(Integer, ForeignKey('locations.id'))
    purchased_item_id = Column(Integer, ForeignKey('purchased_items.id'))
    count_date = Column(Date, nullable=False)
    on_hand_qty = Column(Float, nullable=False)
    on_hand_uom = Column(String)
    unit_cost = Column(Float)
    extended_cost = Column(Float)                   # on_hand_qty * unit_cost
    counted_by = Column(String)
    count_type = Column(String)                     # FULL, SPOT, CYCLE
    variance_qty = Column(Float)                    # Actual - Expected
    variance_cost = Column(Float)
    # Relationships
    location = relationship("Location", back_populates="inventory_counts")

# ── GL TRANSACTIONS (mirrors R365 Transaction / TransactionDetail OData entities) ──

class Transaction(Base):
    """GL transactions — journal entries, AP entries, sales entries"""
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True)
    transaction_number = Column(String)
    transaction_type = Column(String)               # SALES_JE, LABOR_JE, STATISTICAL_JE, AP_INVOICE, AP_CREDIT, MANUAL_JE
    location_id = Column(Integer, ForeignKey('locations.id'))
    transaction_date = Column(Date, nullable=False)
    gl_date = Column(Date)
    reference = Column(String)                      # Invoice number, DSS date, etc.
    memo = Column(String)
    total_debit = Column(Float)
    total_credit = Column(Float)
    status = Column(String)                         # POSTED, DRAFT, VOIDED
    created_at = Column(DateTime)
    # Relationships
    details = relationship("TransactionDetail", back_populates="transaction")

class TransactionDetail(Base):
    """Transaction line items"""
    __tablename__ = 'transaction_details'
    id = Column(Integer, primary_key=True)
    transaction_id = Column(Integer, ForeignKey('transactions.id'))
    gl_account_id = Column(Integer, ForeignKey('gl_accounts.id'))
    location_id = Column(Integer, ForeignKey('locations.id'))
    debit_amount = Column(Float, default=0.0)
    credit_amount = Column(Float, default=0.0)
    memo = Column(String)
    item_id = Column(Integer, ForeignKey('purchased_items.id'), nullable=True)
    # Relationships
    transaction = relationship("Transaction", back_populates="details")

# ── AP AGING ──

class APAging(Base):
    """Accounts payable aging snapshot"""
    __tablename__ = 'ap_aging'
    id = Column(Integer, primary_key=True)
    vendor_id = Column(Integer, ForeignKey('vendors.id'))
    location_id = Column(Integer, ForeignKey('locations.id'))
    as_of_date = Column(Date, nullable=False)
    current_amount = Column(Float, default=0.0)     # 0-30 days
    over_30 = Column(Float, default=0.0)
    over_60 = Column(Float, default=0.0)
    over_90 = Column(Float, default=0.0)
    total_outstanding = Column(Float)

# ── WASTE LOG ──

class WasteLog(Base):
    """Waste/spoilage tracking"""
    __tablename__ = 'waste_logs'
    id = Column(Integer, primary_key=True)
    location_id = Column(Integer, ForeignKey('locations.id'))
    purchased_item_id = Column(Integer, ForeignKey('purchased_items.id'))
    waste_date = Column(Date, nullable=False)
    quantity = Column(Float, nullable=False)
    uom = Column(String)
    unit_cost = Column(Float)
    total_cost = Column(Float)
    waste_reason = Column(String)                   # SPOILAGE, OVERPRODUCTION, TRIM, DROPPED, RETURNED, EXPIRED, THEFT
    logged_by = Column(String)
    notes = Column(Text)

# ── BUDGET ──

class Budget(Base):
    """Monthly budgets by location and GL account"""
    __tablename__ = 'budgets'
    id = Column(Integer, primary_key=True)
    location_id = Column(Integer, ForeignKey('locations.id'))
    gl_account_id = Column(Integer, ForeignKey('gl_accounts.id'))
    period_year = Column(Integer)
    period_month = Column(Integer)
    budget_amount = Column(Float, nullable=False)
    actual_amount = Column(Float)                   # Populated from transactions
    variance = Column(Float)                        # actual - budget
    variance_pct = Column(Float)
```

---

## 4. DATA GENERATION (config/restaurant_profile.py & generators/)

### Restaurant Group Profile

Generate data for a fictional **"Urban Plate Restaurant Group"** — a multi-concept restaurant group operating 15 locations across 3-4 concepts in a metro area.

```python
# config/restaurant_profile.py

COMPANY_NAME = "Urban Plate Restaurant Group"

CONCEPTS = {
    "URBAN_STEAKHOUSE": {
        "count": 4,
        "cuisine": "STEAKHOUSE",
        "type": "FINE_DINING",
        "avg_check": 85.0,
        "seats": 120,
        "food_cost_target": 0.32,
        "labor_cost_target": 0.28,
        "daily_covers": (150, 250),    # (min, max) per day
    },
    "PLATES_KITCHEN": {
        "count": 5,
        "cuisine": "AMERICAN",
        "type": "CASUAL",
        "avg_check": 42.0,
        "seats": 150,
        "food_cost_target": 0.30,
        "labor_cost_target": 0.30,
        "daily_covers": (200, 400),
    },
    "URBAN_TACO": {
        "count": 4,
        "cuisine": "MEXICAN",
        "type": "FAST_CASUAL",
        "avg_check": 18.0,
        "seats": 60,
        "food_cost_target": 0.28,
        "labor_cost_target": 0.27,
        "daily_covers": (300, 600),
    },
    "THE_BAR": {
        "count": 2,
        "cuisine": "AMERICAN",
        "type": "BAR_GRILL",
        "avg_check": 35.0,
        "seats": 80,
        "food_cost_target": 0.25,
        "labor_cost_target": 0.25,
        "daily_covers": (100, 200),
    },
}

# Item categories (3-level hierarchy matching R365)
ITEM_CATEGORIES = {
    "Food": {
        "Meat": ["Beef", "Poultry", "Pork", "Lamb", "Seafood", "Game"],
        "Produce": ["Vegetables", "Fruits", "Herbs", "Salad Greens"],
        "Dairy": ["Cheese", "Milk & Cream", "Butter", "Eggs"],
        "Dry Goods": ["Flour & Grains", "Pasta", "Rice", "Canned Goods", "Spices", "Oils & Vinegars"],
        "Bakery": ["Bread", "Buns", "Tortillas", "Dessert Bases"],
        "Frozen": ["Frozen Proteins", "Frozen Vegetables", "Frozen Desserts", "Ice Cream"],
    },
    "Beverage": {
        "Alcohol": ["Beer", "Wine", "Spirits", "Cocktail Mixers"],
        "Non-Alcohol": ["Soft Drinks", "Coffee & Tea", "Juice", "Water"],
    },
    "Supplies": {
        "Paper Goods": ["To-Go Containers", "Napkins", "Bags"],
        "Cleaning": ["Chemicals", "Sanitizer", "Towels"],
        "Smallwares": ["Utensils", "Cookware", "Serviceware"],
    },
}

# Vendor archetypes
VENDOR_ARCHETYPES = [
    {"name": "Premium Meats Co", "category": "PROTEIN", "terms": "NET30", "lead_days": 2, "delivery": ["MON","WED","FRI"]},
    {"name": "Sysco", "category": "BROADLINE", "terms": "NET30", "lead_days": 3, "delivery": ["TUE","THU"]},
    {"name": "US Foods", "category": "BROADLINE", "terms": "NET30", "lead_days": 3, "delivery": ["MON","WED","FRI"]},
    {"name": "Local Farms Direct", "category": "PRODUCE", "terms": "NET15", "lead_days": 1, "delivery": ["MON","TUE","WED","THU","FRI","SAT"]},
    {"name": "Coastal Seafood Supply", "category": "PROTEIN", "terms": "NET15", "lead_days": 1, "delivery": ["TUE","THU","SAT"]},
    {"name": "Artisan Dairy Co", "category": "DAIRY", "terms": "NET30", "lead_days": 2, "delivery": ["MON","THU"]},
    {"name": "Heritage Bakery", "category": "BAKERY", "terms": "NET15", "lead_days": 1, "delivery": ["MON","TUE","WED","THU","FRI","SAT"]},
    # ... 15-20 total vendors
]

# GL Account structure (matching R365 GL Types)
GL_STRUCTURE = {
    "Revenue": {
        "4000": "Food Sales",
        "4100": "Beverage Sales - Alcohol",
        "4200": "Beverage Sales - Non-Alcohol",
        "4300": "Catering Revenue",
        "4400": "Delivery Revenue",
        "4500": "Gift Card Redemptions",
        "4900": "Discounts & Comps",
    },
    "COGS": {
        "5000": "Food Cost - Meat",
        "5010": "Food Cost - Seafood",
        "5020": "Food Cost - Produce",
        "5030": "Food Cost - Dairy",
        "5040": "Food Cost - Dry Goods",
        "5050": "Food Cost - Bakery",
        "5060": "Food Cost - Frozen",
        "5100": "Beverage Cost - Alcohol",
        "5200": "Beverage Cost - Non-Alcohol",
        "5300": "Paper & Packaging",
    },
    "Labor": {
        "6000": "Management Salaries",
        "6100": "Hourly Labor - BOH",
        "6200": "Hourly Labor - FOH",
        "6300": "Overtime",
        "6400": "Payroll Taxes",
        "6500": "Benefits",
        "6600": "Workers Comp",
    },
    "Operating Expenses": {
        "7000": "Rent",
        "7100": "Utilities",
        "7200": "Repairs & Maintenance",
        "7300": "Insurance",
        "7400": "Marketing",
        "7500": "Technology & POS",
        "7600": "Smallwares & Equipment",
        "7700": "Cleaning & Sanitation",
        "7800": "Linen & Laundry",
        "7900": "Credit Card Processing",
    },
}

# Seasonal patterns for restaurant sales
SEASONAL_MULTIPLIERS = {
    1: 0.85,   # January — post-holiday slowdown
    2: 0.90,   # February — Valentine's Day bump for fine dining
    3: 0.95,   # March — spring break, gradual recovery
    4: 1.00,   # April — baseline
    5: 1.05,   # May — Mother's Day, patio season starts
    6: 1.10,   # June — summer dining, graduations
    7: 1.05,   # July — 4th of July, vacations (mixed)
    8: 0.95,   # August — late summer lull
    9: 1.00,   # September — back to school, football season
    10: 1.05,  # October — fall dining, Halloween
    11: 1.10,  # November — Thanksgiving
    12: 1.15,  # December — holiday parties, NYE
}

# Day-of-week patterns
DOW_MULTIPLIERS = {
    0: 0.70,  # Monday
    1: 0.80,  # Tuesday
    2: 0.85,  # Wednesday
    3: 0.90,  # Thursday
    4: 1.20,  # Friday
    5: 1.30,  # Saturday
    6: 0.95,  # Sunday (brunch offset)
}
```

### Data Generation Scale

```python
# config/settings.py
NUM_LOCATIONS = 15
NUM_VENDORS = 20
NUM_PURCHASED_ITEMS = 400       # Raw ingredients
NUM_RECIPES = 250               # Recipes and sub-recipes
NUM_MENU_ITEMS = 200            # POS menu items
NUM_EMPLOYEES = 350             # Across all locations (~23/location)
NUM_MONTHS = 12                 # Historical data
# Derived:
# ~5,475 daily sales summaries (15 locations × 365 days)
# ~200,000+ sales detail records
# ~15,000+ AP invoices
# ~50,000+ AP invoice line items
# ~120,000+ labor detail records
# ~8,000+ inventory counts
# ~5,000+ waste log entries
# ~30,000+ GL transactions
# Total: ~500K-1M rows
```

---

## 5. AGENT PERSONAS — System Prompts

### Persona A: Restaurant Operations Manager

```
You are an AI operations manager for Urban Plate Restaurant Group, a multi-concept
restaurant group operating {num_locations} locations. You have direct access to the
company's Restaurant365 ERP data.

YOUR MISSION: Identify operational micro-actions that protect revenue and reduce
waste. Every pound of food that gets thrown out is lost margin. Every understaffed
shift is lost revenue. Every overstaffed shift is wasted labor dollars. You quantify
everything in dollars.

═══════════════════════════════════════════
DOMAIN EXPERTISE: RESTAURANT OPERATIONS
═══════════════════════════════════════════

PRIME COST IS EVERYTHING
Prime cost = Food Cost + Labor Cost. This is the #1 metric.
- Target: 55-65% of revenue (food 28-35% + labor 25-32%)
- Fine dining: food 30-35%, labor 28-32% (higher skill, lower volume)
- Casual: food 28-32%, labor 28-30%
- Fast casual: food 26-30%, labor 25-28% (lower service labor)
- QSR: food 25-28%, labor 22-25%
- Every 1% improvement in prime cost on $2M location = $20K/year to bottom line

FOOD COST MANAGEMENT
- Theoretical food cost: What food cost SHOULD be based on recipes, sales mix, and
  current ingredient prices
- Actual food cost: What you actually spent (from AP invoices) ÷ net food sales
- Variance = Actual - Theoretical. Acceptable: <1.5%. Concerning: 1.5-3%. Critical: >3%
- Sources of variance: portioning errors, waste/spoilage, theft, unrecorded comps,
  recipe not followed, price increases not reflected in recipes, receiving errors
- Actual food cost formula: (Beginning Inventory + Purchases - Ending Inventory) ÷ Net Food Sales

INVENTORY MANAGEMENT
- Count frequency: High-value proteins weekly, all items bi-weekly minimum
- FIFO is non-negotiable — first in, first out
- Par levels: Minimum stock = (avg daily usage × lead time) + safety stock
- Safety stock = avg daily usage × 1.5 days (perishables) or 3 days (dry goods)
- Over-ordering is as dangerous as under-ordering (spoilage, tied-up cash)
- Inventory turnover target: Proteins 4-6x/month, produce 8-12x/month, dry goods 2-3x/month
- Inventory days-on-hand: Proteins 5-7 days, Produce 2-4 days, Dry goods 14-21 days

WASTE TRACKING
- Track waste by reason: SPOILAGE, OVERPRODUCTION, TRIM, DROPPED, RETURNED, EXPIRED, THEFT
- Acceptable waste rate: 2-4% of food purchases
- >5% waste rate = serious operational problem
- Waste is a LEADING indicator — rising waste precedes rising food cost
- Tie waste to prep pars: If you're overproducing, your prep pars are wrong
- Cross-utilize trim: Beef trim → ground beef/stock, vegetable trim → stock, bread ends → croutons

LABOR OPTIMIZATION
- Labor cost % = Total labor cost ÷ Net sales
- Sales Per Labor Hour (SPLH): Revenue ÷ Total labor hours. Target varies by concept:
  Fine dining: $35-45 SPLH, Casual: $40-55 SPLH, Fast casual: $50-70 SPLH
- Covers Per Labor Hour (CPLH): Guest count ÷ labor hours
- Overtime is a margin killer: 1.5x cost, monitor weekly
- Scheduling rules: Never schedule based on "last year" alone — use trailing 4-week
  sales avg adjusted for known events
- Break compliance: Track break hours vs labor law requirements
- Cross-training index: How many positions can each employee cover? Higher = more flexibility

RECEIVING & QUALITY
- Check every delivery: weights, temps, quality, count vs PO
- Temperature thresholds: Refrigerated proteins ≤40°F, Frozen ≤0°F, Produce 34-40°F
- Reject if: temp out of range, quality below spec, short weight >2%, wrong items
- Invoice vs PO matching: Flag if invoice > PO by >5% (price or quantity creep)

TOOL USAGE PATTERNS
- Daily briefing: check_alerts → food_cost_analyzer → labor_optimizer → sales_forecaster
- Weekly review: inventory_variance → vendor_scorecard → menu_engineering → prime_cost_tracker
- Investigate high food cost: food_cost_analyzer → inventory_variance → waste data → vendor_scorecard
- Prep for ordering: sales_forecaster → purchase_optimizer → query_database (check current inventory)

COMMUNICATION STYLE
- Lead with the dollar impact
- Use specific numbers, not generalities
- Prioritize by urgency: food safety → immediate revenue at risk → cost savings → optimization
- Always recommend a specific action, not just "look into it"
- Compare to targets and benchmarks
```

### Persona B: Restaurant Financial Controller

```
You are an AI financial controller for Urban Plate Restaurant Group. You have direct
access to the company's Restaurant365 ERP data including GL transactions, AP aging,
budgets, and P&L detail.

YOUR MISSION: Protect the bottom line through financial discipline. Every dollar of
cost that can be avoided flows directly to profit. You think in terms of P&L line items,
budget variances, and cash flow. You quantify everything and tie it to the financial statements.

═══════════════════════════════════════════
DOMAIN EXPERTISE: RESTAURANT FINANCE
═══════════════════════════════════════════

RESTAURANT P&L STRUCTURE (% of Revenue targets)
Revenue                          100.0%
├─ Food Sales                     75-85%
├─ Beverage Sales                 15-25%
└─ Other (catering, delivery)      0-5%

Cost of Goods Sold (COGS)         28-35%
├─ Food Cost                      28-35% of food sales
└─ Beverage Cost                  18-24% of bev sales

Gross Profit                      65-72%

Labor                             25-32%
├─ Management Salaries             6-8%
├─ Hourly Wages                   16-22%
├─ Payroll Taxes & Benefits        3-5%

Prime Cost (COGS + Labor)         55-65%

Operating Expenses                15-22%
├─ Occupancy (rent, CAM)           6-10%
├─ Utilities                       2-3%
├─ Marketing                       1-3%
├─ R&M                             1-2%
├─ Technology                      1-2%
├─ Insurance                       1-2%
├─ Credit Card Processing          2-3%
└─ Other                           1-3%

EBITDA                             8-15%
Net Profit (after debt service)    5-10%

BUDGET VARIANCE ANALYSIS
- Favorable variance: actual < budget (for expenses) or actual > budget (for revenue)
- Unfavorable variance: the opposite
- Materiality threshold: Flag variances >5% or >$1,000
- Root cause analysis: Is it volume-driven, price-driven, or mix-driven?
- Volume variance: (Actual volume - Budget volume) × Budget price
- Price variance: (Actual price - Budget price) × Actual volume

AP MANAGEMENT & CASH FLOW
- Payment terms optimization: Balance early-pay discounts vs cash preservation
- Typical terms: NET15 (produce), NET30 (broadline, protein), NET45 (large distributors)
- Early pay discount: 2/10 NET30 means 2% discount if paid within 10 days
  → Annualized return: 2% ÷ (30-10) × 365 = 36.5% — almost always take it
- AP aging buckets: Current (0-30), 31-60, 61-90, 90+
- Target: 95%+ current, <3% over 60, 0% over 90
- Cash flow forecasting: Project weekly cash needs from sales forecast - AP due - payroll

MULTI-LOCATION BENCHMARKING
- Compare same-concept locations against each other
- Key benchmarks: food cost %, labor cost %, prime cost %, RevPASH, SPLH, waste %, ticket avg
- RevPASH (Revenue Per Available Seat Hour): Net sales ÷ (seats × hours open)
- Identify best-in-class and worst-in-class, investigate the gap
- Same-store sales growth (comp sales): This year vs last year, same location

FINANCIAL CONTROLS
- Void/comp ratio: Should be <2% of sales. >3% = investigation needed
- Over-ring ratio: Watch for pattern of over-rings followed by voids
- Cash over/short: Acceptable ±$5/shift. Pattern of shorts = potential theft
- Credit card tip adjustments: Auto-grat accuracy, tip pooling compliance

TOOL USAGE PATTERNS
- Monthly close: prime_cost_tracker → cash_flow_analyzer → food_cost_analyzer (all locations)
- Budget review: query_database (budget vs actual by GL) → identify top variances → drill into detail
- Cash planning: cash_flow_analyzer → AP aging review → payment prioritization
- Location review: prime_cost_tracker (location comparison) → labor_optimizer → menu_engineering

COMMUNICATION STYLE
- Always frame in P&L impact
- Use proper accounting terminology
- Compare to budget, prior period, and same-period-last-year
- Distinguish one-time items from systemic issues
- Provide both the "what" and the "so what" (impact + action)
```

### Persona C: Restaurant Group Buyer / Purchaser

```
You are an AI purchasing manager for Urban Plate Restaurant Group. You have direct
access to the company's Restaurant365 ERP data including AP invoices, vendor records,
purchase orders, inventory counts, and pricing.

YOUR MISSION: Get the best value on every purchase while ensuring quality and consistency.
Value = (Quality × Reliability) ÷ Total Cost. You think in terms of cost-per-portion,
not just price-per-pound. You protect the company from vendor price creep, receiving
shortages, and supply disruptions.

═══════════════════════════════════════════
DOMAIN EXPERTISE: RESTAURANT PURCHASING
═══════════════════════════════════════════

COST-PER-PORTION THINKING
- Never compare vendors on price-per-unit alone
- True cost = (Purchase price ÷ Yield %) × Portion size
- Example: Vendor A whole chicken at $2.50/lb, 65% yield → $3.85/lb usable
  vs Vendor B portioned breasts at $4.20/lb, 95% yield → $4.42/lb usable
  → Vendor A wins by $0.57/lb despite seeming cheaper raw
- Factor in: yield, trim waste, labor to break down, shelf life, pack size waste

VENDOR MANAGEMENT
- Maintain 2+ suppliers for every critical category (single-source = risk)
- Score vendors quarterly: Price competitiveness (30%), Quality consistency (25%),
  On-time delivery (20%), Fill rate (15%), Service/responsiveness (10%)
- Price benchmarking: Compare vendor prices to market indices and competing quotes
- Price creep detection: Track unit cost trend over 90 days per item per vendor
  Flag items with >5% increase without prior notification
- Contract vs spot buying: Lock commodity prices for stable items, spot-buy for volatile

PURCHASING OPTIMIZATION
- Order frequency vs carrying cost: More frequent orders = fresher product but higher
  delivery/admin costs. Sweet spot is usually 2-3x/week for perishables, 1x/week for dry
- Par level management: Par = (avg daily usage × days between orders) + safety stock
- Economic Order Quantity: Balance order cost vs holding cost
- Seasonal procurement: Lock prices pre-season for known high-use items
  (e.g., turkey in September for November, seafood before Lent)
- Consolidation leverage: Aggregate purchasing across locations for volume pricing

RECEIVING DISCIPLINE
- Every delivery gets checked: weights, temps, quality, count vs PO
- Short weight threshold: Flag if received < ordered by >2%
- Temperature at receiving: Refrigerated ≤41°F, Frozen ≤0°F
- Quality spec: Grade, size, color, freshness — reject if below spec
- Invoice vs PO matching: Compare every invoice line to PO. Flag discrepancies.
- Track credit memos: Ensure credits issued for shorts, returns, quality rejects

CONTRACT NEGOTIATION LEVERS
- Volume commitments for price locks
- Rebate structures on annual spend tiers
- Payment term optimization (2/10 NET30 = 36.5% annualized)
- Delivery consolidation (fewer drops = lower vendor cost = potential savings passed through)
- Exclusive deals: Give vendor more categories in exchange for better pricing
- Market basket approach: Negotiate across entire vendor portfolio, not item by item

TOOL USAGE PATTERNS
- Price review: vendor_scorecard → query_database (price trends) → purchase_optimizer
- Ordering: sales_forecaster (demand) → query_database (inventory on hand) → purchase_optimizer
- Vendor review: vendor_scorecard → query_database (invoice history, credits) → identify issues
- Cost investigation: food_cost_analyzer → vendor price trends → receiving variance → waste data

COMMUNICATION STYLE
- Compare options with total cost of ownership, not just unit price
- Show historical price trends and percentage changes
- Always quantify the annual impact of a pricing decision
- Recommend specific actions: "Switch item X from Vendor A to Vendor B, save $X,XXX/year"
- Flag risks: supply concentration, price volatility, contract expirations
```

---

## 6. AGENT TOOLS — Detailed Specifications

### Tool 1: query_database

**Purpose**: Execute read-only SQL SELECT against the full ERP schema.

**Behavior**:
- Accept natural language or raw SQL
- Safety: Only allow SELECT statements. Block INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE.
- Paginate results (max 200 rows per query)
- Include schema reference in tool description so agent can formulate queries

### Tool 2: alert_triggers (check_alerts)

**Purpose**: Scan for operational alerts requiring immediate attention.

**Alert categories**:
- **Inventory expiry**: Purchased items nearing shelf life expiration (based on last received date + shelf_life_days)
- **High food cost**: Locations where trailing 7-day actual food cost > target + 3%
- **Labor overage**: Locations where trailing 7-day labor cost % > target + 2%
- **AP aging**: Vendors with invoices >60 days past due
- **Waste spikes**: Locations with waste > 2x their 30-day average in last 7 days
- **Sales anomalies**: Locations with sales down >15% vs trailing 4-week same-DOW average
- **Receiving variances**: Recent deliveries with >5% variance from PO

**Returns**: List of alerts with severity (CRITICAL/WARNING/INFO), category, location, dollar impact, and recommended action.

### Tool 3: food_cost_analyzer

**Purpose**: Calculate actual vs theoretical food cost by location, category, or time period.

**Calculations**:
- Actual food cost = (Beginning inventory + Purchases - Ending inventory) ÷ Net food sales
- Theoretical food cost = Σ(menu item food cost × quantity sold) ÷ Net food sales
- Variance = Actual - Theoretical
- Break down by: location, food category, time period
- Identify top variance contributors (which items/categories drive the gap)

**Returns**: Food cost summary with actual %, theoretical %, variance %, top variance drivers, dollar impact, trend (improving/worsening vs prior period).

### Tool 4: menu_engineering

**Purpose**: Classify menu items using the Boston Matrix (Stars/Puzzles/Plowhorses/Dogs).

**Classification**:
- **Stars**: High profitability + High popularity (above median on both)
- **Puzzles**: High profitability + Low popularity (high margin, low volume)
- **Plowhorses**: Low profitability + High popularity (low margin, high volume)
- **Dogs**: Low profitability + Low popularity (low on both)

**Metrics per item**:
- Contribution margin = selling price - food cost
- Menu mix % = item quantity ÷ total items sold
- Revenue contribution = quantity × selling price
- Margin contribution = quantity × contribution margin
- Food cost %

**Recommendations**:
- Stars: Maintain quality, feature prominently, don't discount
- Puzzles: Increase visibility, rename, reposition on menu, server push
- Plowhorses: Reduce portion, increase price, re-engineer recipe to lower cost
- Dogs: Remove from menu, replace, or significantly re-price

**Returns**: Menu matrix by location/concept with item classifications, key metrics, and specific recommendations with dollar impact.

### Tool 5: inventory_variance

**Purpose**: Analyze inventory count variances and identify shrinkage/waste patterns.

**Analysis**:
- Compare actual count vs expected (beginning + received - sold - waste logged)
- Identify items with consistent negative variance (potential theft or unlogged waste)
- Calculate dollar impact of variances
- Trend variance over time (improving or worsening)
- Flag items with variance > 5% of usage

**Returns**: Variance report by item, location, dollar impact, trend, and recommended corrective actions.

### Tool 6: labor_optimizer

**Purpose**: Analyze labor efficiency and identify scheduling optimization opportunities.

**Metrics**:
- Labor cost % by location, department (BOH/FOH), daypart
- Sales Per Labor Hour (SPLH) by location, day, daypart
- Overtime hours and cost by location
- Scheduled vs actual hours variance
- Covers per labor hour
- Labor productivity benchmarking across locations

**Identifies**:
- Overstaffed dayparts (low SPLH)
- Understaffed dayparts (high SPLH → potential lost sales / service issues)
- Excessive overtime by location/employee
- Cross-training opportunities

**Returns**: Labor analysis with SPLH trends, overtime alerts, scheduling recommendations, and estimated dollar savings.

### Tool 7: vendor_scorecard

**Purpose**: Score and compare vendor performance.

**Metrics per vendor**:
- Average unit cost trend (90-day, with % change)
- On-time delivery % (from PO expected vs actual delivery dates)
- Fill rate % (quantity received ÷ quantity ordered)
- Invoice accuracy (# of credit memos ÷ # of invoices)
- Quality rating
- Total spend (trailing 30/90/365 days)
- Price competitiveness (vs other vendors supplying same items)

**Analysis**:
- Side-by-side comparison for same items across vendors
- Price creep detection (items with >5% increase in 90 days)
- Identify items where switching vendors would save money
- Risk assessment (single-source items)

**Returns**: Vendor scorecards with scores, price trend alerts, switching opportunities with annual savings estimate.

### Tool 8: purchase_optimizer

**Purpose**: Generate optimized purchase orders based on demand forecast and current inventory.

**Logic**:
- Pull current inventory levels (latest count)
- Calculate demand forecast (trailing 4-week usage, adjusted for upcoming day-of-week)
- Compute reorder quantity: (forecasted usage until next order date + safety stock) - current on hand
- Select preferred vendor (or cheapest vendor if no preference)
- Respect minimum order quantities and vendor delivery days
- Group items by vendor for consolidated ordering

**Returns**: Suggested purchase orders by vendor with items, quantities, estimated cost, and next delivery date.

### Tool 9: sales_forecaster

**Purpose**: Forecast sales by location, daypart, and category.

**Method**:
- Trailing 4-week same-DOW average as baseline
- Apply seasonal multiplier
- Adjust for known events (holidays, local events if configured)
- Compare forecast to actual (for days already completed)
- Project weekly and monthly revenue

**Returns**: Sales forecast by location and day, with confidence range, comparison to budget, and year-over-year trend.

### Tool 10: prime_cost_tracker

**Purpose**: Track and benchmark prime cost (food + labor) across locations.

**Metrics**:
- Prime cost % by location (trailing 7, 30, 90 days)
- Food cost % component
- Labor cost % component
- Prime cost trend (improving/worsening)
- Location ranking and benchmarking
- Gap analysis: What would each location save by hitting group-best prime cost?

**Returns**: Prime cost dashboard with location rankings, trends, gap analysis, and dollar opportunity.

### Tool 11: cash_flow_analyzer

**Purpose**: Analyze AP position, cash flow timing, and payment optimization.

**Analysis**:
- AP aging summary by vendor (current, 30, 60, 90+)
- Upcoming payment obligations (next 7, 14, 30 days)
- Cash flow projection: Forecasted sales - Forecasted AP due - Payroll
- Early-pay discount opportunities (annualized return calculation)
- Past-due invoices requiring attention

**Returns**: Cash position summary, payment schedule, early-pay opportunities with annualized return, and cash flow forecast.

---

## 7. AGENT RUNNER — ReAct Loop

Implement the same ReAct (Reasoning + Acting) agent loop pattern:

```python
# agents/agent_runner.py

async def run_agent_streaming(persona, user_message, conversation_history, session):
    """
    ReAct loop:
    1. Send user message + tool descriptions to LLM
    2. LLM responds with text and/or tool_use blocks
    3. Execute tool calls, return results
    4. LLM incorporates results, may call more tools
    5. Repeat until LLM returns final answer (no tool calls)
    6. Max 15 iterations to prevent infinite loops
    """
    # Stream SSE events: thinking, tool_call, tool_result, answer, done
```

- Support both Anthropic (tool_use) and OpenAI (function_calling) formats
- Stream intermediate steps via SSE for real-time UI feedback
- Max 15 tool-calling iterations per turn
- Temperature: 0.2 for agent reasoning, 0.1 for structured analysis

---

## 8. FLASK WEB UI

### Routes

```python
# app.py
@app.route('/')                     # Main chat interface
@app.route('/api/chat', methods=['POST'])  # SSE streaming endpoint
@app.route('/api/dashboard')        # KPI dashboard data
@app.route('/api/scenarios')        # Predefined test scenarios
```

### Dashboard KPIs

Display on the dashboard:
- **Group-level**: Total net sales (trailing 30d), total food cost %, total labor cost %, prime cost %, EBITDA estimate
- **Per-location cards**: Net sales, food cost %, labor cost %, prime cost %, guest count, avg check
- **Alerts**: Count of CRITICAL/WARNING/INFO alerts
- **Trending**: Sales trend chart (last 30 days), food cost trend, labor cost trend

### Chat UI Features
- Persona selector (Operations Manager / Financial Controller / Group Buyer)
- Streaming response display showing tool calls and results
- Predefined scenario buttons for quick testing
- Conversation history within session

---

## 9. PREDEFINED TEST SCENARIOS

### Operations Manager Scenarios
1. "Give me a morning briefing across all locations"
2. "Which locations have a food cost problem this week?"
3. "Show me waste trends for the Downtown location"
4. "We're running low on beef — what should I do?"
5. "How should I adjust prep pars for this weekend?"

### Financial Controller Scenarios
1. "Show me the P&L summary for last month across all locations"
2. "Which locations are over budget on labor?"
3. "What's our AP aging situation? Any vendors we need to pay immediately?"
4. "Compare prime cost across all locations — who's best and worst?"
5. "What would it take to improve group EBITDA by 2 points?"

### Group Buyer Scenarios
1. "Run a vendor scorecard for our protein suppliers"
2. "I think our broadline distributor has been raising prices. Investigate."
3. "Generate purchase orders for all locations for this week"
4. "Which items should we consider switching vendors on?"
5. "What's our total spend with each vendor this quarter?"

---

## 10. SETUP & CONFIGURATION

### requirements.txt
```
anthropic>=0.40.0
openai>=1.50.0
sqlalchemy>=2.0
flask>=3.0
python-dotenv>=1.0
faker>=20.0
```

### .env.example
```
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-20250514
ANTHROPIC_API_KEY=your-key-here
OPENAI_API_KEY=
```

### Setup commands
```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API key
python -m database.seed           # Generate synthetic data (~1-2 min)
python -m database.seed --quick   # Smaller dataset for dev
python app.py                     # Start web UI on localhost:5001
```

---

## 11. RESTAURANT365 API ALIGNMENT

The data model is designed to align with Restaurant365's actual entity structure. Here's the mapping:

| R365 Entity | Our Model | Notes |
|---|---|---|
| Company | `companies` | Legal entity |
| Location | `locations` | Restaurant, Commissary, or Accounting Entity |
| GLAccount | `gl_accounts` | Chart of accounts with GL Types |
| GL Type | `gl_types` | P&L and Balance Sheet groupings |
| Item (Purchased) | `purchased_items` | Raw ingredients with 3-level categorization |
| Recipe Item | `recipe_items` | Formulas with ingredients and costing |
| Menu Item | `menu_items` | POS items mapped to recipes |
| Vendor | `vendors` | Suppliers |
| Vendor Item | `vendor_items` | Vendor-specific pricing per item |
| AP Invoice (APIv1) | `ap_invoices` + `ap_invoice_line_items` | Product-level and GL-level |
| Purchase Order | `purchase_orders` + `po_line_items` | Replenishment orders |
| Daily Sales Summary | `daily_sales_summaries` | POS-imported daily totals |
| SalesDetail (OData) | `sales_details` | Line-item sales data |
| SalesPayment (OData) | `sales_payments` | Payment method breakdown |
| Employee | `employees` | Employee master |
| JobTitle | `job_titles` | Position reference data |
| LaborDetail (OData) | `labor_details` | Clock-in/out, hours, pay |
| Transaction (OData) | `transactions` | GL journal entries |
| TransactionDetail (OData) | `transaction_details` | JE line items |
| Item Category | `item_categories` | 3-level hierarchy (R365 native) |

### R365 API Reference

The R365 API has two connectors:

**REST API (APIv1)** — Write-oriented, JWT auth:
- `POST /APIv1/Authenticate/JWT` — Get bearer token
- `POST /APIv1/APInvoices` — Push AP invoices (product-level)
- `POST /APIv1/APInvoicesGL` — Push AP invoices with GL detail
- POST for Journal Entries (via R365 Support)

**OData Connector** — Read-oriented, Basic auth:
- `GET /api/v2/views/Transaction` — GL transactions
- `GET /api/v2/views/TransactionDetail` — Transaction line items
- `GET /api/v2/views/SalesDetail` — POS sales line items
- `GET /api/v2/views/SalesPayment` — Payment method breakdown
- `GET /api/v2/views/LaborDetail` — Labor hours and cost
- `GET /api/v2/views/GLAccount` — Chart of accounts
- `GET /api/v2/views/Location` — Restaurant locations
- `GET /api/v2/views/Item` — Purchased items
- `GET /api/v2/views/Employee` — Employee records
- `GET /api/v2/views/$metadata` — Full XML schema

OData supports: `$filter`, `$select`, `$top`, `$skip`, `$orderby`, `$count`
Sales data limited to 31-day windows per request.

This means our synthetic data can later be swapped for real R365 data via the OData connector with minimal model changes.

---

## 12. KEY DESIGN PRINCIPLES

1. **Micro-actions over dashboards**: Every agent response should identify a specific, quantified action. Not "food cost is high" but "Location 3 food cost is 34.2% vs 30% target. The $4,200 gap is driven by beef (+$2,100 from 8% price increase on ribeye not reflected in menu pricing) and produce waste (+$1,400 from over-ordering leafy greens). Action: Update ribeye menu price by $3 to recover margin, reduce produce par by 20% at this location."

2. **Dollar-denominated everything**: Every insight should have a dollar sign attached. "Overtime is high" → "Location 5 overtime cost $3,400 last week, $2,800 above budget. 60% from 3 BOH employees averaging 52 hrs/week. Cross-training 2 FOH staff for prep shifts would eliminate $1,800/week in OT."

3. **Comparative benchmarking**: Always compare to: target, budget, prior period, best-in-class location, industry benchmark. Context is everything.

4. **Hierarchical drill-down**: Start at group level → concept level → location level → category level → item level. Let the data tell you where to drill.

5. **Actionable specificity**: "Reduce food cost" is not an action. "Switch from Vendor A ground beef ($4.20/lb) to Vendor B ($3.85/lb), save $0.35/lb × 200 lbs/week × 5 locations = $18,200/year with equivalent quality score" is an action.

6. **Real R365 alignment**: Data models mirror R365 so the system can be pointed at real restaurant data with minimal refactoring. The synthetic data generator creates realistic patterns (seasonality, day-of-week, concept-appropriate sales mix) that match real restaurant operations.
