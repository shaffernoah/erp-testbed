"""Customer health analyzer -- produces a composite health score (0-100) for a
customer account with a detailed breakdown of contributing factors.
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
        "customer_id": {"type": "string"},
        "business_name": {"type": "string"},
        "health_score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "Composite health score: 80+ Healthy, 50-79 Needs Attention, <50 At Risk",
        },
        "health_label": {
            "type": "string",
            "enum": ["Healthy", "Needs Attention", "At Risk"],
        },
        "factor_scores": {
            "type": "object",
            "properties": {
                "order_consistency": {
                    "type": "object",
                    "properties": {
                        "score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "weight": {"type": "number"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["score", "weight", "rationale"],
                },
                "revenue_trend": {
                    "type": "object",
                    "properties": {
                        "score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "weight": {"type": "number"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["score", "weight", "rationale"],
                },
                "payment_behaviour": {
                    "type": "object",
                    "properties": {
                        "score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "weight": {"type": "number"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["score", "weight", "rationale"],
                },
                "product_mix_breadth": {
                    "type": "object",
                    "properties": {
                        "score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "weight": {"type": "number"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["score", "weight", "rationale"],
                },
                "engagement": {
                    "type": "object",
                    "properties": {
                        "score": {"type": "integer", "minimum": 0, "maximum": 100},
                        "weight": {"type": "number"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["score", "weight", "rationale"],
                },
            },
            "required": [
                "order_consistency",
                "revenue_trend",
                "payment_behaviour",
                "product_mix_breadth",
                "engagement",
            ],
        },
        "strengths": {
            "type": "array",
            "items": {"type": "string"},
        },
        "concerns": {
            "type": "array",
            "items": {"type": "string"},
        },
        "recommended_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "expected_impact": {"type": "string"},
                },
                "required": ["action", "priority"],
            },
        },
    },
    "required": [
        "customer_id",
        "health_score",
        "health_label",
        "factor_scores",
        "strengths",
        "concerns",
        "recommended_actions",
    ],
}


class CustomerHealthAnalyzer:
    """Evaluate overall account health for a customer.

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
        customer_id: str,
        question: Optional[str] = None,
    ) -> dict:
        """Run the customer-health analysis.

        Parameters
        ----------
        customer_id : str
            The customer to evaluate.
        question : str | None
            Override the default analysis question.

        Returns
        -------
        dict
            Structured health assessment matching ``OUTPUT_SCHEMA``.
        """
        logger.info("Running customer health analysis for %s", customer_id)

        # Use the churn context because it already includes order/payment trends
        # and category mix -- all of which feed into health scoring.
        data = self.context.get_churn_context(customer_id)

        default_question = (
            f"Evaluate the overall health of customer {customer_id} by "
            f"examining:\n"
            f"1. **Order consistency** -- Are orders regular and in line with "
            f"their historical frequency?\n"
            f"2. **Revenue trend** -- Is monthly revenue growing, stable, or "
            f"declining?\n"
            f"3. **Payment behaviour** -- Are they paying on time?  Is AR "
            f"aging acceptable?\n"
            f"4. **Product mix breadth** -- Are they buying across multiple "
            f"categories or narrowing their mix?\n"
            f"5. **Engagement** -- Cari enrollment, order recency, and "
            f"lifetime value trajectory.\n\n"
            f"Assign a composite health score from 0 to 100.  Scores above "
            f"80 are 'Healthy', 50-79 'Needs Attention', below 50 'At Risk'.  "
            f"Provide factor-level scores, strengths, concerns, and "
            f"recommended actions."
        )

        messages = self.prompts.build_analysis_prompt(
            analyzer_type="customer_health",
            data_context=data,
            question=question or default_question,
            output_schema=OUTPUT_SCHEMA,
        )

        result = self.llm.complete_json(messages, temperature=ANALYSIS_DEFAULT_TEMPERATURE)
        logger.info(
            "Customer health analysis complete for %s -- score=%s",
            customer_id,
            result.get("health_score", "N/A"),
        )
        return result
