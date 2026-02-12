"""Operations test scenarios."""

from scenarios.runner import Scenario

OPERATIONS_SCENARIOS = [
    Scenario(
        id="O1",
        name="Dispute Resolution",
        description="Handle a quantity discrepancy on a ribeye delivery",
        persona="vendor_ops",
        user_message="We have a dispute on invoice INV-2025-004521. The customer says they ordered 200 lbs of boneless ribeye but only received 180 lbs. Investigate and prepare a credit memo.",
        expected_tools=["query_database", "dispute_handler"],
        expected_output_keys=["dispute_summary", "credit_amount"],
    ),
    Scenario(
        id="O2",
        name="Automated Reorder Check",
        description="Check which beef products need reordering",
        persona="vendor_ops",
        user_message="Check if we need to reorder any beef products based on current inventory levels and upcoming demand. Factor in supplier lead times.",
        expected_tools=["query_database", "reorder_suggestions"],
        expected_output_keys=["reorder_list"],
    ),
]
