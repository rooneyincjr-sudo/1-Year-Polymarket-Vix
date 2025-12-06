"""Feature engineering for VIX forecasting."""
from __future__ import annotations

from typing import Iterable, List

import sys
from pathlib import Path

import pandas as pd

try:
    from . import config
    from .utils import LOGGER, save_dataframe
except ImportError:
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))
    from src import config  # type: ignore
    from src.utils import LOGGER, save_dataframe  # type: ignore


def build_lagged_features(
    series: pd.Series, lags: Iterable[int], prefix: str
) -> pd.DataFrame:
    data = {}
    for lag in lags:
        data[f"{prefix}_lag{lag}"] = series.shift(lag)
    return pd.DataFrame(data)


def merge_mui_vix(
    mui_path=config.PROCESSED_DATA / "mui_2024.csv",
    vix_path=config.RAW_VIX / "vix_2024.csv",
    output_path=config.PROCESSED_DATA / "mui_and_vix_2024.csv",
    mui_lags: Iterable[int] = (0, 1, 2, 3, 5),
    vix_lags: Iterable[int] = (0, 1, 2, 3, 5),
) -> pd.DataFrame:
    mui = pd.read_csv(mui_path, index_col=0, parse_dates=True)
    vix = pd.read_csv(vix_path, index_col=0, parse_dates=True)

    # Normalize indexes to be tz-naive daily datetimes so the join works.
    mui.index = pd.to_datetime(mui.index).tz_localize(None)
    vix.index = pd.to_datetime(vix.index).tz_localize(None)

    merged = mui.join(vix, how="inner")
    target = merged["VIX"].shift(-1).rename("VIX_target")
    feature_frames: List[pd.DataFrame] = [target.to_frame()]

    for col in mui.columns:
        feature_frames.append(build_lagged_features(merged[col], mui_lags, prefix=col))
    feature_frames.append(build_lagged_features(merged["VIX"], vix_lags, prefix="VIX"))

    dataset = pd.concat(feature_frames, axis=1)
    dataset = dataset.dropna()
    save_dataframe(dataset, output_path)
    LOGGER.info("Saved feature set to %s", output_path)
    return dataset


