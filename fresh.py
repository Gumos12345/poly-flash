#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fresh.py - skaner swiezych, cienkich rynkow (to jedyne miejsce, gdzie maly kapital
moze miec realna przewage: arbitraz i brakujaca plynnosc, a nie "loteria po 0.001").

Co liczy dla kazdego rynku:
  yes_ask, no_ask  -> suma. Jesli suma < 1.0, kupno OBU stron daje gwarantowana wyplate 1.0
  (zysk = 1 - suma), o ile w ksiedze jest wystarczajaco sztuk po tych cenach.
  depth_yes / depth_no - ile sztuk jest po najlepszym asku (realna egzekucja, nie marzenie).

Uzycie:
  python fresh.py                       # rynki z ostatnich 48 h, wolumen < 2000 USD
  python fresh.py --hours 24 --max-vol 500
  python fresh.py --min-edge 0.02       # pokaz tylko sume ask <= 0.98
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
UA = {"User-Agent": "fresh-scan/1.0"}


def _get(url, params=None, timeout=20):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def book_side(token, side):
    """(best_price, size) dla strony ksiedza. side='sell' -> ask, 'buy' -> bid."""
    try:
        p = float(_get(f"{CLOB}/price", {"token_id": token, "side": side})["price"])
    except Exception:
        return 0.0, 0.0
    try:
        b = _get(f"{CLOB}/book", {"token_id": token})
        levels = b.get("asks" if side == "sell" else "bids") or []
        if not levels:
            return p, 0.0
        best = min(float(x["price"]) for x in levels) if side == "sell" \
            else max(float(x["price"]) for x in levels)
        size = sum(float(x["size"]) for x in levels if abs(float(x["price"]) - best) < 1e-9)
        return p, size
    except Exception:
        return p, 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=48.0)
    ap.add_argument("--max-vol", type=float, default=2000.0)
    ap.add_argument("--min-edge", type=float, default=0.0, help="1 - suma ask >= ta wartosc")
    ap.add_argument("--pages", type=int, default=6)
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--max-markets", type=int, default=40, help="ile rynkow sprawdzic w ksiedze")
    args = ap.parse_args()

    cutoff = time.time() - args.hours * 3600.0
    print(f"== FRESH SCAN == rynki utworzone w ciagu {args.hours:.0f} h, "
          f"wolumen < {args.max_vol:.0f} USD")
    rows, seen, cand = [], set(), []
    for page in range(args.pages):
        try:
            data = _get(f"{GAMMA}/markets", {"closed": "false", "active": "true",
                                             "limit": 100, "offset": page * 100,
                                             "order": "createdAt", "ascending": "false"})
        except Exception as e:
            print(f"  [gamma] {e!r}")
            break
        if not data:
            break
        for m in data:
            slug = m.get("slug")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            created = m.get("createdAt") or m.get("creationDate")
            try:
                ts = time.mktime(time.strptime(str(created)[:19], "%Y-%m-%dT%H:%M:%S"))
            except Exception:
                continue
            if ts < cutoff:
                continue
            vol = float(m.get("volume") or 0.0)
            if vol > args.max_vol:
                continue
            try:
                toks = json.loads(m["clobTokenIds"])
                outs = json.loads(m["outcomes"])
            except Exception:
                continue
            if len(toks) != 2 or len(outs) != 2:
                continue
            cand.append((slug, ts, vol, toks, outs))
            if len(cand) >= args.max_markets:
                break
        if len(cand) >= args.max_markets:
            break

    from concurrent.futures import ThreadPoolExecutor

    def _check(c):
        slug, ts, vol, toks, outs = c
        ya, yd = book_side(toks[0], "sell")
        na, nd = book_side(toks[1], "sell")
        if ya <= 0 or na <= 0:
            return None
        return {"slug": slug[:52], "age_h": (time.time() - ts) / 3600.0, "vol": vol,
                "ya": ya, "na": na, "sum": ya + na, "edge": 1.0 - (ya + na),
                "yd": yd, "nd": nd, "min_depth": min(yd, nd)}

    with ThreadPoolExecutor(8) as pool:
        for r in pool.map(_check, cand):
            if r:
                rows.append(r)
    rows.sort(key=lambda r: -r["edge"])
    print(f"rynkow w oknie: {len(rows)}\n")
    print(f"{'rynek':52s} {'wiek':>5s} {'vol$':>7s} {'YES ask':>8s} {'NO ask':>7s} "
          f"{'suma':>6s} {'edge':>6s} {'szt':>6s}")
    shown = 0
    for r in rows:
        if r["edge"] < args.min_edge:
            continue
        print(f"{r['slug']:52s} {r['age_h']:5.1f} {r['vol']:7.1f} {r['ya']:8.3f} {r['na']:7.3f} "
              f"{r['sum']:6.3f} {r['edge']:+6.3f} {r['min_depth']:6.1f}")
        shown += 1
        if shown >= args.limit:
            break
    if not shown:
        print("  (brak rynkow spelniajacych prog - arbitrazu nie ma, i to jest normalne)")
    print("\nUWAGA: edge > 0 to JEDYNA realna przewaga przy malym kapitale (kupno obu stron).")
    print("       Cena 0.001 bez glebokosci = pulapka: nie sprzedasz, a wygrana ~0.1%.")


if __name__ == "__main__":
    main()
