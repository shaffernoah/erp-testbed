"""
Vercel serverless function entry point.

Serves the LaFrieda ERP Agent API:
  POST /api/chat   - Agent chat with streaming SSE
  GET  /api/kpis   - Dashboard KPI data
"""

import os
import sys
import json
import time
import inspect
import logging
from datetime import date, timedelta
from pathlib import Path

# Ensure project root is on sys.path so existing imports work
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, request, Response, stream_with_context, jsonify

import anthropic
from sqlalchemy import func, and_
from database.connection import get_session
from database.models import Inventory, Lot, Product, Route, Invoice
from agents.tool_registry import Tool, ToolRegistry
from agents.prompts.vendor_ops_agent import SYSTEM_PROMPT as OPS_PROMPT
from agents.prompts.vendor_sales_agent import SYSTEM_PROMPT as SALES_PROMPT
from agents.prompts.restaurant_agent import SYSTEM_PROMPT as RESTAURANT_PROMPT

from agents.tools.query_database import TOOL_DEF as qd_def
from agents.tools.alert_triggers import TOOL_DEF as at_def
from agents.tools.campaign_generator import TOOL_DEF as cg_def
from agents.tools.payment_optimizer import TOOL_DEF as po_def
from agents.tools.reorder_suggestions import TOOL_DEF as rs_def
from agents.tools.dispute_handler import TOOL_DEF as dh_def
from agents.tools.inventory_optimizer import TOOL_DEF as io_def
from agents.tools.slow_mover_scanner import TOOL_DEF as sms_def
from agents.tools.route_optimizer import TOOL_DEF as ro_def
from agents.tools.profit_opportunity_scanner import TOOL_DEF as pos_def

logging.basicConfig(level=logging.WARNING)

PUBLIC_DIR = PROJECT_ROOT / "public"
app = Flask(__name__, static_folder=str(PUBLIC_DIR), static_url_path='')

# --- Setup (shared across requests in warm container) ---
session = get_session()
model = os.getenv('LLM_MODEL', 'claude-sonnet-4-20250514')

PERSONAS = {
    "vendor_ops": {"name": "Vendor Operations", "prompt": OPS_PROMPT},
    "vendor_sales": {"name": "Vendor Sales", "prompt": SALES_PROMPT},
    "restaurant": {"name": "Restaurant Buyer", "prompt": RESTAURANT_PROMPT},
}


def build_registry():
    """Build tool registry with session-bound functions."""
    registry = ToolRegistry()
    for td in [qd_def, at_def, cg_def, po_def, rs_def, dh_def, io_def, sms_def, ro_def, pos_def]:
        sig = inspect.signature(td.function)
        if 'session' in sig.parameters:
            def make_bound(fn):
                def bound(**kwargs):
                    return fn(session=session, **kwargs)
                return bound
            tool = Tool(
                name=td.name, description=td.description, parameters=td.parameters,
                function=make_bound(td.function),
                requires_confirmation=td.requires_confirmation, tags=td.tags,
            )
        else:
            tool = td
        registry.register(tool)
    return registry


registry = build_registry()


def run_agent_streaming(user_message, persona_key, conversation_history, api_key):
    """Generator that yields SSE events as the agent works."""
    persona = PERSONAS.get(persona_key, PERSONAS["vendor_ops"])
    system_prompt = persona["prompt"]
    tools_payload = registry.get_tools_for_anthropic()

    # Create client with the user-provided API key
    client = anthropic.Anthropic(api_key=api_key)

    messages = []
    for msg in conversation_history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    max_iterations = 15
    t0 = time.time()
    tool_calls_count = 0

    for iteration in range(max_iterations):
        yield f"data: {json.dumps({'type': 'thinking', 'content': f'Iteration {iteration + 1}...'})}\n\n"

        try:
            response = client.messages.create(
                model=model, max_tokens=4096, temperature=0.2,
                system=system_prompt, messages=messages, tools=tools_payload,
            )
        except anthropic.AuthenticationError:
            yield f"data: {json.dumps({'type': 'answer', 'content': 'Invalid API key. Please check your Anthropic API key and try again.', 'tool_calls': 0, 'elapsed': 0, 'iterations': 0})}\n\n"
            yield "data: {\"type\": \"done\"}\n\n"
            return
        except Exception as e:
            yield f"data: {json.dumps({'type': 'answer', 'content': f'API error: {str(e)}', 'tool_calls': 0, 'elapsed': 0, 'iterations': 0})}\n\n"
            yield "data: {\"type\": \"done\"}\n\n"
            return

        text_parts = []
        tool_use_blocks = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_use_blocks.append(block)

        if response.stop_reason == "end_turn" or not tool_use_blocks:
            elapsed = round(time.time() - t0, 1)
            final_text = '\n'.join(text_parts)
            yield f"data: {json.dumps({'type': 'answer', 'content': final_text, 'tool_calls': tool_calls_count, 'elapsed': elapsed, 'iterations': iteration + 1})}\n\n"
            yield "data: {\"type\": \"done\"}\n\n"
            return

        for block in tool_use_blocks:
            args_preview = json.dumps(block.input)
            if len(args_preview) > 300:
                args_preview = args_preview[:300] + '...'
            yield f"data: {json.dumps({'type': 'tool_call', 'name': block.name, 'args': args_preview})}\n\n"

        for text in text_parts:
            if text.strip():
                yield f"data: {json.dumps({'type': 'thinking', 'content': text})}\n\n"

        assistant_content = []
        for block in response.content:
            if block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_content.append({
                    "type": "tool_use", "id": block.id,
                    "name": block.name, "input": block.input,
                })
        messages.append({"role": "assistant", "content": assistant_content})

        tool_results = []
        for block in tool_use_blocks:
            tool_calls_count += 1
            result = registry.execute(block.name, block.input)
            result_str = json.dumps(result, default=str)

            preview = result_str[:400] + '...' if len(result_str) > 400 else result_str
            yield f"data: {json.dumps({'type': 'tool_result', 'name': block.name, 'preview': preview})}\n\n"

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_str,
            })

        messages.append({"role": "user", "content": tool_results})

    elapsed = round(time.time() - t0, 1)
    yield f"data: {json.dumps({'type': 'answer', 'content': '(Max iterations reached. The agent may need a more specific question.)', 'tool_calls': tool_calls_count, 'elapsed': elapsed, 'iterations': max_iterations})}\n\n"
    yield "data: {\"type\": \"done\"}\n\n"


# --- Routes ---

@app.route('/api/chat', methods=['POST'])
def chat():
    api_key = request.headers.get('X-API-Key', '').strip()
    if not api_key:
        return jsonify({"error": "Missing API key. Please enter your Anthropic API key."}), 401

    data = request.json
    user_message = data.get('message', '')
    persona = data.get('persona', 'vendor_ops')
    history = data.get('history', [])

    return Response(
        stream_with_context(run_agent_streaming(user_message, persona, history, api_key)),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route('/api/kpis', methods=['GET'])
def get_kpis():
    """Return real-time KPI data for dashboard cards."""
    today = date.today()

    try:
        # --- Expiry Risk ---
        expiry_cutoff = today + timedelta(days=7)
        expiry_lots = (
            session.query(Lot)
            .filter(
                Lot.status.in_(["AVAILABLE", "RESERVED"]),
                Lot.expiration_date <= expiry_cutoff,
                Lot.expiration_date >= today,
                Lot.current_quantity_lbs > 0,
            )
            .all()
        )
        expiry_value = 0
        for lot in expiry_lots:
            product = session.query(Product).get(lot.sku_id)
            if product and product.cost_per_lb:
                expiry_value += float(lot.current_quantity_lbs or 0) * float(product.cost_per_lb)

        expiry_count = len(expiry_lots)
        expiry_status = "critical" if expiry_count > 15 else ("warning" if expiry_count > 5 else "ok")

        # --- Slow Movers ---
        slow_mover_q = (
            session.query(
                func.count(func.distinct(Inventory.sku_id)).label("sku_count"),
                func.sum(Inventory.total_value).label("total_value"),
            )
            .filter(
                Inventory.quantity_on_hand > 0,
                Inventory.days_in_inventory >= 21,
                Inventory.days_until_expiry > 7,
            )
            .first()
        )
        slow_count = int(slow_mover_q.sku_count or 0) if slow_mover_q else 0
        slow_value = float(slow_mover_q.total_value or 0) if slow_mover_q else 0
        slow_status = "warning" if slow_value > 10000 else "ok"

        # --- Route Efficiency ---
        lookback = today - timedelta(days=14)
        routes = session.query(Route).filter(Route.is_active == True).all()
        active_route_count = len(routes)

        if routes:
            utilizations = []
            for route in routes:
                actual = (
                    session.query(func.count(Invoice.invoice_id))
                    .filter(
                        Invoice.route_id == route.route_id,
                        Invoice.invoice_date >= lookback,
                    )
                    .scalar() or 0
                )
                delivery_days = 12
                avg_daily = actual / delivery_days if delivery_days > 0 else 0
                estimated = route.estimated_stops or 15
                util = (avg_daily / estimated * 100) if estimated > 0 else 0
                utilizations.append(util)
            avg_util = round(sum(utilizations) / len(utilizations), 0) if utilizations else 0
        else:
            avg_util = 0

        route_status = "ok" if avg_util >= 80 else ("warning" if avg_util >= 60 else "critical")

        # --- Margin Opportunities ---
        high_margin_products = (
            session.query(func.count(Product.sku_id))
            .filter(
                Product.is_active == True,
                Product.target_margin_pct >= 0.35,
            )
            .scalar() or 0
        )
        avg_target_margin = (
            session.query(func.avg(Product.target_margin_pct))
            .filter(
                Product.is_active == True,
                Product.target_margin_pct >= 0.35,
            )
            .scalar() or 0
        )
        margin_count = int(high_margin_products)
        avg_margin = round(float(avg_target_margin) * 100, 1)

        # --- Recent Alerts ---
        recent_alerts = []
        for lot in expiry_lots[:8]:
            days_left = (lot.expiration_date - today).days
            product = session.query(Product).get(lot.sku_id)
            product_name = product.name if product else lot.sku_id
            severity = "critical" if days_left <= 2 else ("warning" if days_left <= 4 else "info")
            recent_alerts.append({
                "severity": severity,
                "title": f"Lot {lot.lot_number} expires in {days_left}d",
                "detail": f"{product_name} | {lot.current_quantity_lbs:.0f} lbs",
            })

        return jsonify({
            "expiry_risk": {
                "count": expiry_count,
                "value": round(expiry_value, 0),
                "status": expiry_status,
            },
            "slow_movers": {
                "count": slow_count,
                "value": round(slow_value, 0),
                "status": slow_status,
            },
            "route_efficiency": {
                "avg_utilization": int(avg_util),
                "active_routes": active_route_count,
                "status": route_status,
            },
            "margin_opps": {
                "count": margin_count,
                "avg_margin": avg_margin,
                "status": "info",
            },
            "recent_alerts": recent_alerts,
        })
    except Exception as e:
        logging.exception("KPI endpoint error")
        return jsonify({"error": str(e)}), 500


@app.route('/')
def serve_index():
    """Serve the frontend index.html."""
    from flask import send_from_directory
    return send_from_directory(str(PUBLIC_DIR), 'index.html')
