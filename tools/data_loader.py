"""CSV data loading with a simple module-level cache.

We intentionally avoid @st.cache_data here so these functions can be
called both from the agent tools layer and from standalone scripts.
"""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"

_cache: dict[str, pd.DataFrame] = {}


def load(name: str) -> pd.DataFrame:
    """Load a CSV from the data/ folder by name (without .csv extension).

    Returns an empty DataFrame if the file does not exist yet, so agents
    degrade gracefully before the user has pasted in their data.
    """
    if name in _cache:
        logger.debug("cache hit  → %s  (%d rows)", name, len(_cache[name]))
        return _cache[name]

    path = DATA_DIR / f"{name}.csv"
    if not path.exists():
        logger.warning("CSV not found: %s.csv  (returning empty DataFrame)", name)
        return pd.DataFrame()

    df = pd.read_csv(path, low_memory=False)
    _cache[name] = df
    logger.info("loaded CSV  → %s  (%d rows, %d cols)", name, len(df), len(df.columns))
    return df


def reload(name: str) -> pd.DataFrame:
    """Force a re-read from disk (useful after the user drops in a new CSV)."""
    logger.info("reloading CSV from disk → %s", name)
    _cache.pop(name, None)
    return load(name)


def available_tables() -> list[str]:
    """Return the names of all CSVs currently present in data/."""
    tables = [p.stem for p in sorted(DATA_DIR.glob("*.csv"))]
    logger.debug("available tables: %s", tables)
    return tables
