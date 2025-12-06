# Troubleshooting Guide

## 🚨 Common Issues and Solutions

### Issue: "No Polymarket price data collected" with 400 Errors

#### Symptoms:
```
[WARNING] Failed to fetch price history for token ...: 400 Client Error: Bad Request
[WARNING] No price history for european_central_bank_cuts_rates...
[WARNING] No Polymarket price data collected. Aborting downstream steps.
```

#### What's Happening:

The Polymarket API has **two separate endpoints**:

1. **Gamma API** (Market Metadata)
   - Returns ALL markets including those that:
     - Never had trading activity
     - Were created but never deployed to CLOB
     - Have invalid/malformed token IDs
   
2. **CLOB API** (Price History)  
   - Only returns data for markets that **actually traded**
   - Returns 400 errors for tokens that don't exist in their system

**Result**: Some token IDs from the metadata simply don't have price history, which is **expected behavior**.

#### Solutions:

**Option 1: Wait for Partial Success** ⏱️ (Recommended)

The improved code now tracks success rate. Even if many tokens fail (400 errors), as long as **some** succeed, you'll get data:

```bash
# Delete the empty price cache
rm data/raw/polymarket_macro_prices_2024.csv

# Run again - be patient, this takes 5-10 minutes
python main.py
```

**Expected output:**
```
[INFO] Progress: 20/50 tokens successful (40 markets processed)
[INFO] Progress: 40/100 tokens successful (80 markets processed)
[INFO] Price fetch complete: 87/228 tokens successful (38.2%), 141 failed
[INFO] Built price table: 365 days × 87 markets
✓ Successfully collected price data: 365 days × 87 markets
```

**✅ Success criteria**: As long as you get **at least 10-20 successful tokens**, the analysis can proceed.

---

**Option 2: Reduce Date Range** 📅

Some markets may only have recent data. Try a shorter date range:

Edit `src/config.py`:

```python
# Instead of full year
START_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
END_DATE = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

# Try last 6 months
START_DATE = datetime(2024, 7, 1, tzinfo=timezone.utc)
END_DATE = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
```

Then run:
```bash
rm data/raw/markets_2024_cache.json  # Force refresh with new dates
rm data/raw/polymarket_macro_prices_2024.csv
python main.py
```

---

**Option 3: Filter for Active Markets** 🎯

Modify the market selection to only include markets with trading volume:

Edit `src/polymarket_api.py`, in `select_macro_markets_2024()`:

```python
def select_macro_markets_2024(session: Session | None = None) -> List[dict]:
    markets = fetch_markets_2024(session=session)
    
    # Filter for macro markets with actual trading activity
    macro = [
        m for m in markets 
        if is_macro_market(m) 
        and m.get('volume', 0) > 100  # Only markets with $100+ volume
        and m.get('clobTokenIds')  # Must have token IDs
    ]
    
    LOGGER.info("Selected %s macro markets from %s total", len(macro), len(markets))
    return macro
```

---

**Option 4: Use Sample Markets** 🧪

For testing, use only markets you know have data:

Create a test script:

```python
# test_price_fetch.py
from src.polymarket_api import build_prices_table, select_macro_markets_2024

# Get all markets
all_markets = select_macro_markets_2024()

# Filter for markets with high volume (likely to have data)
active_markets = [
    m for m in all_markets 
    if m.get('volume', 0) > 1000  # $1000+ volume
][:20]  # Take first 20

print(f"Testing with {len(active_markets)} high-volume markets")

# Try to build price table
prices = build_prices_table(active_markets)

if not prices.empty:
    print(f"✓ Success! Got data: {prices.shape}")
    prices.to_csv('data/raw/test_prices.csv')
else:
    print("✗ Still no data")
```

Run:
```bash
python test_price_fetch.py
```

---

### Issue: Rate Limiting (429 Errors)

#### Symptoms:
```
[WARNING] Rate limited for token ..., waiting 2 seconds...
```

#### Solution:

**This is handled automatically** with exponential backoff (1s, 2s, 4s). However, if you're seeing many of these:

1. **Increase the delay** between requests:

   Edit `src/polymarket_api.py` line 223:
   ```python
   time.sleep(0.5)  # Change to 1.0 or 2.0
   ```

2. **Wait and retry**:
   ```bash
   # Wait 5-10 minutes, then try again
   python main.py
   ```

---

### Issue: All Tokens Failing

#### Symptoms:
```
[ERROR] No price data fetched! All 228 tokens failed.
```

#### Diagnostic Steps:

1. **Check internet connection**:
   ```bash
   curl https://clob.polymarket.com/prices-history
   # Should return: {"error":"Missing required query parameter: market"}
   # If you get timeout/connection error, network issue
   ```

2. **Check API accessibility**:
   ```bash
   # Test with a known working token
   curl "https://clob.polymarket.com/prices-history?market=21742633143463906290569050155826241533067272736897614950488156847949938836455&startTs=1704067200&endTs=1735689599&fidelity=1440"
   # Should return JSON array of price data
   ```

3. **Check market cache**:
   ```bash
   # Ensure cache has token IDs
   python -c "
   import json
   data = json.load(open('data/raw/markets_2024_cache.json'))
   print(f'Markets: {len(data)}')
   sample = data[0]
   print(f'Token IDs present: {\"clobTokenIds\" in sample}')
   "
   ```

---

### Issue: "Loaded existing price data from ... (0 columns)"

#### Symptoms:
```
[INFO] Loaded existing price data from ... (0 columns)
```

#### Cause:
Previous run created empty CSV file.

#### Solution:
```bash
# Delete the empty cache
rm data/raw/polymarket_macro_prices_2024.csv

# Run again
python main.py
```

---

## 📊 Understanding Success Rates

### Typical Success Rates:

- **Good**: 30-50% of tokens succeed (~70-115 markets)
- **Acceptable**: 15-30% of tokens succeed (~35-70 markets)  
- **Poor**: <15% of tokens succeed (<35 markets)
- **Failed**: 0% tokens succeed (all return 400/429)

### Why Low Success Rates Are Expected:

1. **Metadata includes all markets** - even ones never deployed
2. **CLOB only has traded markets** - subset of metadata
3. **Some markets resolve before trading starts**
4. **Some markets have technical issues**

As long as you get **50+ successful markets**, the MUI analysis will work fine!

---

## 🔍 Debugging Commands

### Check what's in the cache:

```bash
# Market cache
python -c "
import json
data = json.load(open('data/raw/markets_2024_cache.json'))
print(f'Total markets: {len(data)}')
with_tokens = sum(1 for m in data if m.get('clobTokenIds'))
print(f'Markets with tokens: {with_tokens}')
"
```

### Check successful fetches:

```bash
# Price cache
python -c "
import pandas as pd
prices = pd.read_csv('data/raw/polymarket_macro_prices_2024.csv', index_col=0)
print(f'Days: {len(prices)}')
print(f'Markets: {len(prices.columns)}')
print(f'Sample columns: {list(prices.columns[:5])}')
"
```

### Test single token:

```python
# test_single_token.py
from src.polymarket_api import fetch_price_history_for_token
from src import config
from src.utils import to_unix_ts

# Known working token from Trump election market
token_id = "21742633143463906290569050155826241533067272736897614950488156847949938836455"

start_ts = to_unix_ts(config.START_DATE)
end_ts = to_unix_ts(config.END_DATE)

df = fetch_price_history_for_token(token_id, start_ts, end_ts)

if not df.empty:
    print(f"✓ Success! Got {len(df)} data points")
    print(df.head())
else:
    print("✗ Failed to fetch")
```

---

## 💡 Best Practices

1. **Be patient on first run** - Takes 5-10 minutes to fetch all data
2. **Don't panic on 400 errors** - These are expected for ~50% of tokens
3. **Check success rate** - Look for "X/Y tokens successful" in logs
4. **Use cache** - Second run is instant
5. **Delete empty cache files** - If a run fails, clean up before retrying

---

## 📞 Still Having Issues?

If none of the above helps:

1. Check the logs carefully for the success rate
2. Verify you have at least some successful tokens
3. Try with a smaller date range
4. Test with a single known-working token
5. Check if Polymarket's API is having issues

Remember: **Some token failures are normal and expected!** The key is getting enough successful fetches to have meaningful data.

