#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
drift.py - test hipotezy "kup taniasko na nowym rynku i poczekaj, az plynnosc
podniesie cene".

Dla rynkow utworzonych w ciagu N dni bierze historie ceny YES i sprawdza:
  p0    - pierwsza cena w historii (czyli "wejscie na starcie")
  p1h, p6h, p24h - cena po 1/6/24 godzinach od p0
  pmax  - maksymalna cena po p0 (ile mozna bylo wyjac, gdyby ktos kupowal)

Potem grupuje po p0 i liczy: jak czesto pmax/p0 > 2, >5, >10 oraz mediane pmax.

Uzycie:
  python drift.py --days 14 --max-markets 40 --max-vol 1000
  python drift.py --days 30 --max-markets 80 --max-vol 100 --below 0.15
"""
import argparse
import json
import time
import urllib.parse
import urllib.request

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


def get(url, params=None, timeout=20):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "drift/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def hist(token, fidelity=60):
    try:
        d = get(f"{CLOB}/prices-history", {"market": token, "interval": "max",
                                           "fidelity": fidelity})
        return [(int(x["t"]), float(x["p"])) for x in d.get("history", [])]
    except Exception:
        return []


def at(series, ts):
    """Cena najblizsza ts (w tolerancji 2x fidelity)."""
    best, bd = None, 1e18
    for t, p in series:
        d = abs(t - ts)
        if d < bd:
            best, bd = p, d
    return best if bd <= 7200 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=14)
    ap.add_argument("--max-markets", type=int, default=40)
    ap.add_argument("--max-vol", type=float, default=1000.0)
    ap.add_argument("--below", type=float, default=0.25, help="analizuj tylko p0 <= tyle")
    ap.add_argument("--pages", type=int, default=6)
    ap.add_argument("--min-age-h", type=float, default=24.0,
                    help="rynek musi miec co najmniej tyle godzin historii")
    ap.add_argument("--min-vol", type=float, default=0.0)
    args = ap.parse_args()

    cutoff = time.time() - args.days * 86400
    rows, seen, cand = [], set(), []
    for pg in range(args.pages):
        part = get(f"{GAMMA}/markets", {"closed": "false", "active": "true", "limit": 100,
                                        "offset": pg * 100, "order": "volume",
                                        "ascending": "true"})
        for m in part or []:
            slug = m.get("slug")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            try:
                ts = time.mktime(time.strptime(str(m.get("createdAt"))[:19], "%Y-%m-%dT%H:%M:%S"))
            except Exception:
                continue
            if ts < cutoff:
                continue
            if float(m.get("volume") or 0) > args.max_vol:
                continue
            if float(m.get("volume") or 0) < args.min_vol:
                continue
            if (time.time() - ts) < args.min_age_h * 3600:
                continue
            try:
                toks = json.loads(m["clobTokenIds"])
                outs = json.loads(m["outcomes"])
            except Exception:
                continue
            if len(toks) != 2 or len(outs) != 2:
                continue
            cand.append((slug, float(m.get("volume") or 0), toks[0]))
            if len(cand) >= args.max_markets:
                break
        if len(cand) >= args.max_markets:
            break

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as pool:
        hists = list(pool.map(lambda c: hist(c[2], fidelity=10), cand))
    for (slug, vol, _tok), h in zip(cand, hists):
        if True:
            if len(h) < 5:
                continue
            p0, t0 = h[0][1], h[0][0]
            after = [(t, p) for t, p in h if t >= t0]
            pmax = max(p for _, p in after) if after else p0
            rows.append({"slug": slug, "vol": vol, "p0": p0,
                         "p1h": at(h, t0 + 3600), "p6h": at(h, t0 + 6 * 3600),
                         "p24h": at(h, t0 + 24 * 3600), "pmax": pmax,
                         "n": len(h), "span_h": (h[-1][0] - t0) / 3600.0})

    print(f"rynkow z historia: {len(rows)} | okno {args.days:.0f} dni | vol<={args.max_vol:.0f}")
    if not rows:
        print("brak danych - zwieksz --max-markets albo --max-vol")
        return
    sub = [r for r in rows if r["p0"] <= args.below]
    print(f"z tego p0 <= {args.below:.2f}: {len(sub)}\n")
    print(f"{'rynek':44s} {'vol$':>7s} {'p0':>5s} {'+1h':>5s} {'+6h':>5s} {'+24h':>6s} "
          f"{'max':>5s} {'max/p0':>7s}")
    for r in sorted(sub, key=lambda x: x["p0"])[:25]:
        ratio = (r["pmax"] / r["p0"]) if r["p0"] > 0 else 0
        f = lambda v: f"{v:.3f}" if v is not None else "  -  "
        print(f"{r['slug'][:44]:44s} {r['vol']:7.0f} {r['p0']:5.3f} {f(r['p1h'])} "
              f"{f(r['p6h'])} {f(r['p24h'])} {r['pmax']:5.3f} {ratio:7.1f}x")

    if sub:
        import statistics
        ratios = [(r["pmax"] / r["p0"]) if r["p0"] > 0 else 0 for r in sub]
        print(f"\npodsumowanie (p0 <= {args.below:.2f}, n={len(sub)}):")
        print(f"  mediana pmax/p0        : {statistics.median(ratios):.1f}x")
        for k in (2, 5, 10):
            print(f"  pmax/p0 >= {k:2d}x        : {sum(1 for x in ratios if x >= k) / len(sub) * 100:5.1f}%")
        over = [r for r in sub if r["p24h"] is not None]
        if over:
            print(f"  cena po 24h > p0       : "
                  f"{sum(1 for r in over if r['p24h'] > r['p0']) / len(over) * 100:5.1f}%"
                  f"  (n={len(over)})")


if __name__ == "__main__":
    main()
