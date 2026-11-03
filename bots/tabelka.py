#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TABELKA NA ŻYWO — podgląd obu dry-runów w terminalu (bez zależności, tylko czyta state/*.json).

  python3 tabelka.py                 # jeden rzut tabeli
  python3 tabelka.py --watch         # odświeżanie co 20 s (Ctrl+C kończy podgląd)
  python3 tabelka.py -w -i 10        # co 10 s
  python3 tabelka.py --set 2         # tylko przebieg 42-wariantowy
  python3 tabelka.py --top 10        # 10 najlepszych
  python3 tabelka.py --sort wr       # pnl | wr | n | dd
  python3 tabelka.py --trades        # + ostatnie 8 zamkniętych transakcji
  python3 tabelka.py -w --trades     # wszystko razem
"""
import argparse
import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
SETS = {"1": ("dryrun1", "PRZEBIEG 1 (25 wariantów)"), "2": ("dryrun2", "PRZEBIEG 2 (42 warianty)"), "3": ("live_s2", "LIVE/PAPER S2_TP70")}


def load(name):
    p = os.path.join(ROOT, "state", name + ".json")
    for _ in range(3):
        try:
            with open(p) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(0.15)
    return None


def m_of(b, start):
    cl = b.get("closed") or []
    n = len(cl)
    wins = sum(1 for t in cl if t["pnl"] > 0)
    pnl = sum(t["pnl"] for t in cl)
    run = peak = 50.0
    dd = 0.0
    for t in cl:
        run += t["pnl"]
        peak = max(peak, run)
        dd = max(dd, (peak - run) / peak if peak > 0 else 0.0)
    per = {}
    for t in cl:
        a = per.setdefault(t["tf"], [0, 0.0])
        a[0] += 1
        a[1] += t["pnl"]
    tp = sum(1 for t in cl if t.get("exit") == "TP")
    return dict(name=b.get("name", "?"), n=n, wins=wins, wr=(wins / n * 100 if n else 0.0), pnl=pnl,
                dd=dd * 100, eq=50.0 + pnl, open=len(b.get("positions") or []), per=per, tp=tp,
                p5=per.get("5m", [0, 0.0]), p15=per.get("15m", [0, 0.0]),
                edge=(sum(t.get("edge", 0) for t in cl) / n if n else 0.0),
                px=(sum(t.get("entry", 0) for t in cl) / n if n else 0.0),
                hold=(sum(t.get("hold", 0) for t in cl) / n if n else 0.0))


def line(cols, widths, hl=None):
    out = []
    for i, c in enumerate(cols):
        s = str(c)
        out.append(s.ljust(widths[i]) if i == 1 else s.rjust(widths[i]))
    return " ".join(out)


def render(which, top, sort_by, show_trades):
    w = shutil.get_terminal_size((80, 24)).columns
    cols = ["#", "wariant", "n", "WR%", "PnL$"]
    if w >= 66:
        cols += ["W/L", "ret%", "DD%"]
    if w >= 92:
        cols += ["5m$", "15m$", "px", "edge", "otw"]
    widths = [3, min(24, max(12, w // 4)), 3, 5, 8]
    if w >= 66:
        widths += [7, 6, 6]
    if w >= 92:
        widths += [8, 8, 5, 6, 3]
    rows_out = []
    for key in which:
        name, label = SETS[key]
        d = load(name)
        if not d:
            rows_out.append("  (brak %s — bot jeszcze nie zapisał stanu)" % name)
            continue
        books = d.get("books") or ({"1": d["book"]} if d.get("book") else {})
        ms = [m_of(b, d.get("start", time.time())) for b in books.values()]
        ms.sort(key={"pnl": lambda m: -m["pnl"], "wr": lambda m: -m["wr"], "n": lambda m: -m["n"],
                     "dd": lambda m: m["dd"]}.get(sort_by, lambda m: -m["pnl"]))
        n = sum(m["n"] for m in ms)
        pnl = sum(m["pnl"] for m in ms)
        wr = (sum(m["wins"] for m in ms) / n * 100) if n else 0.0
        rows_out.append("")
        rows_out.append("%s   n=%d   suma PnL=%+.2f$   WR=%.1f%%   wariantów=%d" % (label, n, pnl, wr, len(ms)))
        rows_out.append(line(cols, widths))
        rows_out.append(line(["" if i else "-" for i in range(len(cols))], widths).replace(" ", "-"))
        for m in ms[:top]:
            row = [m["name"].replace("S1_", "").replace("S2_", "")[:widths[1]],
                   m["n"], "%.1f" % m["wr"], "%+.2f" % m["pnl"]]
            row.insert(0, "")
            if w >= 66:
                row += ["%d/%d" % (m["wins"], m["n"] - m["wins"]), "%+.1f" % (m["pnl"] / 50.0 * 100),
                        "%.1f" % m["dd"]]
            if w >= 92:
                row += ["%+.1f" % m["p5"][1], "%+.1f" % m["p15"][1], "%.2f" % m["px"],
                        "%+.3f" % m["edge"], str(m["open"])]
            rows_out.append(line(row, widths))
        if show_trades:
            cl = [(b.get("name", "?"), t) for b in (d.get("books") or {"1": d.get("book") or {}}).values()
                  for t in (b.get("closed") or [])]
            cl.sort(key=lambda bt: -bt[1].get("t_open", 0))
            rows_out.append("  ostatnie transakcje:")
            for bn, t in cl[:8]:
                rows_out.append("   %-4s %-3s %-4s %5.2f x%-4s %-4s %+7.2f$  %s" % (
                    t["asset"], t["tf"], t["side"], t["entry"], "%.0f" % t.get("shares", 0),
                    t.get("exit", "?"), t["pnl"], bn.replace("S1_", "").replace("S2_", "")[:16]))
    return "\n".join(rows_out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-w", "--watch", action="store_true")
    ap.add_argument("-i", "--interval", type=int, default=20)
    ap.add_argument("--set", choices=["1", "2", "3", "both"], default="both")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--sort", choices=["pnl", "wr", "n", "dd"], default="pnl")
    ap.add_argument("--trades", action="store_true")
    a = ap.parse_args()
    which = ["1", "2"] if a.set == "both" else [a.set]
    try:
        while True:
            body = render(which, a.top, a.sort, a.trades)
            head = "DRY-RUNY  %s UTC%s" % (time.strftime("%H:%M:%S", time.gmtime()),
                                           "   (Ctrl+C = wyjście, odświeżanie co %ds)" % a.interval
                                           if a.watch else "")
            if a.watch:
                sys.stdout.write("\033[H\033[2J")
            sys.stdout.write(head + "\n" + "=" * min(120, shutil.get_terminal_size((80, 24)).columns) +
                             "\n" + body + "\n")
            sys.stdout.flush()
            if not a.watch:
                break
            time.sleep(a.interval)
    except KeyboardInterrupt:
        print("\nkoniec podglądu (bot dalej działa)")


if __name__ == "__main__":
    main()
