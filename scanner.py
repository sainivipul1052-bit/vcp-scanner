import urllib.request
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

print("Running Manas Arora VCP Daily Tracker (True Horizontal Base at 10/20 SMA + Zero Pre-Rally)...")

# LIVE FORWARD-TEST START DATE (Starts fresh from ₹50,000 on Oct 16, 2026)
LIVE_START_DATE = "2026-10-16"
INITIAL_CAPITAL = 50000.0

# 1. Fetch NSE Midcap 150 & Smallcap 250 Universe
req = lambda u: urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
mid = pd.read_csv(urllib.request.urlopen(req('https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv')))
sml = pd.read_csv(urllib.request.urlopen(req('https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv')))
tickers = [x + '.NS' for x in list(set(mid['Symbol'].dropna().tolist() + sml['Symbol'].dropna().tolist())) if 'DUMMY' not in str(x)]

print(f"Fetched {len(tickers)} stocks. Downloading 1Y daily data...")
d = yf.download(tickers, period='1y', interval='1d', group_by='ticker', auto_adjust=True, threads=True)
dates = d.index

# 2. Daily Forward Simulation & Automatic Profit Reinvestment
cash = INITIAL_CAPITAL
pos = []
trd = []
eq = []
cooldown = {}

for i in range(65, len(dates)):
    cd = dates[i]
    if str(cd)[:10] < LIVE_START_DATE:
        continue

    # --- A. Manage Live Open Positions (Exact Video 5 Trailing & Exit Rules) ---
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

        # 1. Hard Stop Loss Hit
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

        # 2. Scale Out 50% into strength at +38% from Move Start Base
        if hi >= p['scale_px'] and not p['scaled'] and p['sh'] >= 2:
            sell_sh = max(1, p['sh'] // 2)
            ep = p['scale_px']
            pnl = (ep - p['ep']) * sell_sh
            cash += sell_sh * ep
            p['sh'] -= sell_sh
            p['scaled'] = True
            p['sl'] = round(max(p['sl'], p['ep'] * 1.18), 2)
            p['st_type'] = 'LOCK_+18%_SL'
            trd.append({
                'Status': 'CLOSED_PARTIAL', 'Stock': tk.replace('.NS', ''), 'Exit_Reason': 'SCALE_OUT_38%',
                'Buy_Date': str(p['bd'])[:10], 'Sell_Date': str(cd)[:10], 'Days_Held': p['days'],
                'Entry_Px': round(p['ep'], 2), 'Exit_or_CMP': ep, 'Current_SL': p['sl'],
                'Shares': sell_sh, 'PnL_Rs': round(pnl, 2), 'PnL_%': round(((ep / p['ep']) - 1) * 100, 2)
            })

        # 3. Upper Limit Target (+48% from Move Start Base)
        if hi >= p['tgt']:
            ep = p['tgt']
            pnl = (ep - p['ep']) * p['sh']
            cash += p['sh'] * ep
            cooldown[tk] = i
            trd.append({
                'Status': 'CLOSED', 'Stock': tk.replace('.NS', ''), 'Exit_Reason': 'TARGET_48%',
                'Buy_Date': str(p['bd'])[:10], 'Sell_Date': str(cd)[:10], 'Days_Held': p['days'],
                'Entry_Px': round(p['ep'], 2), 'Exit_or_CMP': ep, 'Current_SL': p['sl'],
                'Shares': p['sh'], 'PnL_Rs': round(pnl, 2), 'PnL_%': round(((ep / p['ep']) - 1) * 100, 2)
            })
            pos.remove(p)
            continue

        # 4. 10-SMA Trail once stretched (Video 5 Rule: Switch from 20MA to 10MA near 40%)
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

        # 5. 20-SMA Closing Trail once 20-SMA crosses above Breakeven (Video 5 Rule)
        if p['days'] >= 10 and s20 > p['ep'] * 1.01 and cl < s20 * 0.985:
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

        # 6. Move SL to Breakeven at +7.5% (Video 5 Rule: 6-8% in favor -> Cost SL)
        if p['max_g'] >= 0.075 and not p['sm']:
            p['sl'] = round(p['ep'] * 1.003, 2)
            p['sm'] = True
            p['st_type'] = 'BREAKEVEN_SL'
        if p['max_g'] >= 0.22:
            new_sl = round(max(p['sl'], p['ep'] * 1.12, s20 * 0.985), 2)
            if new_sl > p['sl']:
                p['sl'] = new_sl
                p['st_type'] = '20SMA_HARD_SL'

    # --- B. Daily Scan for True Day-1 Entries (From Horizontal 4D Base on 10/20 SMA) ---
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

                # 1. Prior Uptrend Force (>=35% in last 65 days) & Purple Dots
                r3m = (float(hi_s.iloc[:-1].max()) / float(lo_s.iloc[-65:-10].min())) - 1
                if r3m < 0.35:
                    continue
                rets = cp.iloc[:-1].pct_change(); v_prev = vols.iloc[:-1]; h_prev = hi_s.iloc[:-1]
                green_dots = int(((rets >= 0.048) & (v_prev >= 500000)).sum())
                if green_dots < 2:
                    continue

                # 2. Must be in a Consolidation Base (3% to 24% below 35-day peak), NOT at a brand new high after a 5-day rally!
                peak_px = float(h_prev.tail(35).max())
                dd = 1 - (prev_c / peak_px)
                if dd > 0.24 or dd < 0.03:
                    continue

                # 3. Clean Consolidation (Any big red day must be old/reclaimed - Video 5 NALCO rule)
                red_mask = (rets.tail(15) <= -0.048) & (v_prev.tail(15) >= 500000)
                if red_mask.any() and prev_c < float(h_prev.tail(15)[red_mask].max()):
                    continue

                # 4. HUGGING 10 SMA & 20 SMA (Blocks PVRINOX +7.2% & CYIENT +7.1% above 20 SMA!)
                s10 = float(cp.iloc[-11:-1].mean())
                s20 = float(cp.iloc[-21:-1].mean())
                s20_prev = float(cp.iloc[-26:-6].mean())
                dist_10 = abs(prev_c - s10) / s10
                dist_20 = (prev_c - s20) / s20
                if not (dist_10 <= 0.030 and -0.025 <= dist_20 <= 0.040 and s20 >= s20_prev):
                    continue

                # 5. HORIZONTAL 4-DAY BOX & ZERO 5-DAY PRE-RALLY (Blocks CYIENT +12.7% 5-bar rally!)
                five_day_net = ((prev_c / float(cp.iloc[-7])) - 1) * 100
                box_4d = ((float(hi_s.iloc[-5:-1].max()) - float(lo_s.iloc[-5:-1].min())) / prev_c) * 100
                rng_yest = ((float(hi_s.iloc[-2]) - float(lo_s.iloc[-2])) / prev_c) * 100
                h_lows = float(lo_s.iloc[-2]) >= float(lo_s.iloc[-7:-2].min())
                v_dry = float(vols.iloc[-3:-1].mean()) <= v20 * 0.85
                if not (-4.0 <= five_day_net <= 3.8 and box_4d <= 6.0 and rng_yest <= 3.2 and h_lows and v_dry):
                    continue

                # 6. Day-1 Strong Start Trigger (Video 5 Rule: Open > Prev Close, Cross Prev Day High on High Volume)
                prev_hi = round(float(hi_s.iloc[-2]) * 1.001, 2)
                td_op = float(op_s.iloc[-1]); td_hi = float(hi_s.iloc[-1]); td_lo = float(lo_s.iloc[-1])
                strong_open = (td_op >= prev_c * 0.998) and (td_op <= prev_hi * 1.025)
                strong_vol_brk = (td_hi > prev_hi) and (cc > prev_hi) and (float(vols.iloc[-1]) >= v20 * 1.30)
                if strong_open and strong_vol_brk:
                    ep_px = max(prev_hi, round(td_op, 2))
                    # Stop Loss = Low of the Day (LOD) or tight yesterday low (Video 5 Rule: 106 entry, 103 LOD SL)
                    sl_px = round(max(min(td_lo, float(lo_s.iloc[-2])) * 0.996, ep_px * 0.962), 2)
                    if td_lo <= sl_px:
                        continue
                    risk_pct = (ep_px - sl_px) / ep_px
                    if 0.012 <= risk_pct <= 0.042:
                        move_start_px = round(float(lo_s.iloc[-5:-1].min()), 2)
                        score = (green_dots * 25) + (r3m * 50) - (box_4d * 10)
                        day_cands.append((score, tk, ep_px, sl_px, move_start_px))
            except Exception:
                continue

        day_cands.sort(key=lambda x: x[0], reverse=True)
        for score, tk, ep, sl, move_start_px in day_cands:
            if len(pos) >= 4 or cash < 8000:
                break
            rps = ep - sl
            op_val_now = sum([p['sh'] * float(d[p['tk']].loc[cd, 'Close']) for p in pos if cd in d[p['tk']].index and not pd.isna(d[p['tk']].loc[cd, 'Close'])])
            tot_eq = cash + op_val_now
            sh = min(int((tot_eq * 0.025) / rps), int(min(cash * 0.95, tot_eq * 0.35) / ep))
            if sh <= 0 or sh * ep > cash:
                continue
            cash -= sh * ep
            pos.append({
                'tk': tk, 'bd': cd, 'ep': ep, 'sh': sh, 'sl': sl,
                'scale_px': round(move_start_px * 1.38, 2), 'tgt': round(move_start_px * 1.48, 2),
                'sm': False, 'scaled': False, 'days': 0,
                'max_g': (float(d[tk].loc[cd, 'High']) / ep) - 1, 'st_type': 'INIT_SL'
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
live_eq = eq_df['Total_Equity'].iloc[-1] if not eq_df.empty else INITIAL_CAPITAL

summary_row = pd.DataFrame([{
    'Last_Updated': datetime.now().strftime('%Y-%m-%d'),
    'Live_Start_Date': LIVE_START_DATE,
    'Initial_Capital': INITIAL_CAPITAL,
    'Current_Total_Equity': live_eq,
    'Total_Net_PnL_Rs': eq_df['Net_Profit_Rs'].iloc[-1] if not eq_df.empty else 0.0,
    'Net_Return_%': eq_df['Net_Return_%'].iloc[-1] if not eq_df.empty else 0.0,
    'Max_Drawdown_%': max_dd,
    'Completed_Trades': len(closed_df),
    'Win_or_BE_Rate_%': win_rate,
    'Active_Open_Positions': len(pos),
    'Cash_Available': round(cash, 2)
}])
summary_row.to_csv('portfolio_summary.csv', index=False)

# 5. Live Scanner for Upcoming Watchlist (best_stocks.csv)
# Finds ONLY Horizontal Coiled Bases resting right on 10/20 SMA (like IREDA & NALCO in Video 5)
candidates = []
today_str = datetime.now().strftime('%Y-%m-%d')
risk_per_trade = live_eq * 0.028
max_cap_per_trade = min(cash * 0.95, live_eq * 0.35) if cash > 8000 else live_eq * 0.35

for tk in tickers:
    try:
        dt = d[tk].dropna()
        if len(dt) < 65:
            continue
        hist = dt.tail(65)
        cp = hist['Close']; vols = hist['Volume']; hi_s = hist['High']; lo_s = hist['Low']
        cc = float(cp.iloc[-1]); s10 = float(cp.tail(10).mean()); s20 = float(cp.tail(20).mean())
        s20_prev = float(cp.iloc[-25:-5].mean()); v20 = float(vols.tail(20).mean())
        if cc < 30 or cc > 4500 or v20 < 200000:
            continue

        # 1. Prior Rally Force (>=35% in last 65 days) & Purple Dots
        r3m = ((float(hi_s.max()) / float(lo_s.tail(65).min())) - 1) * 100
        if r3m < 35.0:
            continue
        rets = cp.pct_change()
        green_dots = int(((rets >= 0.048) & (vols >= 500000)).sum())
        if green_dots < 2:
            continue

        # 2. Must be in a Consolidation Pullback (3% to 24% below peak), NOT already breaking out at highs!
        dd = (1 - (cc / float(hi_s.tail(35).max()))) * 100
        if dd > 24.0 or dd < 3.0:
            continue

        # 3. Clean Pullback (No unrecovered big red days in last 15 sessions)
        red_mask = (rets.tail(15) <= -0.048) & (vols.tail(15) >= 500000)
        if not ((not red_mask.any()) or (cc >= float(hi_s.tail(15)[red_mask].max()))):
            continue

        # 4. HUGGING 10 SMA & 20 SMA (Blocks PVRINOX at +7.2% & CYIENT at +7.1% above 20 SMA!)
        dist_10sma = round(((cc / s10) - 1) * 100, 1)
        dist_20sma = round(((cc / s20) - 1) * 100, 1)
        if not (-2.5 <= dist_10sma <= 3.0 and -2.5 <= dist_20sma <= 4.0 and s20 >= s20_prev):
            continue

        # 5. HORIZONTAL 4-DAY BOX & ZERO 5-DAY PRE-RALLY (Blocks CYIENT's +12.69% 5-bar rally!)
        five_day_net = round(((cc / float(cp.iloc[-6])) - 1) * 100, 1)
        box_4d = round(((float(hi_s.tail(4).max()) - float(lo_s.tail(4).min())) / cc) * 100, 2)
        rng_today = round(((float(hi_s.iloc[-1]) - float(lo_s.iloc[-1])) / cc) * 100, 2)
        v_ratio = round(float(vols.tail(2).mean()) / v20, 2) if v20 > 0 else 9.9
        h_lows = float(lo_s.iloc[-1]) >= float(lo_s.tail(6).min())

        if -4.0 <= five_day_net <= 3.8 and box_4d <= 6.0 and rng_today <= 3.2 and v_ratio <= 0.90 and h_lows:
            tier = "1_IREDA_COIL" if (box_4d <= 4.5 and abs(dist_10sma) <= 2.0 and v_ratio <= 0.75) else "2_BASE_COIL"
            entry = round(float(hi_s.iloc[-1]) * 1.001, 2)
            sl = round(max(float(lo_s.tail(2).min()) * 0.996, entry * 0.965), 2)
            rps = max(entry - sl, 0.5)
            sl_pct = round(((entry - sl) / entry) * 100, 2)
            # Move Start Low = Bottom of the tight 4-day box (exact point where the new move starts!)
            move_start_low = round(float(lo_s.tail(4).min()), 2)
            sh = int(min(risk_per_trade / rps, max_cap_per_trade / entry))
            if sh > 0 and 1.0 <= sl_pct <= 4.0:
                candidates.append({
                    'Scan_Date': today_str, 'Tier': tier, 'Stock': tk.replace('.NS', ''),
                    'CMP': round(cc, 2), 'Purple_Dots': green_dots, 'Pullback_From_High%': round(dd, 1),
                    'Dist_10SMA%': dist_10sma, 'Dist_20SMA%': dist_20sma,
                    '5D_Net_Chg%': five_day_net, '4D_Box_Width%': box_4d,
                    'Today_Rng%': rng_today, 'Vol_Dry_x20D': v_ratio,
                    'Day1_Buy_Above': entry, 'LOD_SL': sl, 'SL_%': sl_pct,
                    'BE_Move_At_+8%': round(entry * 1.08, 2),
                    'ScaleOut_38%': round(move_start_low * 1.38, 2),
                    'Target_48%': round(move_start_low * 1.48, 2),
                    'Qty_for_50k': sh, 'Capital_Req': round(sh * entry, 0)
                })
    except Exception:
        continue

cdf = pd.DataFrame(candidates)
if not cdf.empty:
    cdf = cdf.sort_values(by=['Tier', '4D_Box_Width%', 'Today_Rng%'], ascending=[True, True, True]).head(15)
    cdf.to_csv('best_stocks.csv', index=False)
else:
    pd.DataFrame(columns=[
        'Scan_Date', 'Tier', 'Stock', 'CMP', 'Purple_Dots', 'Pullback_From_High%',
        'Dist_10SMA%', 'Dist_20SMA%', '5D_Net_Chg%', '4D_Box_Width%',
        'Today_Rng%', 'Vol_Dry_x20D', 'Day1_Buy_Above', 'LOD_SL', 'SL_%',
        'BE_Move_At_+8%', 'ScaleOut_38%', 'Target_48%', 'Qty_for_50k', 'Capital_Req'
    ]).to_csv('best_stocks.csv', index=False)

print("\n=== FRESH LIVE PORTFOLIO SUMMARY ===")
print(summary_row.to_string(index=False))
print("\n=== TRUE HORIZONTAL BASE WATCHLIST (ZERO 5-DAY PRE-RALLY) ===")
if not cdf.empty:
    print(cdf.to_string(index=False))
else:
    print("No stocks met the strict horizontal 10/20 SMA coil today.")
