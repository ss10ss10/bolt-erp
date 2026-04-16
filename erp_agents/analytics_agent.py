from pathlib import Path

from agents import Agent

from context import ERPContext
from tools.analytics_tools import (
    get_executive_kpi_dashboard,
    get_operational_health_summary,
    get_revenue_vs_cost_trend,
    get_top_products_by_revenue,
)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "analytics_agent.md"


def build() -> Agent[ERPContext]:
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    return Agent[ERPContext](
        name="Analytics BI Agent",
        handoff_description="Handles cross-domain KPI dashboards, executive summaries, revenue vs cost trends, top products, and operational health snapshots.",
        instructions=instructions,
        tools=[
            get_executive_kpi_dashboard,
            get_revenue_vs_cost_trend,
            get_top_products_by_revenue,
            get_operational_health_summary,
        ],
        model="gpt-4o",
    )
