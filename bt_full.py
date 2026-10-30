#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bt_full.py - pelny raport z bt_cache2.json.

Dla kazdej kombinacji (timing x side x przedzial ceny x grupa rynku) liczy:
  n, srednia cena, skutecznosc, breakeven, EDGE w pp, EV%, t, CI95, PnL,
  tempo (transakcje/dzien, transakcje/godzine), sredni czas wejscia od startu.

Timingi:
  pre       - 0..PRE_GAME_WINDOW_H przed startem
  live45    - pierwsze LIVE_ENTRY_MAX_MIN minut meczu (bez look-ahead)
  live_full - 0..LIVE_WINDOW_H po starcie (tylko do porownania, NIE handlowac)

Uzycie:
  python bt_full.py                  # tabele + bt_full_out.csv
  python bt_full.py --min-n 20 --top 40
"""
import argparse
import csv
import math
import statistics
import sys

try:
    import bot_v2_dry_v3 as bot
except ImportError:
    sys.exit("brak bot_v2_dry_v3.py w tym katalogu")

BINS = [(0.02, 0.05), (0.05, 0.10), (0.10, 0.15), (0.15, 0.20), (0.20, 0.25),
        (0.25, 0.30), (0.30, 0.35), (0.35, 0.40), (0.40, 0.45), (0.45, 0.50),
        (0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 0.75),
        (0.75, 0.80), (0.80, 0.85), (0.85, 0.90), (0.90, 0.95), (0.95, 0.98)]
TIMINGS = ("pre", "live45", "live_full")
GROUPS = ("spread", "totals", "moneyline", "other")


def time_ok(gs, t, timing):
    if timing == "pre":
        return 0 < gs - t <= bot.PRE_GAME_WINDOW_H * 3600.0
    if timing == "live45":
        return 0 <= t - gs <= bot.LIVE_ENTRY_MAX_MIN * 60.0
    if timing == "live_full":
        return 0 <= t - gs <= bot.LIVE_WINDOW_H * 3600.0
    return False


def sim(m, side, lo, hi, timing):
    """Pierwsze wejscie spelniajace warunki. Zwraca dict albo None."""
    gs = bot._ts(m.get("game_start"))
    f = m.get("final_yes")
    if gs is None or f is None or 0.01 < f < 0.99:
        return None
    fee = bot.fee_for_tag(",".join(m.get("source_tags") or ["sports"]))
    for t, p in m["history"]:
        if not time_ok(gs, t, timing):
            continue
        price = p if side == "yes" else 1.0 - p
        if not (lo <= price <= hi):
            continue
        if not bot._same_day_ok(m, ref_ts=t, gs=gs):
            continue
        cost = price + bot.taker_fee(1.0, price, fee) + bot.ASSUMED_SPREAD / 2.0
        if cost <= 0 or cost >= 1:
            continue
        won = (f >= 0.99) if side == "yes" else (f <= 0.01)
        return {"price": price, "cost": cost, "won": won, "entry_t": t, "gs": gs,
                "offset_min": (t - gs) / 60.0,
                "pnl_pct": ((1.0 if won else 0.0) - cost) / cost * 100.0}
    return None


def stats(rows, days, hours_live):
    n = len(rows)
    if not n:
        return None
    pnl = [r["pnl_pct"] for r in rows]
    mean = statistics.mean(pnl)
    sd = statistics.stdev(pnl) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n else 0.0
    cost = statistics.mean(r["cost"] for r in rows)
    wr = sum(1 for r in rows if r["won"]) / n
    return {
        "n": n, "price": statistics.mean(r["price"] for r in rows), "cost": cost,
        "wr": wr * 100.0, "be": cost * 100.0, "edge_pp": (wr - cost) * 100.0,
        "ev": mean, "t": (mean / se) if se > 1e-9 else 0.0,
        "ci_lo": mean - 1.96 * se, "ci_hi": mean + 1.96 * se,
        "per_day": n / days if days else 0.0,
        "per_hour": n / hours_live if hours_live else 0.0,
        "offset": statistics.mean(r["offset_min"] for r in rows),
        "pnl_usd": mean / 100.0 * n,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-n", type=int, default=15)
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--out", default="bt_full_out.csv")
    ap.add_argument("--min-vol", type=float, default=None)
    ap.add_argument("--bin-width", type=float, default=None,
                    help="szerokosc przedzialu ceny (np. 0.10); domyslnie siatka 0.05")
    ap.add_argument("--spread", type=float, default=None, help="nadpisz ASSUMED_SPREAD (np. 0.05)")
    ap.add_argument("--per-event", action="store_true",
                    help="max 1 wejscie na mecz (linie spreadu/totals sa skorelowane)")
    args = ap.parse_args()

    if args.min_vol is not None:
        bot.BT_MIN_VOL = args.min_vol
    if args.spread is not None:
        bot.ASSUMED_SPREAD = float(args.spread)
    bins = BINS
    if args.bin_width:
        w = float(args.bin_width)
        edges = [0.02]
        while edges[-1] + w < 0.98:
            edges.append(round(edges[-1] + w, 4))
        edges.append(0.98)
        bins = [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]

    cache = bot._load(bot.BT_CACHE, None)
    if not cache:
        sys.exit(f"brak {bot.BT_CACHE} - najpierw: python bot_v2_dry_v3.py --fetch-history --days 30")
    cache = [m for m in cache if float(m.get("volume") or 0.0) >= bot.BT_MIN_VOL]
    starts = [bot._ts(m.get("game_start")) for m in cache if bot._ts(m.get("game_start"))]
    days = (max(starts) - min(starts)) / 86400.0 if starts else 0.0
    hours = days * 24.0
    print(f"cache: {len(cache)} rynkow | okres: {days:.1f} dni | vol>={bot.BT_MIN_VOL:.0f} | "
          f"spread={bot.ASSUMED_SPREAD:.3f} | live45={bot.LIVE_ENTRY_MAX_MIN} min | "
          f"pre<={bot.PRE_GAME_WINDOW_H}h")
    print()

    rows = []
    for timing in TIMINGS:
        for side in ("yes", "no"):
            for lo, hi in bins:
                base = [(m, sim(m, side, lo, hi, timing)) for m in cache]
                hits = [(m, r) for m, r in base if r]
                if args.per_event:
                    seen, dedup = set(), []
                    for m, r in hits:
                        key = m.get("event") or m.get("slug")
                        if key in seen:
                            continue
                        seen.add(key)
                        dedup.append((m, r))
                    hits = dedup
                st = stats([r for _, r in hits], days, hours)
                if st:
                    rows.append(dict(timing=timing, side=side, lo=lo, hi=hi, group="ALL",
                                     label=f"{timing} {side.upper()} {lo:.2f}-{hi:.2f}", **st))
                for g in GROUPS:
                    sub = [(m, sim(m, side, lo, hi, timing)) for m in cache
                           if (m.get("group") or "other") == g]
                    gh = [(m, r) for m, r in sub if r]
                    if args.per_event:
                        seen2, dd = set(), []
                        for m, r in gh:
                            key = m.get("event") or m.get("slug")
                            if key in seen2:
                                continue
                            seen2.add(key)
                            dd.append((m, r))
                        gh = dd
                    st2 = stats([r for _, r in gh], days, hours)
                    if st2:
                        rows.append(dict(timing=timing, side=side, lo=lo, hi=hi, group=g,
                                         label=f"{timing} {side.upper()} {lo:.2f}-{hi:.2f} [{g}]",
                                         **st2))

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"zapisano {len(rows)} wierszy do {args.out}")
    print()

    def show(title, rr):
        print(f"== {title} ==")
        print(f"{'regula':36s} {'n':>4s} {'cena':>5s} {'skut':>6s} {'be':>5s} {'edge':>6s} "
              f"{'EV':>8s} {'t':>6s} {'CI95':>15s} {'/dzien':>6s} {'/godz':>6s} {'PnL$':>7s}")
        if not rr:
            print("  (brak wierszy spelniajacych prog - zwieksz cache albo zmniejsz --min-n)")
        for r in rr:
            print(f"{r['label'][:36]:36s} {r['n']:4d} {r['price']:5.2f} {r['wr']:5.1f}% "
                  f"{r['be']:5.1f} {r['edge_pp']:+6.1f} {r['ev']:+7.1f}% {r['t']:+6.2f} "
                  f"[{r['ci_lo']:+6.1f},{r['ci_hi']:+5.1f}] {r['per_day']:6.2f} {r['per_hour']:6.2f} "
                  f"{r['pnl_usd']:+7.2f}")
        print()

    ok = [r for r in rows if r["n"] >= args.min_n]
    show(f"NAJLEPSZY EDGE (n>={args.min_n})",
         sorted(ok, key=lambda r: -(r["edge_pp"] * math.log(max(r["n"], 2))))[:args.top])
    show(f"NAJLEPSZE EV (n>={args.min_n})", sorted(ok, key=lambda r: -r["ev"])[:args.top])
    sig = [r for r in ok if r["t"] >= 2.0 and r["ev"] > 0]
    show(f"ISTOTNE t>=2 i EV>0 (n>={args.min_n})",
         sorted(sig, key=lambda r: -r["t"])[:args.top])
    print(f"testowanych kombinacji: {len(rows)} | przy t>=2 ok. {0.025 * len(rows):.0f} "
          f"trafien czysto przypadkiem")


if __name__ == "__main__":
    main()
