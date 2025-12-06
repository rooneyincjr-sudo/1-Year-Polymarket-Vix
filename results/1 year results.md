## Pipeline Overview and Current Results

### 1) Polymarket prices (step 1)
- Loads curated macro markets from `data/raw/macro_markets_curated.json` (237 included, 24 excluded).
- Uses cached prices at `data/raw/polymarket_macro_prices_2024.csv` (no re-scrape unless deleted).

### 2) Uncertainty measures (step 2)
- Converts outcome price paths to uncertainty series per market.
- Output: `data/processed/polymarket_uncertainty_2024.csv`.

### 3) MUI construction (step 3)
- Completeness filter: ≥80% coverage within each market’s active window (start/end from curated file; min window 14 days).
- Window-aware fill: forward/backfill inside the window; mean-impute outside to avoid bleeding across inactive periods.
- Standardize, then PCA → first component as `MUI`.
- Output: `data/processed/mui_2024.csv` (82/131 markets retained).

### 4) VIX data (step 4)
- Uses `data/raw/vix_2024.csv` if present; otherwise downloads via yfinance.

### 5) Feature engineering (step 5)
- Merges MUI with VIX, builds lags (default lags 0,1,2,3,5), target is next-day VIX.
- Output: `data/processed/mui_and_vix_2024.csv`.

### 6) Modeling (step 6)
- Models: OLS, LASSO (alpha=0.05), RandomForest (300 trees, seed=0).
- TimeSeriesSplit CV (n_splits=5). Artifacts per model:
  - Tables: `{model}_fold_metrics.csv`, `{model}_predictions.csv` in `results/tables/`.
  - Figures: `{model}_pred_vs_actual.png`, `{model}_residuals.png` in `results/figures/`.
  - RF feature importances: `feature_importances.csv`.
- Aggregate CV metrics (RMSE/MAE):
  - OLS: 2.38 / 1.62
  - LASSO: 1.80 / 1.13
  - RandomForest: 2.30 / 1.49
- Fold metrics (examples):
  - LASSO folds RMSE: 1.36, 0.61, 3.49, 1.20, 2.37 (`results/tables/lasso_fold_metrics.csv`)
  - OLS folds RMSE: 3.92, 0.63, 3.67, 1.23, 2.46 (`results/tables/ols_fold_metrics.csv`)
  - RF folds RMSE: 1.70, 0.66, 4.52, 1.75, 2.89 (`results/tables/randomforest_fold_metrics.csv`)
- RF top importances (`feature_importances.csv`):
  - `VIX_lag0` dominates (~0.82), then `MUI_lag0` (~0.03), `VIX_lag2`, `MUI_lag3`, `MUI_lag5`, etc.

### How to rerun without re-scraping prices
1. Ensure raw files exist: `data/raw/polymarket_macro_prices_2024.csv` and `data/raw/vix_2024.csv`.
2. Remove downstream artifacts if you want a fresh rebuild:
   - `data/processed/polymarket_uncertainty_2024.csv`
   - `data/processed/mui_2024.csv`
   - `data/processed/mui_and_vix_2024.csv`
   - `results/tables/feature_importances.csv` and any model tables/figures
3. Run `python main.py` (network needed only if VIX/raw prices are missing).

### Notes
- Matplotlib may warn about cache directories in sandboxed runs; plots still render to `results/figures/`.
- PCA sign is arbitrary; use relative movements of MUI, not absolute sign.
