"""Generate daily inventory snapshots for Pat LaFrieda ERP testbed.

For each of the most recent 30 days, creates a snapshot per active lot
recording quantity on hand, weight, reserved vs. available, freshness
score, and storage bin assignments.
"""

from datetime import date, timedelta

from generators.base import rng, make_id
from config.settings import INVENTORY_SNAPSHOT_DAYS
from database.models import Inventory


# ---------------------------------------------------------------------------
# Zone / bin derivation helpers
# ---------------------------------------------------------------------------

# Map storage location prefix to a zone label
_ZONE_MAP = {
    "COOLER":  "COLD_STORAGE",
    "AGING":   "DRY_AGING",
    "FREEZER": "FROZEN",
    "STAGING": "STAGING",
}


def _zone_for_location(location: str) -> str:
    """Derive the zone from a storage location string like 'NJ_COOLER_A'."""
    for key, zone in _ZONE_MAP.items():
        if key in location:
            return zone
    return "COLD_STORAGE"


def _bin_for_location(location: str, lot_index: int) -> str:
    """Assign a deterministic bin within a storage location.

    Format: {location}-R{row:02d}-S{shelf:02d}
    """
    row = (lot_index % 20) + 1
    shelf = (lot_index // 20 % 10) + 1
    return f"{location}-R{str(row).zfill(2)}-S{str(shelf).zfill(2)}"


# ---------------------------------------------------------------------------
# Freshness score
# ---------------------------------------------------------------------------

def _freshness_score(snapshot_date: date, received_date: date, expiration_date: date) -> float:
    """Compute a linear freshness score from 1.0 (at receipt) to 0.0 (at expiry).

    Returns a value clamped to [0.0, 1.0].
    """
    total_life = (expiration_date - received_date).days
    if total_life <= 0:
        return 0.0
    elapsed = (snapshot_date - received_date).days
    score = 1.0 - (elapsed / total_life)
    return round(max(0.0, min(1.0, score)), 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_inventory(session, products, lots) -> list[Inventory]:
    """Create daily inventory snapshots for the most recent 30 days.

    Only lots that are still active (not DEPLETED) on a given snapshot
    date contribute a record.  Lots whose received_date is after the
    snapshot date are excluded (they hadn't arrived yet).

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Active database session.
    products : list[Product]
        Previously generated Product instances.
    lots : list[Lot]
        Previously generated Lot instances.

    Returns
    -------
    list[Inventory]
        The generated Inventory ORM objects.
    """
    today = date.today()

    # Build a quick lookup: sku_id -> Product
    product_map = {p.sku_id: p for p in products}

    # Pre-compute the snapshot date range (most recent N days, inclusive)
    snapshot_dates = [
        today - timedelta(days=d)
        for d in range(INVENTORY_SNAPSHOT_DAYS - 1, -1, -1)
    ]

    inventory_records: list[Inventory] = []

    for lot_idx, lot in enumerate(lots):
        # Skip lots that are fully depleted — they have no remaining stock
        # to snapshot.  (EXPIRED and HOLD lots still have physical inventory.)
        if lot.status == "DEPLETED":
            continue

        product = product_map.get(lot.sku_id)
        if product is None:
            continue

        # Derive storage bin once per lot (bin stays fixed)
        location = lot.storage_location or "NJ_COOLER_A"
        zone = _zone_for_location(location)
        bin_location = _bin_for_location(location, lot_idx)

        unit_cost = getattr(product, "cost_per_lb", 5.0) or 5.0

        for snap_date in snapshot_dates:
            # Only include if the lot had been received by this date
            if lot.received_date and snap_date < lot.received_date:
                continue

            # Only include if the lot had not expired more than 7 days before
            # the snapshot (we keep a short tail for reporting).
            if lot.expiration_date and snap_date > lot.expiration_date + timedelta(days=7):
                continue

            # --- Simulate a gradual drawdown of quantity ---
            total_life = (lot.expiration_date - lot.received_date).days if lot.expiration_date and lot.received_date else 30
            if total_life <= 0:
                total_life = 1
            days_elapsed = (snap_date - lot.received_date).days

            # Linear drawdown from initial to current, with some noise
            progress = min(1.0, days_elapsed / total_life)
            initial = lot.initial_quantity_lbs or 0.0
            final = lot.current_quantity_lbs or 0.0
            simulated_qty = initial - (initial - final) * progress
            # Add a touch of daily noise (within +/- 2%)
            simulated_qty = max(0.0, simulated_qty * (1.0 + float(rng.uniform(-0.02, 0.02))))
            simulated_qty = round(simulated_qty, 2)

            # Weight mirrors quantity (sold by LB)
            weight_on_hand = simulated_qty

            # Reserved: small fraction of available for pending orders
            reserved_pct = float(rng.uniform(0.0, 0.15))
            quantity_reserved = round(simulated_qty * reserved_pct, 2)
            quantity_available = round(simulated_qty - quantity_reserved, 2)

            # Days metrics
            days_in_inventory = days_elapsed
            days_until_expiry = (lot.expiration_date - snap_date).days if lot.expiration_date else None

            # Freshness
            freshness = _freshness_score(
                snap_date,
                lot.received_date,
                lot.expiration_date,
            )

            # Value
            total_value = round(weight_on_hand * unit_cost, 2)

            # Last movement: random recent date up to snap_date
            days_since_move = int(rng.integers(0, min(days_elapsed + 1, 8)))
            last_movement_date = snap_date - timedelta(days=days_since_move)

            inventory = Inventory(
                inventory_id=make_id("INV"),
                sku_id=lot.sku_id,
                lot_id=lot.lot_id,
                location=location,
                zone=zone,
                bin_location=bin_location,
                quantity_on_hand=simulated_qty,
                weight_on_hand_lbs=weight_on_hand,
                quantity_reserved=quantity_reserved,
                quantity_available=quantity_available,
                unit_cost=unit_cost,
                total_value=total_value,
                days_in_inventory=days_in_inventory,
                days_until_expiry=days_until_expiry,
                freshness_score=freshness,
                last_count_date=snap_date,
                last_movement_date=last_movement_date,
                snapshot_date=snap_date,
            )

            inventory_records.append(inventory)

    # Bulk add for performance
    session.add_all(inventory_records)
    return inventory_records
