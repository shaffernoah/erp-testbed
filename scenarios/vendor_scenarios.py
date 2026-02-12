"""Vendor-side test scenarios."""

from scenarios.runner import Scenario

VENDOR_SCENARIOS = [
    Scenario(
        id="V1",
        name="Demand Forecast",
        description="Forecast Prime Ribeye demand for the next 2 weeks",
        persona="vendor_ops",
        user_message="What is the demand forecast for USDA Prime Ribeye for the next 2 weeks? Include any seasonal factors.",
        expected_tools=["query_database"],
        expected_output_keys=["forecast", "confidence", "factors"],
    ),
    Scenario(
        id="V2",
        name="Churn Risk Detection",
        description="Identify top accounts showing churn signals",
        persona="vendor_ops",
        user_message="Which of our top-50 accounts by revenue show signs of churn risk? Look at order frequency changes and payment delays.",
        expected_tools=["query_database"],
        expected_output_keys=["at_risk_accounts", "risk_factors"],
    ),
    Scenario(
        id="V3",
        name="Spoilage Risk Assessment",
        description="Identify inventory at risk of expiring in 7 days",
        persona="vendor_ops",
        user_message="What inventory is at risk of expiring in the next 7 days? Suggest actions for each at-risk lot.",
        expected_tools=["query_database", "alert_triggers"],
        expected_output_keys=["at_risk_lots", "suggested_actions"],
    ),
    Scenario(
        id="V4",
        name="Campaign Generation",
        description="Generate a Cari reward campaign to move excess pork belly",
        persona="vendor_sales",
        user_message="Generate a Cari rewards campaign to move excess pork belly inventory before it expires. Target restaurants that have ordered pork belly before.",
        expected_tools=["query_database", "campaign_generator"],
        expected_output_keys=["campaign"],
    ),
]
