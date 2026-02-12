# Pat LaFrieda ERP Testbed

A self-contained Python testbed for evaluating LLM analysis and agentic actions against realistic food distribution ERP data, modeled after Pat LaFrieda Meat Purveyors using Inecta ERP (Dynamics 365 Business Central).

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill in API keys
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# Seed the database with dummy data
python -m database.seed

# Explore in a notebook
jupyter notebook notebooks/01_data_exploration.ipynb
```

## Project Structure

```
lafrieda-erp-testbed/
├── config/           # Settings and LaFrieda business constants
├── database/         # SQLAlchemy models, connection, seed orchestrator
├── generators/       # Data generation (products, customers, invoices, etc.)
├── analysis/         # LLM analysis framework (analyzers for demand, margin, churn, etc.)
├── agents/           # Agentic framework (tool registry, ReAct runner, 7 tools, 3 personas)
├── scenarios/        # Predefined test scenarios (vendor, restaurant, operations)
├── notebooks/        # Jupyter demos
├── tests/            # Unit tests
└── data/             # Generated SQLite database (created by seed)
```

## What This Tests

### 1. Dummy Data (ERP Simulation)
- **300 products** (beef cuts, burger blends, pork, poultry, lamb, charcuterie)
- **1,000 restaurant customers** across NYC metro (Manhattan, Brooklyn, Queens, NJ, etc.)
- **50,000 invoices** with 250K line items over 12 months
- **5,000 lots** with expiry tracking, USDA grades, catch-weight
- Realistic seasonal patterns, customer tiers, and payment behaviors

### 2. LLM Analysis Framework
Six analyzers that feed ERP data to Claude for structured insights:
- **Demand Forecast** — predict category demand with seasonal awareness
- **Margin Analysis** — identify outliers and optimization opportunities
- **Customer Health** — composite score from engagement/payment/relationship signals
- **Spoilage Risk** — lots near expiry vs. demand velocity
- **Pricing Benchmark** — cross-customer pricing comparison
- **Churn Prediction** — order frequency decay detection

### 3. Agentic Actions Framework
Seven tools an LLM agent can call against the database:
- **query_database** — natural language to SQL
- **reorder_suggestions** — inventory vs. demand vs. lead time
- **campaign_generator** — outputs Cari Reward API-compatible JSON
- **payment_optimizer** — maximize Cari rewards via payment timing
- **alert_triggers** — threshold-based alerts (expiry, temp, payment anomalies)
- **dispute_handler** — invoice discrepancy analysis and credit memos
- **inventory_optimizer** — stock transfer recommendations

Three agent personas: Vendor Operations, Vendor Sales, Restaurant Buyer.

## Running Scenarios

```python
from database.connection import get_session
from analysis.llm_client import LLMClient
from agents.tool_registry import ToolRegistry
from scenarios.vendor_scenarios import VENDOR_SCENARIOS
from scenarios.runner import run_all_scenarios

session = get_session()
llm = LLMClient()

# Register tools, set up persona, run scenarios
# See notebooks/03_agent_demos.ipynb for full examples
```

## Cari Integration

Campaign generation outputs match the Cari Reward API schema exactly:
- Condition types: `ANY`, `INVOICE_TOTAL_OVER`, `DAYS_BEFORE`, `FIRST_INVOICES`, `INVOICE_INCLUDES_ITEMS`
- Reward types: `FIXED`, `PERCENTAGE`, `PERCENTAGE_OF_ITEMS`
- Tiered rewards with `condition_value` and `reward_value` JSON structures
