# dryrun2 — wyniki dry-runu

Start: 2026-11-03 19:07 UTC | bankroll startowy: **$50.00** | wariantów: **42** | transakcji: **0**

> Paper trading na żywych orderbookach Polymarket (CLOB) i cenach Binance. Zero prawdziwych zleceń. Fill po kolejnych poziomach książki, opłata takera 0.07·p·(1−p), rozliczenie z Gammy.

## Ranking (po PnL)

| # | wariant | n | W/L | WR% | PnL $ | ROI% | zwrot% | DD% | kapitał | stawka | otw | śr.px | śr.edge | TP |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

## Rozbicie 5m vs 15m

| wariant | tf | n | W | PnL $ |
|---|---|---|---|---|

## Parametry wariantów

| # | wariant | model | px pasmo | edge | fair min | TP | SL | timing | drabinka | filtry |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | S2_CORE_v3 | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 2 | S2_LAD_1pct | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +1%/+1% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 3 | S2_LAD_2pct | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +2%/+2% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 4 | S2_LAD_3pct | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +3%/+3% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 5 | S2_LAD_4pct | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +4%/+4% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 6 | S2_LAD_50_UD | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 7 | S2_PROP_2.5pct | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | prop | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 8 | S2_TP60 | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.60 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 9 | S2_TP70 | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.70 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 10 | S2_TP90 | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.90 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 11 | S2_HOLD | v3 | 0.10–0.90 | 0.040 | 0.45 | - | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 12 | S2_EDGE_2c | v3 | 0.10–0.90 | 0.020 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 13 | S2_EDGE_3c | v3 | 0.10–0.90 | 0.030 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 14 | S2_EDGE_6c | v3 | 0.10–0.90 | 0.060 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 15 | S2_EDGE_8c | v3 | 0.10–0.90 | 0.080 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 16 | S2_M1_normal | v1 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 17 | S2_M2_t5 | v2 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05 |
| 18 | S2_M3_mkt25 | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.25 |
| 19 | S2_F_persist3 | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=3, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 20 | S2_F_nopersist | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 21 | S2_F_imb | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, imb_filter=0.55, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 22 | S2_F_depth5 | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=5, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 23 | S2_F_spread4 | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.04, vol_cushion=1.05, w_mkt=0.15 |
| 24 | S2_F_antichase | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, anti_chase=0.04, vol_cushion=1.05, w_mkt=0.15 |
| 25 | S2_F_ALL | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=3, imb_filter=0.54, depth_x=5, max_spread=0.04, anti_chase=0.04, vol_cushion=1.05, w_mkt=0.15 |
| 26 | S2_T_late5m | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [150, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 27 | S2_T_last60_5m | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [240, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 28 | S2_T_late15m | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [600, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 29 | S2_T_last3m_15m | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [720, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 30 | S2_UP_only | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 31 | S2_DOWN_only | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 32 | S2_BTC_only | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 33 | S2_ALTS_only | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 34 | S2_5m_only | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 35 | S2_15m_only | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 36 | S2_SL25 | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | 25% | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 37 | S2_SL35 | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | 35% | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 38 | S2_DDhalt20 | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15, dd_halt=0.2 |
| 39 | S2_HICONF | v3 | 0.10–0.90 | 0.050 | 0.60 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 40 | S2_CHEAP_only | v3 | 0.10–0.55 | 0.060 | 0.50 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 41 | S2_SNIPER | v3 | 0.10–0.92 | 0.030 | 0.75 | 0.80 | - | {"5m": [240, 300], "15m": [720, 900]} | +50%/+50% UP | persist=1, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
| 42 | S2_CORR1 | v3 | 0.10–0.90 | 0.040 | 0.45 | 0.80 | - | {"5m": [0, 300], "15m": [0, 900]} | +50%/+50% UP | persist=2, depth_x=3, max_spread=0.06, vol_cushion=1.05, w_mkt=0.15 |
