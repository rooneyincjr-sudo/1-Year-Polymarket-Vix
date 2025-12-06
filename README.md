# Macro Uncertainty Index & VIX Forecasting

Build a Macro Uncertainty Index (MUI) from Polymarket macro prediction markets and test whether it helps forecast the VIX. The pipeline fetches data, engineers uncertainty features, constructs the index via PCA, and evaluates several time-series models.

## Repository layout
- `src/` – code modules
  - `config.py` – dates, API endpoints, paths, keywords, random seed
  - `utils.py` – logging, directory setup, reproducibility helpers
  - `polymarket_api.py` – Polymarket market metadata + price history collection
  - `uncertainty.py` – convert prices to per-market uncertainty measures
  - `mui.py` – build the Macro Uncertainty Index via PCA
  - `vix.py` – download VIX data from Yahoo Finance
  - `features.py` – join MUI + VIX, create lagged features/targets
  - `models.py` – OLS, LASSO, Random Forest with time-series CV + plots
  - `__init__.py` – package marker
- `main.py` – end-to-end orchestrator
- `data/`
  - `raw/polymarket/` – Polymarket caches, curated markets, price history
  - `raw/vix/` – VIX downloads
  - `processed/` – derived tables (uncertainty, MUI, merged features)
- `results/` – `tables/` and `figures/` produced by model training
- `notebooks/` – exploratory analysis
- `requirements.txt` – Python dependencies

## Data sources
- **Polymarket Gamma API** (`https://gamma-api.polymarket.com/markets`) for market metadata.
- **Polymarket CLOB API** (`https://clob.polymarket.com/prices-history`) for historical prices.
- **Yahoo Finance (via `yfinance`)** for VIX levels (ticker `^VIX`).

## Required packages
Key runtime dependencies (full list in `requirements.txt`):
- `pandas`, `numpy`, `scikit-learn`, `matplotlib`, `seaborn`
- `requests`, `yfinance`

## Reproducible workflow
1. **Setup**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Run the pipeline** (downloads data if not already cached):
   ```bash
   python main.py
   ```
   - Outputs land in `data/raw`, `data/processed`, and `results/`.
3. **Inspect results**
   - Tables: `results/tables/*`
   - Figures: `results/figures/*`

### Notes
- The pipeline is idempotent: if outputs already exist, steps are skipped.
- Network access is required for fresh Polymarket and Yahoo Finance downloads.
- Reproducibility: seeds are set via `config.SEED` and applied at pipeline start.

## Data cleaning and market selection
The Polymarket universe is narrowed in two passes:
- **Keyword filter:** questions are matched against macro-economic keywords from `src/config.py` (`MACRO_KEYWORDS`). Only those markets continue to price collection.
- **Manual curation:** the keyword-selected list is written to `data/raw/polymarket/macro_markets_curated.json` with an `include` flag. Set `include: false` to drop extraneous or off-topic markets before building uncertainty series. This curated file is read on subsequent runs, so edits persist without further API calls.
# 1-Year-Polymarket-Vix
