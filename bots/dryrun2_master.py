#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DRY-RUN 2 — 40 wariantów „pod poprawę przewagi, jakości i skuteczności BIN”
============================================================================
Bankroll 50 $, stawka startowa 1.25 $ (2.5% kapitału), ta sama drabinka co w dry-runie 1
(50 -> 1.25 / 75 -> 1.875 / 112.5 -> 2.8125; poziom = +50% kapitału).

CO POPRAWIONO WOBEC BOTA (najr_live_UP_HOLD.py) — to jest sedno tego przebiegu:
  1. MODEL v3 (mikrostruktura): fair = (1-w)*model + w*mid rynku (w=0.15–0.25). Model przestaje
     być przesadnie pewny siebie, gdy rynek „wie lepiej” (świeża informacja, której nie ma w CEX).
  2. OGONY t5 (model v2/v3): rozkład Studenta 5 st. swobody zamiast normalnego — przy tym samym
     z-score mniejsza pewność, czyli mniej fałszywych „pewniaków” (główna przyczyna strat BIN).
  3. ZMIENNOŚĆ PODWÓJNA: sigma = mieszanka krótkiej (60 barów) i długiej (240 barów) wg fazy okna —
     na starcie okna liczy się szerszy kontekst, na końcu bieżący „oddech” rynku.
  4. PRZEWAGA NETTO: edge = p − ask − fee(ask); opłata takera 0.07·p·(1−p) jest zawsze odejmowana,
     więc „dodatnia przewaga” = realny zysk, a nie brutto.
  5. FILTR GŁĘBOKOŚCI: wejście tylko gdy w książce jest ≥ 3–5× stawki po zadanej cenie
     (mniej poślizgu na fillu, który w tym silniku liczony jest po kolejnych poziomach).
  6. FILTR SPREADU: nie wchodzimy przy spreadzie > 4–8c (tam spread zjada całą przewagę).
  7. PERSIST (trwałość sygnału): przewaga musi utrzymać się 2–3 cykle — odsiewa pojedyncze,
     przypadkowe „iskry” w książce (podbijane zlecenia, chwilowe braki płynności).
  8. ANTI-CHASE: blokada wejścia, gdy ask podniósł się > 4–6c w ostatnich ~30 s (gonimy cenę).
  9. IMBALANCE: zgodność z nierównowagą książki (bid/ask top-5) — filtr informacyjnego przepływu.
 10. STOP-LOSS i KILL-SWITCH na drawdown — ograniczenie ogona strat.
 11. KONTROLA KORELACJI: max 1 pozycja na okno (wariant S2_CORR1).

Uruchomienie:
    python3 dryrun2_master.py --minutes 480
    python3 dryrun2_master.py --report
Wyniki: reports/dryrun2_report.md + .csv + trades.jsonl ; stan: state/dryrun2.json
"""
import sys
import poly_dryrun_engine as E

LAD = dict(kind="ladder", start_stake=1.25, step_bank=0.50, step_stake=0.50, down=False)
BASE = dict(tfs=("5m", "15m"), min_px=0.10, max_px=0.90, min_fair=0.45, edge=0.04,
            model="v3", w_mkt=0.15, vol_cushion=1.05, tp=0.80, max_pos=7, persist=2,
            depth_x=3, max_spread=0.06, timing={"5m": (0, 300), "15m": (0, 900)})


def var(vid, name, **kw):
    v = dict(id=vid, name=name, ladder=dict(LAD))
    v.update(BASE)
    v.update({k: val for k, val in kw.items() if k != "ladder"})
    if "ladder" in kw:
        v["ladder"] = dict(LAD, **kw["ladder"])
    return v


VARIANTS = [
    # ---------- baza i drabinka stawki (1/2/3/4%/50%, UD, % kapitału)
    var(1, "S2_CORE_v3"),
    var(2, "S2_LAD_1pct", ladder=dict(step_bank=0.01, step_stake=0.01)),
    var(3, "S2_LAD_2pct", ladder=dict(step_bank=0.02, step_stake=0.02)),
    var(4, "S2_LAD_3pct", ladder=dict(step_bank=0.03, step_stake=0.03)),
    var(5, "S2_LAD_4pct", ladder=dict(step_bank=0.04, step_stake=0.04)),
    var(6, "S2_LAD_50_UD", ladder=dict(down=True)),
    var(7, "S2_PROP_2.5pct", ladder=dict(kind="prop", pct=0.025)),

    # ---------- take-profit (wyjście po bid)
    var(8, "S2_TP60", tp=0.60),
    var(9, "S2_TP70", tp=0.70),
    var(10, "S2_TP90", tp=0.90),
    var(11, "S2_HOLD", tp=None),

    # ---------- próg przewagi
    var(12, "S2_EDGE_2c", edge=0.02),
    var(13, "S2_EDGE_3c", edge=0.03),
    var(14, "S2_EDGE_6c", edge=0.06),
    var(15, "S2_EDGE_8c", edge=0.08),

    # ---------- model
    var(16, "S2_M1_normal", model="v1"),
    var(17, "S2_M2_t5", model="v2", w_mkt=0.0),
    var(18, "S2_M3_mkt25", model="v3", w_mkt=0.25),

    # ---------- filtry jakości
    var(19, "S2_F_persist3", persist=3),
    var(20, "S2_F_nopersist", persist=0),
    var(21, "S2_F_imb", imb_filter=0.55),
    var(22, "S2_F_depth5", depth_x=5),
    var(23, "S2_F_spread4", max_spread=0.04),
    var(24, "S2_F_antichase", anti_chase=0.04),
    var(25, "S2_F_ALL", persist=3, depth_x=5, max_spread=0.04, anti_chase=0.04, imb_filter=0.54),

    # ---------- okna wejścia
    var(26, "S2_T_late5m", timing={"5m": (150, 300), "15m": (0, 900)}),
    var(27, "S2_T_last60_5m", timing={"5m": (240, 300), "15m": (0, 900)}),
    var(28, "S2_T_late15m", timing={"5m": (0, 300), "15m": (600, 900)}),
    var(29, "S2_T_last3m_15m", timing={"5m": (0, 300), "15m": (720, 900)}),

    # ---------- strona / aktywa / interwał
    var(30, "S2_UP_only", side="Up"),
    var(31, "S2_DOWN_only", side="Down"),
    var(32, "S2_BTC_only", assets=["BTC"]),
    var(33, "S2_ALTS_only", assets=["ETH", "SOL", "XRP", "DOGE", "BNB", "HYPE"]),
    var(34, "S2_5m_only", tfs=("5m",)),
    var(35, "S2_15m_only", tfs=("15m",)),

    # ---------- ryzyko
    var(36, "S2_SL25", sl=0.25),
    var(37, "S2_SL35", sl=0.35),
    var(38, "S2_DDhalt20", dd_halt=0.20),

    # ---------- pewność / cena / sniper / korelacja
    var(39, "S2_HICONF", min_fair=0.60, edge=0.05),
    var(40, "S2_CHEAP_only", max_px=0.55, min_fair=0.50, edge=0.06),
    var(41, "S2_SNIPER", min_fair=0.75, max_px=0.92, edge=0.03, persist=1,
        timing={"5m": (240, 300), "15m": (720, 900)}),
    var(42, "S2_CORR1", max_per_window=1, max_pos=6),
]

if __name__ == "__main__":
    sys.exit(E.cli(VARIANTS, "dryrun2", sys.argv[1:]) or 0)
