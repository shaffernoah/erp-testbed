"""Orchestrate data generation in dependency order.

Usage:
    python -m database.seed          # Full seed (drops and recreates all tables)
    python -m database.seed --quick  # Quick seed (fewer records for testing)
"""

import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table

from database.connection import reset_database, get_session
from generators.products import generate_products
from generators.suppliers import generate_suppliers
from generators.customers import generate_customers
from generators.routes import generate_routes
from generators.lots import generate_lots
from generators.inventory import generate_inventory
from generators.pricing import generate_pricing
from generators.purchase_orders import generate_purchase_orders
from generators.invoices import generate_invoices
from generators.payments import generate_payments
from generators.quality import generate_quality_records
from generators.campaigns import generate_campaigns
from generators.financial_summaries import generate_financial_summaries

console = Console()


def seed_all():
    """Drop all tables, recreate, and populate with generated data."""
    console.print("\n[bold blue]LaFrieda ERP Testbed — Data Seeding[/bold blue]\n")

    # Reset database
    console.print("[yellow]Resetting database...[/yellow]")
    engine = reset_database()
    session = get_session(engine)

    results = {}
    total_start = time.time()

    # ── Phase 1: Independent entities (no foreign key deps) ──────────
    console.print("\n[bold]Phase 1: Independent entities[/bold]")

    t = time.time()
    products = generate_products(session)
    session.flush()
    results["products"] = len(products)
    console.print(f"  Products:   {len(products):>6}  ({time.time()-t:.1f}s)")

    t = time.time()
    suppliers = generate_suppliers(session)
    session.flush()
    results["suppliers"] = len(suppliers)
    console.print(f"  Suppliers:  {len(suppliers):>6}  ({time.time()-t:.1f}s)")

    t = time.time()
    customers = generate_customers(session)
    session.flush()
    results["customers"] = len(customers)
    console.print(f"  Customers:  {len(customers):>6}  ({time.time()-t:.1f}s)")

    t = time.time()
    routes = generate_routes(session)
    session.flush()
    results["routes"] = len(routes)
    console.print(f"  Routes:     {len(routes):>6}  ({time.time()-t:.1f}s)")

    # ── Phase 2: Entities depending on Phase 1 ───────────────────────
    console.print("\n[bold]Phase 2: Dependent entities[/bold]")

    t = time.time()
    lots = generate_lots(session, products, suppliers)
    session.flush()
    results["lots"] = len(lots)
    console.print(f"  Lots:       {len(lots):>6}  ({time.time()-t:.1f}s)")

    t = time.time()
    inv_records = generate_inventory(session, products, lots)
    session.flush()
    results["inventory"] = len(inv_records)
    console.print(f"  Inventory:  {len(inv_records):>6}  ({time.time()-t:.1f}s)")

    t = time.time()
    pricing = generate_pricing(session, products, customers)
    session.flush()
    results["pricing"] = len(pricing)
    console.print(f"  Pricing:    {len(pricing):>6}  ({time.time()-t:.1f}s)")

    t = time.time()
    pos = generate_purchase_orders(session, products, suppliers)
    session.flush()
    results["purchase_orders"] = len(pos)
    console.print(f"  POs:        {len(pos):>6}  ({time.time()-t:.1f}s)")

    # ── Phase 3: Invoices (links everything) ─────────────────────────
    console.print("\n[bold]Phase 3: Invoices[/bold]")

    t = time.time()
    invoices = generate_invoices(session, products, customers, lots, routes)
    session.flush()
    results["invoices"] = len(invoices)
    console.print(f"  Invoices:   {len(invoices):>6}  ({time.time()-t:.1f}s)")

    # ── Phase 4: Post-invoice entities ───────────────────────────────
    console.print("\n[bold]Phase 4: Post-invoice entities[/bold]")

    t = time.time()
    payments = generate_payments(session, invoices, customers)
    session.flush()
    results["payments"] = len(payments)
    console.print(f"  Payments:   {len(payments):>6}  ({time.time()-t:.1f}s)")

    t = time.time()
    qr = generate_quality_records(session, lots)
    session.flush()
    results["quality_records"] = len(qr)
    console.print(f"  Quality:    {len(qr):>6}  ({time.time()-t:.1f}s)")

    t = time.time()
    camps = generate_campaigns(session, products, customers)
    session.flush()
    results["campaigns"] = len(camps)
    console.print(f"  Campaigns:  {len(camps):>6}  ({time.time()-t:.1f}s)")

    # ── Phase 5: Financial summaries (computed from invoices/payments) ─
    console.print("\n[bold]Phase 5: Financial summaries[/bold]")

    t = time.time()
    fin = generate_financial_summaries(session, invoices, payments, customers)
    session.flush()
    ar_count = len(fin.get("ar_aging", []))
    margin_count = len(fin.get("margin_summaries", []))
    results["ar_aging"] = ar_count
    results["margin_summaries"] = margin_count
    console.print(f"  AR Aging:   {ar_count:>6}  ({time.time()-t:.1f}s)")
    console.print(f"  Margins:    {margin_count:>6}")

    # ── Commit everything ────────────────────────────────────────────
    console.print("\n[yellow]Committing to database...[/yellow]")
    session.commit()
    session.close()

    total_elapsed = time.time() - total_start

    # ── Summary table ────────────────────────────────────────────────
    console.print()
    table = Table(title="Seed Summary")
    table.add_column("Entity", style="cyan")
    table.add_column("Count", justify="right", style="green")
    for entity, count in results.items():
        table.add_row(entity, f"{count:,}")
    console.print(table)
    console.print(f"\n[bold green]Done in {total_elapsed:.1f}s[/bold green]\n")


if __name__ == "__main__":
    seed_all()
