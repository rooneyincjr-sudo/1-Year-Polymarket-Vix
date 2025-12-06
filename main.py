"""End-to-end orchestration for building the Macro Uncertainty Index and VIX models.

Pipeline:
1. Fetch Polymarket 2024 markets → Filter to macro → Get price history
2. Compute uncertainty measures from prices
3. Build MUI (Macro Uncertainty Index) via PCA
4. Download VIX data
5. Generate lagged features
6. Train and evaluate models
"""
from __future__ import annotations

from src import config
from src.features import merge_mui_vix
from src.models import run_models
from src.mui import build_mui
from src.polymarket_api import fetch_and_save_prices
from src.uncertainty import process_and_save_uncertainty
from src.utils import LOGGER, ensure_directories
from src.vix import fetch_vix


def main():
    """Run the full MUI pipeline."""
    # Setup directories
    ensure_directories([
        config.DATA_DIR,
        config.RAW_DATA,
        config.PROCESSED_DATA,
        config.RESULTS_DIR / "tables",
        config.RESULTS_DIR / "figures",
    ])

    # Step 1: Polymarket price data
    LOGGER.info("=" * 60)
    LOGGER.info("STEP 1: Collecting Polymarket price data")
    LOGGER.info("=" * 60)
    prices = fetch_and_save_prices()

    if prices.empty:
        LOGGER.error("No Polymarket price data collected. Aborting.")
        raise SystemExit(1)

    # Step 2: Uncertainty measures
    LOGGER.info("=" * 60)
    LOGGER.info("STEP 2: Computing uncertainty measures")
    LOGGER.info("=" * 60)
    uncertainty = process_and_save_uncertainty()

    # Step 3: MUI via PCA
    LOGGER.info("=" * 60)
    LOGGER.info("STEP 3: Building Macro Uncertainty Index (PCA)")
    LOGGER.info("=" * 60)
    mui = build_mui()

    # Step 4: VIX data
    LOGGER.info("=" * 60)
    LOGGER.info("STEP 4: Downloading VIX data")
    LOGGER.info("=" * 60)
    vix = fetch_vix()

    if vix.empty:
        LOGGER.error("No VIX data downloaded. Aborting.")
        raise SystemExit(1)

    # Step 5: Feature engineering
    LOGGER.info("=" * 60)
    LOGGER.info("STEP 5: Building feature set with lags")
    LOGGER.info("=" * 60)
    dataset = merge_mui_vix()

    # Step 6: Model training
    LOGGER.info("=" * 60)
    LOGGER.info("STEP 6: Training models with time-series CV")
    LOGGER.info("=" * 60)
    results = run_models()

    # Summary
    LOGGER.info("=" * 60)
    LOGGER.info("PIPELINE COMPLETE")
    LOGGER.info("=" * 60)
    LOGGER.info("Model results: %s", results)


if __name__ == "__main__":
    main()
