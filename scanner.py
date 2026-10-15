import urllib.request
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

print("Running Manas Arora VCP Live Forward Tracker (Starting Fresh from ₹50,000)...")

# LIVE FORWARD-TEST START DATE (Ignores all historical backtest trades before this date!)
LIVE_START_DATE = "2026-10-16"
INITIAL_CAPITAL = 50000.0

# 1. Fetch NSE Midcap 150 & Smallcap 250 Universe
req = lambda u: urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
mid = pd.read_csv(urllib.request.urlopen(req('https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv')))
sml = pd.read_csv(urllib.request.urlopen(req('https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv')))
tickers = [x + '.NS' for x in list(set(mid['Symbol'].dropna().tolist() + sml['Symbol'].dropna().tolist())) if 'DUMMY' not in str(x)]

print(f"Fetched {len(tickers)} stocks. Downloading daily data for indicator calculations...")
d = yf.download(tickers, period='1y', interval='1d', group_by='ticker', auto_adjust=True, threads=True)
dates = d.index

# 2. Run Forward Simulation ONLY on or after LIVE_START_DATE
cash = INITIAL_CAPITAL
pos = []
trd = []
eq = []
cooldown = {}

for i in range(65, len(dates)):
    cd = dates[i]
    # Skip all past backtest dates prior to live start date!
    if str(cd)[:10] < LIVE_START_DATE:
        continue

    # --- A. Manage Live Open Positions ---
    for p in pos[:]:
        tk = p['tk']
        dt = d[tk]
        if cd not in dt.index or pd.isna(dt.loc[cd, 'Close']):
            continue
        hist = dt.loc[:cd].tail(25)
        row = hist.iloc[-1]
        lo = float(row['Low'])
        hi = float(row['High'])
        cl = float(row['Close'])
        s10 = float(hist['Close'].tail(10).mean())
        s20 = float(hist['Close'].tail(20).mean())
        p['days'] += 1

        # 1. Stop Loss Hit
        if lo <= p['sl']:
            ep = round(p['sl'], 2)
            pnl = (ep - p['ep']) * p['sh']
            cash += p['sh'] * ep
            cooldown[tk] = i
            trd.append({
                'Status': 'CLOSED', 'Stock': tk.replace('.NS', ''), 'Exit_Reason': p['st_type'],
                'Buy_Date': str(p['bd'])[:10], 'Sell_Date': str(cd)[:10], 'Days_Held': p['days'],
                'Entry_Px': round(p['ep'], 2), 'Exit_or_CMP': ep, 'Current_SL': p['sl'],
                'Shares': p['sh'], 'PnL_Rs': round(pnl, 2), 'PnL_%': round(((ep / p['ep']) - 1) * 100, 2)
            })
            pos.remove(p)
            continue

        cg = (hi / p['ep']) - 1
        p['max_g'] = max(p['max_g'], cg)

        # 2. Scale Out 50% at +36% Gain
        if cg >= 0.36 and not p['scaled'] and p['sh'] >= 2:
            sell_sh = max(1, p['sh'] // 2)
            ep = round(p['ep'] * 1.36, 2)
            pnl = (ep - p['ep']) * sell_sh
            cash += sell_sh * ep
            p['sh'] -= sell_sh
            p['scaled'] = True
            p['sl'] = round(max(p['sl'], p['ep'] * 1.22), 2)
            p['st_type'] = 'LOCK_+22%_SL'
            trd.append({
                'Status': 'CLOSED_PARTIAL', 'Stock': tk.replace('.NS', ''), 'Exit_Reason': 'SCALE_OUT_36%',
                'Buy_Date': str(p['bd'])[:10], 'Sell_Date': str(cd)[:10], 'Days_Held': p['days'],
                'Entry_Px': round(p['ep'], 2), 'Exit_or_CMP': ep, 'Current_SL': p['sl'],
                'Shares': sell_sh, 'PnL_Rs': round(pnl, 2), 'PnL_%': 36.0
            })

        # 3. Upper Limit Target (+48%)
        if cg >= 0.48 or hi >= p['tgt']:
            ep = round(p['ep'] * 1.48, 2)
            pnl = (ep - p['ep']) * p['sh']
            cash += p['sh'] * ep
            cooldown[tk] = i
            trd.append({
                'Status': 'CLOSED', 'Stock': tk.replace('.NS', ''), 'Exit_Reason': 'TARGET_48%',
                'Buy_Date': str(p['bd'])[:10], 'Sell_Date': str(cd)[:10], 'Days_Held': p['days'],
                'Entry_Px': round(p['ep'], 2), 'Exit_or_CMP': ep, 'Current_SL': p['sl'],
                'Shares': p['sh'], 'PnL_Rs': round(pnl, 2), 'PnL_%': 48.0
            })
            pos.remove(p)
            continue

        # 4. 10-SMA Trail (After 36% Scale-Out)
        if p['scaled'] and cl < s10 * 0.99:
            ep = round(max(cl, p['sl']), 2)
            pnl = (ep - p['ep']) * p['sh']
            cash += p['sh'] * ep
            cooldown[tk] = i
            trd.append({
                'Status': 'CLOSED', 'Stock': tk.replace('.NS', ''), 'Exit_Reason': '10SMA_TRAIL',
                'Buy_Date': str(p['bd'])[:10], 'Sell_Date': str(cd)[:10], 'Days_Held': p['days'],
                'Entry_Px': round(p['ep'], 2), 'Exit_or_CMP': ep, 'Current_SL': p['sl'],
                'Shares': p['sh'], 'PnL_Rs': round(pnl, 2), 'PnL_%': round(((ep / p['ep']) - 1) * 100, 2)
            })
            pos.remove(p)
            continue

        # 5. 20-SMA Trail (After 12+ Days)
        if p['days'] >= 12 and s20 > p['ep'] * 1.01 and cl < s20 * 0.985:
            ep = round(max(cl, p['sl']), 2)
            pnl = (ep - p['ep']) * p['sh']
            cash += p['sh'] * ep
            cooldown[tk] = i
            trd.append({
                'Status': 'CLOSED', 'Stock': tk.replace('.NS', ''), 'Exit_Reason': '20SMA_TRAIL',
                'Buy_Date': str(p['bd'])[:10], 'Sell_Date': str(cd)[:10], 'Days_Held': p['days'],
                'Entry_Px': round(p['ep'], 2), 'Exit_or_CMP': ep, 'Current_SL': p['sl'],
                'Shares': p['sh'], 'PnL_Rs': round(pnl, 2), 'PnL_%': round(((ep / p['ep']) - 1) * 100, 2)
            })
            pos.remove(p)
            continue

        # 6. Time Stop (18 Days Stagnant)
        if p['days'] >= 18 and p['max_g'] < 0.10 and ((cl / p['ep']) - 1) < 0.03:
            ep = round(cl, 2)
            pnl = (ep - p['ep']) * p['sh']
            cash += p['sh'] * ep
            cooldown[tk] = i
            trd.append({
                'Status': 'CLOSED', 'Stock': tk.replace('.NS', ''), 'Exit_Reason': 'TIME_STOP_18D',
                'Buy_Date': str(p['bd'])[:10], 'Sell_Date': str(cd)[:10], 'Days_Held': p['days'],
                'Entry_Px': round(p['ep'], 2), 'Exit_or_CMP': ep, 'Current_SL': p['sl'],
                'Shares': p['sh'], 'PnL_Rs': round(pnl, 2), 'PnL_%': round(((ep / p['ep']) - 1) * 100, 2)
            })
            pos.remove(p)
            continue

        # 7. Move SL to Breakeven at +7.5% & Lock +12% at +20%
        if p['max_g'] >= 0.075 and not p['sm']:
            p['sl'] = round(p['ep'] * 1.003, 2)
            p['sm'] = True
            p['st_type'] = 'BREAKEVEN_SL'
        if p['max_g'] >= 0.20:
            new_sl = round(max(p['sl'], p['ep'] * 1.12), 2)
            if new_sl > p['sl']:
                p['sl'] = new_sl
                p['st_type'] = 'LOCK_+12%_SL'

    # --- B. Scan for New Live Day-1 Strong Start Entries ---
    if len(pos) < 4 and cash > 8000:
        day_cands = []
        for tk in tickers:
            if any(p['tk'] == tk for p in pos):
                continue
            if tk in cooldown and (i - cooldown[tk]) < 15:
                continue
            try:
                dt = d[tk].loc[:cd].dropna()
                if len(dt) < 65 or dt.index[-1] != cd:
                    continue
                hist = dt.tail(65)
                cp = hist['Close']; vols = hist['Volume']; hi_s = hist['High']; lo_s = hist['Low']; op_s = hist['Open']
                prev_c = float(cp.iloc[-2]); cc = float(cp.iloc[-1]); v20 = float(vols.iloc[-21:-1].mean())
                if prev_c < 30 or prev_c > 4500 or v20 < 200000:
                    continue
                r3m = (prev_c / float(lo_s.iloc[-65:-10].min())) - 1
                if r3m < 0.35:
                    continue
                rets = cp.iloc[:-1].pct_change(); v_prev = vols.iloc[:-1]; h_prev = hi_s.iloc[:-1]
                green_dots = int(((rets >= 0.048) & (v_prev >= 500000)).sum())
                if green_dots < 2:
                    continue
                peak_px = float(h_prev.max()); dd = 1 - (prev_c / peak_px)
                if dd > 0.24 or dd < 0.03:
                    continue
                red_mask = (rets.tail(20) <= -0.048) & (v_prev.tail(20) >= 500000)
                if red_mask.any() and prev_c < float(h_prev.tail(20)[red_mask].max()):
                    continue
                s20 = float(cp.iloc[-21:-1].mean()); s20_prev = float(cp.iloc[-26:-6].mean())
                if not (prev_c >= s20 * 0.97 and s20 >= s20_prev):
                    continue
                rng_yest = (float(hi_s.iloc[-2]) - float(lo_s.iloc[-2])) / prev_c
                rng_2d = float(((hi_s.iloc[-3:-1] - lo_s.iloc[-3:-1]) / cp.iloc[-3:-1]).mean())
                h_lows = float(lo_s.iloc[-2]) >= float(lo_s.iloc[-6:-2].min())
                v_dry = float(vols.iloc[-2]) <= v20 * 0.85
                if not (rng_yest < 0.032 and rng_2d < 0.035 and h_lows and v_dry):
                    continue
                prev_hi = round(float(hi_s.iloc[-2]) * 1.001, 2)
                td_op = float(op_s.iloc[-1]); td_hi = float(hi_s.iloc[-1]); td_lo = float(lo_s.iloc[-1])
                strong_open = (td_op >= prev_c * 0.998) and (td_op <= prev_hi * 1.025) and ((td_op - td_lo) / td_op <= 0.015)
                strong_vol_brk = (td_hi > prev_hi) and (cc > prev_hi) and (float(vols.iloc[-1]) >= v20 * 1.35)
                if strong_open and strong_vol_brk:
                    ep_px = max(prev_hi, round(td_op, 2))
                    sl_px = round(max(min(td_lo, float(lo_s.iloc[-2])) * 0.996, ep_px * 0.962), 2)
                    if td_lo <= sl_px:
                        continue
                    risk_pct = (ep_px - sl_px) / ep_px
                    if 0.012 <= risk_pct <= 0.04:
                        score = (green_dots * 25) + (r3m * 50) + (float(vols.iloc[-1]) / v20 * 10)
                        day_cands.append((score, tk, ep_px, sl_px))
            except Exception:
                continue

        day_cands.sort(key=lambda x: x[0], reverse=True)
        for score, tk, ep, sl in day_cands:
            if len(pos) >= 4 or cash < 8000:
                break
            rps = ep - sl
            tot_eq = eq[-1]['Total_Equity'] if eq else INITIAL_CAPITAL
            sh = min(int((tot_eq * 0.025) / rps), int(min(cash * 0.95, tot_eq * 0.35) / ep))
            if sh <= 0 or sh * ep > cash:
                continue
            cash -= sh * ep
            pos.append({
                'tk': tk, 'bd': cd, 'ep': ep, 'sh': sh, 'sl': sl,
                'tgt': round(ep * 1.48, 2), 'sm': False, 'scaled': False,
                'days': 0, 'max_g': (float(d[tk].loc[cd, 'High']) / ep) - 1, 'st_type': 'INIT_SL'
            })

    # Track Daily Live Equity
    op_val = sum([p['sh'] * float(d[p['tk']].loc[cd, 'Close']) for p in pos if cd in d[p['tk']].index and not pd.isna(d[p['tk']].loc[cd, 'Close'])])
    tot_eq = round(cash + op_val, 2)
    eq.append({
        'Date': str(cd)[:10],
        'Starting_Capital': INITIAL_CAPITAL,
        'Cash_Available': round(cash, 2),
        'Open_Positions_Value': round(op_val, 2),
        'Total_Equity': tot_eq,
        'Net_Profit_Rs': round(tot_eq - INITIAL_CAPITAL, 2),
        'Net_Return_%': round(((tot_eq / INITIAL_CAPITAL) - 1) * 100, 2),
        'Open_Trades_Count': len(pos)
    })

# 3. Save Live Trade Log (trade_log.csv)
open_rows = []
for p in pos:
    curr_px = round(float(d[p['tk']].dropna()['Close'].iloc[-1]), 2)
    unrl_pnl = round((curr_px - p['ep']) * p['sh'], 2)
    unrl_pct = round(((curr_px / p['ep']) - 1) * 100, 2)
    open_rows.append({
        'Status': 'OPEN_ACTIVE', 'Stock': p['tk'].replace('.NS', ''), 'Exit_Reason': f"ACTIVE ({p['st_type']})",
        'Buy_Date': str(p['bd'])[:10], 'Sell_Date': 'HOLDING', 'Days_Held': p['days'],
        'Entry_Px': round(p['ep'], 2), 'Exit_or_CMP': curr_px, 'Current_SL': p['sl'],
        'Shares': p['sh'], 'PnL_Rs': unrl_pnl, 'PnL_%': unrl_pct
    })

all_rows = open_rows + trd[::-1]
if all_rows:
    trade_log_df = pd.DataFrame(all_rows)
else:
    trade_log_df = pd.DataFrame(columns=[
        'Status', 'Stock', 'Exit_Reason', 'Buy_Date', 'Sell_Date', 'Days_Held',
        'Entry_Px', 'Exit_or_CMP', 'Current_SL', 'Shares', 'PnL_Rs', 'PnL_%'
    ])
trade_log_df.to_csv('trade_log.csv', index=False)

# 4. Save Live Portfolio Summary (portfolio_summary.csv)
eq_df = pd.DataFrame(eq)
closed_df = pd.DataFrame(trd)
win_rate = round((len(closed_df[closed_df['PnL_Rs'] >= 0]) / len(closed_df)) * 100, 1) if not closed_df.empty else 0.0
max_dd = round(((eq_df['Total_Equity'] / eq_df['Total_Equity'].cummax()) - 1).min() * 100, 2) if not eq_df.empty else 0.0

summary_row = pd.DataFrame([{
    'Last_Updated': datetime.now().strftime('%Y-%m-%d'),
    'Live_Start_Date': LIVE_START_DATE,
    'Initial_Capital': INITIAL_CAPITAL,
    'Current_Total_Equity': eq_df['Total_Equity'].iloc[-1] if not eq_df.empty else INITIAL_CAPITAL,
    'Total_Net_PnL_Rs': eq_df['Net_Profit_Rs'].iloc[-1] if not eq_df.empty else 0.0,
    'Net_Return_%': eq_df['Net_Return_%'].iloc[-1] if not eq_df.empty else 0.0,
    'Max_Drawdown_%': max_dd,
    'Completed_Trades': len(closed_df),
    'Win_or_BE_Rate_%': win_rate,
    'Active_Open_Positions': len(pos),
    'Cash_Available': eq_df['Cash_Available'].iloc[-1] if not eq_df.empty else INITIAL_CAPITAL
}])
summary_row.to_csv('portfolio_summary.csv', index=False)

# 5. Live Scanner for Upcoming Watchlist (best_stocks.csv)
candidates = []
today_str = datetime.now().strftime('%Y-%m-%d')
for tk in tickers:
    try:
        dt = d[tk].dropna()
        if len(dt) < 65:
            continue
        hist = dt.tail(65)
        cp = hist['Close']; vols = hist['Volume']; hi_s = hist['High']; lo_s = hist['Low']
        cc = float(cp.iloc[-1]); s20 = float(cp.tail(20).mean()); s20_prev = float(cp.iloc[-25:-5].mean()); v20 = float(vols.tail(20).mean())
        if cc < 30 or cc > 4500 or v20 < 200000:
            continue
        r3m = ((cc / float(lo_s.tail(65).min())) - 1) * 100
        if r3m < 35.0:
            continue
        rets = cp.pct_change()
        green_dots = int(((rets >= 0.048) & (vols >= 500000)).sum())
        if green_dots < 2:
            continue
        dd = (1 - (cc / float(hi_s.max()))) * 100
        if dd > 24.0 or dd < 1.5:
            continue
        red_mask = (rets.tail(20) <= -0.048) & (vols.tail(20) >= 500000)
        if not ((not red_mask.any()) or (cc >= float(hi_s.tail(20)[red_mask].max()))):
            continue
        if not (cc >= s20 * 0.965 and s20 >= s20_prev):
            continue
        rng_2d = float(((hi_s.tail(2) - lo_s.tail(2)) / cp.tail(2)).mean() * 100)
        v_ratio = round(float(vols.iloc[-1]) / v20, 2) if v20 > 0 else 9.9
        h_lows = float(lo_s.iloc[-1]) >= float(lo_s.tail(5).min())
        if rng_2d <= 4.5 and v_ratio <= 1.05 and h_lows:
            tier = "1_ULTRA_STRICT" if (rng_2d <= 3.5 and v_ratio <= 0.90) else "2_VCP_RADAR"
            entry = round(float(hi_s.iloc[-1]) * 1.001, 2)
            sl = round(max(float(lo_s.tail(2).min()) * 0.996, entry * 0.96), 2)
            rps = max(entry - sl, 0.5)
            sl_pct = round(((entry - sl) / entry) * 100, 2)
            sh = int(min(1400 / rps, 16500 / entry))
            if sh > 0 and 1.0 <= sl_pct <= 4.5:
                candidates.append({
                    'Scan_Date': today_str, 'Tier': tier, 'Stock': tk.replace('.NS', ''),
                    'CMP': round(cc, 2), 'Purple_Dots': green_dots, '3M_Force%': round(r3m, 1),
                    'Pullback%': round(dd, 1), 'Tight_2D%': round(rng_2d, 2), 'Vol_Dry_x20D': v_ratio,
                    'Day1_Buy_Above': entry, 'LOD_SL': sl, 'SL_%': sl_pct,
                    'BE_Move_At_+8%': round(entry * 1.08, 2), 'ScaleOut_36%': round(entry * 1.36, 2),
                    'Target_48%': round(entry * 1.48, 2), 'Qty_for_50k': sh, 'Capital_Req': round(sh * entry, 0)
                })
    except Exception:
        continue

cdf = pd.DataFrame(candidates)
if not cdf.empty:
    cdf = cdf.sort_values(by=['Tier', 'Purple_Dots', 'Tight_2D%'], ascending=[True, False, True]).head(15)
    cdf.to_csv('best_stocks.csv', index=False)
else:
    pd.DataFrame(columns=[
        'Scan_Date', 'Tier', 'Stock', 'CMP', 'Purple_Dots', '3M_Force%', 'Pullback%',
        'Tight_2D%', 'Vol_Dry_x20D', 'Day1_Buy_Above', 'LOD_SL', 'SL_%',
        'BE_Move_At_+8%', 'ScaleOut_36%', 'Target_48%', 'Qty_for_50k', 'Capital_Req'
    ]).to_csv('best_stocks.csv', index=False)

print("\n=== FRESH LIVE PORTFOLIO SUMMARY ===")
print(summary_row.to_string(index=False))
        
