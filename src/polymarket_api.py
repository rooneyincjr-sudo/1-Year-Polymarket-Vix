"""Functions to interact with Polymarket APIs for market metadata and prices.

Pipeline workflow (designed to minimize API calls):
1. Fetch all 2024 markets from Gamma API (cached)
2. Filter to macro-relevant markets using keywords (no API calls)
3. Fetch price history only for filtered markets using CLOB API
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Iterable, List

import pandas as pd
import requests

# Handle both relative and absolute imports
try:
    from . import config
    from .utils import LOGGER, ensure_directories, save_dataframe, to_unix_ts
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src import config
    from src.utils import LOGGER, ensure_directories, save_dataframe, to_unix_ts


Session = requests.Session


# =============================================================================
# STEP 1: Fetch Market Metadata (Gamma API)
# =============================================================================

def fetch_markets_2024(
    session: Session | None = None,
    limit: int = config.DEFAULT_REQUEST_LIMIT,
    use_cache: bool = True,
    cache_path: Path | None = config.RAW_POLYMARKET / "markets_2024_cache.json",
) -> List[dict]:
    """Fetch all markets from 2024 using pagination, with caching.
    
    This is the first step in the pipeline - get market metadata without
    fetching price data yet. Results are cached to avoid repeated API calls.
    """
    if use_cache and cache_path and cache_path.exists():
        try:
            with cache_path.open("r") as f:
                cached = json.load(f)
            LOGGER.info("Loaded %d markets from cache: %s", len(cached), cache_path)
            return cached
        except Exception as exc:
            LOGGER.warning("Failed to read cache %s: %s", cache_path, exc)

    s = session or requests.Session()
    markets: List[dict] = []
    offset = 0
    
    LOGGER.info("Fetching 2024 markets from Gamma API...")
    
    while True:
        params = {
            "limit": limit,
            "offset": offset,
            "start_date_min": config.START_DATE.isoformat(),
            "start_date_max": config.END_DATE.isoformat(),
        }
        resp = s.get(config.GAMMA_API_URL, params=params, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        
        batch = payload.get("markets", []) if isinstance(payload, dict) else payload
        if not batch:
            break
            
        markets.extend(batch)
        LOGGER.info("Fetched %d markets (offset %d)", len(batch), offset)
        
        if len(batch) < limit:
            break
        offset += limit

    # Cache for future runs
    if use_cache and cache_path:
        try:
            ensure_directories([cache_path.parent])
            with cache_path.open("w") as f:
                json.dump(markets, f)
            LOGGER.info("Cached %d markets to %s", len(markets), cache_path)
        except Exception as exc:
            LOGGER.warning("Failed to write cache: %s", exc)

    return markets


# =============================================================================
# STEP 2: Filter Markets by Keywords (with caching and manual curation)
# =============================================================================

def is_macro_market(market: dict, keywords: Iterable[str] | None = None) -> bool:
    """Check if market question matches macro-economic keywords."""
    text = market.get("question", "")
    if not text:
        return False
    words = keywords or config.MACRO_KEYWORDS
    lowered = text.lower()
    return any(k.lower() in lowered for k in words)


def load_curated_markets(
    curated_path: Path = config.RAW_POLYMARKET / "macro_markets_curated.json",
) -> List[dict] | None:
    """Load manually curated markets list if it exists.
    
    The curated file is a human-readable JSON with an 'include' field.
    Markets with include=false are excluded from the pipeline.
    
    Returns:
        List of included markets, or None if file doesn't exist
    """
    if not curated_path.exists():
        return None
    
    try:
        with curated_path.open("r") as f:
            markets = json.load(f)
        
        # Filter to only included markets
        included = [m for m in markets if m.get("include", True)]
        excluded = len(markets) - len(included)
        
        if excluded > 0:
            LOGGER.info("Loaded %d markets from curated list (%d excluded)", 
                       len(included), excluded)
        else:
            LOGGER.info("Loaded %d markets from curated list: %s", 
                       len(included), curated_path)
        
        return included
        
    except Exception as exc:
        LOGGER.warning("Failed to read curated markets: %s", exc)
        return None


def create_curated_file(
    markets: List[dict],
    output_path: Path = config.RAW_POLYMARKET / "macro_markets_curated.json",
    sort_by_volume: bool = True,
) -> None:
    """Create a human-readable, editable version of the markets list.
    
    The output file contains simplified market data with an 'include' field
    that can be set to false to exclude markets from the pipeline.
    """
    readable = []
    for m in markets:
        readable.append({
            "include": True,
            "slug": m.get("slug", ""),
            "question": m.get("question", ""),
            "outcomes": m.get("outcomes", []),
            "volume": m.get("volume", 0),
            "startDate": (m.get("startDate") or "")[:10],
            "endDate": (m.get("endDate") or "")[:10],
            "id": m.get("id", ""),
            "clobTokenIds": m.get("clobTokenIds", ""),
        })
    
    if sort_by_volume:
        readable.sort(key=lambda x: float(x.get("volume") or 0), reverse=True)
    
    ensure_directories([output_path.parent])
    with output_path.open("w") as f:
        json.dump(readable, f, indent=2)
    
    LOGGER.info("Created curated file with %d markets: %s", len(readable), output_path)


def select_macro_markets(
    markets: List[dict] | None = None,
    session: Session | None = None,
    use_curated: bool = True,
    curated_path: Path = config.RAW_POLYMARKET / "macro_markets_curated.json",
) -> List[dict]:
    """Get macro markets, preferring the curated list if available.
    
    Priority order:
    1. Curated file (macro_markets_curated.json) - if exists, uses this
    2. Filter from full markets list using keywords
    
    The curated file allows manual exclusion by setting include=false.
    
    Args:
        markets: Pre-loaded markets list (if None, loads from cache/API)
        session: Optional requests session
        use_curated: Whether to use curated file if available
        curated_path: Path to curated markets file
    
    Returns:
        List of macro market dicts
    """
    # Try curated file first (allows manual filtering)
    if use_curated:
        curated = load_curated_markets(curated_path)
        if curated is not None:
            return curated
    
    # Fall back to keyword filtering
    if markets is None:
        markets = fetch_markets_2024(session=session)
    
    macro = [m for m in markets if is_macro_market(m)]
    LOGGER.info("Selected %d macro markets from %d total", len(macro), len(markets))
    
    # Create curated file for future manual editing
    if use_curated and macro:
        create_curated_file(macro, curated_path)
    
    return macro


# =============================================================================
# STEP 3: Fetch Price Data (CLOB API) - Only for filtered markets
# =============================================================================

def _clean_slug(text: str) -> str:
    """Convert text to a clean slug for column names."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def extract_token_ids(market: dict) -> List[str]:
    """Extract CLOB token IDs from market metadata."""
    raw = market.get("clobTokenIds")
    if not raw:
        return []
    
    # Handle JSON string format
    if isinstance(raw, str):
        raw = raw.strip()
        if raw.startswith("["):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return [t.strip().strip('"\'') for t in raw.split(",") if t.strip()]
    
    # Handle list format
    if isinstance(raw, list):
        return [str(t).strip().strip('"\'') for t in raw if t]
    
    return []


def fetch_price_history(
    token_id: str,
    fidelity: int = config.DEFAULT_FIDELITY_MINUTES,
    session: Session | None = None,
    max_retries: int = 3,
) -> pd.DataFrame:
    """Fetch price history for a token using the proven interval=max approach.
    
    Args:
        token_id: The CLOB token ID
        fidelity: Data granularity in minutes (1440 = daily, 60 = hourly)
        session: Optional requests session for connection pooling
        max_retries: Max retry attempts for rate limiting
    
    Returns:
        DataFrame with timestamp and price columns
    """
    s = session or requests.Session()
    token_id = str(token_id).strip().strip('[]"\'')
    
    # Use the proven working parameters: interval=max
    params = {
        "market": token_id,
        "interval": "max",
        "fidelity": fidelity,
    }
    
    for attempt in range(max_retries):
        try:
            resp = s.get(config.CLOB_HISTORY_URL, params=params, timeout=30)
            
            if resp.status_code == 429:  # Rate limited
                wait_time = 2 ** attempt
                LOGGER.warning("Rate limited, waiting %ds...", wait_time)
                time.sleep(wait_time)
                continue
            
            resp.raise_for_status()
            data = resp.json()
            
            # Extract history from response
            history = data.get("history", []) if isinstance(data, dict) else data
            if not history:
                return pd.DataFrame(columns=["timestamp", "price"])
            
            # Parse into DataFrame
            df = pd.DataFrame(history)
            df = df.rename(columns={"t": "timestamp", "p": "price"})
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
            df = df[["timestamp", "price"]].dropna()
            
            return df
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400:
                # Invalid token, no data available
                return pd.DataFrame(columns=["timestamp", "price"])
            LOGGER.warning("HTTP error for token %s: %s", token_id[:20], e)
            
        except requests.exceptions.RequestException as e:
            LOGGER.warning("Request error for token %s: %s", token_id[:20], e)
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
                
        except Exception as e:
            LOGGER.warning("Unexpected error for token %s: %s", token_id[:20], e)
            break
    
    return pd.DataFrame(columns=["timestamp", "price"])


def build_prices_table(
    macro_markets: List[dict],
    session: Session | None = None,
    delay: float = 0.3,
) -> pd.DataFrame:
    """Build price table from macro markets.
    
    Args:
        macro_markets: List of filtered macro market dicts
        session: Optional requests session
        delay: Seconds to wait between API calls (rate limiting)
    
    Returns:
        DataFrame with daily prices, one column per market outcome
    """
    s = session or requests.Session()
    start_ts = to_unix_ts(config.START_DATE)
    end_ts = to_unix_ts(config.END_DATE)
    
    all_series: List[pd.Series] = []
    total_tokens = 0
    successful = 0
    
    LOGGER.info("Fetching price history for %d markets...", len(macro_markets))
    
    for idx, market in enumerate(macro_markets, 1):
        tokens = extract_token_ids(market)
        if not tokens:
            continue
        
        slug = _clean_slug(market.get("slug") or market.get("question", "market"))
        outcomes = market.get("outcomes") or []
        
        for tok_idx, token_id in enumerate(tokens):
            total_tokens += 1
            label = outcomes[tok_idx] if tok_idx < len(outcomes) else f"leg{tok_idx+1}"
            col_name = f"{slug}_{_clean_slug(label)}"
            
            df = fetch_price_history(token_id, session=s)
            
            if not df.empty:
                # Filter to 2024 date range
                start_dt = pd.Timestamp(start_ts, unit='s', tz='UTC')
                end_dt = pd.Timestamp(end_ts, unit='s', tz='UTC')
                df = df[(df["timestamp"] >= start_dt) & (df["timestamp"] <= end_dt)]
                
                if not df.empty:
                    successful += 1
                    series = df.set_index("timestamp")["price"].rename(col_name)
                    all_series.append(series)
            
            # Progress logging
            if successful > 0 and successful % 50 == 0:
                LOGGER.info("Progress: %d/%d tokens (%d markets)", successful, total_tokens, idx)
            
            # Rate limiting
            time.sleep(delay)
    
    # Summary
    rate = (successful / total_tokens * 100) if total_tokens > 0 else 0
    LOGGER.info("Fetched %d/%d tokens (%.1f%% success)", successful, total_tokens, rate)
    
    if not all_series:
        LOGGER.error("No price data retrieved!")
        return pd.DataFrame()
    
    # Combine and resample to daily
    prices_df = pd.concat(all_series, axis=1).sort_index()
    prices_df = prices_df.resample("D").last()
    
    LOGGER.info("Built price table: %d days × %d columns", len(prices_df), len(prices_df.columns))
    return prices_df


# =============================================================================
# Main Pipeline Function
# =============================================================================

def fetch_and_save_prices(
    output_path: Path = config.RAW_POLYMARKET / "polymarket_macro_prices_2024.csv",
) -> pd.DataFrame:
    """Run the full pipeline: fetch markets → filter → get prices → save.
    
    This function orchestrates the API-efficient workflow:
    1. Load macro markets (from cache if available, otherwise filter from full list)
    2. Fetch price data only for macro markets
    3. Save to CSV
    
    Cache structure:
    - markets_2024_cache.json: Full 14,000+ markets (from Gamma API)
    - macro_markets_2024_cache.json: Filtered ~261 macro markets
    """
    ensure_directories([output_path.parent])
    
    # Step 1: Get macro markets (uses cache if available)
    LOGGER.info("Step 1: Loading macro markets...")
    macro_markets = select_macro_markets()
    
    if not macro_markets:
        LOGGER.error("No macro markets found!")
        return pd.DataFrame()
    
    LOGGER.info("Working with %d macro markets", len(macro_markets))
    
    # Step 2: Fetch price data
    LOGGER.info("Step 2: Fetching price data...")
    prices = build_prices_table(macro_markets)
    
    # Save
    if not prices.empty:
        save_dataframe(prices, output_path)
        LOGGER.info("Saved prices to %s", output_path)
    
    return prices
