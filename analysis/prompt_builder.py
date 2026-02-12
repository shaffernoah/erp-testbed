"""Prompt builder -- assembles system + user messages for the LLM analyzers.

Converts data context dicts (produced by ``ContextBuilder``) into structured
Markdown tables and wraps them with domain-specific system instructions and
an explicit output schema so the LLM returns parseable JSON.
"""

from __future__ import annotations

import json
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Domain system prompts keyed by analyzer type
# ---------------------------------------------------------------------------

SYSTEM_PROMPTS: dict[str, str] = {
    "demand_forecast": (
        "You are a senior demand-planning analyst specialising in perishable "
        "protein distribution for the New York tri-state area.  You work for "
        "Pat LaFrieda Meat Purveyors, a premium meat distributor serving "
        "restaurants, hotels, and retail accounts.\n\n"
        "Your expertise includes:\n"
        "- Seasonal and day-of-week demand patterns for beef, pork, poultry, "
        "lamb/veal, blends, and charcuterie\n"
        "- Restaurant ordering cycles (weekday vs. weekend prep)\n"
        "- Holiday and event-driven spikes (grilling season, Thanksgiving, "
        "holiday parties)\n"
        "- Weather impacts on protein demand\n\n"
        "Given historical order data, produce a 14-day daily demand forecast.  "
        "Always return valid JSON matching the requested schema."
    ),
    "margin_analysis": (
        "You are a financial analyst specialising in gross margin optimisation "
        "for a premium meat distribution business.  You understand catch-weight "
        "pricing, USDA grade premiums, customer-tier pricing strategies, and "
        "the relationship between volume, mix, and margin.\n\n"
        "Analyse the provided margin data and identify:\n"
        "- Margin trends and anomalies\n"
        "- Underperforming categories or customers\n"
        "- Pricing improvement opportunities\n"
        "- Volume/mix effects on blended margin\n\n"
        "Always return valid JSON matching the requested schema."
    ),
    "customer_health": (
        "You are a customer-success analyst for Pat LaFrieda Meat Purveyors.  "
        "You evaluate the overall health of a restaurant or hospitality "
        "account by examining ordering patterns, payment behaviour, AR aging, "
        "product mix breadth, and engagement signals.\n\n"
        "Produce a health score from 0 to 100 and a detailed breakdown "
        "explaining each factor.  A score above 80 is 'Healthy', 50-80 is "
        "'Needs Attention', and below 50 is 'At Risk'.\n\n"
        "Always return valid JSON matching the requested schema."
    ),
    "spoilage_risk": (
        "You are an inventory-risk analyst for a perishable-goods distributor.  "
        "You assess lots approaching their expiration date against current "
        "demand velocity to quantify spoilage exposure and recommend "
        "actions -- such as targeted promotions, price reductions, rerouting "
        "to high-velocity accounts, or write-off.\n\n"
        "Rank each at-risk lot by urgency and provide specific, actionable "
        "recommendations.\n\n"
        "Always return valid JSON matching the requested schema."
    ),
    "pricing_benchmark": (
        "You are a pricing-strategy analyst for a premium meat distributor.  "
        "You compare the prices charged to different customers for the same "
        "SKUs, taking into account customer tier, volume commitments, contract "
        "types, and market conditions.\n\n"
        "Identify pricing inconsistencies, customers paying significantly "
        "above or below the median, and opportunities for price optimisation "
        "without jeopardising customer relationships.\n\n"
        "Always return valid JSON matching the requested schema."
    ),
    "churn_prediction": (
        "You are a customer-retention analyst for Pat LaFrieda Meat Purveyors.  "
        "You evaluate churn risk for restaurant and hospitality accounts by "
        "analysing order-frequency trends, revenue trajectory, payment "
        "behaviour changes, product-mix narrowing, and AR deterioration.\n\n"
        "Return a churn probability between 0.0 and 1.0 with supporting "
        "risk factors and recommended retention actions.\n\n"
        "Always return valid JSON matching the requested schema."
    ),
}


class PromptBuilder:
    """Assembles LLM prompt messages from data context and analysis type."""

    # ------------------------------------------------------------------
    # Markdown table formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _dict_list_to_markdown(rows: list[dict], title: str | None = None) -> str:
        """Convert a list of flat dicts to a Markdown table string."""
        if not rows:
            return f"### {title}\n_No data available._\n" if title else "_No data available._\n"

        headers = list(rows[0].keys())
        lines: list[str] = []
        if title:
            lines.append(f"### {title}")
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for row in rows:
            vals = [str(row.get(h, "")) for h in headers]
            lines.append("| " + " | ".join(vals) + " |")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _single_dict_to_markdown(data: dict, title: str | None = None) -> str:
        """Render a single dict as a key-value Markdown table."""
        if not data:
            return f"### {title}\n_No data available._\n" if title else "_No data available._\n"

        lines: list[str] = []
        if title:
            lines.append(f"### {title}")
        lines.append("| Field | Value |")
        lines.append("| --- | --- |")
        for k, v in data.items():
            lines.append(f"| {k} | {v} |")
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Context formatter
    # ------------------------------------------------------------------

    def format_context(self, data_context: dict) -> str:
        """Turn a data-context dict into a readable Markdown string.

        The method inspects each value: ``list[dict]`` becomes a table,
        ``dict`` becomes a key-value table, and scalars are rendered inline.
        """
        parts: list[str] = ["## Data Context\n"]
        for key, value in data_context.items():
            title = key.replace("_", " ").title()
            if isinstance(value, list) and value and isinstance(value[0], dict):
                parts.append(self._dict_list_to_markdown(value, title=title))
            elif isinstance(value, dict):
                parts.append(self._single_dict_to_markdown(value, title=title))
            elif isinstance(value, list):
                parts.append(f"### {title}\n{', '.join(str(v) for v in value)}\n")
            else:
                parts.append(f"**{title}:** {value}\n")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Public prompt builder
    # ------------------------------------------------------------------

    def build_analysis_prompt(
        self,
        analyzer_type: str,
        data_context: dict,
        question: Optional[str] = None,
        output_schema: Optional[dict] = None,
    ) -> list[dict]:
        """Build the ``messages`` array for an LLM analysis request.

        Parameters
        ----------
        analyzer_type : str
            Key into ``SYSTEM_PROMPTS`` (e.g. ``"demand_forecast"``).
        data_context : dict
            Data produced by a ``ContextBuilder`` method.
        question : str | None
            An explicit analysis question / instruction appended to the user
            message.  If *None*, a default question for the analyzer type is
            used.
        output_schema : dict | None
            A JSON-schema-like dict describing the expected response shape.
            When provided it is appended to the user message to guide the LLM.

        Returns
        -------
        list[dict]
            ``[{"role": "system", ...}, {"role": "user", ...}]``
        """
        system_text = SYSTEM_PROMPTS.get(analyzer_type, SYSTEM_PROMPTS.get("margin_analysis", ""))

        # Format the data context.
        context_md = self.format_context(data_context)

        # Build the user message.
        user_parts: list[str] = [context_md]

        if question:
            user_parts.append(f"\n## Analysis Request\n{question}\n")

        if output_schema:
            user_parts.append(
                "\n## Required Output Format\n"
                "Respond with **only** valid JSON matching this schema:\n"
                f"```json\n{json.dumps(output_schema, indent=2)}\n```\n"
            )

        user_text = "\n".join(user_parts)

        return [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ]
