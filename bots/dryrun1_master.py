#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DRY-RUN 1 — warianty zamówione przez użytkownika + ulepszenia
=============================================================
Bankroll 50 $, stawka startowa 1.25 $ (2.5% kapitału). Drabinka „reset stawki przy wzroście bankrolla”:
  50 $ -> 1.25 $ | 75 $ -> 1.875 $ | 112.5 $ -> 2.8125 $  (poziom = +50% kapitału, stawka +50%)
Warianty drabinki 1%/2%/3%/4% wzrostu bankrolla (stawka rośnie mnożnikowo co każdy próg).

Zestaw:
  BASE_obecne        — obecne ustawienia bota (px 0.03–0.85, edge 5c, fair>=0.40, TP 0.80)
  LAD_1 / LAD_2 / LAD_3 / LAD_4 — wzrost bankrolla i stawki co 1 / 2 / 3 / 4 %
  LAD_2_4            — bankroll +2%, stawka +4% (szybsze składanie zysku)
  LAD_50_UD          — drabinka +50% ale stawka także SPADA (wariant UD, jak w bocie)
  MAX_70/80/90       — maksymalna szansa (cena wejścia) 70/80/90%
  MIN_20/30/40/50/60 — minimalna szansa 20/30/40/50/60%
  T5_5m_po2m/po3m    — wejście po 2 / 3 minutach trwania rynku 5m
  T15_15m_po5m/7m/10m— wejście po 5 / 7 / 10 minutach trwania rynku 15m
  IMP_MICRO          — fair mieszane z mid rynku (mniej pewny siebie model) + filtr głębokości i spreadu
  IMP_PERSIST        — sygnał musi się utrzymać 2 cykle (odrzuca jednorazowe „iskry”) + anti-chase
  IMP_T5             — ogony Studenta t5 + bufor zmienności (mniej overconfidence)
  IMP_QUAL           — pełny pakiet: model v3 + persist + głębokość + spread + imbalance
  IMP_STRICT         — wysokie progi: edge 8c, fair>=55%, cena <=80c, persist 2, głębokość 4x stawki

Uruchomienie:
    python3 dryrun1_master.py                 # start (Ctrl+C kończy i zapisuje)
    python3 dryrun1_master.py --minutes 480   # auto-stop po 8 h
    python3 dryrun1_master.py --report        # tabela z zapisanego stanu
    python3 dryrun1_master.py --reset         # zerowanie
Wyniki: reports/dryrun1_report.md + .csv + trades.jsonl ; stan: state/dryrun1.json
"""
import sys
import poly_dryrun_engine as E

LAD = dict(kind="ladder", start_stake=1.25, step_bank=0.50, step_stake=0.50, down=False)


def var(vid, name, **kw):
    v = dict(id=vid, name=name, tfs=("5m", "15m"), min_px=0.03, max_px=0.85, min_fair=0.40,
             edge=0.05, model="v1", tp=0.80, max_pos=7,
             timing={"5m": (0, 300), "15m": (0, 900)}, ladder=dict(LAD))
    v.update({k: val for k, val in kw.items() if k != "ladder"})
    if "ladder" in kw:
        v["ladder"] = dict(LAD, **kw["ladder"])
    return v


VARIANTS = [
    # ---------- baza / drabinka stawki
    var(1, "S1_BASE_obecne"),
    var(2, "S1_LAD_1pct", ladder=dict(step_bank=0.01, step_stake=0.01)),
    var(3, "S1_LAD_2pct", ladder=dict(step_bank=0.02, step_stake=0.02)),
    var(4, "S1_LAD_3pct", ladder=dict(step_bank=0.03, step_stake=0.03)),
    var(5, "S1_LAD_4pct", ladder=dict(step_bank=0.04, step_stake=0.04)),
    var(6, "S1_LAD_2_4", ladder=dict(step_bank=0.02, step_stake=0.04)),
    var(7, "S1_LAD_50_UD", ladder=dict(down=True)),

    # ---------- maksymalna szansa (cena wejścia)
    var(8, "S1_MAX_70", max_px=0.70),
    var(9, "S1_MAX_80", max_px=0.80),
    var(10, "S1_MAX_90", max_px=0.90),

    # ---------- minimalna szansa
    var(11, "S1_MIN_20", min_px=0.20),
    var(12, "S1_MIN_30", min_px=0.30),
    var(13, "S1_MIN_40", min_px=0.40),
    var(14, "S1_MIN_50", min_px=0.50, min_fair=0.50),
    var(15, "S1_MIN_60", min_px=0.60, min_fair=0.60),

    # ---------- okna wejścia (5m: po 2/3 min; 15m: po 5/7/10 min)
    var(16, "S1_T5_po2m", timing={"5m": (120, 300), "15m": (0, 900)}),
    var(17, "S1_T5_po3m", timing={"5m": (180, 300), "15m": (0, 900)}),
    var(18, "S1_T15_po5m", timing={"5m": (0, 300), "15m": (300, 900)}),
    var(19, "S1_T15_po7m", timing={"5m": (0, 300), "15m": (420, 900)}),
    var(20, "S1_T15_po10m", timing={"5m": (0, 300), "15m": (600, 900)}),

    # ---------- moje ulepszenia (pobieranie kursu / szukanie przewagi / jakość sygnału)
    var(21, "S1_IMP_MICRO", model="v3", w_mkt=0.20, edge=0.04, max_px=0.90, depth_x=3, max_spread=0.06),
    var(22, "S1_IMP_PERSIST", persist=2, anti_chase=0.05),
    var(23, "S1_IMP_T5", model="v2", vol_cushion=1.10),
    var(24, "S1_IMP_QUAL", model="v3", w_mkt=0.15, persist=2, depth_x=4, max_spread=0.05, imb_filter=0.52),
    var(25, "S1_IMP_STRICT", edge=0.08, min_fair=0.55, max_px=0.80, persist=2, depth_x=4),
]

if __name__ == "__main__":
    sys.exit(E.cli(VARIANTS, "dryrun1", sys.argv[1:]) or 0)
