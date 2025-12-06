"""Download VIX data for 2024 using yfinance."""
import pandas as pd
import yfinance as yf
from pathlib import Path

# Output path
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "raw" / "vix_2024.csv"

def fetch_vix() -> pd.DataFrame:
    """Download VIX data from Yahoo Finance for 2024."""
    print("Downloading VIX data for 2024...")
    
    data = yf.download("^VIX", start="2024-01-01", end="2024-12-31", progress=False)
    
    if data.empty:
        print("No VIX data downloaded")
        return pd.DataFrame()
    
    # Handle multi-level column index from yfinance
    if isinstance(data.columns, pd.MultiIndex):
        vix = data[("Close", "^VIX")].to_frame(name="VIX")
    else:
        vix = data[["Close"]].rename(columns={"Close": "VIX"})
    
    # Save to CSV
    vix.to_csv(OUTPUT_PATH)
    print(f"Saved VIX data to {OUTPUT_PATH} ({len(vix)} rows)")
    
    return vix


if __name__ == "__main__":
    vix = fetch_vix()
    if not vix.empty:
        print(f"\nVIX data summary:")
        print(f"  Date range: {vix.index.min().date()} to {vix.index.max().date()}")
        print(f"  Data points: {len(vix)}")
        print(f"  VIX range: {vix['VIX'].min():.2f} - {vix['VIX'].max():.2f}")
