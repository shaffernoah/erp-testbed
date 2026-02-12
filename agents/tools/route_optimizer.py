"""Tool: route_optimizer -- delivery route efficiency analyzer.

Analyses delivery route performance by comparing estimated vs actual stops,
duration, geographic clustering, and truck capacity utilization.  Identifies
opportunities to increase drops per route through truck reallocation,
route consolidation, or stop resequencing.

Pattern: Analyze routes -> Identify inefficiencies -> Recommend changes
         -> Quantify savings (extra stops/week, fuel, labor)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from database.models import Customer, Invoice, Route
from agents.tool_registry import Tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Truck capacity heuristics
# ---------------------------------------------------------------------------

_TRUCK_CAPACITY = {
    "16FT_BOX": {"max_lbs": 3000, "max_stops": 15, "label": "16ft Box Truck"},
    "20FT_BOX": {"max_lbs": 5000, "max_stops": 20, "label": "20ft Box Truck"},
    "26FT_BOX": {"max_lbs": 8000, "max_stops": 25, "label": "26ft Box Truck"},
    "SPRINTER": {"max_lbs": 2000, "max_stops": 18, "label": "Sprinter Van"},
    "REFRIGERATED": {"max_lbs": 6000, "max_stops": 20, "label": "Refrigerated Truck"},
}

# Average cost per route-hour (driver + fuel + vehicle)
_COST_PER_ROUTE_HOUR = 85.0
# Average revenue per delivery stop
_AVG_REVENUE_PER_STOP = 450.0


# ---------------------------------------------------------------------------
# Core tool function
# ---------------------------------------------------------------------------

def route_optimize(session: Session) -> dict:
    """Analyze delivery route efficiency and recommend optimizations.

    The optimizer considers:
    1. **Utilization** -- actual stops vs estimated capacity per route.
    2. **Stops per hour** -- delivery throughput efficiency.
    3. **Geographic overlap** -- routes serving same zone that could merge.
    4. **Truck mismatch** -- wrong truck size for actual volume.

    Returns
    -------
    dict with ``recommendations`` list and ``summary`` stats.
    """
    today = date.today()
    lookback = today - timedelta(days=14)
    recommendations: List[dict] = []

    # ------------------------------------------------------------------
    # 1. Get all active routes
    # ------------------------------------------------------------------
    routes = (
        session.query(Route)
        .filter(Route.is_active == True)
        .all()
    )

    if not routes:
        return {
            "status": "success",
            "scan_date": str(today),
            "message": "No active routes found.",
            "recommendations": [],
            "summary": {},
        }

    # ------------------------------------------------------------------
    # 2. Get actual delivery performance (last 14 days)
    # ------------------------------------------------------------------
    delivery_stats = (
        session.query(
            Invoice.route_id,
            func.count(func.distinct(Invoice.customer_id)).label("distinct_customers"),
            func.count(Invoice.invoice_id).label("total_deliveries"),
            func.sum(Invoice.total_amount).label("total_revenue"),
            func.avg(Invoice.total_amount).label("avg_delivery_value"),
        )
        .filter(
            Invoice.invoice_date >= lookback,
            Invoice.route_id.isnot(None),
        )
        .group_by(Invoice.route_id)
        .all()
    )

    stats_by_route: Dict[str, dict] = {}
    for row in delivery_stats:
        # Normalize to daily averages (14-day window, ~12 delivery days)
        delivery_days = 12
        stats_by_route[row.route_id] = {
            "distinct_customers": int(row.distinct_customers or 0),
            "total_deliveries": int(row.total_deliveries or 0),
            "avg_daily_stops": round(int(row.total_deliveries or 0) / delivery_days, 1),
            "total_revenue": round(float(row.total_revenue or 0), 2),
            "avg_delivery_value": round(float(row.avg_delivery_value or 0), 2),
        }

    # ------------------------------------------------------------------
    # 3. Get delivery zone distribution per route
    # ------------------------------------------------------------------
    zone_dist = (
        session.query(
            Invoice.route_id,
            Customer.delivery_zone,
            func.count(Invoice.invoice_id).label("deliveries"),
        )
        .join(Customer, Invoice.customer_id == Customer.customer_id)
        .filter(
            Invoice.invoice_date >= lookback,
            Invoice.route_id.isnot(None),
            Customer.delivery_zone.isnot(None),
        )
        .group_by(Invoice.route_id, Customer.delivery_zone)
        .all()
    )

    zones_by_route: Dict[str, List[str]] = defaultdict(list)
    for row in zone_dist:
        zones_by_route[row.route_id].append(row.delivery_zone)

    # ------------------------------------------------------------------
    # 4. Analyze each route
    # ------------------------------------------------------------------
    route_data: List[dict] = []
    for route in routes:
        stats = stats_by_route.get(route.route_id, {})
        avg_daily_stops = stats.get("avg_daily_stops", 0)
        estimated_stops = route.estimated_stops or 15
        estimated_hours = route.estimated_duration_hours or 8
        truck_type = (route.truck_type or "20FT_BOX").upper().replace(" ", "_")
        truck_info = _TRUCK_CAPACITY.get(truck_type, _TRUCK_CAPACITY["20FT_BOX"])

        utilization = avg_daily_stops / estimated_stops if estimated_stops > 0 else 0
        stops_per_hour = avg_daily_stops / estimated_hours if estimated_hours > 0 else 0

        entry = {
            "route_id": route.route_id,
            "route_name": route.route_name,
            "zone": route.zone,
            "truck_type": truck_type,
            "truck_label": truck_info["label"],
            "estimated_stops": estimated_stops,
            "estimated_hours": estimated_hours,
            "avg_daily_stops": avg_daily_stops,
            "utilization": round(utilization, 2),
            "stops_per_hour": round(stops_per_hour, 2),
            "avg_delivery_value": stats.get("avg_delivery_value", 0),
            "total_14d_revenue": stats.get("total_revenue", 0),
            "delivery_zones": zones_by_route.get(route.route_id, []),
        }
        route_data.append(entry)

        # --- Underutilized routes ---
        if utilization < 0.7 and avg_daily_stops > 0:
            unused_capacity = estimated_stops - avg_daily_stops
            weekly_opportunity = round(unused_capacity * 6, 0)  # 6 delivery days
            revenue_opportunity = round(weekly_opportunity * _AVG_REVENUE_PER_STOP, 0)

            recommendations.append({
                "issue_type": "UNDERUTILIZED",
                "severity": "HIGH" if utilization < 0.5 else "MEDIUM",
                "route_id": route.route_id,
                "route_name": route.route_name,
                "zone": route.zone,
                "current_metrics": {
                    "avg_daily_stops": avg_daily_stops,
                    "estimated_capacity": estimated_stops,
                    "utilization_pct": round(utilization * 100, 1),
                    "stops_per_hour": round(stops_per_hour, 2),
                },
                "recommendation": (
                    f"Route is at {utilization * 100:.0f}% capacity "
                    f"({avg_daily_stops:.0f} of {estimated_stops} stops). "
                    f"Consider adding {unused_capacity:.0f} stops from adjacent "
                    f"zones or downsizing to a smaller truck to reduce costs."
                ),
                "estimated_impact": {
                    "extra_stops_per_week": weekly_opportunity,
                    "revenue_opportunity_per_week": revenue_opportunity,
                },
            })

        # --- Overloaded routes ---
        if utilization > 1.2:
            overload_pct = round((utilization - 1.0) * 100, 1)
            recommendations.append({
                "issue_type": "OVERLOADED",
                "severity": "HIGH",
                "route_id": route.route_id,
                "route_name": route.route_name,
                "zone": route.zone,
                "current_metrics": {
                    "avg_daily_stops": avg_daily_stops,
                    "estimated_capacity": estimated_stops,
                    "utilization_pct": round(utilization * 100, 1),
                },
                "recommendation": (
                    f"Route is {overload_pct}% over capacity "
                    f"({avg_daily_stops:.0f} stops vs {estimated_stops} estimated). "
                    f"Split into two routes or upgrade to a larger truck to "
                    f"maintain delivery quality and reduce delays."
                ),
                "estimated_impact": {
                    "risk": "Late deliveries, driver fatigue, quality complaints",
                    "excess_stops_per_day": round(avg_daily_stops - estimated_stops, 1),
                },
            })

        # --- Truck mismatch ---
        truck_max_stops = truck_info["max_stops"]
        if avg_daily_stops > truck_max_stops * 1.1:
            # Small truck on big route
            better_truck = None
            for t_type, t_info in _TRUCK_CAPACITY.items():
                if t_info["max_stops"] >= avg_daily_stops and t_type != truck_type:
                    better_truck = t_info
                    better_truck_type = t_type
                    break
            if better_truck:
                recommendations.append({
                    "issue_type": "TRUCK_MISMATCH",
                    "severity": "MEDIUM",
                    "route_id": route.route_id,
                    "route_name": route.route_name,
                    "zone": route.zone,
                    "current_metrics": {
                        "truck_type": truck_info["label"],
                        "truck_max_stops": truck_max_stops,
                        "avg_daily_stops": avg_daily_stops,
                    },
                    "recommendation": (
                        f"Currently using {truck_info['label']} (max {truck_max_stops} stops) "
                        f"but averaging {avg_daily_stops:.0f} stops/day. "
                        f"Upgrade to {better_truck['label']} for better capacity match."
                    ),
                    "estimated_impact": {
                        "recommended_truck": better_truck["label"],
                        "capacity_headroom": better_truck["max_stops"] - avg_daily_stops,
                    },
                })

    # ------------------------------------------------------------------
    # 5. Geographic overlap detection (merge candidates)
    # ------------------------------------------------------------------
    zone_routes: Dict[str, List[dict]] = defaultdict(list)
    for rd in route_data:
        if rd["zone"]:
            zone_routes[rd["zone"]].append(rd)

    for zone, zone_route_list in zone_routes.items():
        if len(zone_route_list) < 2:
            continue

        # Find pairs where both are underutilized
        for i, r1 in enumerate(zone_route_list):
            for r2 in zone_route_list[i + 1:]:
                combined_stops = r1["avg_daily_stops"] + r2["avg_daily_stops"]
                max_single_capacity = max(r1["estimated_stops"], r2["estimated_stops"])

                if (r1["utilization"] < 0.8 and r2["utilization"] < 0.8
                        and combined_stops <= max_single_capacity * 1.1):
                    combined_revenue = r1["total_14d_revenue"] + r2["total_14d_revenue"]
                    hours_saved = min(r1["estimated_hours"], r2["estimated_hours"])
                    weekly_savings = round(hours_saved * _COST_PER_ROUTE_HOUR * 6, 0)

                    recommendations.append({
                        "issue_type": "MERGE_CANDIDATE",
                        "severity": "HIGH",
                        "route_id": f"{r1['route_id']} + {r2['route_id']}",
                        "route_name": f"{r1['route_name']} + {r2['route_name']}",
                        "zone": zone,
                        "current_metrics": {
                            "route_a_stops": r1["avg_daily_stops"],
                            "route_a_utilization": r1["utilization"],
                            "route_b_stops": r2["avg_daily_stops"],
                            "route_b_utilization": r2["utilization"],
                            "combined_stops": round(combined_stops, 1),
                            "max_single_capacity": max_single_capacity,
                        },
                        "recommendation": (
                            f"Both routes serve {zone} at low utilization. "
                            f"Merging would create one route with {combined_stops:.0f} stops "
                            f"(within {max_single_capacity}-stop capacity). "
                            f"Saves one truck + driver, ~${weekly_savings:,.0f}/week."
                        ),
                        "estimated_impact": {
                            "trucks_saved": 1,
                            "weekly_cost_savings": weekly_savings,
                            "annual_cost_savings": round(weekly_savings * 52, 0),
                            "hours_saved_per_day": hours_saved,
                        },
                    })

    # ------------------------------------------------------------------
    # 6. Sort recommendations by severity
    # ------------------------------------------------------------------
    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    recommendations.sort(key=lambda r: severity_order.get(r["severity"], 3))

    # Summary stats
    total_extra_stops = sum(
        r.get("estimated_impact", {}).get("extra_stops_per_week", 0)
        for r in recommendations
    )
    total_weekly_savings = sum(
        r.get("estimated_impact", {}).get("weekly_cost_savings", 0)
        for r in recommendations
    )

    return {
        "status": "success",
        "scan_date": str(today),
        "routes_analyzed": len(route_data),
        "recommendation_count": len(recommendations),
        "recommendations": recommendations,
        "summary": {
            "total_routes_analyzed": len(route_data),
            "issues_found": len(recommendations),
            "by_type": {
                issue: sum(1 for r in recommendations if r["issue_type"] == issue)
                for issue in ["UNDERUTILIZED", "OVERLOADED", "TRUCK_MISMATCH", "MERGE_CANDIDATE"]
                if any(r["issue_type"] == issue for r in recommendations)
            },
            "potential_extra_stops_per_week": round(total_extra_stops, 0),
            "potential_weekly_savings": round(total_weekly_savings, 0),
            "potential_annual_savings": round(total_weekly_savings * 52, 0),
        },
    }


# ---------------------------------------------------------------------------
# Tool definition for registration
# ---------------------------------------------------------------------------

TOOL_DEF = Tool(
    name="route_optimizer",
    description=(
        "Analyze delivery route efficiency by comparing estimated vs actual "
        "stops, duration, and geographic clustering. Identifies underutilized "
        "routes, overloaded routes, truck-size mismatches, and merge candidates "
        "where two low-utilization routes in the same zone could be combined. "
        "Returns specific recommendations with estimated cost savings and "
        "extra stops per week."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    function=route_optimize,
    requires_confirmation=False,
    tags=["ops", "logistics"],
)
