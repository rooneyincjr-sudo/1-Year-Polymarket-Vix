"""Download VIX data for a given year using yfinance."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yfinance as yf

try:
    from . import config
    from .utils import LOGGER, ensure_directories
except ImportError:
    import sys

    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))
    from src import config  # type: ignore
    from src.utils import LOGGER, ensure_directories  # type: ignore


def _year_bounds(year: int) -> tuple[str, str]:
    """Return start/end ISO strings for the requested year."""
    return (f"{year}-01-01", f"{year}-12-31")


def fetch_vix(
    ticker: str = config.VIX_TICKER,
    year: int = config.YEAR,
    output_path: Path | None = None,
) -> pd.DataFrame:
    """Download VIX data and store to `data/raw`.
    
    Uses config defaults so the pipeline is reproducible and parameterized by year.
    """
    start, end = _year_bounds(year)
    target = output_path or config.RAW_VIX / f"vix_{year}.csv"
    ensure_directories([target.parent])

    LOGGER.info("Downloading %s data for %s", ticker, year)
    data = yf.download(ticker, start=start, end=end, progress=False)

    if data.empty:
        LOGGER.warning("No VIX data downloaded for %s", year)
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        vix = data[("Close", ticker)].to_frame(name="VIX")
    else:
        vix = data[["Close"]].rename(columns={"Close": "VIX"})

    vix.to_csv(target)
    LOGGER.info("Saved VIX data to %s (%s rows)", target, len(vix))
    return vix


if __name__ == "__main__":
    fetched = fetch_vix()
    if not fetched.empty:
        LOGGER.info(
            "VIX summary | %s to %s | rows=%s | range=%.2f..%.2f",
            fetched.index.min().date(),
            fetched.index.max().date(),
            len(fetched),
            fetched["VIX"].min(),
            fetched["VIX"].max(),
        )
