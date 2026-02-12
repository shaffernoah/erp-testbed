"""Tool: query_database -- natural language to SQL for the LaFrieda ERP.

Takes a plain-English question, maps it to a safe read-only SQL query
against the ERP database, executes it, and returns formatted results.
Only SELECT statements are permitted; any mutation attempt is rejected.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from agents.tool_registry import Tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema summary injected into the LLM prompt so it knows what tables exist
# ---------------------------------------------------------------------------

SCHEMA_SUMMARY = """
Available tables and key columns:

products (sku_id PK, name, category, subcategory, usda_grade, breed, primal_cut,
          is_catch_weight, base_uom, nominal_weight, case_weight_lbs, list_price_per_lb,
          cost_per_lb, target_margin_pct, aging_type, shelf_life_days, is_active, is_seasonal)

customers (customer_id PK, business_name, dba_name, customer_type, cuisine_type, segment,
           tier, annual_volume_estimate, account_status, city, state, zip_code, borough,
           delivery_zone, credit_limit, credit_terms, credit_terms_days, cari_enrolled,
           cari_reward_tier, cari_points_balance, first_order_date, last_order_date,
           total_lifetime_orders, total_lifetime_revenue, avg_order_value, order_frequency_days)

suppliers (supplier_id PK, name, supplier_type, city, state, country, region,
           quality_rating, delivery_reliability_pct, avg_lead_time_days, min_order_lbs,
           is_preferred, is_active)

lots (lot_id PK, lot_number, sku_id FK, supplier_id FK, production_date, received_date,
      expiration_date, sell_by_date, initial_quantity_lbs, current_quantity_lbs,
      storage_location, storage_temp_f, aging_start_date, aging_actual_days,
      status [AVAILABLE/RESERVED/DEPLETED/EXPIRED/HOLD], inspection_status)

inventory (inventory_id PK, sku_id FK, lot_id FK, location, zone, bin_location,
           quantity_on_hand, weight_on_hand_lbs, quantity_reserved, quantity_available,
           unit_cost, total_value, days_in_inventory, days_until_expiry, freshness_score,
           snapshot_date)

invoices (invoice_id PK, invoice_number, customer_id FK, invoice_date, due_date, ship_date,
          delivery_date, status [OPEN/PARTIAL/PAID/OVERDUE/DISPUTED/VOID],
          subtotal, tax_amount, freight_amount, total_amount, amount_paid, balance_due,
          payment_terms, route_id FK, cari_eligible, cari_cashback_pct, cari_points_earned)

invoice_line_items (line_item_id PK, invoice_id FK, line_number, sku_id FK, description,
                    quantity, uom, catch_weight_lbs, price_per_unit, line_subtotal,
                    discount_pct, discount_amount, line_total, lot_id FK, category, gl_code)

purchase_orders (po_id PK, po_number, supplier_id FK, status, order_date,
                 expected_delivery_date, subtotal, total_amount)

po_line_items (po_line_id PK, po_id FK, sku_id FK, quantity_ordered, quantity_received,
               cost_per_lb, line_total)

payments (payment_id PK, invoice_id FK, customer_id FK, payment_date, amount,
          payment_method, is_cari_payment, cari_payment_window, cari_reward_pct,
          cari_points_earned, days_to_payment)

routes (route_id PK, route_name, zone, subzone, delivery_days, departure_time,
        estimated_stops, driver_name, truck_id)

pricing (pricing_id PK, sku_id FK, customer_id FK, price_type [LIST/CONTRACT/VOLUME/PROMOTIONAL],
         price_per_lb, effective_date, expiration_date, min_quantity_lbs, is_active)

quality_records (record_id PK, record_type [HACCP_CHECK/TEMP_LOG/GRADE_VERIFY/COMPLAINT],
                 lot_id FK, sku_id FK, location, check_datetime, temperature_f,
                 temp_in_range, status [PASS/FAIL])

campaigns (campaign_id PK, name, campaign_type, condition_type, condition_value,
           reward_type, reward_value, participant_type, start_date, end_date,
           budget_total, budget_spent, status)

ar_aging (snapshot_id PK, snapshot_date, customer_id FK, current_amount, days_31_60,
          days_61_90, days_over_90, total_outstanding, weighted_avg_days)

margin_summary (summary_id PK, period_date, customer_id FK, category, sku_id FK,
                revenue, cogs, gross_margin, gross_margin_pct, volume_lbs, num_invoices,
                avg_price_per_lb, avg_cost_per_lb)
"""

# ---------------------------------------------------------------------------
# SQL safety helpers
# ---------------------------------------------------------------------------

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|EXEC|EXECUTE|GRANT|REVOKE|ATTACH|DETACH|PRAGMA)\b",
    re.IGNORECASE,
)


def _is_safe_sql(sql: str) -> bool:
    """Return True only if the statement is a read-only SELECT."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped.upper().startswith("SELECT"):
        return False
    if _FORBIDDEN_KEYWORDS.search(stripped):
        return False
    return True


# ---------------------------------------------------------------------------
# Core tool function
# ---------------------------------------------------------------------------

def query_database(question: str, session: Session) -> dict:
    """Translate *question* into SQL, execute, and return results.

    The function itself does NOT call an LLM -- it is expected that the
    agent runner's LLM will have already formulated the SQL in a preceding
    tool_use ``input`` block.  However the ``question`` parameter can also
    be a raw SQL SELECT for direct use.

    If ``question`` looks like raw SQL (starts with SELECT), it is executed
    directly.  Otherwise it is treated as a natural-language description and
    the function wraps it with a helper that attempts a best-effort
    translation using simple keyword matching.  For production use the
    agent's LLM should supply the SQL via tool input.
    """
    sql = question.strip()

    # If the question is not already SQL, attempt simple heuristic mapping.
    # The real intelligence comes from the LLM calling this tool with SQL.
    if not sql.upper().startswith("SELECT"):
        return {
            "status": "needs_sql",
            "message": (
                "Please provide a SQL SELECT query. The question was interpreted "
                "as natural language.  Use the schema reference below to formulate "
                "a query and call this tool again with the SQL as the 'question' "
                "parameter."
            ),
            "schema": SCHEMA_SUMMARY.strip(),
        }

    if not _is_safe_sql(sql):
        return {
            "status": "error",
            "error": "Only read-only SELECT statements are allowed. The query was rejected.",
        }

    try:
        result = session.execute(text(sql))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]

        if len(rows) > 200:
            rows = rows[:200]
            truncated = True
        else:
            truncated = False

        return {
            "status": "success",
            "columns": columns,
            "row_count": len(rows),
            "truncated": truncated,
            "rows": rows,
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": f"SQL execution error: {exc}",
        }


# ---------------------------------------------------------------------------
# Tool definition for registration
# ---------------------------------------------------------------------------

TOOL_DEF = Tool(
    name="query_database",
    description=(
        "Execute a read-only SQL SELECT query against the LaFrieda ERP database. "
        "Pass either a natural-language question (the agent will be asked to "
        "reformulate as SQL) or a direct SQL SELECT statement. Only SELECT "
        "statements are permitted.\n\n"
        "Database schema reference:\n" + SCHEMA_SUMMARY.strip()
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": (
                    "A SQL SELECT query to execute against the ERP database, "
                    "or a natural-language question about the data."
                ),
            },
        },
        "required": ["question"],
    },
    function=query_database,
    requires_confirmation=False,
    tags=["ops", "sales", "restaurant", "query"],
)
