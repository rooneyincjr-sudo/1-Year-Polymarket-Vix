"""Model training and evaluation for VIX forecasting."""
from __future__ import annotations

from typing import Dict, Tuple, List

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Lasso, LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import TimeSeriesSplit

try:
    from . import config
    from .utils import LOGGER, ensure_directories, set_all_seeds
except ImportError:
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))
    from src import config  # type: ignore
    from src.utils import LOGGER, ensure_directories, set_all_seeds  # type: ignore


Metrics = Dict[str, float]


def evaluate_ts_model(
    model,
    X: pd.DataFrame,
    y: pd.Series,
    n_splits: int = config.N_SPLITS,
) -> Tuple[Metrics, List[dict], pd.DataFrame]:
    """Time-series CV with fold metrics and predictions."""
    tscv = TimeSeriesSplit(n_splits=n_splits)
    rmses, maes = [], []
    fold_rows: List[dict] = []
    pred_rows: List[dict] = []
    for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        preds = model.predict(X.iloc[test_idx])
        mse = mean_squared_error(y.iloc[test_idx], preds)
        fold_rmse = np.sqrt(mse)
        fold_mae = mean_absolute_error(y.iloc[test_idx], preds)
        rmses.append(fold_rmse)
        maes.append(fold_mae)
        fold_rows.append(
            {
                "fold": fold,
                "start_date": y.index[test_idx].min(),
                "end_date": y.index[test_idx].max(),
                "rmse": float(fold_rmse),
                "mae": float(fold_mae),
            }
        )
        for idx, pred in zip(y.index[test_idx], preds):
            pred_rows.append(
                {
                    "date": idx,
                    "fold": fold,
                    "y_true": float(y.loc[idx]),
                    "y_pred": float(pred),
                    "residual": float(y.loc[idx] - pred),
                }
            )

    metrics = {"rmse": float(np.mean(rmses)), "mae": float(np.mean(maes))}
    pred_df = pd.DataFrame(pred_rows).set_index("date").sort_index()
    return metrics, fold_rows, pred_df


def _plot_pred_vs_actual(pred_df: pd.DataFrame, model_name: str, output_path: Path) -> None:
    plt.figure(figsize=(6, 6))
    plt.scatter(pred_df["y_true"], pred_df["y_pred"], alpha=0.5, s=12)
    lims = [
        min(pred_df["y_true"].min(), pred_df["y_pred"].min()),
        max(pred_df["y_true"].max(), pred_df["y_pred"].max()),
    ]
    plt.plot(lims, lims, "k--", linewidth=1)
    plt.xlabel("Actual VIX")
    plt.ylabel("Predicted VIX")
    plt.title(f"{model_name} — Predicted vs Actual")
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200)
    plt.close()


def _plot_residuals(pred_df: pd.DataFrame, model_name: str, output_path: Path) -> None:
    plt.figure(figsize=(8, 3))
    plt.plot(pred_df.index, pred_df["residual"], linewidth=0.9)
    plt.axhline(0, color="k", linestyle="--", linewidth=0.8)
    plt.xlabel("Date")
    plt.ylabel("Residual (y - y_pred)")
    plt.title(f"{model_name} — Residuals over time")
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=200)
    plt.close()


def run_models(dataset_path=config.PROCESSED_DATA / "mui_and_vix_2024.csv") -> Dict[str, Metrics]:
    set_all_seeds()
    data = pd.read_csv(dataset_path, index_col=0, parse_dates=True)
    y = data.pop("VIX_target")
    X = data

    results: Dict[str, Metrics] = {}
    models = {
        "OLS": LinearRegression(),
        "LASSO": Lasso(alpha=0.05),
        "RandomForest": RandomForestRegressor(
            n_estimators=300, random_state=config.SEED
        ),
    }

    tables_dir = config.RESULTS_DIR / "tables"
    figs_dir = config.RESULTS_DIR / "figures"
    ensure_directories([tables_dir, figs_dir])

    for name, model in models.items():
        metrics, fold_rows, pred_df = evaluate_ts_model(model, X, y)
        results[name] = metrics
        LOGGER.info("%s -> RMSE: %.4f | MAE: %.4f", name, metrics["rmse"], metrics["mae"])

        # Save fold metrics and predictions
        pd.DataFrame(fold_rows).to_csv(tables_dir / f"{name.lower()}_fold_metrics.csv", index=False)
        pred_df.to_csv(tables_dir / f"{name.lower()}_predictions.csv")

        _plot_pred_vs_actual(pred_df, name, figs_dir / f"{name.lower()}_pred_vs_actual.png")
        _plot_residuals(pred_df, name, figs_dir / f"{name.lower()}_residuals.png")

    feature_importances = models["RandomForest"].fit(X, y).feature_importances_
    importance_df = pd.DataFrame({"feature": X.columns, "importance": feature_importances})
    importance_df = importance_df.sort_values(by="importance", ascending=False)
    importance_path = config.RESULTS_DIR / "tables" / "feature_importances.csv"
    ensure_directories([importance_path.parent])
    importance_df.to_csv(importance_path, index=False)
    return results


