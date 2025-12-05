"""Download VIX data using yfinance."""
from __future__ import annotations

import pandas as pd
import yfinance as yf

from . import config
from .utils import LOGGER, save_dataframe


def fetch_vix(
    ticker: str = config.VIX_TICKER,
    start_date: str = config.START_DATE.date().isoformat(),
    end_date: str = (config.END_DATE.date()).isoformat(),
    output_path=config.RAW_DATA / "vix_2024.csv",
) -> pd.DataFrame:
    data = yf.download(ticker, start=start_date, end=end_date)
    if data.empty:
        LOGGER.warning("No VIX data downloaded for %s", ticker)
        return pd.DataFrame()
    vix = data[["Adj Close"]].rename(columns={"Adj Close": "VIX"})
    save_dataframe(vix, output_path)
    LOGGER.info("Saved VIX data to %s", output_path)
    return vix


