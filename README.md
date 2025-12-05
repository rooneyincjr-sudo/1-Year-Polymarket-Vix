# Macro Uncertainty Index & VIX Forecasting

This project builds a Macro Uncertainty Index (MUI) from Polymarket macro/economic prediction markets and evaluates its ability to forecast the VIX.

## Project Structure
- `src/config.py` – configuration for keywords, date ranges, directories, and API URLs.
- `src/polymarket_api.py` – API wrappers to collect Polymarket market metadata and daily prices.
- `src/uncertainty.py` – transforms market prices into per-market uncertainty measures.
- `src/mui.py` – constructs the MUI and optional sub-indices using PCA.
- `src/vix.py` – downloads daily VIX data via `yfinance`.
- `src/features.py` – merges MUI with VIX and creates lagged features/targets.
- `src/models.py` – trains/evaluates OLS, LASSO, and Random Forest models with time-series CV.
- `main.py` – orchestrates the full pipeline end-to-end.
- `data/` – raw and processed datasets (created at runtime).
- `results/` – model outputs and tables.

## Quickstart
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the full pipeline (requires network access for Polymarket and Yahoo Finance):
   ```bash
   python main.py
   ```

Outputs are written to `data/raw`, `data/processed`, and `results/tables`.
