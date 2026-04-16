from pathlib import Path

from agents import Agent

from context import ERPContext
from tools.manufacturing_tools import (
    get_bom,
    get_manufacturing_orders,
    get_production_summary,
    get_quality_report,
)

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "manufacturing_agent.md"


def build() -> Agent[ERPContext]:
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")
    return Agent[ERPContext](
        name="Manufacturing Agent",
        handoff_description="Handles production orders, bill of materials (BOM), work centre operations, and quality/yield analysis.",
        instructions=instructions,
        tools=[
            get_manufacturing_orders,
            get_production_summary,
            get_bom,
            get_quality_report,
        ],
        model="gpt-4o",
    )
