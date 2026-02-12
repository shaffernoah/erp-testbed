"""Demand forecast analyzer -- produces a 14-day daily demand forecast for a
product category using historical order data and LLM reasoning.
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

# JSON output schema the LLM must adhere to.
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "forecast_horizon_days": {"type": "integer"},
        "daily_forecast": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "predicted_lbs": {"type": "number"},
                    "predicted_orders": {"type": "integer"},
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "notes": {"type": "string"},
                },
                "required": ["date", "predicted_lbs", "predicted_orders", "confidence"],
            },
        },
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Key assumptions behind the forecast.",
        },
        "risks": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Factors that could cause the forecast to miss.",
        },
        "weekly_summary": {
            "type": "object",
            "properties": {
                "week_1_total_lbs": {"type": "number"},
                "week_2_total_lbs": {"type": "number"},
            },
        },
    },
    "required": [
        "category",
        "forecast_horizon_days",
        "daily_forecast",
        "assumptions",
        "risks",
    ],
}


class DemandForecastAnalyzer:
    """Generate a 14-day demand forecast for a product category.

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
        category: str,
        lookback_days: int = 90,
        question: Optional[str] = None,
    ) -> dict:
        """Run the demand-forecast analysis.

        Parameters
        ----------
        category : str
            Product category (e.g. ``"BEEF"``, ``"PORK"``).
        lookback_days : int
            Number of historical days to include in context.
        question : str | None
            Override the default analysis question.

        Returns
        -------
        dict
            Structured forecast matching ``OUTPUT_SCHEMA``.
        """
        logger.info("Running demand forecast for category=%s lookback=%d", category, lookback_days)

        data = self.context.get_demand_context(category, lookback_days=lookback_days)

        default_question = (
            f"Based on the historical daily order volumes for the {category} category, "
            f"produce a 14-day daily demand forecast starting from tomorrow.  "
            f"Consider day-of-week patterns, any visible trends, and seasonal "
            f"factors.  For each day, provide predicted pounds, predicted order "
            f"count, and a confidence level (high / medium / low).  Also list "
            f"your key assumptions and the biggest risks to the forecast."
        )

        messages = self.prompts.build_analysis_prompt(
            analyzer_type="demand_forecast",
            data_context=data,
            question=question or default_question,
            output_schema=OUTPUT_SCHEMA,
        )

        result = self.llm.complete_json(messages, temperature=ANALYSIS_DEFAULT_TEMPERATURE)
        logger.info("Demand forecast complete for %s", category)
        return result
