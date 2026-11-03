#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ŁĄCZNA EKSPOZYCJA OBU BOTÓW (live_s2 + najr_live) - jeden ekran, żeby nie przekroczyć limitu.

  python3 exposure.py            # jednorazowo
  python3 exposure.py -w -i 15   # odświeżanie co 15 s
  python3 exposure.py --max-cost 12.5   # alarm przy przekroczeniu kosztu otwartych pozycji
"""
import argparse
import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))


def load(p):
    if not os.path.exists(p):
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return None


def rows_s2(d):
    out = []
    if not d:
        return out
    book = d.get("book") or {}
    for p in book.get("positions") or []:
        out.append(("S2_TP70", p.get("asset"), p.get("tf"), p.get("side"),
                    float(p.get("cost") or 0), float(p.get("entry") or 0), int(p.get("end") or 0)))
    return out


def rows_najr(d):
    out = []
    if not d:
        return out
    for t in d.get("trades") or []:
        if t.get("status") not in ("open", "pending", "check"):
            continue
        out.append(("NAJR", t.get("asset"), t.get("tf"), t.get("side"),
                    float(t.get("cost") or t.get("stake") or 0), float(t.get("entry") or 0),
                    int(t.get("end_ts") or 0)))
    return out


def render(max_cost, bank):
    import glob
    files = sorted(glob.glob(os.path.join(ROOT, "state", "live_*.json")))
    r = []
    for f in files:
        lbl = os.path.basename(f)[:-5].replace("live_", "").upper()
        for row in rows_s2(load(f)):
            r.append((lbl,) + tuple(row[1:]))
    b = load(os.path.join(ROOT, "najr_live_state.json"))
    r += rows_najr(b)
    a = load(os.path.join(ROOT, "state", "live_tp70.json")) or (load(files[0]) if files else None)
    w = shutil.get_terminal_size((80, 24)).columns
    L = []
    L.append("EKSPOZYCJA  %s UTC" % time.strftime("%H:%M:%S", time.gmtime()))
    L.append("-" * min(w, 78))
    if not r:
        L.append("brak otwartych pozycji")
    else:
        L.append("%-9s %-5s %-4s %-5s %8s %7s %8s" % ("bot", "moneta", "tf", "strona", "koszt $", "cena", "do konca"))
        for bot, asset, tf, side, cost, entry, end in r:
            rem = (end - time.time()) if end else 0
            L.append("%-9s %-5s %-4s %-5s %8.2f %7.3f %7.0fs" % (bot, asset, tf, side, cost, entry, max(rem, 0)))
    cost = sum(x[4] for x in r)
    L.append("-" * min(w, 78))
    L.append("OTWARTE: %d pozycji | koszt razem %.2f $ | %.1f%% bankrolla (%.0f $)"
             % (len(r), cost, (cost / bank * 100 if bank else 0), bank))
    if a:
        bk = a.get("book") or {}
        L.append("S2:     kapitał %.2f $ | PnL dnia %+.2f $ | halt=%s"
                 % (bank + float(bk.get("realized") or 0), float(a.get("day_pnl") or 0),
                    "TAK" if a.get("halt") else "nie"))
    if b:
        realized = sum(float(t.get("pnl") or 0) for t in (b.get("trades") or []) if t.get("status") == "closed")
        L.append("NAJR:   zrealizowane razem %+.2f $ (stan z pliku)" % realized)
    if max_cost and cost > max_cost:
        L.append("!!! ALARM: koszt otwartych %.2f $ > limit %.2f $ - zamknij część pozycji" % (cost, max_cost))
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-w", "--watch", action="store_true")
    ap.add_argument("-i", "--interval", type=int, default=15)
    ap.add_argument("--bank", type=float, default=50.0)
    ap.add_argument("--max-cost", type=float, default=12.5)
    a = ap.parse_args()
    try:
        while True:
            txt = render(a.max_cost, a.bank)
            if a.watch:
                sys.stdout.write("\033[H\033[2J")
            print(txt, flush=True)
            if not a.watch:
                break
            time.sleep(a.interval)
    except KeyboardInterrupt:
        print("\nkoniec podglądu (boty dalej działają)")


if __name__ == "__main__":
    main()
