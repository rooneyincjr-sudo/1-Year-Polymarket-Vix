"""Project-wide configuration constants for the Polymarket MUI pipeline."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

YEAR = 2024
START_DATE = datetime(YEAR, 1, 1, tzinfo=timezone.utc)
END_DATE = datetime(YEAR, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

MACRO_KEYWORDS = [
    "cpi",
    "inflation",
    "fed",
    "rate",
    "fomc",
    "hike",
    "cut",
    "recession",
    "gdp",
    "unemployment",
    "jobs",
    "nfp",
    "debt ceiling",
    "shutdown",
    "default",
]

DATA_DIR = Path("data")
RAW_DATA = DATA_DIR / "raw"
PROCESSED_DATA = DATA_DIR / "processed"
RESULTS_DIR = Path("results")

GAMMA_API_URL = "https://gamma-api.polymarket.com/markets"
CLOB_HISTORY_URL = "https://clob.polymarket.com/prices-history"

DEFAULT_FIDELITY_MINUTES = 1440
DEFAULT_REQUEST_LIMIT = 100

# Optional mapping for multi-outcome markets where outcomes encode ordered values.
# Keys should match market slugs used in price tables; values map outcome label to numeric code.
OUTCOME_VALUE_MAP = {
    # Example structure:
    # "fed_rate_cut_range": {
    #     "<4.75%": 0,
    #     "4.75%-5%": 1,
    #     "5%-5.25%": 2,
    #     "5.25%-5.5%": 3,
    #     ">5.5%": 4,
    # },
}

MIN_DATA_COMPLETENESS = 0.65

N_SPLITS = 5
VIX_TICKER = "^VIX"
