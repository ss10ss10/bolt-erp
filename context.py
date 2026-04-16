from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import plotly.graph_objects as go


@dataclass
class ERPContext:
    """Shared mutable context passed through every agent run.

    Tools append tables and charts here so Streamlit can render them
    after Runner.run() completes, alongside the agent's text response.

    Deduplication is built in: if a tool is called more than once with
    the same result (e.g. due to SDK retry), only one copy is stored.
    """

    tables: list[dict[str, Any]] = field(default_factory=list)
    charts: list[go.Figure] = field(default_factory=list)
    active_agent: str = "Intent Router"

    def add_table(self, title: str, df: pd.DataFrame) -> None:
        """Add a table, skipping duplicates by title."""
        for existing in self.tables:
            if existing["title"] == title:
                return
        self.tables.append({"title": title, "df": df})

    def add_chart(self, fig: go.Figure) -> None:
        """Add a chart, skipping duplicates by title."""
        new_title = fig.layout.title.text if fig.layout.title else ""
        for existing in self.charts:
            existing_title = existing.layout.title.text if existing.layout.title else ""
            if existing_title == new_title:
                return
        self.charts.append(fig)

    def clear(self) -> None:
        self.tables.clear()
        self.charts.clear()
        self.active_agent = "Intent Router"
