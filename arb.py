#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
arb.py - tylko realny arbitraz: ask_YES + ask_NO < 1.

Logika: kupujesz N akcji YES po ya i N akcji NO po na. Wyplata = N (jedna strona
zawsze placi 1). Koszt = N*(ya+na). Zysk = N*(1-ya-na), bez ryzyka wyniku.

Wazne: kupujesz ROWNA LICZBE AKCJI, nie rowne kwoty (inaczej to nie arbitraz).

Uzycie:
  python arb.py                        # skan, nic nie kupuje
  python arb.py --min-edge 0.03 -v
  python arb.py --live --stake 2       # kupuje obie strony (wymaga kluczy)
"""
import argparse
import json
import os
import sys
import time
import http.client
import urllib.parse

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
_CONN = {}


def _get(url, params=None, timeout=8):
    parts = urllib.parse.urlsplit(url)
    path = parts.path + (("?" + parts.query) if parts.query else "")
    if params:
        path += ("&" if "?" in path else "?") + urllib.parse.urlencode(params)
    host = parts.netloc
    conn = _CONN.get(host) or http.client.HTTPSConnection(host, timeout=timeout)
    _CONN[host] = conn
    try:
        conn.request("GET", path, headers={"User-Agent": "arb/1.0", "Connection": "keep-alive"})
        r = conn.getresponse()
        body = r.read()
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        return json.loads(body)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        _CONN.pop(host, None)
        raise


def side(token, which):
    """(cena, rozmiar) najlepszego poziomu. which='ask' lub 'bid'."""
    try:
        b = _get(f"{CLOB}/book", {"token_id": token})
    except Exception:
        return 0.0, 0.0
    lv = b.get("asks" if which == "ask" else "bids") or []
    if not lv:
        return 0.0, 0.0
    best = min(float(x["price"]) for x in lv) if which == "ask" \
        else max(float(x["price"]) for x in lv)
    size = sum(float(x["size"]) for x in lv if abs(float(x["price"]) - best) < 1e-9)
    return best, size


def scan(max_vol, pages, min_vol=0.0):
    out, seen = [], set()
    now = time.time()
    for pg in range(pages):
        part = _get(f"{GAMMA}/markets", {"closed": "false", "active": "true", "limit": 100,
                                         "offset": pg * 100, "order": "volume", "ascending": "true"})
        for m in part or []:
            slug = m.get("slug")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            vol = float(m.get("volume") or 0.0)
            if vol > max_vol or vol < min_vol:
                continue
            try:
                ets = time.mktime(time.strptime(str(m.get("endDate"))[:19], "%Y-%m-%dT%H:%M:%S"))
            except Exception:
                continue
            if ets < now:
                continue
            try:
                toks = json.loads(m["clobTokenIds"])
                outs = json.loads(m["outcomes"])
            except Exception:
                continue
            if len(toks) != 2 or len(outs) != 2:
                continue
            out.append({"slug": slug, "vol": vol, "toks": toks, "outs": outs})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-vol", type=float, default=5000.0)
    ap.add_argument("--min-vol", type=float, default=0.0)
    ap.add_argument("--pages", type=int, default=4)
    ap.add_argument("--min-edge", type=float, default=0.01)
    ap.add_argument("--stake", type=float, default=1.0, help="USD na cala pare (obie strony)")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    mk = scan(args.max_vol, args.pages, args.min_vol)
    print(f"== ARB SCAN == rynkow w oknie: {len(mk)} | prog edge {args.min_edge:.2f} "
          f"| {'LIVE' if args.live else 'DRY'}")

    broker = None
    if args.live:
        import bot_v2_dry_v3 as bot
        broker = bot.LiveBroker()

    found = 0
    for m in mk:
        ya, yd = side(m["toks"][0], "ask")
        na, nd = side(m["toks"][1], "ask")
        if ya <= 0 or na <= 0:
            continue
        edge = 1.0 - (ya + na)
        if args.verbose and edge > -0.05:
            print(f"  {m['slug'][:46]:46s} vol={m['vol']:8.0f} YES={ya:.3f} NO={na:.3f} "
                  f"suma={ya+na:.3f} edge={edge:+.3f}")
        if edge < args.min_edge:
            continue
        n = min(yd, nd)                       # ile akcji da sie kupic po obu cenach
        n = min(n, args.stake / (ya + na))
        if n < 1:
            continue
        found += 1
        zysk = n * edge
        print(f"\n[ARB] {m['slug'][:48]} edge={edge:+.3f} | {n:.1f} akcji | "
              f"koszt ${n * (ya + na):.2f} -> wyplata ${n:.2f} | zysk ${zysk:.2f}")
        if args.live and broker:
            for tok, price in ((m["toks"][0], ya), (m["toks"][1], na)):
                try:
                    import bot_v2_dry_v3 as bot
                    r = broker.buy_no(tok, n * price, price, bot.get_tick_size(tok), 0.0)
                    print("   [LIVE]", str(r)[:150])
                except Exception as e:
                    print("   [LIVE ERR]", repr(e))
    print(f"\nznalezione arbitraze: {found}")
    if not found:
        print("brak arbitrazu (suma askow > 1) - to normalne, okazje sa rzadkie")


if __name__ == "__main__":
    main()
