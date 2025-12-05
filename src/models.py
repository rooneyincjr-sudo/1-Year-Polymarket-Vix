"""Model training and evaluation for VIX forecasting."""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Lasso, LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

from . import config
from .utils import LOGGER, ensure_directories


Metrics = Dict[str, float]


def evaluate_ts_model(model, X: pd.DataFrame, y: pd.Series, n_splits: int = config.N_SPLITS) -> Metrics:
    tscv = TimeSeriesSplit(n_splits=n_splits)
    rmses, maes = [], []
    for train_idx, test_idx in tscv.split(X):
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        preds = model.predict(X.iloc[test_idx])
        rmses.append(mean_squared_error(y.iloc[test_idx], preds, squared=False))
        maes.append(mean_absolute_error(y.iloc[test_idx], preds))
    return {"rmse": float(np.mean(rmses)), "mae": float(np.mean(maes))}


def run_models(dataset_path=config.PROCESSED_DATA / "mui_and_vix_2024.csv") -> Dict[str, Metrics]:
    data = pd.read_csv(dataset_path, index_col=0, parse_dates=True)
    y = data.pop("VIX_target")
    X = data

    results: Dict[str, Metrics] = {}
    models = {
        "OLS": LinearRegression(),
        "LASSO": Lasso(alpha=0.05),
        "RandomForest": RandomForestRegressor(n_estimators=300, random_state=0),
    }

    for name, model in models.items():
        metrics = evaluate_ts_model(model, X, y)
        results[name] = metrics
        LOGGER.info("%s -> RMSE: %.4f | MAE: %.4f", name, metrics["rmse"], metrics["mae"])

    feature_importances = models["RandomForest"].fit(X, y).feature_importances_
    importance_df = pd.DataFrame({"feature": X.columns, "importance": feature_importances})
    importance_df = importance_df.sort_values(by="importance", ascending=False)
    importance_path = config.RESULTS_DIR / "tables" / "feature_importances.csv"
    ensure_directories([importance_path.parent])
    importance_df.to_csv(importance_path, index=False)
    return results


