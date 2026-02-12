"""Generate delivery routes covering the NYC metro area."""

from generators.base import rng, fake, to_json
from config.settings import NUM_ROUTES
from database.models import Route


# Hardcoded route definitions representing LaFrieda's real delivery network.
# Each tuple: (route_id, name, zone, subzone, days, departure, stops, duration, truck_type)
_ROUTE_DEFS = [
    # --- Manhattan (8) ---
    ("RT-MAN-01", "Manhattan Midtown AM", "MANHATTAN", "MIDTOWN",
     ["MON", "TUE", "WED", "THU", "FRI"], "04:00", 25, 4.5, "REFRIGERATED_26FT"),
    ("RT-MAN-02", "Manhattan Midtown PM", "MANHATTAN", "MIDTOWN",
     ["MON", "WED", "FRI"], "10:00", 15, 3.5, "REFRIGERATED_16FT"),
    ("RT-MAN-03", "Manhattan Downtown AM", "MANHATTAN", "DOWNTOWN",
     ["MON", "TUE", "WED", "THU", "FRI"], "04:30", 20, 4.0, "REFRIGERATED_26FT"),
    ("RT-MAN-04", "Manhattan UES", "MANHATTAN", "UES",
     ["TUE", "THU", "SAT"], "05:00", 15, 3.5, "REFRIGERATED_26FT"),
    ("RT-MAN-05", "Manhattan UWS", "MANHATTAN", "UWS",
     ["MON", "WED", "FRI"], "05:00", 12, 3.0, "REFRIGERATED_16FT"),
    ("RT-MAN-06", "Manhattan Harlem", "MANHATTAN", "HARLEM",
     ["TUE", "THU"], "06:00", 8, 2.5, "REFRIGERATED_16FT"),
    ("RT-MAN-07", "Manhattan FiDi/Tribeca", "MANHATTAN", "DOWNTOWN",
     ["MON", "WED", "FRI"], "04:00", 18, 4.0, "REFRIGERATED_26FT"),
    ("RT-MAN-08", "Manhattan Chelsea/Meatpacking", "MANHATTAN", "MIDTOWN",
     ["MON", "TUE", "WED", "THU", "FRI", "SAT"], "04:00", 22, 4.0, "REFRIGERATED_26FT"),

    # --- Brooklyn (4) ---
    ("RT-BKN-01", "Brooklyn Williamsburg/Greenpoint", "BROOKLYN", "WILLIAMSBURG",
     ["MON", "WED", "FRI"], "05:00", 15, 3.5, "REFRIGERATED_26FT"),
    ("RT-BKN-02", "Brooklyn DUMBO/Heights", "BROOKLYN", "DUMBO",
     ["TUE", "THU", "SAT"], "05:30", 12, 3.0, "REFRIGERATED_16FT"),
    ("RT-BKN-03", "Brooklyn Park Slope/Prospect", "BROOKLYN", "PARK_SLOPE",
     ["MON", "WED", "FRI"], "05:30", 10, 3.0, "REFRIGERATED_16FT"),
    ("RT-BKN-04", "Brooklyn Bushwick/Bed-Stuy", "BROOKLYN", "BUSHWICK",
     ["TUE", "THU"], "06:00", 8, 2.5, "REFRIGERATED_16FT"),

    # --- Queens (3) ---
    ("RT-QNS-01", "Queens Astoria/LIC", "QUEENS", "ASTORIA",
     ["MON", "WED", "FRI"], "05:00", 12, 3.0, "REFRIGERATED_26FT"),
    ("RT-QNS-02", "Queens Flushing", "QUEENS", "FLUSHING",
     ["TUE", "THU"], "06:00", 8, 2.5, "REFRIGERATED_16FT"),
    ("RT-QNS-03", "Queens Forest Hills/Rego Park", "QUEENS", "FOREST_HILLS",
     ["WED", "FRI"], "06:00", 6, 2.0, "REFRIGERATED_16FT"),

    # --- NJ (4) ---
    ("RT-NJM-01", "NJ Hoboken/JC", "NJ", "HOBOKEN",
     ["MON", "TUE", "WED", "THU", "FRI"], "05:00", 18, 3.5, "REFRIGERATED_26FT"),
    ("RT-NJM-02", "NJ Bergen County", "NJ", "BERGEN",
     ["MON", "WED", "FRI"], "06:00", 12, 3.5, "REFRIGERATED_26FT"),
    ("RT-NJM-03", "NJ Princeton/Central", "NJ", "CENTRAL",
     ["TUE", "THU"], "05:30", 8, 4.0, "REFRIGERATED_26FT"),
    ("RT-NJM-04", "NJ Shore", "NJ", "SHORE",
     ["MON", "THU"], "04:30", 10, 5.0, "REFRIGERATED_26FT"),

    # --- Other (4) ---
    ("RT-BRX-01", "Bronx", "BRONX", "BRONX",
     ["TUE", "THU", "SAT"], "06:00", 10, 3.0, "REFRIGERATED_26FT"),
    ("RT-WCH-01", "Westchester", "WESTCHESTER", "WESTCHESTER",
     ["MON", "WED", "FRI"], "05:30", 12, 4.0, "REFRIGERATED_26FT"),
    ("RT-CTF-01", "CT Fairfield", "CT", "FAIRFIELD",
     ["TUE", "FRI"], "05:00", 8, 4.5, "REFRIGERATED_26FT"),
    ("RT-LIS-01", "Long Island", "LI", "LI",
     ["MON", "WED", "FRI"], "05:00", 10, 4.5, "REFRIGERATED_26FT"),
]


def generate_routes(session) -> list[Route]:
    """Create delivery routes and add them to the session.

    Returns the list of Route objects created.
    """
    routes: list[Route] = []

    for idx, (route_id, name, zone, subzone, days, departure,
              stops, duration, truck_type) in enumerate(_ROUTE_DEFS, start=1):
        truck_id = f"TRK-{str(idx).zfill(3)}"

        route = Route(
            route_id=route_id,
            route_name=name,
            zone=zone,
            subzone=subzone,
            delivery_days=to_json(days),
            departure_time=departure,
            estimated_stops=stops,
            estimated_duration_hours=duration,
            driver_name=fake.name(),
            truck_id=truck_id,
            truck_type=truck_type,
            is_active=True,
        )
        session.add(route)
        routes.append(route)

    return routes
