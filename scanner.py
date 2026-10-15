import urllib.request
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

print("Starting Manas Arora Purple-Dot & VCP Weekly Screener...")

# 1. Dynamically Fetch NSE Midcap 150 & Smallcap 250 Universe
req = lambda u: urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
mid = pd.read_csv(urllib.request.urlopen(req('https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv')))
sml = pd.read_csv(urllib.request.urlopen(req('https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv')))
tickers = [x + '.NS' for x in list(set(mid['Symbol'].dropna().tolist() + sml['Symbol'].dropna().tolist())) if 'DUMMY' not in str(x)]

print(f"Fetched {len(tickers)} stocks from NSE. Downloading 1Y daily data...")
d = yf.download(tickers, period='1y', interval='1d', group_by='ticker', auto_adjust=True, threads=True)

candidates = []
today_str = datetime.now().strftime('%Y-%m-%d')

for tk in tickers:
    try:
        dt = d[tk].dropna()
        if len(dt) < 65:
            continue
        hist = dt.tail(65)
        cp = hist['Close']
        vols = hist['Volume']
        hi_s = hist['High']
        lo_s = hist['Low']

        cc = float(cp.iloc[-1])
        s10 = float(cp.tail(10).mean())
        s20 = float(cp.tail(20).mean())
        s20_prev = float(cp.iloc[-25:-5].mean())
        v20 = float(vols.tail(20).mean())

        # Liquidity & Price Filter (For ₹50,000 Capital)
        if cc < 30 or cc > 4500 or v20 < 200000:
            continue

        # 1. Buying Force: Up >= 35% from 3-month low
        r3m = ((cc / float(lo_s.tail(65).min())) - 1) * 100
        if r3m < 35.0:
            continue

        # 2. Purple Dot Filter: Days with >= +4.8% move on >= 5,00,000 volume in last 65 days
        rets = cp.pct_change()
        green_dots = int(((rets >= 0.048) & (vols >= 500000)).sum())
        if green_dots < 2:
            continue

        # 3. Consolidation Quality: Drawdown <= 24% & No Unrecovered Red Purple Dots (-5% on >5L vol)
        dd = (1 - (cc / float(hi_s.max()))) * 100
        if dd > 24.0 or dd < 1.5:
            continue
        red_mask = (rets.tail(20) <= -0.048) & (vols.tail(20) >= 500000)
        clean_pullback = (not red_mask.any()) or (cc >= float(hi_s.tail(20)[red_mask].max()))
        if not clean_pullback:
            continue

        # 4. Moving Average Trend & Support
        if not (cc >= s20 * 0.965 and s20 >= s20_prev):
            continue

        # 5. VCP Tightness & Volume Dry-Up on Right Side of Base
        rng_today = ((float(hi_s.iloc[-1]) - float(lo_s.iloc[-1])) / cc) * 100
        rng_2d = float(((hi_s.tail(2) - lo_s.tail(2)) / cp.tail(2)).mean() * 100)
        v_ratio = round(float(vols.iloc[-1]) / v20, 2) if v20 > 0 else 9.9
        h_lows = float(lo_s.iloc[-1]) >= float(lo_s.tail(5).min())

        if rng_2d <= 4.5 and v_ratio <= 1.05 and h_lows:
            tier = "1_ULTRA_STRICT" if (rng_2d <= 3.5 and v_ratio <= 0.90) else "2_VCP_RADAR"
            entry = round(float(hi_s.iloc[-1]) * 1.001, 2)
            sl = round(max(float(lo_s.tail(2).min()) * 0.996, entry * 0.96), 2)
            rps = max(entry - sl, 0.5)
            sl_pct = round(((entry - sl) / entry) * 100, 2)

            # Position Sizing for ₹50,000 Capital (Max ~2.8% portfolio risk or ₹16,500 per position)
            sh = int(min(1400 / rps, 16500 / entry))

            if sh > 0 and 1.0 <= sl_pct <= 4.5:
                candidates.append({
                    'Scan_Date': today_str,
                    'Tier': tier,
                    'Stock': tk.replace('.NS', ''),
                    'CMP': round(cc, 2),
                    'Purple_Dots': green_dots,
                    '3M_Force%': round(r3m, 1),
                    'Pullback%': round(dd, 1),
                    'Tight_2D%': round(rng_2d, 2),
                    'Vol_Dry_x20D': v_ratio,
                    'Day1_Buy_Above': entry,
                    'LOD_SL': sl,
                    'SL_%': sl_pct,
                    'BE_Move_At_+8%': round(entry * 1.08, 2),
                    'ScaleOut_36%': round(entry * 1.36, 2),
                    'Target_48%': round(entry * 1.48, 2),
                    'Qty_for_50k': sh,
                    'Capital_Req': round(sh * entry, 0)
                })
    except Exception:
        continue

cdf = pd.DataFrame(candidates)
if not cdf.empty:
    cdf = cdf.sort_values(by=['Tier', 'Purple_Dots', 'Tight_2D%'], ascending=[True, False, True]).head(15)
    cdf.to_csv('best_stocks.csv', index=False)
    print(f"\nSaved {len(cdf)} setups to best_stocks.csv!")
    print(cdf.to_string(index=False))
else:
    print("No stocks passed the filters today.")
    pd.DataFrame(columns=[
        'Scan_Date', 'Tier', 'Stock', 'CMP', 'Purple_Dots', '3M_Force%', 'Pullback%',
        'Tight_2D%', 'Vol_Dry_x20D', 'Day1_Buy_Above', 'LOD_SL', 'SL_%',
        'BE_Move_At_+8%', 'ScaleOut_36%', 'Target_48%', 'Qty_for_50k', 'Capital_Req'
    ]).to_csv('best_stocks.csv', index=False)
    
