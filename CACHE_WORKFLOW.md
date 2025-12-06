# Cache-First Workflow Guide

## 🔄 How the Caching System Works

The project implements a **cache-first** approach to minimize API calls and speed up subsequent runs.

### Workflow Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    START: Run main.py                    │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │ Check Market Cache    │
         │ (markets_2024_cache.  │
         │       json)           │
         └───────┬───────────────┘
                 │
        ┌────────┴────────┐
        │                 │
    EXISTS           NOT EXISTS
        │                 │
        ▼                 ▼
  ┌─────────┐      ┌──────────────┐
  │ Load    │      │ Fetch from   │
  │ from    │      │ Polymarket   │
  │ Cache   │      │ API (~4s)    │
  │ (0.15s) │      │ Max 5100     │
  └────┬────┘      │ markets      │
       │           └──────┬───────┘
       │                  │
       │                  ▼
       │           ┌──────────────┐
       │           │ Save to      │
       │           │ Cache File   │
       │           └──────┬───────┘
       │                  │
       └──────────┬───────┘
                  │
                  ▼
         ┌────────────────┐
         │ Filter Macro   │
         │ Markets (114)  │
         └────────┬───────┘
                  │
                  ▼
         ┌───────────────────────┐
         │ Check Price Cache     │
         │ (polymarket_macro_    │
         │    prices_2024.csv)   │
         └───────┬───────────────┘
                 │
        ┌────────┴────────┐
        │                 │
    EXISTS           NOT EXISTS
        │                 │
        ▼                 ▼
  ┌─────────┐      ┌──────────────┐
  │ Load    │      │ Fetch Price  │
  │ from    │      │ History for  │
  │ Cache   │      │ Each Token   │
  │ (fast)  │      │ (slower,     │
  └────┬────┘      │ 0.5s delay   │
       │           │ per request) │
       │           └──────┬───────┘
       │                  │
       │                  ▼
       │           ┌──────────────┐
       │           │ Save to      │
       │           │ Cache File   │
       │           └──────┬───────┘
       │                  │
       └──────────┬───────┘
                  │
                  ▼
         ┌────────────────┐
         │ Continue with  │
         │ VIX, MUI, etc. │
         └────────────────┘
```

## 📂 Cache Files

### 1. Market Cache
- **File**: `data/raw/markets_2024_cache.json`
- **Contents**: 5,100 market records from Polymarket
- **Size**: ~10-15 MB
- **Lifespan**: Permanent (delete to refresh)

### 2. Price Cache
- **File**: `data/raw/polymarket_macro_prices_2024.csv`
- **Contents**: Daily price history for all macro market tokens
- **Size**: Varies based on number of markets/tokens
- **Lifespan**: Permanent (delete to refresh)

## ✅ Verification

### Test the Cache System

```bash
# Activate virtual environment
source venv/bin/activate

# Test caching directly (won't fetch prices, just markets)
python src/polymarket_api.py

# Run full pipeline (will fetch prices if cache doesn't exist)
python main.py
```

### Expected Output (with cache):

```
[INFO] Loaded 5100 markets from cache: data/raw/markets_2024_cache.json
[INFO] Selected 114 macro markets from 5100 total
[INFO] Loaded existing price data from data/raw/polymarket_macro_prices_2024.csv (XXX columns)
```

### Expected Output (without cache):

```
[INFO] Fetching markets from API (max offset: 5000)...
[INFO] Fetched 100 markets (offset 0)
[INFO] Fetched 100 markets (offset 100)
...
[INFO] Saved 5100 markets to cache: data/raw/markets_2024_cache.json
[INFO] Selected 114 macro markets from 5100 total
[Starting price fetch...]
```

## 🔧 Cache Management

### Force Refresh Market Data

```bash
# Delete market cache
rm data/raw/markets_2024_cache.json

# Re-run to fetch fresh data
python main.py
```

### Force Refresh Price Data

```bash
# Delete price cache
rm data/raw/polymarket_macro_prices_2024.csv

# Re-run to fetch fresh data
python main.py
```

### Force Refresh Everything

```bash
# Delete all cache files
rm data/raw/markets_2024_cache.json
rm data/raw/polymarket_macro_prices_2024.csv

# Re-run to fetch all fresh data
python main.py
```

## 🎯 Performance Benefits

| Operation | Without Cache | With Cache | Improvement |
|-----------|---------------|------------|-------------|
| Market Loading | ~4 seconds | ~0.15 seconds | **27x faster** |
| API Calls (markets) | ~51 calls | 0 calls | **100% reduction** |
| Price Loading | Minutes | Instant | **∞ faster** |
| API Calls (prices) | Hundreds | 0 calls | **100% reduction** |

## ⚙️ Programmatic Control

### In Python Code

```python
from src.polymarket_api import fetch_markets_2024, fetch_and_save_prices

# Use cache (default)
markets = fetch_markets_2024(use_cache=True)
prices = fetch_and_save_prices(use_cache=True)

# Force fresh fetch (ignore cache)
markets = fetch_markets_2024(use_cache=False)
prices = fetch_and_save_prices(force_refresh=True)

# Custom cache path
markets = fetch_markets_2024(
    use_cache=True,
    cache_path=Path("custom/path/cache.json")
)
```

## 🚨 Troubleshooting

### Issue: "Loaded 0 rows, 0 columns" for price cache

**Cause**: Previous price fetch failed or was interrupted  
**Solution**: Delete the empty cache file and re-run

```bash
rm data/raw/polymarket_macro_prices_2024.csv
python main.py
```

### Issue: "ImportError: attempted relative import"

**Cause**: Running a module file directly instead of through main.py  
**Solution**: Fixed! The imports now handle both relative and absolute imports. You can run:

```bash
# Option 1: Run through main.py (recommended)
python main.py

# Option 2: Run module directly (now works)
python src/polymarket_api.py
```

### Issue: Rate limiting (429 errors)

**Cause**: Too many API requests too quickly  
**Solution**: The code handles this automatically with:
- Exponential backoff (1s, 2s, 4s delays)
- 0.5s delay between requests
- Retry logic (3 attempts)

If still occurring, wait a few minutes and try again, or use cached data.

## 📝 Cache Logic Implementation

### Market Cache (in `fetch_markets_2024`)

```python
# 1. Check if cache exists
if use_cache:
    cached_markets = _load_markets_cache(cache_path)
    if cached_markets:
        return cached_markets  # ✓ Return cached data

# 2. If no cache, fetch from API
markets = []
# ... fetch logic ...

# 3. Save to cache for next time
_save_markets_cache(markets, cache_path)
return markets
```

### Price Cache (in `fetch_and_save_prices`)

```python
# 1. Check if price cache exists
if use_cache and not force_refresh and Path(path).exists():
    try:
        prices = pd.read_csv(path, ...)
        return prices  # ✓ Return cached data
    except Exception:
        pass  # Fall through to fetch

# 2. If no cache, fetch from API
macro_markets = select_macro_markets_2024()  # Uses market cache!
prices = build_prices_table(macro_markets)

# 3. Save to cache for next time
save_dataframe(prices, path)
return prices
```

## 🎉 Summary

The cache-first workflow:

1. ✅ **Checks cache first** - Always looks for cached data before fetching
2. ✅ **Fetches only when needed** - Only calls APIs if cache doesn't exist
3. ✅ **Saves automatically** - Automatically caches fetched data
4. ✅ **Handles errors gracefully** - Falls back to API fetch if cache is corrupt
5. ✅ **Configurable** - Can force refresh or disable caching if needed

This approach reduces API load by **~90-100%** on subsequent runs! 🚀

