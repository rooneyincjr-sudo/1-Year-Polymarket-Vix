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
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

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


def _run_inference_with_statsmodels(
    X: pd.DataFrame,
    y: pd.Series,
    output_dir: Path,
    hac_max_lag: int = 5,
) -> None:
    """
    Fit a single OLS with HAC/Newey-West SEs for inference only.

    This is intentionally separate from the scikit-learn models used for
    prediction so we can report coefficient t-stats/p-values.
    """
    try:
        import statsmodels.api as sm  # type: ignore
    except ImportError:
        LOGGER.warning("statsmodels not installed; skipping inference OLS.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    X_with_const = sm.add_constant(X, has_constant="add")
    model = sm.OLS(y, X_with_const)
    results = model.fit(cov_type="HAC", cov_kwds={"maxlags": hac_max_lag})

    summary_path = output_dir / "ols_inference_summary.txt"
    with open(summary_path, "w") as f:
        f.write(results.summary().as_text())

    coef_table = pd.DataFrame(
        {
            "coef": results.params,
            "std_err": results.bse,
            "t_stat": results.tvalues,
            "p_value": results.pvalues,
        }
    )
    coef_table.to_csv(output_dir / "ols_inference_coefs.csv")
    LOGGER.info(
        "Saved inference OLS with HAC(maxlags=%d) to %s and %s",
        hac_max_lag,
        summary_path,
        output_dir / "ols_inference_coefs.csv",
    )


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


def run_models(
    dataset_path=config.PROCESSED_DATA / "mui_and_vix_2024.csv",
    run_inference: bool = True,
    hac_max_lag: int = 5,
) -> Dict[str, Dict[str, Metrics]]:
    """
    Train models for two feature sets:
    1) with MUI + VIX lags (augmented)
    2) VIX-only lags (baseline)

    Returns a nested dict keyed by feature_set -> model_name -> metrics.
    """
    set_all_seeds()
    data = pd.read_csv(dataset_path, index_col=0, parse_dates=True)
    y = data.pop("VIX_target")

    # Feature sets for baseline comparison
    vix_cols = [col for col in data.columns if col.startswith("VIX_")]
    feature_sets = {
        "with_mui": data,
        "vix_only": data[vix_cols],
    }

    # Models (LASSO now scaled for proper penalization)
    models = {
        "OLS": LinearRegression(),
        "LASSO": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "lasso",
                    Lasso(alpha=0.05, random_state=config.SEED, max_iter=5000),
                ),
            ]
        ),
        "RandomForest": RandomForestRegressor(
            n_estimators=300, random_state=config.SEED
        ),
    }

    tables_dir = config.RESULTS_DIR / "tables"
    figs_dir = config.RESULTS_DIR / "figures"
    ensure_directories([tables_dir, figs_dir])

    results: Dict[str, Dict[str, Metrics]] = {}
    summary_rows: List[dict] = []
    for feature_tag, X in feature_sets.items():
        results[feature_tag] = {}
        for name, model in models.items():
            metrics, fold_rows, pred_df = evaluate_ts_model(model, X, y)
            results[feature_tag][name] = metrics
            summary_rows.append(
                {
                    "feature_set": feature_tag,
                    "model": name,
                    "rmse": metrics["rmse"],
                    "mae": metrics["mae"],
                }
            )
            LOGGER.info(
                "%s (%s) -> RMSE: %.4f | MAE: %.4f",
                name,
                feature_tag,
                metrics["rmse"],
                metrics["mae"],
            )

            # Save fold metrics and predictions
            pd.DataFrame(fold_rows).to_csv(
                tables_dir / f"{name.lower()}_{feature_tag}_fold_metrics.csv",
                index=False,
            )
            pred_df.to_csv(tables_dir / f"{name.lower()}_{feature_tag}_predictions.csv")

            _plot_pred_vs_actual(
                pred_df, f"{name} ({feature_tag})", figs_dir / f"{name.lower()}_{feature_tag}_pred_vs_actual.png"
            )
            _plot_residuals(
                pred_df, f"{name} ({feature_tag})", figs_dir / f"{name.lower()}_{feature_tag}_residuals.png"
            )

    # Comparison summary table (easy to check MUI value-add)
    pd.DataFrame(summary_rows).to_csv(
        tables_dir / "model_feature_set_summary.csv", index=False
    )

    # Feature importances from full model only (consistent with previous behavior)
    rf_importances = models["RandomForest"].fit(feature_sets["with_mui"], y).feature_importances_
    importance_df = pd.DataFrame(
        {"feature": feature_sets["with_mui"].columns, "importance": rf_importances}
    ).sort_values(by="importance", ascending=False)
    importance_path = config.RESULTS_DIR / "tables" / "feature_importances.csv"
    ensure_directories([importance_path.parent])
    importance_df.to_csv(importance_path, index=False)

    # Optional inference run for one specification (augmented)
    if run_inference:
        _run_inference_with_statsmodels(
            feature_sets["with_mui"], y, tables_dir, hac_max_lag=hac_max_lag
        )

    return results


