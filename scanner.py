import urllib.request
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime

print("Running Manas Arora VCP System (Fixed 20-SMA Base Math + All 7 Video Rules)...")

# Starts fresh from ₹50,000 on Oct 16, 2026 (ignores historical backtest trades)
LIVE_START_DATE = "2026-10-16"
INITIAL_CAPITAL = 50000.0

# 1. Fetch NSE Midcap 150, Smallcap 250 & Microcap 250 Universe (~650 NSE Stocks)
req = lambda u: urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
symbols = []
for url in [
    'https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv',
    'https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv',
    'https://nsearchives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv'
]:
    try:
        df_idx = pd.read_csv(urllib.request.urlopen(req(url)))
        symbols.extend(df_idx['Symbol'].dropna().tolist())
    except Exception:
        pass

tickers = [x + '.NS' for x in sorted(list(set(symbols))) if 'DUMMY' not in str(x)]
print(f"Fetched {len(tickers)} NSE stocks. Downloading 1Y daily data...")
d = yf.download(tickers, period='1y', interval='1d', group_by='ticker', auto_adjust=True, threads=True)
dates = d.index

# Compute Broader Market Regime (Rule 6: Is Mid/Smallcap Index above its 20-day SMA?)
close_matrix = pd.DataFrame({tk: d[tk]['Close'] for tk in tickers if tk in d and 'Close' in d[tk]})
mkt_index = close_matrix.pct_change().mean(axis=1).add(1).cumprod()
mkt_sma20 = mkt_index.rolling(20).mean()

# 2. Daily Forward Portfolio Engine (With Rule 4, 5, 6 & 7 + Profit Reinvestment)
cash = INITIAL_CAPITAL
realized_profit = 0.0
pos = []
trd = []
eq = []
cooldown = {}
loss_streak = 0
pause_until_idx = -1

for i in range(85, len(dates)):
    cd = dates[i]
    if str(cd)[:10] < LIVE_START_DATE:
        continue

    mkt_weak = bool(mkt_index.iloc[i] < mkt_sma20.iloc[i]) if not pd.isna(mkt_sma20.iloc[i]) else False

    # --- A. Manage Open Positions (Rule 4, 5 & 6) ---
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

        # 1. Check Stop Loss Hit
        if lo <= p['sl']:
            ep = round(p['sl'], 2)
            pnl = (ep - p['ep']) * p['sh']
            cash += p['sh'] * ep
            realized_profit += pnl
            cooldown[tk] = i
            if pnl < 0 and not p['scaled_28']:
                loss_streak += 1
                if loss_streak >= 6:
                    pause_until_idx = i + 8
            else:
                loss_streak = 0
            trd.append({
                'Status': 'CLOSED', 'Stock': tk.replace('.NS', ''), 'Exit_Reason': p['st_type'],
                'Buy_Date': str(p['bd'])[:10], 'Sell_Date': str(cd)[:10], 'Days_Held': p['days'],
                'Swing_Start': p['orig'], 'Entry_Px': round(p['ep'], 2), 'Exit_or_CMP': ep,
                'Current_SL': p['sl'], 'Shares': p['sh'], 'PnL_Rs': round(pnl, 2),
                'PnL_%': round(((ep / p['ep']) - 1) * 100, 2)
            })
            pos.remove(p)
            continue

        cg = (hi / p['ep']) - 1
        p['max_g'] = max(p['max_g'], cg)
        move_from_start = (hi / p['orig']) - 1

        # Rule 4.1: At +7.5% profit, move stop to Breakeven
        if p['max_g'] >= 0.075 and not p['sm']:
            p['sl'] = round(p['ep'] * 1.002, 2)
            p['sm'] = True
            p['st_type'] = 'BREAKEVEN_SL'

        # Rule 5.1: Gradual Scale-Out Tranche 1 at +28% from Swing Start (Typical 25-30% Swing Range)
        if hi >= p['t1_28'] and not p['scaled_28'] and p['sh'] >= 3:
            sell_sh = max(1, p['sh'] // 3)
            ep = p['t1_28']
            pnl = (ep - p['ep']) * sell_sh
            cash += sell_sh * ep
            realized_profit += pnl
            p['sh'] -= sell_sh
            p['scaled_28'] = True
            loss_streak = 0
            p['sl'] = round(max(p['sl'], p['ep'] * 1.10), 2)
            p['st_type'] = 'LOCK_+10%_SL'
            trd.append({
                'Status': 'PARTIAL_1', 'Stock': tk.replace('.NS', ''), 'Exit_Reason': 'SWING_28%_SCALE',
                'Buy_Date': str(p['bd'])[:10], 'Sell_Date': str(cd)[:10], 'Days_Held': p['days'],
                'Swing_Start': p['orig'], 'Entry_Px': round(p['ep'], 2), 'Exit_or_CMP': ep,
                'Current_SL': p['sl'], 'Shares': sell_sh, 'PnL_Rs': round(pnl, 2),
                'PnL_%': round(((ep / p['ep']) - 1) * 100, 2)
            })

        # Rule 5.2: Gradual Scale-Out Tranche 2 at +40% from Swing Start (Entering 40-50% Extended Zone)
        if hi >= p['t2_40'] and not p['scaled_40'] and p['sh'] >= 2:
            sell_sh = max(1, p['sh'] // 2)
            ep = p['t2_40']
            pnl = (ep - p['ep']) * sell_sh
            cash += sell_sh * ep
            realized_profit += pnl
            p['sh'] -= sell_sh
            p['scaled_40'] = True
            p['sl'] = round(max(p['sl'], p['ep'] * 1.22, s10 * 0.985), 2)
            p['st_type'] = '10SMA_EXT_SL'
            trd.append({
                'Status': 'PARTIAL_2', 'Stock': tk.replace('.NS', ''), 'Exit_Reason': 'EXTENDED_40%_SCALE',
                'Buy_Date': str(p['bd'])[:10], 'Sell_Date': str(cd)[:10], 'Days_Held': p['days'],
                'Swing_Start': p['orig'], 'Entry_Px': round(p['ep'], 2), 'Exit_or_CMP': ep,
                'Current_SL': p['sl'], 'Shares': sell_sh, 'PnL_Rs': round(pnl, 2),
                'PnL_%': round(((ep / p['ep']) - 1) * 100, 2)
            })

        # Rule 5.3: Final Exit at +48% Super-Extended Limit from Swing Start
        if hi >= p['t3_48']:
            ep = p['t3_48']
            pnl = (ep - p['ep']) * p['sh']
            cash += p['sh'] * ep
            realized_profit += pnl
            cooldown[tk] = i
            loss_streak = 0
            trd.append({
                'Status': 'CLOSED', 'Stock': tk.replace('.NS', ''), 'Exit_Reason': 'SUPER_EXT_48%',
                'Buy_Date': str(p['bd'])[:10], 'Sell_Date': str(cd)[:10], 'Days_Held': p['days'],
                'Swing_Start': p['orig'], 'Entry_Px': round(p['ep'], 2), 'Exit_or_CMP': ep,
                'Current_SL': p['sl'], 'Shares': p['sh'], 'PnL_Rs': round(pnl, 2),
                'PnL_%': round(((ep / p['ep']) - 1) * 100, 2)
            })
            pos.remove(p)
            continue

        # Rule 4.3 & Rule 6: Tighten trail to 10-SMA if extended >=35% OR if Market is Weak (<20 SMA)
        if p['days'] >= 4 and ((move_from_start >= 0.35 or p['scaled_40']) or (mkt_weak and cl > p['ep'] * 1.05)):
            if cl < s10 * 0.99 and s10 > p['ep']:
                ep = round(max(cl, p['sl']), 2)
                pnl = (ep - p['ep']) * p['sh']
                cash += p['sh'] * ep
                realized_profit += pnl
                cooldown[tk] = i
                if pnl > 0:
                    loss_streak = 0
                reason = 'WEAK_MKT_10SMA_EXIT' if mkt_weak else '10SMA_TRAIL_EXIT'
                trd.append({
                    'Status': 'CLOSED', 'Stock': tk.replace('.NS', ''), 'Exit_Reason': reason,
                    'Buy_Date': str(p['bd'])[:10], 'Sell_Date': str(cd)[:10], 'Days_Held': p['days'],
                    'Swing_Start': p['orig'], 'Entry_Px': round(p['ep'], 2), 'Exit_or_CMP': ep,
                    'Current_SL': p['sl'], 'Shares': p['sh'], 'PnL_Rs': round(pnl, 2),
                    'PnL_%': round(((ep / p['ep']) - 1) * 100, 2)
                })
                pos.remove(p)
                continue

        # Rule 4.2: Trail 20-day SMA on a closing basis once 20-SMA catches up above entry price
        if p['days'] >= 5 and s20 > p['ep'] * 1.005:
            hard_20sl = round(s20 * 0.975, 2)
            if hard_20sl > p['sl']:
                p['sl'] = hard_20sl
                p['st_type'] = '20SMA_HARD_SL'
            if cl < s20 * 0.985:
                ep = round(max(cl, p['sl']), 2)
                pnl = (ep - p['ep']) * p['sh']
                cash += p['sh'] * ep
                realized_profit += pnl
                cooldown[tk] = i
                if pnl > 0:
                    loss_streak = 0
                trd.append({
                    'Status': 'CLOSED', 'Stock': tk.replace('.NS', ''), 'Exit_Reason': '20SMA_CLOSE_TRAIL',
                    'Buy_Date': str(p['bd'])[:10], 'Sell_Date': str(cd)[:10], 'Days_Held': p['days'],
                    'Swing_Start': p['orig'], 'Entry_Px': round(p['ep'], 2), 'Exit_or_CMP': ep,
                    'Current_SL': p['sl'], 'Shares': p['sh'], 'PnL_Rs': round(pnl, 2),
                    'PnL_%': round(((ep / p['ep']) - 1) * 100, 2)
                })
                pos.remove(p)
                continue

    # --- B. Daily Entry Scan (Rule 1, 2, 3 & 7 - Fixed 20-SMA Base Math!) ---
    if len(pos) < 4 and cash > 6000 and i >= pause_until_idx:
        day_cands = []
        for tk in tickers:
            if any(p['tk'] == tk for p in pos):
                continue
            if tk in cooldown and (i - cooldown[tk]) < 15:
                continue
            try:
                dt = d[tk].loc[:cd].dropna()
                if len(dt) < 85 or dt.index[-1] != cd:
                    continue
                hist = dt.tail(85)
                cp = hist['Close']; vols = hist['Volume']; hi_s = hist['High']; lo_s = hist['Low']; op_s = hist['Open']
                prev_c = float(cp.iloc[-2]); cc = float(cp.iloc[-1]); v20 = float(vols.iloc[-21:-1].mean())
                if prev_c < 30 or prev_c > 4500 or v20 < 200000:
                    continue

                # Rule 1a: Strong Preceding Uptrend (>=30% rally in last 3-4 months + >=2 Purple Dots)
                r3m = (float(hi_s.iloc[-45:-1].max()) / float(lo_s.iloc[:-15].min())) - 1
                if r3m < 0.30:
                    continue
                rets = cp.iloc[:-1].pct_change(); v_prev = vols.iloc[:-1]; h_prev = hi_s.iloc[:-1]
                green_dots = int(((rets >= 0.048) & ((v_prev >= 500000) | (v_prev >= v20 * 2.0))).sum())
                if green_dots < 2:
                    continue

                # Rule 1b: Controlled Correction (<=25% from peak) & Clean Pullback
                peak_px = float(h_prev.tail(45).max())
                dd = 1 - (prev_c / peak_px)
                if dd > 0.25 or dd < 0.02:
                    continue
                red_mask = (rets.tail(15) <= -0.048) & (v_prev.tail(15) >= max(500000, v20 * 1.8))
                if red_mask.any() and prev_c < float(h_prev.tail(15)[red_mask].max()):
                    continue

                # Rule 1c & Rule 2 (FIXED): Reclaiming/Hugging 20-SMA in an Uptrend (20-SMA >= 50-SMA & higher than 20 days ago)
                # Blocks stocks already extended >5% above 20-SMA (like CYIENT & PVRINOX) without the 5-day lag paradox!
                s10 = float(cp.iloc[-11:-1].mean())
                s20 = float(cp.iloc[-21:-1].mean())
                s20_20d_ago = float(cp.iloc[-41:-21].mean())
                s50 = float(cp.iloc[-51:-1].mean())
                dist_20 = (prev_c - s20) / s20
                if not (-0.025 <= dist_20 <= 0.050 and s20 >= s50 * 0.99 and s20 > s20_20d_ago):
                    continue

                # Rule 1d (FIXED): Bar-by-Bar Contraction compared to 25-day base swings + Zero 5-Day Pre-Rally
                five_day_chg = ((prev_c / float(cp.iloc[-7])) - 1) * 100
                bar_ranges_25 = ((hi_s.iloc[-26:-1] - lo_s.iloc[-26:-1]) / cp.iloc[-26:-1]) * 100
                max_25d_bar = float(bar_ranges_25.max())
                rng_yest = float(bar_ranges_25.iloc[-1])
                rng_2d = float(bar_ranges_25.tail(2).mean())
                inside_bar = (float(hi_s.iloc[-2]) <= float(hi_s.iloc[-3])) and (float(lo_s.iloc[-2]) >= float(lo_s.iloc[-3]))
                bar_contracted = (rng_yest <= 3.2 and rng_2d <= 3.5) and (rng_yest <= max_25d_bar * 0.50 or inside_bar)
                h_lows = float(lo_s.iloc[-2]) >= float(lo_s.iloc[-8:-2].min())
                v_dry = float(vols.iloc[-2]) <= v20 * 0.95
                if not (-5.0 <= five_day_chg <= 4.5 and bar_contracted and h_lows and v_dry):
                    continue

                # Rule 3: Strong Start Entry Method (Gap-Up > Prev Close + High Volume + Cross Prev Day High)
                prev_hi = round(float(hi_s.iloc[-2]) * 1.001, 2)
                td_op = float(op_s.iloc[-1]); td_hi = float(hi_s.iloc[-1]); td_lo = float(lo_s.iloc[-1])
                gap_up_start = (td_op >= prev_c * 0.999) and (td_op <= prev_hi * 1.025)
                strong_vol_brk = (td_hi > prev_hi) and (cc > prev_hi) and (float(vols.iloc[-1]) >= v20 * 1.30)
                if gap_up_start and strong_vol_brk:
                    ep_px = max(prev_hi, round(td_op, 2))
                    sl_px = round(max(min(td_lo, float(lo_s.iloc[-2])) * 0.996, ep_px * 0.962), 2)
                    if td_lo <= sl_px:
                        continue
                    risk_pct = (ep_px - sl_px) / ep_px
                    if 0.010 <= risk_pct <= 0.042:
                        swing_start_low = round(float(lo_s.iloc[-10:-1].min()), 2)
                        score = (green_dots * 25) + (r3m * 50) - (rng_2d * 15)
                        day_cands.append((score, tk, ep_px, sl_px, swing_start_low))
            except Exception:
                continue

        day_cands.sort(key=lambda x: x[0], reverse=True)
        for score, tk, ep, sl, sw_start in day_cands:
            if len(pos) >= 4 or cash < 6000:
                break
            rps = ep - sl
            op_val_now = sum([p['sh'] * float(d[p['tk']].loc[cd, 'Close']) for p in pos if cd in d[p['tk']].index and not pd.isna(d[p['tk']].loc[cd, 'Close'])])
            tot_eq = cash + op_val_now
            risk_alloc = (tot_eq * 0.0125) if loss_streak >= 4 else (tot_eq * 0.025)
            max_cap = (tot_eq * 0.20) if loss_streak >= 4 else (tot_eq * 0.35)
            sh = min(int(risk_alloc / rps), int(min(cash * 0.95, max_cap) / ep))
            if sh <= 0 or sh * ep > cash:
                continue
            cash -= sh * ep
            pos.append({
                'tk': tk, 'bd': cd, 'orig': sw_start, 'ep': ep, 'sh': sh, 'sl': sl,
                't1_28': round(sw_start * 1.28, 2), 't2_40': round(sw_start * 1.40, 2), 't3_48': round(sw_start * 1.48, 2),
                'sm': False, 'scaled_28': False, 'scaled_40': False, 'days': 0,
                'max_g': (float(d[tk].loc[cd, 'High']) / ep) - 1, 'st_type': 'LOD_INIT_SL'
            })

    op_val = sum([p['sh'] * float(d[p['tk']].loc[cd, 'Close']) for p in pos if cd in d[p['tk']].index and not pd.isna(d[p['tk']].loc[cd, 'Close'])])
    tot_eq = round(cash + op_val, 2)
    eq.append({
        'Date': str(cd)[:10], 'Starting_Capital': INITIAL_CAPITAL,
        'Realized_Profit_Reinvested': round(realized_profit, 2), 'Cash_Available': round(cash, 2),
        'Open_Positions_Value': round(op_val, 2), 'Total_Equity': tot_eq,
        'Net_Profit_Rs': round(tot_eq - INITIAL_CAPITAL, 2),
        'Net_Return_%': round(((tot_eq / INITIAL_CAPITAL) - 1) * 100, 2), 'Open_Trades_Count': len(pos)
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
        'Swing_Start': p['orig'], 'Entry_Px': round(p['ep'], 2), 'Exit_or_CMP': curr_px,
        'Current_SL': p['sl'], 'Shares': p['sh'], 'PnL_Rs': unrl_pnl, 'PnL_%': unrl_pct
    })

all_rows = open_rows + trd[::-1]
if all_rows:
    pd.DataFrame(all_rows).to_csv('trade_log.csv', index=False)
else:
    pd.DataFrame(columns=[
        'Status', 'Stock', 'Exit_Reason', 'Buy_Date', 'Sell_Date', 'Days_Held',
        'Swing_Start', 'Entry_Px', 'Exit_or_CMP', 'Current_SL', 'Shares', 'PnL_Rs', 'PnL_%'
    ]).to_csv('trade_log.csv', index=False)

# 4. Save Live Portfolio Summary (portfolio_summary.csv)
eq_df = pd.DataFrame(eq)
closed_df = pd.DataFrame(trd)
win_rate = round((len(closed_df[closed_df['PnL_Rs'] >= 0]) / len(closed_df)) * 100, 1) if not closed_df.empty else 0.0
max_dd = round(((eq_df['Total_Equity'] / eq_df['Total_Equity'].cummax()) - 1).min() * 100, 2) if not eq_df.empty else 0.0
live_eq = eq_df['Total_Equity'].iloc[-1] if not eq_df.empty else INITIAL_CAPITAL
mkt_regime_now = "HEALTHY (>20 SMA)" if (not pd.isna(mkt_sma20.iloc[-1]) and mkt_index.iloc[-1] >= mkt_sma20.iloc[-1]) else "WEAK (<20 SMA - Trail 10SMA)"

summary_row = pd.DataFrame([{
    'Last_Updated': datetime.now().strftime('%Y-%m-%d'), 'Live_Start_Date': LIVE_START_DATE,
    'Market_Regime': mkt_regime_now, 'Initial_Capital': INITIAL_CAPITAL,
    'Realized_Profit_Reinvested': round(realized_profit, 2), 'Current_Total_Equity': live_eq,
    'Total_Net_PnL_Rs': eq_df['Net_Profit_Rs'].iloc[-1] if not eq_df.empty else 0.0,
    'Net_Return_%': eq_df['Net_Return_%'].iloc[-1] if not eq_df.empty else 0.0,
    'Max_Drawdown_%': max_dd, 'Completed_Trades': len(closed_df), 'Win_or_BE_Rate_%': win_rate,
    'Loss_Streak': loss_streak, 'Active_Open_Positions': len(pos), 'Cash_Available': round(cash, 2)
}])
summary_row.to_csv('portfolio_summary.csv', index=False)

# 5. Evening Watchlist Scanner (Fixed 20-SMA Base Math & 25-Day Bar Contraction)
candidates = []
today_str = datetime.now().strftime('%Y-%m-%d')
risk_mult = 0.0125 if loss_streak >= 4 else 0.025
risk_per_trade = live_eq * risk_mult
max_cap_per_trade = min(cash * 0.95, live_eq * (0.20 if loss_streak >= 4 else 0.35)) if cash > 6000 else live_eq * 0.35

for tk in tickers:
    try:
        dt = d[tk].dropna()
        if len(dt) < 85:
            continue
        hist = dt.tail(85)
        cp = hist['Close']; vols = hist['Volume']; hi_s = hist['High']; lo_s = hist['Low']
        cc = float(cp.iloc[-1]); s10 = float(cp.tail(10).mean()); s20 = float(cp.tail(20).mean())
        s20_20d_ago = float(cp.iloc[-40:-20].mean()); s50 = float(cp.tail(50).mean()); v20 = float(vols.tail(20).mean())
        if cc < 30 or cc > 4500 or v20 < 150000:
            continue

        # 1. Strong Preceding Uptrend (>=30% rally in last 3-4 months + >=2 Purple Dots)
        r3m = ((float(hi_s.tail(45).max()) / float(lo_s.iloc[:-15].min())) - 1) * 100
        if r3m < 30.0:
            continue
        rets = cp.pct_change()
        green_dots = int(((rets >= 0.048) & ((vols >= 500000) | (vols >= v20 * 2.0))).sum())
        if green_dots < 2:
            continue

        # 2. Controlled Correction (2% to 25% below 45-day peak) & Clean Pullback
        dd = (1 - (cc / float(hi_s.tail(45).max()))) * 100
        if dd > 25.0 or dd < 2.0:
            continue
        red_mask = (rets.tail(15) <= -0.048) & (vols.tail(15) >= max(500000, v20 * 1.8))
        if not ((not red_mask.any()) or (cc >= float(hi_s.tail(15)[red_mask].max()))):
            continue

        # 3. Reclaiming / Hugging 20-SMA in an Uptrend (Fixed 20-SMA Base Math!)
        # Blocks stocks that already ran >5.0% above 20-SMA or >4.5% in the last 5 days!
        dist_20sma = round(((cc / s20) - 1) * 100, 1)
        five_day_chg = round(((cc / float(cp.iloc[-6])) - 1) * 100, 1)
        if not (-2.5 <= dist_20sma <= 5.0 and s20 >= s50 * 0.99 and s20 > s20_20d_ago and -5.0 <= five_day_chg <= 4.5):
            continue

        # 4. Bar-by-Bar Contraction compared to 25-day base swings + Higher Lows on right side
        bar_ranges_25 = ((hi_s.tail(25) - lo_s.tail(25)) / cp.tail(25)) * 100
        max_25d_bar = round(float(bar_ranges_25.max()), 2)
        today_bar = round(float(bar_ranges_25.iloc[-1]), 2)
        rng_2d = round(float(bar_ranges_25.tail(2).mean()), 2)
        inside_bar = (float(hi_s.iloc[-1]) <= float(hi_s.iloc[-2])) and (float(lo_s.iloc[-1]) >= float(lo_s.iloc[-2]))
        contracting = (today_bar <= 3.2 and rng_2d <= 3.5) and (today_bar <= max_25d_bar * 0.50 or inside_bar)
        h_lows = float(lo_s.iloc[-1]) >= float(lo_s.tail(8).min())
        v_ratio = round(float(vols.iloc[-1]) / v20, 2) if v20 > 0 else 9.9

        if contracting and h_lows and v_ratio <= 1.0:
            tier = "1_DAY1_BAR_VCP" if (today_bar <= 2.4 or inside_bar) and abs(dist_20sma) <= 3.5 and v_ratio <= 0.80 else "2_RECLAIM_20SMA"
            entry = round(float(hi_s.iloc[-1]) * 1.001, 2)
            sl = round(max(float(lo_s.tail(2).min()) * 0.996, entry * 0.962), 2)
            rps = max(entry - sl, 0.5)
            sl_pct = round(((entry - sl) / entry) * 100, 2)
            swing_start_low = round(float(lo_s.tail(10).min()), 2)
            sh = int(min(risk_per_trade / rps, max_cap_per_trade / entry))
            if sh > 0 and 1.0 <= sl_pct <= 4.2:
                candidates.append({
                    'Scan_Date': today_str, 'Tier': tier, 'Stock': tk.replace('.NS', ''),
                    'CMP': round(cc, 2), 'Purple_Dots': green_dots, 'Pullback%': round(dd, 1),
                    'Dist_20SMA%': dist_20sma, '5D_Chg%': five_day_chg,
                    'Max_25D_Bar%': max_25d_bar, 'Today_Bar%': today_bar,
                    'Inside_Bar': 'YES' if inside_bar else 'NO', 'Vol_x20D': v_ratio,
                    'GapUp_Above_Close': round(cc, 2), 'Buy_Stop_High': entry,
                    'LOD_SL': sl, 'SL_%': sl_pct, 'BE_At_+7.5%': round(entry * 1.075, 2),
                    'Scale1_28%_Start': round(swing_start_low * 1.28, 2),
                    'Scale2_40%_Start': round(swing_start_low * 1.40, 2),
                    'Max_48%_Start': round(swing_start_low * 1.48, 2),
                    'Qty_50k': sh, 'Capital_Req': round(sh * entry, 0)
                })
    except Exception:
        continue

cdf = pd.DataFrame(candidates)
if not cdf.empty:
    cdf = cdf.sort_values(by=['Tier', 'Today_Bar%', 'Dist_20SMA%'], ascending=[True, True, True]).head(15)
    cdf.to_csv('best_stocks.csv', index=False)
else:
    pd.DataFrame(columns=[
        'Scan_Date', 'Tier', 'Stock', 'CMP', 'Purple_Dots', 'Pullback%', 'Dist_20SMA%',
        '5D_Chg%', 'Max_25D_Bar%', 'Today_Bar%', 'Inside_Bar', 'Vol_x20D',
        'GapUp_Above_Close', 'Buy_Stop_High', 'LOD_SL', 'SL_%', 'BE_At_+7.5%',
        'Scale1_28%_Start', 'Scale2_40%_Start', 'Max_48%_Start', 'Qty_50k', 'Capital_Req'
    ]).to_csv('best_stocks.csv', index=False)

print("\n=== PORTFOLIO SUMMARY ===")
print(summary_row.to_string(index=False))
print("\n=== EVENING WATCHLIST: RECLAIMED 20-SMA + BAR-BY-BAR CONTRACTION ===")
if not cdf.empty:
    print(cdf.to_string(index=False))
else:
    print("No stocks met the strict Day-1 Bar-by-Bar VCP criteria today.")
