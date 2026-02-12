# Pat LaFrieda ERP Testbed

A self-contained Python testbed for evaluating LLM analysis and agentic actions against realistic food distribution ERP data, modeled after Pat LaFrieda Meat Purveyors.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure your API key

```bash
cp .env.example .env
```

Open `.env` and replace `sk-ant-your-key-here` with your actual Anthropic API key. If you're using OpenAI instead, set `LLM_PROVIDER=openai` and add your OpenAI key.

### 3. Seed the database

The database is **not included in the repo** -- you need to generate it. This creates a SQLite database at `data/lafrieda.db` with ~1M rows of realistic ERP data (takes 1-2 minutes):

```bash
python -m database.seed
```

For a smaller/faster dataset during development:

```bash
python -m database.seed --quick
```

### 4. Run the chat UI

```bash
python app.py
```

Open **http://localhost:5001** in your browser. Pick a persona (Operations, Sales, or Restaurant), type a question, and the agent will query the database and reason through a response.

## Three Ways to Use This

### 1. Chat UI (recommended starting point)

```bash
python app.py
# Open http://localhost:5001
```

Interactive chatbot with three agent personas. Streams the agent's tool calls in real time. Try:
- "What inventory is at risk of expiring in the next 7 days?"
- "Which Cari-enrolled accounts show signs of churn? Build a win-back campaign."
- "Give me a daily operational briefing."

### 2. Jupyter Notebooks

```bash
jupyter notebook notebooks/
```

- `01_data_exploration.ipynb` -- verify data, check distributions
- `02_analysis_demos.ipynb` -- run the 6 LLM analyzers
- `03_agent_demos.ipynb` -- run agent scenarios with full traces

### 3. Scenario Runner (CLI)

```python
from scenarios.vendor_scenarios import VENDOR_SCENARIOS
from scenarios.runner import run_all_scenarios
# See notebooks/03_agent_demos.ipynb for full setup
```

## Project Structure

```
erp-testbed/
  app.py                # Flask chat UI (run this)
  static/app.js         # Frontend JS
  config/               # Settings and LaFrieda business constants
  database/             # SQLAlchemy models, connection, seed orchestrator
  generators/           # Data generation (products, customers, invoices, etc.)
  analysis/             # LLM analysis framework (6 analyzers)
  agents/               # Agentic framework (tool registry, ReAct runner, 7 tools)
    prompts/            # 3 agent personas (vendor ops, vendor sales, restaurant)
    tools/              # 7 callable tools
  scenarios/            # Predefined test scenarios
  notebooks/            # Jupyter demos
  tests/                # Unit tests
  data/                 # SQLite database (created by seed, not in repo)
```

## What's In the Database

- **products** (300) -- Beef, pork, poultry, lamb, blends, charcuterie SKUs
- **customers** (1,000) -- NYC metro restaurant accounts across 4 tiers
- **invoices** (50,000) -- 12 months of order history
- **invoice_line_items** (250,000) -- Catch-weight line items
- **lots** (5,000) -- Inventory lots with expiry, USDA grades, aging
- **suppliers** (20) -- With quality ratings and lead times
- **payments** (~40,000) -- Payment history with Cari reward data
- Plus 8 more tables: routes, POs, quality records, AR aging, pricing, campaigns, margin summaries, PO line items

## Agent Personas

**Vendor Operations** -- Food safety, spoilage prevention, inventory optimization, replenishment planning, operational alerting. Has access to all 7 tools.

**Vendor Sales** -- Customer intelligence, revenue growth, Cari Rewards campaigns, churn detection, competitive pricing. Uses query_database, generate_campaign, check_alerts, optimize_payments.

**Restaurant Buyer** -- Payment optimization, invoice verification, dispute resolution, spend analytics. Uses query_database, optimize_payments, handle_dispute.

## LLM Analyzers

Six standalone analyzers that return structured JSON:
- **Demand Forecast** -- 14-day daily predictions with confidence levels
- **Margin Analysis** -- outliers and pricing optimization opportunities
- **Customer Health** -- composite 0-100 score from engagement/payment signals
- **Spoilage Risk** -- lots near expiry vs. demand velocity
- **Pricing Benchmark** -- cross-customer pricing comparison
- **Churn Prediction** -- order frequency decay detection

## Agent Tools

Seven tools the LLM can call during agentic reasoning:
- **query_database** -- SQL SELECT against the full ERP schema
- **check_alerts** -- scan for expiring lots, temp anomalies, payment issues
- **get_reorder_suggestions** -- inventory vs. demand vs. lead time analysis
- **generate_campaign** -- Cari Reward API-compatible campaign JSON
- **optimize_payments** -- maximize Cari cashback via payment timing
- **handle_dispute** -- invoice discrepancy analysis and credit memos
- **optimize_inventory** -- stock transfer recommendations between zones

## Running Tests

```bash
pytest tests/ -v
```
