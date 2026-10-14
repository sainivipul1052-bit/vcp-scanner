import urllib.request
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

print("Starting VCP Weekly Stock Screener...")

# 1. Fetch NSE Midcap & Smallcap Universe
req = lambda u: urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
mid = pd.read_csv(urllib.request.urlopen(req('https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv')))
sml = pd.read_csv(urllib.request.urlopen(req('https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv')))
t = [x + '.NS' for x in list(set(mid['Symbol'].dropna().tolist() + sml['Symbol'].dropna().tolist())) if 'DUMMY' not in str(x)]

print(f"Fetched {len(t)} stocks from NSE. Downloading historical data...")
d = yf.download(t, period='1y', interval='1d', group_by='ticker', auto_adjust=True, threads=True)

cand = []
for tk in t:
    try:
        dt = d[tk].dropna()
        if len(dt) < 65: continue
        hist = dt.tail(65)
        cp = hist['Close']
        vols = hist['Volume']
        hi_s = hist['High']
        lo_s = hist['Low']
        
        cc = cp.iloc[-1]
        s20 = cp.tail(20).mean()
        s50 = cp.tail(50).mean()
        v20 = vols.tail(20).mean()
        
        r3m = ((cc / cp.iloc[-60]) - 1) * 100
        rng = ((hi_s.tail(3) - lo_s.tail(3)) / cp.tail(3)).mean() * 100
        v_ratio = round(vols.tail(3).mean() / v20, 2) if v20 > 0 else 9.9
        
        if 30 < cc < 4500 and v20 > 120000 and 30 <= r3m <= 95 and cc >= s20 * 0.98 and s20 >= s50 and rng < 4.0:
            entry = round(hi_s.tail(2).max() * 1.002, 2)
            sl = round(max(lo_s.tail(3).min() * 0.994, entry * 0.955), 2)
            rps = max(entry - sl, 0.5)
            sl_pct = round(((entry - sl) / entry) * 100, 2)
            sh = int(min(1400 / rps, 16500 / entry))
            
            if sh > 0 and 1.5 <= sl_pct <= 4.8:
                cand.append({
                    'Date': datetime.now().strftime('%Y-%m-%d'),
                    'Stock': tk,
                    'CMP': round(cc, 2),
                    '3M_Ret%': round(r3m, 1),
                    '3D_Tight%': round(rng, 2),
                    'Vol_Dry': v_ratio,
                    'Early_Entry': entry,
                    'SL': sl,
                    'SL_%': sl_pct,
                    'Target_48%': round(entry * 1.48, 2),
                    'Qty_50k': sh
                })
    except Exception as e:
        continue

# 2. Output and Save to CSV
cdf = pd.DataFrame(cand).sort_values(by=['3D_Tight%', 'Vol_Dry'], ascending=[True, True]) if cand else pd.DataFrame()

if not cdf.empty:
    print(f"\nFound {len(cdf)} top VCP setups. Saving to best_stocks.csv...")
    cdf.to_csv('best_stocks.csv', index=False)
    print(cdf.head(10).to_string(index=False))
else:
    print("No setups found matching strict criteria this week.")
    pd.DataFrame(columns=['Date', 'Stock', 'CMP', '3M_Ret%', '3D_Tight%', 'Vol_Dry', 'Early_Entry', 'SL', 'SL_%', 'Target_48%', 'Qty_50k']).to_csv('best_stocks.csv', index=False)
  
