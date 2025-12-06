"""Convert Polymarket price series into per-market uncertainty measures."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Mapping

import pandas as pd

# Handle both relative and absolute imports
try:
    from . import config
    from .utils import LOGGER, save_dataframe
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src import config
    from src.utils import LOGGER, save_dataframe


OutcomeMapping = Mapping[str, Mapping[str, float]]


def _identify_market_columns(prices: pd.DataFrame) -> Dict[str, Iterable[str]]:
    columns = list(prices.columns)
    slug_candidates = sorted(
        {col.rsplit("_", 1)[0] for col in columns if "_" in col},
        key=len,
        reverse=True,
    )
    groups: Dict[str, list[str]] = {}
    for col in columns:
        base = col
        for slug in slug_candidates:
            if col == slug or col.startswith(f"{slug}_"):
                base = slug
                break
        groups.setdefault(base, []).append(col)
    return groups


def binary_uncertainty(probs: pd.Series) -> pd.Series:
    return 4 * probs * (1 - probs)


def multi_uncertainty(prob_df: pd.DataFrame, outcome_values: Mapping[str, float]) -> pd.Series:
    normed = prob_df.div(prob_df.sum(axis=1), axis=0)
    encoded = pd.DataFrame({col: normed[col] * outcome_values.get(col.split("_", 1)[-1], idx)
                             for idx, col in enumerate(normed.columns)})
    mu = encoded.sum(axis=1)
    centered = encoded.sub(mu, axis=0)
    variance = (centered ** 2).sum(axis=1)
    return variance


def compute_uncertainty(
    prices: pd.DataFrame,
    outcome_value_map: OutcomeMapping | None = None,
) -> pd.DataFrame:
    outcome_value_map = outcome_value_map or config.OUTCOME_VALUE_MAP
    market_columns = _identify_market_columns(prices)
    uncertainty_series = {}
    for market, cols in market_columns.items():
        subset = prices[cols]
        subset = subset.dropna(how="all")
        if subset.empty:
            continue
        if len(cols) <= 1:
            uncertainty_series[f"{market}_U"] = binary_uncertainty(subset.iloc[:, 0])
        elif len(cols) == 2:
            uncertainty_series[f"{market}_U"] = binary_uncertainty(subset.mean(axis=1))
        else:
            mapping = outcome_value_map.get(market, {})
            uncertainty_series[f"{market}_U"] = multi_uncertainty(subset, mapping)
    uncertainty_df = pd.DataFrame(uncertainty_series)
    uncertainty_df = uncertainty_df.sort_index()
    return uncertainty_df


def process_and_save_uncertainty(
    prices_path=config.RAW_DATA / "polymarket_macro_prices_2024.csv",
    output_path=config.PROCESSED_DATA / "polymarket_uncertainty_2024.csv",
    outcome_value_map: OutcomeMapping | None = None,
) -> pd.DataFrame:
    prices = pd.read_csv(prices_path, index_col=0, parse_dates=True)
    uncertainty_df = compute_uncertainty(prices, outcome_value_map=outcome_value_map)
    save_dataframe(uncertainty_df, output_path)
    LOGGER.info("Saved uncertainty series to %s", output_path)
    return uncertainty_df


# Allow running as a script: python -m src.uncertainty
if __name__ == "__main__":
    process_and_save_uncertainty()

