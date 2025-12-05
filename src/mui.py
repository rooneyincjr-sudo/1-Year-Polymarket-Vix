"""Build Macro Uncertainty Index via PCA."""
from __future__ import annotations

from typing import Dict, Iterable

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from . import config
from .utils import LOGGER, save_dataframe


def _standardize(df: pd.DataFrame) -> pd.DataFrame:
    scaler = StandardScaler()
    scaled = scaler.fit_transform(df)
    return pd.DataFrame(scaled, index=df.index, columns=df.columns)


def _run_pca(df: pd.DataFrame, n_components: int = 1) -> pd.DataFrame:
    pca = PCA(n_components=n_components)
    components = pca.fit_transform(df)
    cols = [f"PC{i+1}" for i in range(n_components)]
    return pd.DataFrame(components, index=df.index, columns=cols)


def filter_by_completeness(df: pd.DataFrame, min_ratio: float = config.MIN_DATA_COMPLETENESS) -> pd.DataFrame:
    threshold = int(len(df) * min_ratio)
    keep = [col for col in df.columns if df[col].count() >= threshold]
    filtered = df[keep]
    LOGGER.info("Keeping %s/%s markets after completeness filter", len(keep), len(df.columns))
    return filtered


def build_mui(
    uncertainty_path=config.PROCESSED_DATA / "polymarket_uncertainty_2024.csv",
    output_path=config.PROCESSED_DATA / "mui_2024.csv",
    groups: Dict[str, Iterable[str]] | None = None,
) -> pd.DataFrame:
    uncertainty = pd.read_csv(uncertainty_path, index_col=0, parse_dates=True)
    filtered = filter_by_completeness(uncertainty)
    standardized = _standardize(filtered.fillna(method="ffill").fillna(method="bfill"))
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
            standardized_group = _standardize(group_df.fillna(method="ffill").fillna(method="bfill"))
            comp = _run_pca(standardized_group)
            mui_df[f"MUI_{group_name}"] = comp.iloc[:, 0]
            LOGGER.info("Built sub-index for %s with %s markets", group_name, len(available))

    save_dataframe(mui_df, output_path)
    return mui_df


