
import sys
import subprocess
import importlib.util

for package, module in [("pandas", "pandas"), ("numpy", "numpy"), ("requests", "requests"), ("yfinance", "yfinance")]:
    if importlib.util.find_spec(module) is None:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package])

import io
import time
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

HEADERS = {"User-Agent": "Mozilla/5.0"}
INDEX_FILES = [
    [
        "https://www.niftyindices.com/IndexConstituent/ind_niftymidcap150list.csv",
        "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv"
    ],
    [
        "https://www.niftyindices.com/IndexConstituent/ind_niftysmallcap250list.csv",
        "https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv"
    ]
]

def load_universe():
    symbols = set()
    for urls in INDEX_FILES:
        loaded = False
        for url in urls:
            try:
                response = requests.get(url, headers=HEADERS, timeout=20)
                response.raise_for_status()
                frame = pd.read_csv(io.BytesIO(response.content))
                columns = {str(c).strip().lower(): c for c in frame.columns}
                symbol_column = columns.get("symbol") or columns.get("ticker")
                if symbol_column is None:
                    continue
                found = frame[symbol_column].dropna().astype(str).str.strip()
                found = [s for s in found if s and s.lower() != "nan"]
                if found:
                    symbols.update(s if s.endswith(".NS") else s + ".NS" for s in found)
                    print("Loaded", len(found), "stocks from", url.split("/")[2])
                    loaded = True
                    break
            except Exception as error:
                print("List source failed:", url.split("/")[2], str(error)[:100])
        if not loaded:
            print("Warning: one index list could not be loaded.")
    return sorted(symbols)

def get_stock_frame(data, ticker):
    if not isinstance(data.columns, pd.MultiIndex):
        return data.copy()
    try:
        if ticker in data.columns.get_level_values(0):
            return data[ticker].copy()
        if ticker in data.columns.get_level_values(1):
            return data.xs(ticker, axis=1, level=1).copy()
    except Exception:
        pass
    return pd.DataFrame()

def scan_one(ticker, data):
    try:
        d = get_stock_frame(data, ticker)
        required = ["Close", "High", "Low", "Volume"]
        if d.empty or not all(c in d.columns for c in required):
            return None
        d = d[required].apply(pd.to_numeric, errors="coerce").dropna()
        if len(d) < 70:
            return None

        c, h, l, v = d["Close"], d["High"], d["Low"], d["Volume"]
        price = float(c.iloc[-1])
        previous = float(c.iloc[-2])
        ma20 = float(c.iloc[-21:-1].mean())
        ma50 = float(c.iloc[-51:-1].mean())
        high20 = float(h.iloc[-21:-1].max())
        low60 = float(l.iloc[-61:-1].min())
        avg_volume = float(v.iloc[-21:-1].mean())
        avg_value = float((c.iloc[-21:-1] * v.iloc[-21:-1]).mean())
        range5 = float(((h - l) / c).tail(5).mean())
        pullback = 1 - price / high20 if high20 else 1
        trend60 = previous / float(c.iloc[-61]) - 1
        higher_lows = float(l.iloc[-1]) >= float(l.iloc[-5:-1].min())
        dry_volume = float(v.iloc[-1]) <= avg_volume * 1.15
        near_high = price >= high20 * 0.92
        trend_ok = previous > ma20 and ma20 > ma50 and trend60 >= 0.05
        tight_ok = range5 <= 0.06 and pullback <= 0.12
        if price < 30 or avg_volume < 50000 or avg_value < 5000000:
            return None
        if not (trend_ok and tight_ok and near_high):
            return None

        return {
            "Symbol": ticker.replace(".NS", ""),
            "Price": round(price, 2),
            "Trend_60D_Percent": round(trend60 * 100, 2),
            "Pullback_From_20D_High_Percent": round(pullback * 100, 2),
            "Average_5D_Range_Percent": round(range5 * 100, 2),
            "Higher_Lows": higher_lows,
            "Volume_Drying": dry_volume,
            "Average_Daily_Volume": int(avg_volume),
            "Breakout_Level": round(high20 * 1.001, 2),
            "Stage": "BREAKOUT AREA" if price >= high20 else "NEAR BREAKOUT"
        }
    except Exception:
        return None

def check_intraday(row):
    ticker = row["Symbol"] + ".NS"
    try:
        q = yf.download(
            ticker, period="5d", interval="5m",
            auto_adjust=True, progress=False, threads=False
        )
        if q.empty:
            return None
        if isinstance(q.columns, pd.MultiIndex):
            q.columns = q.columns.get_level_values(0)
        if not all(c in q.columns for c in ["Close", "Volume"]):
            return None
        q = q[["Close", "Volume"]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(q) < 10:
            return None
        price = float(q["Close"].iloc[-1])
        previous = float(q["Close"].iloc[-2])
        volume = float(q["Volume"].iloc[-1])
        average = float(q["Volume"].tail(31).iloc[:-1].mean())
        level = float(row["Breakout_Level"])
        crossed = price > level and previous <= level
        volume_surge = average > 0 and volume >= 1.5 * average
        if crossed and volume_surge:
            return {
                "Symbol": row["Symbol"],
                "Latest_5m_Price": round(price, 2),
                "Breakout_Level": round(level, 2),
                "Volume_vs_Recent_5m_Average": round(volume / average, 2),
                "Signal": "5-MIN BREAKOUT + VOLUME"
            }
    except Exception as error:
        print("Intraday data issue:", ticker, str(error)[:80])
    return None

def main():
    print("Starting early-entry stock scanner...")
    symbols = load_universe()
    print("Total unique stocks loaded:", len(symbols))
    if not symbols:
        raise RuntimeError(
            "Could not download index lists. Check internet access or try again later."
        )

    print("Downloading daily prices for", len(symbols), "stocks...")
    all_data = yf.download(
        symbols,
        period="1y",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False
    )

    if all_data.empty:
        raise RuntimeError("Yahoo Finance returned no daily data. Try again later.")

    print("Checking early-entry conditions...")
    candidates = []
    for ticker in symbols:
        result = scan_one(ticker, all_data)
        if result:
            candidates.append(result)

    radar = pd.DataFrame(candidates)
    if not radar.empty:
        radar = radar.sort_values(
            ["Volume_Drying", "Trend_60D_Percent"],
            ascending=[False, False]
        )
    radar.to_csv("early_entry_radar.csv", index=False)

    print("\n========== EARLY-ENTRY RADAR ==========")
    if radar.empty:
        print("No stocks matched today's conditions.")
    else:
        print(radar.head(50).to_string(index=False))
        print("\nTotal radar candidates:", len(radar))

    alerts = []
    if not radar.empty:
        print("\nChecking 5-minute breakout and volume for up to 35 candidates...")
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [
                pool.submit(check_intraday, row)
                for _, row in radar.head(35).iterrows()
            ]
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        alerts.append(result)
                except Exception as error:
                    print("Intraday check failed:", str(error)[:100])

    alert_frame = pd.DataFrame(alerts)
    alert_frame.to_csv("breakout_alerts.csv", index=False)

    print("\n========== 5-MINUTE BREAKOUT ALERTS ==========")
    if alert_frame.empty:
        print("No confirmed 5-minute breakout alerts among the checked candidates.")
    else:
        print(alert_frame.to_string(index=False))

    print("\nFinished.")
    print("Files created: early_entry_radar.csv and breakout_alerts.csv")

if __name__ == "__main__":
    main()
