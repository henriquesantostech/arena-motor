# Arena of Agents - phase 0: first program
# Downloads daily prices for a few S&P 100 companies and shows a chart.
# Run with:  .venv\Scripts\python.exe phase0\prices.py   (also needs matplotlib)

# --- Part 1: tools ------------------------------------------------------------------
from pathlib import Path            # folders and files

import matplotlib.pyplot as plt     # charts
import pandas as pd                 # tables (like a spreadsheet)
import yfinance as yf               # prices from Yahoo Finance


# --- Part 2: what we want --------------------------------------------------------------
COMPANIES = ["AAPL", "MSFT", "JNJ", "KO", "JPM"]   # Apple, Microsoft, Johnson & Johnson, Coca-Cola, JPMorgan
START = "2025-01-01"
DATA_DIR = Path("data")
CHART_DIR = Path("charts")


# --- Part 3: fetch from Yahoo ------------------------------------------------------------
def fetch_yahoo(companies, start):
    """Returns a table: one row per day, one column per company (closing price)."""
    data = yf.download(companies, start=start, auto_adjust=True, progress=False)
    return data["Close"]


# --- Part 4: check what arrived --------------------------------------------------------
def fetch_prices(companies, start):
    prices = fetch_yahoo(companies, start).dropna(how="all")
    if prices.empty:
        raise SystemExit("Yahoo returned no data. Try again in a moment.")
    missing = [c for c in companies if prices[c].isna().all()]
    if missing:
        print(f"Warning: no data for {missing}")
    print("Source: Yahoo Finance")
    return prices


# --- Part 5: the program -------------------------------------------------------------------
def main():
    prices = fetch_prices(COMPANIES, START)
    print(f"\n{len(prices)} days, from {prices.index[0].date()} to {prices.index[-1].date()}")
    print("\nLast 5 days (closing price, USD):")
    print(prices.tail().round(2))

    DATA_DIR.mkdir(exist_ok=True)
    prices.round(4).to_csv(DATA_DIR / "prices.csv")

    # Every company starts at 100, to compare the evolution rather than the price
    base_100 = prices / prices.bfill().iloc[0] * 100
    base_100.plot(figsize=(10, 5), title="Evolution since the start (start = 100)")
    plt.ylabel("value (start = 100)")
    plt.grid(alpha=0.3)
    CHART_DIR.mkdir(exist_ok=True)
    plt.savefig(CHART_DIR / "prices.png", dpi=120, bbox_inches="tight")
    print(f"\nTable: {DATA_DIR / 'prices.csv'}   Chart: {CHART_DIR / 'prices.png'}")
    plt.show()


if __name__ == "__main__":
    main()
