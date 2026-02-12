"""Generate quality / HACCP records for Pat LaFrieda ERP testbed.

For each inventory lot, creates 1-3 quality records:
  - HACCP_CHECK at receiving
  - TEMP_LOG during storage
  - GRADE_VERIFY for USDA grade confirmation
Lots on HOLD additionally receive a FAIL record with corrective action.
~5 % of temperature readings are intentional out-of-range anomalies.
"""

from datetime import datetime, timedelta

from generators.base import (
    rng,
    make_id,
    fake,
)
from config.lafrieda_profile import TEMP_RANGES, STORAGE_LOCATIONS
from database.models import QualityRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Map storage-location prefix to temp-range key
_LOCATION_TO_ZONE = {
    "NJ_COOLER":      "COOLER",
    "NJ_AGING_ROOM":  "AGING",
    "NJ_FREEZER":     "FREEZER",
    "NJ_STAGING":     "STAGING",
}

_HACCP_POINTS = [
    "RECEIVING_DOCK",
    "COLD_CHAIN_TRANSFER",
    "PRE_STORAGE_INSPECTION",
]

_CRITICAL_LIMITS = {
    "RECEIVING_DOCK":        "Temp <= 40 F within 30 min",
    "COLD_CHAIN_TRANSFER":   "Temp <= 38 F continuous",
    "PRE_STORAGE_INSPECTION": "Visual inspection pass, no off-odor",
}

_CORRECTIVE_ACTIONS = [
    "Product returned to cooler; re-check in 1 hour",
    "Reject lot; notify supplier for replacement",
    "Quarantine lot; escalate to QA manager",
    "Adjust cooler thermostat; re-log after 30 min",
    "Re-grade lot; downgrade USDA classification",
    "Discard affected units; document waste",
]


def _zone_for_location(location: str) -> str:
    """Derive COOLER / AGING / FREEZER / STAGING from the location code."""
    for prefix, zone in _LOCATION_TO_ZONE.items():
        if location and location.startswith(prefix):
            return zone
    return "COOLER"  # default


def _temp_reading(zone: str, anomaly: bool = False) -> float:
    """Generate a temperature reading for the given zone.

    If *anomaly* is True the reading is deliberately out of range.
    """
    low, high = TEMP_RANGES.get(zone, TEMP_RANGES["COOLER"])
    if anomaly:
        # Push 3-8 degrees above the upper bound
        return round(float(rng.uniform(high + 3.0, high + 8.0)), 1)
    return round(float(rng.uniform(low, high)), 1)


def _is_in_range(temp: float, zone: str) -> bool:
    """Return True when temp falls within the zone's acceptable range."""
    low, high = TEMP_RANGES.get(zone, TEMP_RANGES["COOLER"])
    return low <= temp <= high


# ---------------------------------------------------------------------------
# Record builders
# ---------------------------------------------------------------------------

def _make_haccp_record(lot, check_dt: datetime, zone: str) -> dict:
    """Build kwargs for a HACCP_CHECK quality record."""
    haccp_point = str(rng.choice(_HACCP_POINTS))
    is_anomaly = bool(rng.random() < 0.05)
    temp = _temp_reading(zone, anomaly=is_anomaly)
    in_range = _is_in_range(temp, zone)

    return dict(
        record_id=make_id("QR"),
        record_type="HACCP_CHECK",
        lot_id=lot.lot_id,
        sku_id=lot.sku_id,
        location=lot.storage_location,
        check_datetime=check_dt,
        checked_by=fake.name(),
        temperature_f=temp,
        temp_in_range=in_range,
        usda_grade_verified=None,
        grade_matches_expected=None,
        haccp_point=haccp_point,
        critical_limit=_CRITICAL_LIMITS.get(haccp_point),
        actual_value=f"{temp} F",
        corrective_action=None if in_range else str(rng.choice(_CORRECTIVE_ACTIONS)),
        status="PASS" if in_range else "FAIL",
        notes=None,
    )


def _make_temp_log(lot, check_dt: datetime, zone: str) -> dict:
    """Build kwargs for a TEMP_LOG quality record."""
    is_anomaly = bool(rng.random() < 0.05)
    temp = _temp_reading(zone, anomaly=is_anomaly)
    in_range = _is_in_range(temp, zone)

    return dict(
        record_id=make_id("QR"),
        record_type="TEMP_LOG",
        lot_id=lot.lot_id,
        sku_id=lot.sku_id,
        location=lot.storage_location,
        check_datetime=check_dt,
        checked_by=fake.name(),
        temperature_f=temp,
        temp_in_range=in_range,
        usda_grade_verified=None,
        grade_matches_expected=None,
        haccp_point=None,
        critical_limit=None,
        actual_value=f"{temp} F",
        corrective_action=None if in_range else str(rng.choice(_CORRECTIVE_ACTIONS)),
        status="PASS" if in_range else "FAIL",
        notes=None,
    )


def _make_grade_verify(lot, check_dt: datetime) -> dict:
    """Build kwargs for a GRADE_VERIFY quality record."""
    grade = lot.usda_grade or "N/A"
    # ~3 % chance the grade does not match
    matches = bool(rng.random() >= 0.03)

    return dict(
        record_id=make_id("QR"),
        record_type="GRADE_VERIFY",
        lot_id=lot.lot_id,
        sku_id=lot.sku_id,
        location=lot.storage_location,
        check_datetime=check_dt,
        checked_by=fake.name(),
        temperature_f=None,
        temp_in_range=None,
        usda_grade_verified=grade,
        grade_matches_expected=matches,
        haccp_point=None,
        critical_limit=None,
        actual_value=grade,
        corrective_action=None if matches else "Re-grade lot; downgrade USDA classification",
        status="PASS" if matches else "FAIL",
        notes=None if matches else f"Expected {grade}; actual grade did not match",
    )


def _make_hold_fail_record(lot, check_dt: datetime, zone: str) -> dict:
    """Build a mandatory FAIL record for lots with status=HOLD."""
    temp = _temp_reading(zone, anomaly=True)

    return dict(
        record_id=make_id("QR"),
        record_type="HACCP_CHECK",
        lot_id=lot.lot_id,
        sku_id=lot.sku_id,
        location=lot.storage_location,
        check_datetime=check_dt,
        checked_by=fake.name(),
        temperature_f=temp,
        temp_in_range=False,
        usda_grade_verified=None,
        grade_matches_expected=None,
        haccp_point="RECEIVING_DOCK",
        critical_limit=_CRITICAL_LIMITS["RECEIVING_DOCK"],
        actual_value=f"{temp} F",
        corrective_action=str(rng.choice(_CORRECTIVE_ACTIONS)),
        status="FAIL",
        notes=lot.hold_reason or "Lot placed on HOLD pending investigation",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_quality_records(session, lots) -> list[QualityRecord]:
    """Create 1-3 quality records per lot (plus a FAIL for HOLD lots).

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Active database session; generated objects are added but not committed.
    lots : list[Lot]
        Previously generated Lot ORM objects.

    Returns
    -------
    list[QualityRecord]
        The full list of generated QualityRecord ORM objects.
    """
    records: list[QualityRecord] = []

    for lot in lots:
        zone = _zone_for_location(lot.storage_location)

        # Base datetime: received_date at a plausible morning hour
        base_dt = datetime.combine(
            lot.received_date,
            datetime.min.time(),
        ) + timedelta(hours=int(rng.integers(5, 9)))

        # 1) HACCP_CHECK at receiving
        haccp_kwargs = _make_haccp_record(lot, base_dt, zone)
        records.append(QualityRecord(**haccp_kwargs))

        # 2) TEMP_LOG during storage (1-3 days after receiving)
        temp_dt = base_dt + timedelta(
            days=int(rng.integers(1, 4)),
            hours=int(rng.integers(0, 12)),
        )
        temp_kwargs = _make_temp_log(lot, temp_dt, zone)
        records.append(QualityRecord(**temp_kwargs))

        # 3) GRADE_VERIFY (sometimes skipped for non-graded products)
        if lot.usda_grade and lot.usda_grade != "N/A":
            grade_dt = base_dt + timedelta(hours=int(rng.integers(1, 4)))
            grade_kwargs = _make_grade_verify(lot, grade_dt)
            records.append(QualityRecord(**grade_kwargs))

        # 4) Extra FAIL record for HOLD lots
        if lot.status == "HOLD":
            fail_dt = base_dt + timedelta(hours=int(rng.integers(0, 3)))
            fail_kwargs = _make_hold_fail_record(lot, fail_dt, zone)
            records.append(QualityRecord(**fail_kwargs))

    session.add_all(records)
    return records
