"""Churn prediction analyzer -- estimates the probability that a customer
account will churn and identifies the key risk factors driving the prediction.
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
        "churn_probability": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Probability of churn within the next 90 days (0.0 to 1.0).",
        },
        "churn_risk_label": {
            "type": "string",
            "enum": ["low", "moderate", "high", "critical"],
            "description": "low <0.2, moderate 0.2-0.4, high 0.4-0.7, critical >0.7",
        },
        "risk_factors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "factor": {"type": "string"},
                    "signal": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "data_point": {"type": "string"},
                },
                "required": ["factor", "signal", "severity"],
            },
            "description": "Factors contributing to churn risk, ordered by impact.",
        },
        "positive_signals": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Factors that reduce churn risk for this customer.",
        },
        "retention_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "urgency": {
                        "type": "string",
                        "enum": ["immediate", "this_week", "this_month"],
                    },
                    "owner": {
                        "type": "string",
                        "enum": ["sales_rep", "account_manager", "operations", "finance"],
                    },
                    "rationale": {"type": "string"},
                },
                "required": ["action", "urgency", "owner"],
            },
        },
        "comparable_accounts": {
            "type": "string",
            "description": "Brief note on how this account compares to similar ones.",
        },
    },
    "required": [
        "customer_id",
        "churn_probability",
        "churn_risk_label",
        "risk_factors",
        "positive_signals",
        "retention_actions",
    ],
}


class ChurnPredictionAnalyzer:
    """Predict churn probability for a customer account.

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
        """Run churn-prediction analysis for a customer.

        Parameters
        ----------
        customer_id : str
            The customer account to evaluate.
        question : str | None
            Override the default analysis question.

        Returns
        -------
        dict
            Structured churn prediction matching ``OUTPUT_SCHEMA``.
        """
        logger.info("Running churn prediction for customer %s", customer_id)

        data = self.context.get_churn_context(customer_id)

        default_question = (
            f"Evaluate the churn risk for customer {customer_id} over the "
            f"next 90 days.  Examine the following signals:\n\n"
            f"1. **Order frequency trend** -- Is the customer ordering less "
            f"frequently than their historical pattern?\n"
            f"2. **Revenue trajectory** -- Is monthly spend declining month "
            f"over month?\n"
            f"3. **Payment behaviour** -- Are payments slowing?  Is AR aging "
            f"deteriorating?\n"
            f"4. **Product mix narrowing** -- Has the customer reduced the "
            f"number of categories they buy from?\n"
            f"5. **Recency** -- How long since the last order compared to "
            f"their typical order interval?\n"
            f"6. **Engagement** -- Cari enrollment status, lifetime value "
            f"trajectory.\n\n"
            f"Return a churn probability (0.0 to 1.0) with a risk label, "
            f"ordered risk factors with supporting data points, any positive "
            f"retention signals, and specific recommended retention actions "
            f"with urgency and suggested owner."
        )

        messages = self.prompts.build_analysis_prompt(
            analyzer_type="churn_prediction",
            data_context=data,
            question=question or default_question,
            output_schema=OUTPUT_SCHEMA,
        )

        result = self.llm.complete_json(messages, temperature=ANALYSIS_DEFAULT_TEMPERATURE)
        logger.info(
            "Churn prediction complete for %s -- probability=%.2f risk=%s",
            customer_id,
            result.get("churn_probability", -1),
            result.get("churn_risk_label", "N/A"),
        )
        return result
