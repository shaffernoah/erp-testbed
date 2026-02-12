"""Shared utilities for data generators."""

import json
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
from faker import Faker

from config.settings import RANDOM_SEED

# Seeded random state for reproducibility
rng = np.random.default_rng(RANDOM_SEED)
fake = Faker()
Faker.seed(RANDOM_SEED)


def make_id(prefix: str) -> str:
    """Generate a unique ID with prefix, e.g. 'CUST-a1b2c3d4e5f6'."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def make_sequential_id(prefix: str, n: int, width: int = 5) -> str:
    """Generate a sequential ID, e.g. 'CUST-00001'."""
    return f"{prefix}-{str(n).zfill(width)}"


def catch_weight(nominal: float, tolerance_pct: float = 0.10) -> float:
    """Generate a realistic catch weight around a nominal value.

    Uses a normal distribution truncated at +/- tolerance.
    """
    std = nominal * tolerance_pct / 2  # ~95% within tolerance
    weight = rng.normal(nominal, std)
    low = nominal * (1 - tolerance_pct)
    high = nominal * (1 + tolerance_pct)
    return round(float(np.clip(weight, low, high)), 2)


def random_date_between(start: date, end: date) -> date:
    """Return a random date between start and end (inclusive)."""
    delta = (end - start).days
    if delta <= 0:
        return start
    offset = int(rng.integers(0, delta + 1))
    return start + timedelta(days=offset)


def weighted_choice(options: list, weights: list):
    """Choose from options with given weights."""
    probs = np.array(weights, dtype=float)
    probs /= probs.sum()
    idx = rng.choice(len(options), p=probs)
    return options[idx]


def weighted_choices(options: list, weights: list, n: int) -> list:
    """Choose n items from options with given weights (with replacement)."""
    probs = np.array(weights, dtype=float)
    probs /= probs.sum()
    indices = rng.choice(len(options), size=n, p=probs)
    return [options[i] for i in indices]


def jitter(value: float, pct: float = 0.05) -> float:
    """Add small random jitter to a value."""
    factor = 1.0 + rng.uniform(-pct, pct)
    return round(value * factor, 2)


def random_phone() -> str:
    """Generate a realistic NYC-area phone number."""
    area_codes = ["212", "718", "917", "646", "347", "929", "201", "551"]
    area = rng.choice(area_codes)
    return f"({area}) {rng.integers(200,999)}-{rng.integers(1000,9999)}"


def random_zip_for_borough(borough: str) -> str:
    """Generate a plausible zip code for a NYC borough."""
    zip_ranges = {
        "MANHATTAN": (10001, 10282),
        "BROOKLYN": (11201, 11256),
        "QUEENS": (11101, 11697),
        "BRONX": (10451, 10475),
        "NJ": (7001, 7999),
        "WESTCHESTER": (10501, 10710),
        "CT": (6801, 6928),
        "LI": (11501, 11980),
        "OTHER": (10001, 19999),
    }
    low, high = zip_ranges.get(borough, (10001, 19999))
    return str(int(rng.integers(low, high + 1))).zfill(5)


def to_json(obj) -> str:
    """Serialize to JSON string for storage in SQLite text columns."""
    return json.dumps(obj)


def business_days_between(start: date, end: date) -> int:
    """Count business days between two dates."""
    if end < start:
        return -business_days_between(end, start)
    count = 0
    current = start
    while current < end:
        current += timedelta(days=1)
        if current.weekday() < 5:
            count += 1
    return count
