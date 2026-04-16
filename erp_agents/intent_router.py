import logging
from pathlib import Path

from agents import Agent

from context import ERPContext

logger = logging.getLogger(__name__)

from erp_agents.analytics_agent import build as build_analytics
from erp_agents.finance_agent import build as build_finance
from erp_agents.inventory_agent import build as build_inventory
from erp_agents.logistics_agent import build as build_logistics
from erp_agents.manufacturing_agent import build as build_manufacturing
from erp_agents.procurement_agent import build as build_procurement
from erp_agents.sales_agent import build as build_sales

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "intent_router.md"


def build() -> Agent[ERPContext]:
    """Build the Intent Router and wire a fully cyclic agent network.

    Every specialist agent receives handoffs to all other specialists so
    the conversation can jump freely between domains without returning to
    the router each time.
    """
    logger.info("Building agent network…")
    instructions = _PROMPT_PATH.read_text(encoding="utf-8")

    # Build all specialist agents first (no cross-handoffs yet)
    sales = build_sales()
    inventory = build_inventory()
    procurement = build_procurement()
    logistics = build_logistics()
    finance = build_finance()
    manufacturing = build_manufacturing()
    analytics = build_analytics()

    all_specialists: list[Agent[ERPContext]] = [
        sales,
        inventory,
        procurement,
        logistics,
        finance,
        manufacturing,
        analytics,
    ]

    logger.info("All specialist agents built: %s", [a.name for a in all_specialists])

    # Wire cyclic handoffs: every specialist can jump to every other specialist.
    # The Agent dataclass uses a plain list for handoffs, so we can mutate it
    # after construction without any issue.
    for agent in all_specialists:
        agent.handoffs = [peer for peer in all_specialists if peer is not agent]

    logger.info("Cyclic handoffs wired — every specialist can reach every peer")

    # The Intent Router can reach all specialists
    router = Agent[ERPContext](
        name="Intent Router",
        instructions=instructions,
        handoffs=all_specialists,
        model="gpt-4o",
    )

    logger.info("Intent Router ready  (handoffs: %d specialists)", len(all_specialists))
    return router
