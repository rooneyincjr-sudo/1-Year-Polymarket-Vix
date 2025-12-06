"""Convert Polymarket price series into per-market uncertainty measures."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Mapping, List, Tuple

import pandas as pd
import numpy as np

# New imports for grouping related markets
import json
from dataclasses import dataclass

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


# --------------------------------------------------------------------------- #
# Market metadata helpers
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class MarketMeta:
    slug: str
    start: str
    end: str
    outcomes: List[str]


def _load_market_meta(curated_path: Path) -> Dict[str, MarketMeta]:
    """Load curated market metadata to enable grouping similar questions."""
    if not curated_path.exists():
        LOGGER.warning("Curated markets file missing: %s", curated_path)
        return {}

    try:
        with curated_path.open("r") as f:
            markets = json.load(f)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Failed to read curated markets: %s", exc)
        return {}

    meta: Dict[str, MarketMeta] = {}
    for entry in markets:
        slug = entry.get("slug")
        if not slug:
            continue
        if entry.get("include", True) is False:
            continue
        outcomes = entry.get("outcomes") or []
        # outcomes can be stored as a JSON string
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except json.JSONDecodeError:
                outcomes = []
        meta[slug.replace("-", "_")] = MarketMeta(
            slug=slug.replace("-", "_"),
            start=entry.get("startDate", ""),
            end=entry.get("endDate", ""),
            outcomes=list(outcomes),
        )
    return meta


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


def _tokenize_slug(slug: str) -> set[str]:
    return set(part for part in slug.split("_") if part)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _group_similar_slugs(
    meta: Dict[str, MarketMeta],
    similarity_threshold: float = 0.6,
) -> List[List[str]]:
    """Cluster slugs that share the same start/end dates and similar wording.

    We only group markets if:
      * startDate and endDate match
      * Jaccard similarity of token sets exceeds the threshold
    """
    # Bucket by date window first
    by_date: Dict[Tuple[str, str], List[str]] = {}
    for slug, m in meta.items():
        by_date.setdefault((m.start, m.end), []).append(slug)

    clusters: List[List[str]] = []
    for _, slugs in by_date.items():
        used = set()
        tokens = {s: _tokenize_slug(s) for s in slugs}
        for slug in slugs:
            if slug in used:
                continue
            group = [slug]
            used.add(slug)
            for other in slugs:
                if other in used:
                    continue
                if _jaccard(tokens[slug], tokens[other]) >= similarity_threshold:
                    group.append(other)
                    used.add(other)
            clusters.append(group)

    # Keep deterministic ordering
    clusters = [sorted(g) for g in clusters if g]
    return clusters


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

    # Map columns back to their slug (strip the final outcome suffix)
    market_columns = _identify_market_columns(prices)

    # Load curated metadata to group related markets
    meta = _load_market_meta(config.RAW_POLYMARKET / "macro_markets_curated.json")
    clusters = _group_similar_slugs(meta)

    uncertainty_series = {}
    used_slugs: set[str] = set()

    def _yes_prob(slug: str, cols: Iterable[str]) -> pd.Series | None:
        """Pick the first column as Yes; if a second exists, normalize Yes/(Yes+No)."""
        col_list = list(cols)
        if not col_list:
            return None
        subset = prices[col_list].dropna(how="all")
        if subset.empty:
            return None
        yes = subset.iloc[:, 0]
        if len(col_list) >= 2:
            total = subset.iloc[:, 0] + subset.iloc[:, 1]
            ratio = yes / total
            # Explicitly drop inf values to avoid pandas FutureWarning
            ratio = ratio.replace([np.inf, -np.inf], pd.NA)
            return ratio
        return yes

    # First pass: combine similar slugs (same date window + token similarity)
    for cluster in clusters:
        available = [slug for slug in cluster if slug in market_columns]
        if not available:
            continue
        used_slugs.update(available)

        # Build a probability table with one column per slug (Yes leg)
        prob_cols: Dict[str, pd.Series] = {}
        for slug in available:
            series = _yes_prob(slug, market_columns[slug])
            if series is not None:
                prob_cols[slug] = series

        if not prob_cols:
            continue

        prob_df = pd.DataFrame(prob_cols).dropna(how="all")
        if prob_df.empty:
            continue

        if len(prob_df.columns) == 1:
            slug = prob_df.columns[0]
            uncertainty_series[f"{slug}_U"] = binary_uncertainty(prob_df[slug])
        else:
            # Treat grouped questions as a multi-outcome market
            mapping = outcome_value_map.get("_".join(sorted(prob_df.columns)), {})
            uncertainty_series[f"{'_'.join(sorted(prob_df.columns))}_U"] = multi_uncertainty(
                prob_df, mapping
            )

    # Second pass: remaining markets not grouped, use first leg only
    for slug, cols in market_columns.items():
        if slug in used_slugs:
            continue
        series = _yes_prob(slug, cols)
        if series is None:
            continue
        uncertainty_series[f"{slug}_U"] = binary_uncertainty(series)

    uncertainty_df = pd.DataFrame(uncertainty_series)
    uncertainty_df = uncertainty_df.sort_index()
    return uncertainty_df


def process_and_save_uncertainty(
    prices_path=config.RAW_POLYMARKET / "polymarket_macro_prices_2024.csv",
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

