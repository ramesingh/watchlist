import json
import os
import datetime
import re
import glob
import requests
from bs4 import BeautifulSoup
import yfinance as yf

DEFAULT_US_TICKERS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "ANT", "COST",
    "SNPS", "CDNS", "AMZN", "META", "TSLA", "AVGO", "BRK-B", "V"
]

DEFAULT_INDIA_TICKERS = {
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "INFY": "INFY.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "NSE": "544937.BO",
    "BSE": "BSE.NS",
    "TRENT": "TRENT.NS",
    "DMART": "DMART.NS",
    "ICICIBANK": "ICICIBANK.NS",
    "ITC": "ITC.NS",
    "TATAMOTORS": "TATAMOTORS.NS",
    "BHARTIARTL": "BHARTIARTL.NS",
    "BAJFINANCE": "BAJFINANCE.NS",
    "SUNPHARMA": "SUNPHARMA.NS"
}

def load_custom_tickers():
    """
    Checks for watchlist_backup.json (or newest watchlist_backup*.json in the
    current folder or ~/Downloads) exported from stock_watchlist-v6.html so any
    custom tickers added in the UI are automatically fetched daily too.
    """
    us_set = set(DEFAULT_US_TICKERS)
    india_map = dict(DEFAULT_INDIA_TICKERS)

    candidates = []
    for folder in [".", os.path.expanduser("~/Downloads")]:
        candidates.extend(glob.glob(os.path.join(folder, "watchlist_backup*.json")))

    if not candidates:
        return sorted(us_set), india_map

    latest_file = max(candidates, key=os.path.getmtime)
    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        for item in data.get("US", []):
            t = str(item.get("ticker", "")).strip().upper()
            if t:
                us_set.add("BRK-B" if t == "BRK.B" else t)

        for item in data.get("INDIA", []):
            t = str(item.get("ticker", "")).strip().upper()
            ex = str(item.get("ex", "")).strip().upper()
            if not t:
                continue
            if t in india_map:
                continue
            if t.isdigit():
                india_map[t] = f"{t}.BO"
            elif "BSE" in ex and "NSE" not in ex:
                code_match = re.search(r"(\d{6})", ex)
                india_map[t] = f"{code_match.group(1)}.BO" if code_match else f"{t}.BO"
            else:
                india_map[t] = f"{t}.NS"

        print(f"Loaded custom watchlist tickers from: {latest_file}")
    except Exception as e:
        print(f"Warning: could not parse {latest_file}: {e}")

    return sorted(us_set), india_map

def fetch_price(yf_symbol):
    try:
        ticker = yf.Ticker(yf_symbol)
        hist = ticker.history(period="5d")
        if not hist.empty:
            closes = hist["Close"].dropna()
            if not closes.empty:
                return round(float(closes.iloc[-1]), 2)
    except Exception as e:
        print(f"Warning: could not fetch {yf_symbol}: {e}")
    return None

def fetch_ibja_gold():
    url = "https://ibjarates.com/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        matches = re.findall(r"(\d{2}/\d{2}/\d{4})\s+(\d{5,6})\s+(\d{5,6})", text)
        sessions = {}
        for dt, r999, _ in matches:
            val = int(r999)
            if dt not in sessions:
                sessions[dt] = {"date": dt, "am": val, "pm": val}
            else:
                sessions[dt]["pm"] = val
        ordered = list(sessions.values())
        if ordered:
            return ordered[:10]
    except Exception as e:
        print(f"Warning: could not fetch IBJA gold rates: {e}")
    return []

def main():
    us_tickers, india_tickers = load_custom_tickers()

    print(f"Fetching {len(us_tickers)} US stock prices...")
    us_prices = {}
    for sym in us_tickers:
        key = "BRK.B" if sym == "BRK-B" else sym
        price = fetch_price(sym)
        if price is not None:
            us_prices[key] = price

    print(f"Fetching {len(india_tickers)} India stock prices...")
    india_prices = {}
    for key, yf_sym in india_tickers.items():
        price = fetch_price(yf_sym)
        if price is not None:
            india_prices[key] = price
        elif yf_sym.endswith(".NS"):
            # Fallback to BSE suffix if NSE ticker is unavailable
            bo_price = fetch_price(f"{key}.BO")
            if bo_price is not None:
                india_prices[key] = bo_price

    print("Fetching IBJA 24K Gold rates...")
    gold_sessions = fetch_ibja_gold()

    payload = {
        "updated_at": datetime.datetime.now().strftime("%d %b %Y, %I:%M %p IST"),
        "us_prices": us_prices,
        "india_prices": india_prices,
        "gold_sessions": gold_sessions
    }

    with open("live_data.js", "w", encoding="utf-8") as f:
        f.write("window.LIVE_WATCHLIST_DATA = " + json.dumps(payload, indent=2) + ";\n")

    print(f"Done! Updated {len(us_prices)} US stocks, {len(india_prices)} India stocks, and {len(gold_sessions)} gold sessions.")

if __name__ == "__main__":
    main()
