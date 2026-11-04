#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analiza bt_cache2.json: EV, t-stat, przedzialy ufnosci, rozbicie per liga.
Nie zmienia nic w bocie - tylko czyta cache i liczy statystyki.

Uzycie:
    python analyze.py            # pre + live, wszystkie progi
    python analyze.py --tag      # dodatkowo per liga
"""
import argparse
import math
import statistics
import sys

try:
    import bot_v2_dry_v3 as bot
except ImportError:
    sys.exit("brak bot_v2_dry_v3.py w tym katalogu")

THRESHOLDS = (0.50, 0.60, 0.70, 0.75, 0.80, 0.85)


def _trades(cache, timing, no_lo):
    out = []
    for m in cache:
        if bot.BT_USE_POLICY and not bot._bt_policy_ok(m, timing):
            continue
        fee = bot.fee_for_tag(",".join(m.get("source_tags") or ["sports"]))
        t = bot._sim_yes_threshold(m, no_lo, fee, bot.ASSUMED_SPREAD, 1.0, timing)
        if t:
            out.append((t["entry_no"], t["payout"], t["pnl_pct"], t["pnl_usd"]))
    return out


def _describe(tr):
    n = len(tr)
    pnl = [x[2] for x in tr]
    mean = statistics.mean(pnl)
    sd = statistics.stdev(pnl) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n else 0.0
    t = mean / se if se > 1e-9 else 0.0   # sd=0 (identyczne transakcje) -> t nie ma sensu
    return {
        "n": n,
        "mean": mean,
        "sd": sd,
        "t": t,
        "lo": mean - 1.96 * se,
        "hi": mean + 1.96 * se,
        "wr": sum(1 for x in tr if x[1] > 0.5) / n * 100.0 if n else 0.0,
        "price": statistics.mean(x[0] for x in tr) if n else 0.0,
        "pnl": sum(x[3] for x in tr),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", action="store_true", help="dodatkowo rozbicie per liga")
    ap.add_argument("--min-vol", type=float, default=None)
    args = ap.parse_args()

    if args.min_vol is not None:
        bot.BT_MIN_VOL = args.min_vol

    cache = bot._load(bot.BT_CACHE, None)
    if not cache:
        sys.exit(f"brak {bot.BT_CACHE} - najpierw: python bot_v2_dry_v3.py --fetch-history --days 7")
    total = len(cache)
    cache = [m for m in cache if float(m.get("volume") or 0.0) >= bot.BT_MIN_VOL]
    print(f"cache: {total} rynkow | po filtrze plynnosci (vol>={bot.BT_MIN_VOL:.0f}): {len(cache)}"
          f" | spread: {bot.ASSUMED_SPREAD:.3f} | polityka: {'ON' if bot.BT_USE_POLICY else 'OFF'}")
    print()
    print(f"{'wariant':22s} {'n':>5s} {'cena':>6s} {'winrate':>8s} {'EV':>8s} {'t':>6s} "
          f"{'CI95 EV':>18s} {'PnL':>8s}")
    best = None
    for timing in ("pre", "live"):
        for no_lo in THRESHOLDS:
            tr = _trades(cache, timing, no_lo)
            if len(tr) < 2:
                continue
            d = _describe(tr)
            sig = ""
            if abs(d["t"]) >= 2.0 and d["n"] >= 30:
                sig = "  <-- istotne (|t|>=2)"
            if d["t"] > 0 and d["n"] >= 30 and (best is None or d["t"] > best[1]):
                best = (f"{timing} NO>={no_lo:.2f}", d["t"], d)
            print(f"{timing + ' NO>=' + format(no_lo, '.2f'):22s} {d['n']:5d} {d['price']:6.3f} "
                  f"{d['wr']:7.2f}% {d['mean']:+7.2f}% {d['t']:+6.2f} "
                  f"[{d['lo']:+7.1f},{d['hi']:+7.1f}]% {d['pnl']:+8.2f}{sig}")

    print()
    if best:
        name, t, d = best
        print(f"NAJLEPSZY DODATNI: {name}  n={d['n']} EV={d['mean']:+.2f}% t={t:+.2f} "
              f"CI95=[{d['lo']:+.1f},{d['hi']:+.1f}]%")
    else:
        print("BRAK wariantu z dodatnim EV - strategia nie ma edge'a na tej probce")

    if args.tag:
        print()
        print("PER LIGA (wariant: pre NO>=0.50):")
        tags = sorted({t for m in cache for t in (m.get("source_tags") or [])})
        rows = []
        for tag in tags:
            sub = [m for m in cache if tag in (m.get("source_tags") or [])]
            tr = _trades(sub, "pre", 0.50)
            if len(tr) < 5:
                continue
            d = _describe(tr)
            rows.append((tag, d))
        for tag, d in sorted(rows, key=lambda x: -x[1]["mean"]):
            print(f"  {tag:12s} n={d['n']:4d} EV={d['mean']:+7.2f}% t={d['t']:+5.2f} "
                  f"CI95=[{d['lo']:+6.1f},{d['hi']:+6.1f}]% PnL={d['pnl']:+7.2f}")
        if len(rows) > 1:
            print(f"\n  uwaga: {len(rows)} lig testowanych rownolegle - przy |t|<2,5 to szum, "
                  f"nie edge (wielokrotne testowanie)")


if __name__ == "__main__":
    main()
