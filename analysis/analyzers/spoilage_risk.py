"""Spoilage risk analyzer -- identifies inventory lots at risk of expiring
before they can be sold and recommends specific mitigation actions.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from analysis.context_builder import ContextBuilder
from analysis.llm_client import LLMClient
from analysis.prompt_builder import PromptBuilder
from config.settings import ANALYSIS_DEFAULT_TEMPERATURE

logger = logging.getLogger(__name__)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "analysis_date": {"type": "string", "description": "YYYY-MM-DD"},
        "total_at_risk_lbs": {"type": "number"},
        "total_at_risk_value_estimate": {"type": "number"},
        "risk_summary": {
            "type": "object",
            "properties": {
                "critical_count": {
                    "type": "integer",
                    "description": "Lots expiring within 3 days",
                },
                "high_count": {
                    "type": "integer",
                    "description": "Lots expiring within 4-7 days",
                },
                "moderate_count": {
                    "type": "integer",
                    "description": "Lots expiring within 8-14 days",
                },
            },
            "required": ["critical_count", "high_count", "moderate_count"],
        },
        "lot_assessments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "lot_id": {"type": "string"},
                    "lot_number": {"type": "string"},
                    "sku_id": {"type": "string"},
                    "product_name": {"type": "string"},
                    "current_quantity_lbs": {"type": "number"},
                    "days_until_expiry": {"type": "integer"},
                    "risk_level": {
                        "type": "string",
                        "enum": ["critical", "high", "moderate"],
                    },
                    "demand_coverage_days": {
                        "type": "number",
                        "description": "At current demand velocity, how many days of supply this lot represents.",
                    },
                    "sellthrough_probability": {
                        "type": "string",
                        "enum": ["likely", "possible", "unlikely"],
                    },
                    "recommended_action": {
                        "type": "string",
                        "enum": [
                            "normal_sell",
                            "targeted_promotion",
                            "price_reduction",
                            "reroute_to_high_velocity_account",
                            "bundle_deal",
                            "donate",
                            "write_off",
                        ],
                    },
                    "action_detail": {"type": "string"},
                },
                "required": [
                    "lot_id",
                    "sku_id",
                    "days_until_expiry",
                    "risk_level",
                    "sellthrough_probability",
                    "recommended_action",
                    "action_detail",
                ],
            },
        },
        "aggregate_recommendations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "High-level recommendations to reduce spoilage exposure.",
        },
    },
    "required": [
        "analysis_date",
        "total_at_risk_lbs",
        "risk_summary",
        "lot_assessments",
        "aggregate_recommendations",
    ],
}


class SpoilageRiskAnalyzer:
    """Assess and triage inventory lots approaching expiration.

    Parameters
    ----------
    session : sqlalchemy.orm.Session
        Active database session.
    llm_client : LLMClient
        Configured LLM client instance.
    """

    def __init__(self, session: Session, llm_client: LLMClient):
        self.session = session
        self.llm = llm_client
        self.context = ContextBuilder(session)
        self.prompts = PromptBuilder()

    def analyze(
        self,
        question: Optional[str] = None,
    ) -> dict:
        """Run spoilage-risk analysis across all inventory.

        Returns
        -------
        dict
            Structured risk assessment matching ``OUTPUT_SCHEMA``.
        """
        logger.info("Running spoilage risk analysis")

        data = self.context.get_inventory_risk()

        default_question = (
            "Review every at-risk lot listed above.  For each lot:\n"
            "1. Classify the risk level (critical / high / moderate) based on "
            "days until expiry.\n"
            "2. Compare the lot's remaining quantity against the demand "
            "velocity for that SKU to estimate whether it can be sold through "
            "in time.\n"
            "3. Recommend a specific action: normal sell-through (if demand "
            "covers it), targeted promotion to high-velocity accounts, price "
            "reduction, bundle deal, donation, or write-off.\n"
            "4. Provide a brief action detail explaining *why* and *how* to "
            "execute the recommendation.\n\n"
            "Also compute aggregate totals and give high-level "
            "recommendations for reducing future spoilage exposure."
        )

        messages = self.prompts.build_analysis_prompt(
            analyzer_type="spoilage_risk",
            data_context=data,
            question=question or default_question,
            output_schema=OUTPUT_SCHEMA,
        )

        result = self.llm.complete_json(messages, temperature=ANALYSIS_DEFAULT_TEMPERATURE)
        logger.info(
            "Spoilage risk analysis complete -- %d lots assessed",
            len(result.get("lot_assessments", [])),
        )
        return result
