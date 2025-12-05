"""Functions to interact with Polymarket APIs for market metadata and prices."""
from __future__ import annotations

import re
from typing import Iterable, List

import pandas as pd
import requests

from . import config
from .utils import LOGGER, ensure_directories, save_dataframe, to_unix_ts


Session = requests.Session


def _clean_slug(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def fetch_markets_2024(session: Session | None = None, limit: int = config.DEFAULT_REQUEST_LIMIT) -> List[dict]:
    """Fetch all markets that started in 2024 using pagination."""
    s = session or requests.Session()
    markets: List[dict] = []
    offset = 0
    params = {
        "limit": limit,
        "offset": offset,
        "start_date_min": config.START_DATE.isoformat(),
        "start_date_max": config.END_DATE.isoformat(),
    }
    while True:
        params["offset"] = offset
        resp = s.get(config.GAMMA_API_URL, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        batch = payload.get("markets", payload)
        if not batch:
            break
        markets.extend(batch)
        LOGGER.info("Fetched %s markets (offset %s)", len(batch), offset)
        if len(batch) < limit:
            break
        offset += limit
    return markets


def is_macro_market(market: dict, keywords: Iterable[str] | None = None) -> bool:
    text = market.get("question", "")
    if not text:
        return False
    words = keywords or config.MACRO_KEYWORDS
    lowered = text.lower()
    return any(k.lower() in lowered for k in words)


def select_macro_markets_2024(session: Session | None = None) -> List[dict]:
    markets = fetch_markets_2024(session=session)
    macro = [m for m in markets if is_macro_market(m)]
    LOGGER.info("Selected %s macro markets from %s total", len(macro), len(markets))
    return macro


def extract_token_ids(market: dict) -> List[str]:
    raw = market.get("clobTokenIds")
    if not raw:
        return []
    if isinstance(raw, str):
        return [t for t in raw.split(",") if t]
    if isinstance(raw, list):
        return [str(t) for t in raw]
    return []


def _market_slug(market: dict) -> str:
    slug = market.get("slug") or market.get("question", "market")
    return _clean_slug(slug)


def fetch_price_history_for_token(
    token_id: str,
    start_ts: int,
    end_ts: int,
    fidelity: int = config.DEFAULT_FIDELITY_MINUTES,
    session: Session | None = None,
) -> pd.DataFrame:
    s = session or requests.Session()
    params = {"market": token_id, "startTs": start_ts, "endTs": end_ts, "fidelity": fidelity}
    resp = s.get(config.CLOB_HISTORY_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(columns=["timestamp", "price"])
    df = df.rename(columns={"p": "price", "t": "timestamp"})[["timestamp", "price"]]
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    return df


def build_prices_table(macro_markets: List[dict], session: Session | None = None) -> pd.DataFrame:
    """Return wide price DataFrame (daily) for each outcome leg."""
    all_series: List[pd.Series] = []
    s = session or requests.Session()
    start_ts, end_ts = to_unix_ts(config.START_DATE), to_unix_ts(config.END_DATE)

    for market in macro_markets:
        tokens = extract_token_ids(market)
        if not tokens:
            continue
        slug = _market_slug(market)
        outcomes = market.get("outcomes") or []
        for idx, token_id in enumerate(tokens):
            label = outcomes[idx] if idx < len(outcomes) else f"leg{idx+1}"
            clean_label = _clean_slug(label) or f"leg{idx+1}"
            col_name = f"{slug}_{clean_label}"
            df = fetch_price_history_for_token(token_id, start_ts=start_ts, end_ts=end_ts, session=s)
            if df.empty:
                LOGGER.warning("No price history for %s (%s)", slug, token_id)
                continue
            series = df.set_index("timestamp")["price"].rename(col_name)
            all_series.append(series)
    if not all_series:
        return pd.DataFrame()
    prices_df = pd.concat(all_series, axis=1).sort_index()
    prices_df = prices_df.resample("D").last()
    return prices_df


def fetch_and_save_prices(path = config.RAW_DATA / "polymarket_macro_prices_2024.csv") -> pd.DataFrame:
    ensure_directories([path.parent])
    macro_markets = select_macro_markets_2024()
    prices = build_prices_table(macro_markets)
    save_dataframe(prices, path)
    return prices


