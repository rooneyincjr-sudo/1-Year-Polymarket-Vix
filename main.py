"""End-to-end orchestration for building the Macro Uncertainty Index and VIX models."""
from __future__ import annotations

from src import config
from src.features import merge_mui_vix
from src.models import run_models
from src.mui import build_mui
from src.polymarket_api import fetch_and_save_prices
from src.uncertainty import process_and_save_uncertainty
from src.utils import LOGGER, ensure_directories
from src.vix import fetch_vix


if __name__ == "__main__":
    ensure_directories(
        [
            config.DATA_DIR,
            config.RAW_DATA,
            config.PROCESSED_DATA,
            config.RESULTS_DIR / "tables",
            config.RESULTS_DIR / "figures",
        ]
    )

    LOGGER.info("Starting Polymarket price collection...")
    prices = fetch_and_save_prices()

    if prices.empty:
        LOGGER.warning("No Polymarket price data collected. Aborting downstream steps.")
        raise SystemExit(1)

    LOGGER.info("Computing uncertainty measures...")
    uncertainty = process_and_save_uncertainty()

    LOGGER.info("Building Macro Uncertainty Index via PCA...")
    mui = build_mui()

    LOGGER.info("Downloading VIX data...")
    vix = fetch_vix()

    if vix.empty:
        LOGGER.warning("No VIX data downloaded. Aborting feature generation.")
        raise SystemExit(1)

    LOGGER.info("Constructing merged feature set with lags...")
    dataset = merge_mui_vix()

    LOGGER.info("Running models with time-series cross-validation...")
    results = run_models()
    LOGGER.info("Model evaluation complete: %s", results)

