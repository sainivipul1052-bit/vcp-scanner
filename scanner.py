# ULTRA-STRICT MANAS ARORA VCP FILTER (No Chasing, Pure Base Coiling)
        if r3m >= 35 and green_dots >= 2 and days_since_peak >= 8 and 3 <= dd <= 22 and already_moved <= 6.0 and clean_pullback and (cc >= s20 and s20 > s20_10d and s20 >= s50) and rng_2d <= 2.2 and v_ratio <= 0.70 and h_lows:
            tier = "1_PERFECT_VCP"
            sl = round(max(float(lo_s.tail(2).min()) * 0.996, entry * 0.965), 2)
            rps = max(entry - sl, 0.5)
            sl_pct = round(((entry - sl) / entry) * 100, 2)
            scale_px = round(origin_low * 1.35, 2)
            tgt_px = round(origin_low * 1.48, 2)
            rem_gain_pct = round(((tgt_px / entry) - 1) * 100, 1)
            sh = int(min(risk_per_trade_rs / rps, max_alloc_rs / entry))
            
            if sh > 0 and 1.2 <= sl_pct <= 3.8 and rem_gain_pct >= 32.0:
                candidates.append({
                    'Scan_Date': today_str, 'Tier': tier, 'Stock': tk.replace('.NS', ''),
                    'CMP': round(cc, 2), 'Purple_Dots': green_dots, 'Origin_Low': origin_low,
                    'Moved_So_Far%': already_moved, 'Tight_2D%': round(rng_2d, 2),
                    'Vol_Dry_x20D': v_ratio, 'Buy_Above': entry, 'SL': sl, 'SL_%': sl_pct,
                    'BE_Move_At_+7.5%': round(entry * 1.075, 2),
                    'Scale_35%_Origin': scale_px, 'Tgt_48%_Origin': tgt_px,
                    'Net_Upside_Left%': rem_gain_pct, 'Compounded_Qty': sh, 'Capital_Alloc': round(sh * entry, 0)
                })
