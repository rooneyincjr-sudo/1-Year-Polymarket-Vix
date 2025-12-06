"""Build Macro Uncertainty Index via PCA."""
from __future__ import annotations

from typing import Dict, Iterable

import sys
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

# Allow running directly (python src/mui.py) or as module (python -m src.mui)
try:
    from . import config
    from .utils import LOGGER, save_dataframe
except ImportError:
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))
    from src import config  # type: ignore
    from src.utils import LOGGER, save_dataframe  # type: ignore


def _standardize(df: pd.DataFrame) -> pd.DataFrame:
    scaler = StandardScaler()
    scaled = scaler.fit_transform(df)
    return pd.DataFrame(scaled, index=df.index, columns=df.columns)


def _run_pca(df: pd.DataFrame, n_components: int = 1) -> pd.DataFrame:
    pca = PCA(n_components=n_components)
    components = pca.fit_transform(df)
    cols = [f"PC{i+1}" for i in range(n_components)]
    return pd.DataFrame(components, index=df.index, columns=cols)


def _normalize_slug(text: str) -> str:
    """Normalize slugs to match column naming (lowercase, underscores)."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _load_market_meta(curated_path: Path = config.RAW_POLYMARKET / "macro_markets_curated.json"):
    if not curated_path.exists():
        return {}
    try:
        with curated_path.open("r") as f:
            data = json.load(f)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Could not read curated markets: %s", exc)
        return {}
    meta = {}
    for entry in data:
        if entry.get("include", True) is False:
            continue
        raw_slug = entry.get("slug") or ""
        slug = _normalize_slug(raw_slug)
        meta[slug] = {
            "start": entry.get("startDate"),
            "end": entry.get("endDate"),
        }
    return meta


def _window_mask(index: pd.Index, start: str | None, end: str | None) -> pd.Series:
    idx = index
    s = pd.to_datetime(start) if start else None
    e = pd.to_datetime(end) if end else None
    mask = pd.Series(True, index=idx)
    if s is not None:
        mask &= idx >= s
    if e is not None:
        mask &= idx <= e
    return mask


def filter_by_completeness(
    df: pd.DataFrame,
    min_ratio: float = config.MIN_DATA_COMPLETENESS,
    min_days: int = 14,
    meta: dict | None = None,
) -> pd.DataFrame:
    """Keep markets with sufficient coverage inside their active window.

    The active window is defined by curated start/end dates when available;
    otherwise it falls back to the first/last non-null observations.
    """
    meta = meta or {}
    kept = {}

    index_tz = df.index.tz

    for col in df.columns:
        series = df[col]

        # Match on slug prefix: longest matching slug wins
        matched_meta: dict = {}
        best_len = -1
        for slug, info in meta.items():
            if col.startswith(slug) and len(slug) > best_len:
                matched_meta = info
                best_len = len(slug)

        m = matched_meta

        # Determine window bounds: curated dates if present, else inferred span
        start = pd.to_datetime(m.get("start")) if m.get("start") else series.first_valid_index()
        end = pd.to_datetime(m.get("end")) if m.get("end") else series.last_valid_index()

        # Align timezone awareness to the index to avoid invalid comparisons
        if index_tz is not None:
            # Make naive dates tz-aware in the same zone
            if start is not None and start.tzinfo is None:
                start = start.replace(tzinfo=index_tz)
            if end is not None and end.tzinfo is None:
                end = end.replace(tzinfo=index_tz)
        else:
            # Make tz-aware dates naive if index is naive
            if start is not None and start.tzinfo is not None:
                start = start.tz_localize(None)
            if end is not None and end.tzinfo is not None:
                end = end.tz_localize(None)

        if start is None or end is None:
            continue

        mask = (df.index >= start) & (df.index <= end)
        window = series.where(mask)
        window_len = int(mask.sum())

        if window_len < min_days:
            continue

        coverage = window.count() / window_len if window_len > 0 else 0
        if coverage >= min_ratio:
            kept[col] = window

    filtered = pd.DataFrame(kept, index=df.index)
    LOGGER.info("Keeping %s/%s markets after completeness filter", filtered.shape[1], df.shape[1])
    return filtered


def build_mui(
    uncertainty_path=config.PROCESSED_DATA / "polymarket_uncertainty_2024.csv",
    output_path=config.PROCESSED_DATA / "mui_2024.csv",
    groups: Dict[str, Iterable[str]] | None = None,
) -> pd.DataFrame:
    uncertainty = pd.read_csv(uncertainty_path, index_col=0, parse_dates=True)
    meta = _load_market_meta()
    filtered = filter_by_completeness(uncertainty, meta=meta)
    # Fill within active windows only (avoid bleeding values outside windows)
    # Build columns first, then concat once to avoid fragmentation warnings.
    filled_cols = []
    for col in filtered.columns:
        col_mask = filtered[col].notna()
        col_filled = filtered[col].ffill().bfill()
        col_mean = col_filled[col_mask].mean()
        filled_col = col_filled.where(col_mask, col_mean)
        filled_col.name = col
        filled_cols.append(filled_col)

    filled = pd.concat(filled_cols, axis=1) if filled_cols else pd.DataFrame(index=filtered.index)

    standardized = _standardize(filled)
    mui_df = _run_pca(standardized)
    mui_df = mui_df.rename(columns={"PC1": "MUI"})

    if groups:
        for group_name, cols in groups.items():
            available = [c for c in cols if c in uncertainty.columns]
            if not available:
                continue
            group_df = uncertainty[available].copy()
            group_df = filter_by_completeness(group_df)
            if group_df.empty:
                continue
            standardized_group = _standardize(group_df.ffill().bfill())
            comp = _run_pca(standardized_group)
            mui_df[f"MUI_{group_name}"] = comp.iloc[:, 0]
            LOGGER.info("Built sub-index for %s with %s markets", group_name, len(available))

    save_dataframe(mui_df, output_path)
    return mui_df


if __name__ == "__main__":
    output_path = config.PROCESSED_DATA / "mui_2024.csv"
    if output_path.exists():
        LOGGER.info("MUI file already exists: %s", output_path)
    else:
        LOGGER.info("MUI file missing. Building now...")
        build_mui(output_path=output_path)
        LOGGER.info("MUI file created at %s", output_path)

