"""Restaurant-side test scenarios."""

from scenarios.runner import Scenario

RESTAURANT_SCENARIOS = [
    Scenario(
        id="R1",
        name="Payment Copilot",
        description="Optimize payment schedule to maximize Cari rewards",
        persona="restaurant",
        user_message="I have open invoices with Pat LaFrieda. Which should I pay today to maximize my Cari rewards? Show me the math.",
        expected_tools=["query_database", "payment_optimizer"],
        expected_output_keys=["payment_schedule", "expected_rewards"],
    ),
    Scenario(
        id="R2",
        name="Invoice Exception Detection",
        description="Flag pricing anomalies in recent invoices",
        persona="restaurant",
        user_message="Review my last 10 invoices for any pricing discrepancies compared to my contracted rates. Flag anything unusual.",
        expected_tools=["query_database"],
        expected_output_keys=["discrepancies"],
    ),
]
