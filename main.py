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

from pathlib import Path

from src import config
from src.features import merge_mui_vix
from src.models import run_models
from src.mui import build_mui
from src.polymarket_api import fetch_and_save_prices
from src.uncertainty import process_and_save_uncertainty
from src.utils import LOGGER, ensure_directories, set_all_seeds
from src.vix import fetch_vix


def main():
    """Run the full MUI pipeline."""
    # Ensure deterministic behavior for reproducibility across runs
    set_all_seeds()
    # Setup directories
    ensure_directories(
        [
            config.DATA_DIR,
            config.RAW_DATA,
            config.RAW_POLYMARKET,
            config.RAW_VIX,
            config.PROCESSED_DATA,
            config.RESULTS_DIR / "tables",
            config.RESULTS_DIR / "figures",
        ]
    )

    def exists_and_nonempty(path: Path) -> bool:
        return path.exists() and path.stat().st_size > 0

    # Step 1: Polymarket price data
    prices_path = config.RAW_POLYMARKET / "polymarket_macro_prices_2024.csv"
    LOGGER.info("=" * 60)
    LOGGER.info("STEP 1: Collecting Polymarket price data")
    LOGGER.info("=" * 60)
    if exists_and_nonempty(prices_path):
        LOGGER.info("Prices already exist at %s; skipping fetch.", prices_path)
        prices = None
    else:
        prices = fetch_and_save_prices()
        if prices.empty:
            LOGGER.error("No Polymarket price data collected. Aborting.")
            raise SystemExit(1)

    # Step 2: Uncertainty measures
    uncertainty_path = config.PROCESSED_DATA / "polymarket_uncertainty_2024.csv"
    LOGGER.info("=" * 60)
    LOGGER.info("STEP 2: Computing uncertainty measures")
    LOGGER.info("=" * 60)
    if exists_and_nonempty(uncertainty_path):
        LOGGER.info("Uncertainty series already exist at %s; skipping.", uncertainty_path)
        uncertainty = None
    else:
        uncertainty = process_and_save_uncertainty()

    # Step 3: MUI via PCA
    mui_path = config.PROCESSED_DATA / "mui_2024.csv"
    LOGGER.info("=" * 60)
    LOGGER.info("STEP 3: Building Macro Uncertainty Index (PCA)")
    LOGGER.info("=" * 60)
    if exists_and_nonempty(mui_path):
        LOGGER.info("MUI already exists at %s; skipping build.", mui_path)
        mui = None
    else:
        mui = build_mui()

    # Step 4: VIX data
    vix_path = config.RAW_VIX / "vix_2024.csv"
    LOGGER.info("=" * 60)
    LOGGER.info("STEP 4: Downloading VIX data")
    LOGGER.info("=" * 60)
    if exists_and_nonempty(vix_path):
        LOGGER.info("VIX data already exists at %s; skipping download.", vix_path)
        vix = None
    else:
        vix = fetch_vix()
        if vix.empty:
            LOGGER.error("No VIX data downloaded. Aborting.")
            raise SystemExit(1)

    # Step 5: Feature engineering
    features_path = config.PROCESSED_DATA / "mui_and_vix_2024.csv"
    LOGGER.info("=" * 60)
    LOGGER.info("STEP 5: Building feature set with lags")
    LOGGER.info("=" * 60)
    if exists_and_nonempty(features_path):
        LOGGER.info("Feature set already exists at %s; skipping build.", features_path)
        dataset = None
    else:
        dataset = merge_mui_vix()

    # Step 6: Model training
    importance_path = config.RESULTS_DIR / "tables" / "feature_importances.csv"
    LOGGER.info("=" * 60)
    LOGGER.info("STEP 6: Training models with time-series CV")
    LOGGER.info("=" * 60)
    if exists_and_nonempty(importance_path):
        LOGGER.info("Model outputs already exist at %s; skipping training.", importance_path)
        results = None
    else:
        results = run_models()

    # Summary
    LOGGER.info("=" * 60)
    LOGGER.info("PIPELINE COMPLETE")
    LOGGER.info("=" * 60)
    LOGGER.info("Model results: %s", results)


if __name__ == "__main__":
    main()
