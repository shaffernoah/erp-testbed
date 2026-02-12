"""Global configuration for the LaFrieda ERP testbed."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "lafrieda.db"
DB_URL = f"sqlite:///{DB_PATH}"

# Random seed for deterministic data generation
RANDOM_SEED = 42

# LLM configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Data generation scale
NUM_PRODUCTS = 300
NUM_CUSTOMERS = 1000
NUM_SUPPLIERS = 20
NUM_ROUTES = 25
NUM_MONTHS = 12  # months of historical data
TARGET_INVOICES = 50_000
TARGET_LOTS = 5_000
NUM_CAMPAIGNS = 10
INVENTORY_SNAPSHOT_DAYS = 30  # days of daily inventory snapshots

# Agent configuration
AGENT_MAX_ITERATIONS = 10
AGENT_DEFAULT_TEMPERATURE = 0.2
ANALYSIS_DEFAULT_TEMPERATURE = 0.1
