#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zbiorcze podsumowanie obu dry-runów -> results_summary.md (bez sieci, czyta state/*.json)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import poly_dryrun_engine as E  # noqa: E402
import dryrun1_master  # noqa: E402
import dryrun2_master  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))


def load(set_name, variants, bank=50.0):
    p = os.path.join(ROOT, "state", set_name + ".json")
    if not os.path.exists(p):
        return []
    with open(p) as f:
        d = json.load(f)
    out = []
    for v in variants:
        b = E.VBook(v, bank)
        bd = (d.get("books") or {}).get(str(v["id"]))
        if bd:
            b.load(bd)
        out.append(b)
    return out


def row(b):
    s = b.stats()
    return "| %s | %d | %.1f%% | %+.2f | %+.1f%% | %.1f%% | %.2f | %d |" % (
        s["name"], s["n"], s["wr"], s["pnl"], s["ret"], s["dd"], s["equity"], s["open"])


HDR = "| wariant | n | WR | PnL $ | zwrot | DD | kapitał | otw |\n|---|---|---|---|---|---|---|---|"


def block(title, books, ids, note=""):
    sel = [b for b in books if b.id in ids]
    sel.sort(key=lambda b: -b.stats()["pnl"])
    L = ["### " + title, ""]
    if note:
        L += [note, ""]
    L += [HDR] + [row(b) for b in sel] + [""]
    return L


def main():
    b1 = load("dryrun1", dryrun1_master.VARIANTS)
    b2 = load("dryrun2", dryrun2_master.VARIANTS)
    total = sum(b.stats()["n"] for b in b1 + b2)
    L = ["# Dry-runy — zbiorcze podsumowanie", "",
         "Bankroll **50 $** na wariant, stawka startowa **1.25 $** (2.5%% kapitału). "
         "Zamkniętych transakcji łącznie: **%d**." % total, "",
         "Drabinka stawki (zamówiona): 50 $ → 1.25 $, 75 $ → 1.875 $, 112.5 $ → 2.8125 $ "
         "(poziom = +50% kapitału, stawka +50%). Warianty 1/2/3/4% przeliczają stawkę co każdy taki próg.", ""]

    L.append("## Przebieg 1 — warianty zamówione (25)")
    L.append("")
    L += block("Ranking wszystkich wariantów przebiegu 1", b1, {v["id"] for v in dryrun1_master.VARIANTS})
    L += block("Drabinka stawki: 1% / 2% / 3% / 4% / 2-4 / 50-UD", b1, {2, 3, 4, 5, 6, 7},
              "Wszystkie zaczynają z tą samą stawką 1.25 $ — różnią się tempem składania zysku.")
    L += block("Maksymalna szansa (cena wejścia) 70 / 80 / 90%", b1, {8, 9, 10})
    L += block("Minimalna szansa 20 / 30 / 40 / 50 / 60%", b1, {11, 12, 13, 14, 15})
    L += block("Okna wejścia: 5m po 2/3 min, 15m po 5/7/10 min", b1, {16, 17, 18, 19, 20})
    L += block("Ulepszenia (model, filtry jakości, próg przewagi)", b1, {21, 22, 23, 24, 25})

    L.append("## Przebieg 2 — 42 warianty pod przewagę i skuteczność")
    L.append("")
    L += block("Ranking wszystkich wariantów przebiegu 2", b2, {v["id"] for v in dryrun2_master.VARIANTS})
    L += block("Take-profit: 60 / 70 / 80 / 90 / HOLD", b2, {8, 9, 10, 11})
    L += block("Próg przewagi: 2 / 3 / 6 / 8 c", b2, {12, 13, 14, 15})
    L += block("Model: normalny / t5 / mid rynku", b2, {16, 17, 18, 1})
    L += block("Filtry jakości (persist, głębokość, spread, imbalance, anti-chase, ALL)",
              b2, {19, 20, 21, 22, 23, 24, 25})
    L += block("Okna wejścia (late 5m, ostatnie 60 s 5m, late 15m, ostatnie 3 min 15m)", b2, {26, 27, 28, 29})
    L += block("Ryzyko i pewność (SL, kill-switch, min_fair, sniper, korelacja)", b2, {36, 37, 38, 39, 40, 41, 42})

    best1 = sorted([b.stats() for b in b1 if b.stats()["n"]], key=lambda s: -s["pnl"])[:1]
    best2 = sorted([b.stats() for b in b2 if b.stats()["n"]], key=lambda s: -s["pnl"])[:1]
    L += ["## Wnioski", ""]
    for lbl, best in (("Przebieg 1", best1), ("Przebieg 2", best2)):
        if best:
            s = best[0]
            L.append("* **%s** — najlepszy: `%s`, n=%d, WR %.1f%%, PnL %+.2f $ (%.1f%% kapitału), DD %.1f%%, "
                     "średnia cena wejścia %.3f, średnia przewaga %+.3f."
                     % (lbl, s["name"], s["n"], s["wr"], s["pnl"], s["ret"], s["dd"], s["avg_px"], s["avg_edge"]))
    L += ["", "> Przy n < 30 wariantu nie traktuj jak rozstrzygniętego — to jeszcze szum. "
          "Zostaw przebiegi na dłużej i porównuj ponownie po kilkuset transakcjach.", ""]
    out = os.path.join(ROOT, "results_summary.md")
    with open(out, "w") as f:
        f.write("\n".join(L))
    print("zapisano:", out, "| transakcji:", total)


if __name__ == "__main__":
    main()
