# CLOB Price History API - Complete Walkthrough

## 🎯 Overview

This document walks through **exactly** how price data is pulled from the Polymarket CLOB (Central Limit Order Book) price history API.

## 📋 The Complete Flow

### Step 1: Entry Point - `fetch_and_save_prices()`

**Location**: `src/polymarket_api.py`, line 232

**Purpose**: Orchestrate the entire price fetching process with caching

```python
def fetch_and_save_prices(
    path = config.RAW_DATA / "polymarket_macro_prices_2024.csv",
    use_cache: bool = True,
    force_refresh: bool = False
) -> pd.DataFrame:
```

**What it does:**

1. **Check Cache First** (lines 247-253)
   ```python
   if use_cache and not force_refresh and Path(path).exists():
       prices = pd.read_csv(path, index_col=0, parse_dates=True)
       return prices  # Return cached data immediately
   ```

2. **Get Market List** (line 256)
   ```python
   macro_markets = select_macro_markets_2024()
   # Returns list of 114 macro markets with their metadata
   ```

3. **Fetch Price History** (line 259)
   ```python
   prices = build_prices_table(macro_markets)
   # This is where the API calls happen!
   ```

4. **Save to Cache** (line 262)
   ```python
   save_dataframe(prices, path)
   # Saves to: data/raw/polymarket_macro_prices_2024.csv
   ```

---

### Step 2: Build Price Table - `build_prices_table()`

**Location**: `src/polymarket_api.py`, line 201

**Purpose**: Fetch price history for all markets and combine into one DataFrame

```python
def build_prices_table(macro_markets: List[dict], session: Session | None = None) -> pd.DataFrame:
```

**What it does:**

1. **Initialize** (lines 203-205)
   ```python
   all_series: List[pd.Series] = []  # Will hold all price series
   s = session or requests.Session()  # Reuse HTTP session for efficiency
   start_ts, end_ts = to_unix_ts(config.START_DATE), to_unix_ts(config.END_DATE)
   # Converts: datetime(2024, 1, 1) → 1704067200 (Unix timestamp)
   # Converts: datetime(2024, 12, 31, 23, 59, 59) → 1735689599
   ```

2. **Loop Through Markets** (lines 207-224)
   
   For each of the 114 macro markets:
   
   **a) Extract Token IDs** (line 208)
   ```python
   tokens = extract_token_ids(market)
   # Example: ['71321234567890...', '89765432109876...']
   # Each market can have multiple tokens (one per outcome)
   ```
   
   **b) Create Market Identifier** (line 211)
   ```python
   slug = _market_slug(market)
   # Example: "will_fed_cut_rates_in_march"
   ```
   
   **c) Loop Through Token IDs** (lines 213-224)
   
   For each token (outcome) in the market:
   
   ```python
   for idx, token_id in enumerate(tokens):
       # Create column name
       label = outcomes[idx] if idx < len(outcomes) else f"leg{idx+1}"
       clean_label = _clean_slug(label) or f"leg{idx+1}"
       col_name = f"{slug}_{clean_label}"
       # Example: "will_fed_cut_rates_in_march_yes"
       
       # ⭐ FETCH PRICE HISTORY FROM API ⭐
       df = fetch_price_history_for_token(token_id, start_ts=start_ts, end_ts=end_ts, session=s)
       
       # Convert to time series
       series = df.set_index("timestamp")["price"].rename(col_name)
       all_series.append(series)
       
       # Rate limiting delay
       time.sleep(0.5)  # Wait 0.5 seconds between requests
   ```

3. **Combine All Series** (lines 226-229)
   ```python
   if not all_series:
       return pd.DataFrame()
   
   # Combine all series into wide DataFrame
   prices_df = pd.concat(all_series, axis=1).sort_index()
   
   # Resample to daily frequency (take last price of each day)
   prices_df = prices_df.resample("D").last()
   
   return prices_df
   ```

---

### Step 3: Fetch Single Token - `fetch_price_history_for_token()`

**Location**: `src/polymarket_api.py`, line 161

**Purpose**: Make the actual API call to get price history for ONE token

```python
def fetch_price_history_for_token(
    token_id: str,
    start_ts: int,
    end_ts: int,
    fidelity: int = config.DEFAULT_FIDELITY_MINUTES,  # 1440 = daily
    session: Session | None = None,
    max_retries: int = 3,
) -> pd.DataFrame:
```

**What it does:**

1. **Prepare Request** (lines 169-172)
   ```python
   s = session or requests.Session()
   
   # Clean the token ID
   token_id = str(token_id).strip().strip('[]"\'')
   # Removes any brackets or quotes that might be in the data
   
   # Build request parameters
   params = {
       "market": token_id,        # The token ID (long number)
       "startTs": start_ts,       # Unix timestamp: 1704067200
       "endTs": end_ts,           # Unix timestamp: 1735689599
       "fidelity": fidelity       # 1440 minutes = 1 day intervals
   }
   ```

2. **Make API Call with Retry Logic** (lines 174-198)
   ```python
   for attempt in range(max_retries):  # Try up to 3 times
       try:
           # ⭐ THE ACTUAL API CALL ⭐
           resp = s.get(config.CLOB_HISTORY_URL, params=params, timeout=30)
           # URL: https://clob.polymarket.com/prices-history
           # Full URL looks like:
           # https://clob.polymarket.com/prices-history?
           #   market=71321234567890...&
           #   startTs=1704067200&
           #   endTs=1735689599&
           #   fidelity=1440
           
           resp.raise_for_status()  # Raise error if status != 200
           
           # Parse JSON response
           data = resp.json()
           # Response format: [{"t": 1704067200, "p": 0.234}, {"t": 1704153600, "p": 0.245}, ...]
           
   ```

3. **Process Response** (lines 178-184)
   ```python
           df = pd.DataFrame(data)
           # Creates DataFrame from list of dicts
           
           if df.empty:
               return pd.DataFrame(columns=["timestamp", "price"])
           
           # Rename columns from API format to readable names
           df = df.rename(columns={"p": "price", "t": "timestamp"})[["timestamp", "price"]]
           # "p" → "price", "t" → "timestamp"
           
           # Convert Unix timestamp to datetime
           df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
           # 1704067200 → 2024-01-01 00:00:00+00:00
           
           return df
   ```

4. **Error Handling** (lines 185-198)
   ```python
       except requests.exceptions.HTTPError as e:
           if e.response.status_code == 429:  # Rate limit error
               wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
               LOGGER.warning("Rate limited, waiting %s seconds...", wait_time)
               time.sleep(wait_time)
               continue  # Try again
           
           # Other HTTP errors (400, 404, etc.)
           LOGGER.warning("Failed to fetch: %s", e)
           return pd.DataFrame(columns=["timestamp", "price"])
       
       except requests.exceptions.RequestException as e:
           # Network errors, timeouts, etc.
           LOGGER.warning("Request failed: %s", e)
           return pd.DataFrame(columns=["timestamp", "price"])
   
   # If all retries exhausted
   LOGGER.warning("Max retries reached for token %s", token_id)
   return pd.DataFrame(columns=["timestamp", "price"])
   ```

---

## 🔍 Example: Complete API Call

Let's trace through a real example:

### Input Data

**Market**: "Will the Fed cut rates in March?"
- **Token ID**: `71321234567890123456789012345678901234567890123456789012345678901234` (actual IDs are ~77 digits)
- **Start Date**: 2024-01-01 → Unix: `1704067200`
- **End Date**: 2024-12-31 → Unix: `1735689599`
- **Fidelity**: `1440` minutes (daily)

### API Request

```http
GET https://clob.polymarket.com/prices-history?market=71321234567890123456789012345678901234567890123456789012345678901234&startTs=1704067200&endTs=1735689599&fidelity=1440
```

### API Response

```json
[
  {"t": 1704067200, "p": 0.23},
  {"t": 1704153600, "p": 0.25},
  {"t": 1704240000, "p": 0.24},
  {"t": 1704326400, "p": 0.27},
  ...
  {"t": 1735689599, "p": 0.89}
]
```

### Processed DataFrame

After processing:

```
timestamp              price
2024-01-01 00:00:00+00:00  0.23
2024-01-02 00:00:00+00:00  0.25
2024-01-03 00:00:00+00:00  0.24
2024-01-04 00:00:00+00:00  0.27
...
2024-12-31 23:59:59+00:00  0.89
```

### Final Column Name

Renamed to: `will_fed_cut_rates_in_march_yes`

Added to the combined DataFrame with all other markets.

---

## 📊 Final Output Structure

After processing all 114 markets (with multiple tokens each):

```
                        will_fed_cut_march_yes  will_fed_cut_march_no  will_inflation_3pct_yes  ...
timestamp                                                                                          
2024-01-01 00:00:00+00:00                 0.23                   0.77                     0.45  ...
2024-01-02 00:00:00+00:00                 0.25                   0.75                     0.43  ...
2024-01-03 00:00:00+00:00                 0.24                   0.76                     0.41  ...
...
2024-12-31 23:59:59+00:00                 0.89                   0.11                     0.67  ...
```

**Shape**: ~365 rows (days) × ~200+ columns (market outcomes)

**Saved to**: `data/raw/polymarket_macro_prices_2024.csv`

---

## 🔑 Key Configuration

### API Settings (`src/config.py`)

```python
# API Endpoints
CLOB_HISTORY_URL = "https://clob.polymarket.com/prices-history"

# Time Range
START_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
END_DATE = datetime(2024, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

# Data Granularity
DEFAULT_FIDELITY_MINUTES = 1440  # Daily data points (24 hours * 60 minutes)
```

### Fidelity Options

The `fidelity` parameter controls how granular the data is:

- `1` = 1-minute intervals (very granular, huge dataset)
- `60` = 1-hour intervals
- `1440` = 1-day intervals (default, most efficient)
- `10080` = 1-week intervals

**Current setting**: `1440` (daily) is perfect for macro analysis.

---

## ⏱️ Performance & Rate Limiting

### Rate Limiting Protection

1. **Delay Between Requests**: 0.5 seconds
   ```python
   time.sleep(0.5)  # After each token fetch
   ```

2. **Exponential Backoff**: If rate limited (429 error)
   ```python
   wait_time = 2 ** attempt  # 1s, 2s, 4s
   ```

3. **Max Retries**: 3 attempts per token

### Time Estimates

With 114 markets, average 2 tokens each = ~228 API calls

- **Best case**: 228 × 0.5s = 114 seconds (~2 minutes)
- **With rate limits**: 5-10 minutes
- **With cache**: <1 second (instant!)

---

## 🎯 Summary of Data Flow

```
main.py (line 26)
    ↓
fetch_and_save_prices()
    ↓
    ├─→ Check cache → If exists, return cached data ✓
    │
    └─→ If no cache:
        ↓
    build_prices_table(markets)
        ↓
        For each market:
            For each token:
                ↓
        fetch_price_history_for_token()
                ↓
        GET https://clob.polymarket.com/prices-history
                ↓
        Response: [{"t": ..., "p": ...}, ...]
                ↓
        Convert to DataFrame
                ↓
        Wait 0.5 seconds (rate limiting)
                ↓
        Next token...
        ↓
    Combine all series → Wide DataFrame
        ↓
    Resample to daily frequency
        ↓
    Save to CSV cache
        ↓
    Return DataFrame
```

---

## 🔧 Helper Functions

### `to_unix_ts(dt: datetime) -> int`

Converts Python datetime to Unix timestamp:

```python
datetime(2024, 1, 1, tzinfo=timezone.utc) → 1704067200
```

### `extract_token_ids(market: dict) -> List[str]`

Extracts token IDs from market metadata, handling various formats:
- Comma-separated strings
- JSON array strings
- Python lists

### `_market_slug(market: dict) -> str`

Creates clean identifier from market name:

```python
"Will the Fed cut rates in March?" → "will_fed_cut_rates_in_march"
```

### `_clean_slug(text: str) -> str`

Cleans text to valid identifier:
- Lowercase
- Replace non-alphanumeric with underscores
- Strip trailing underscores

---

## 💡 Key Takeaways

1. ✅ **One API call per token** - Not per market (markets can have multiple tokens)
2. ✅ **Caching is automatic** - Second run is instant
3. ✅ **Rate limiting is handled** - Exponential backoff + delays
4. ✅ **Error handling is robust** - Returns empty DataFrame on failure, doesn't crash
5. ✅ **Daily granularity** - 1440-minute fidelity gives one price per day
6. ✅ **Full year coverage** - Jan 1 to Dec 31, 2024

The code is designed to be **resilient**, **efficient**, and **cache-friendly**! 🎉

