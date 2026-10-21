#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sniper.py - lowi "zlote strzaly" na swiezych rynkach.

Zjawisko: nowy rynek startuje z jednostronna ksiazka (tylko ask po 0.02-0.10,
zero bidow). Jesli rynek jest symetryczny (2 wyniki, brak informacji), fair ~0.50,
wiec kupno po 0.04 jest darmowe - o ile sekunde pozniej pojawi sie bid, w ktory
mozna sprzedac.

Tryb domyslny = DRY: nic nie kupuje, tylko mierzy:
  * ile jest takich rynkow, jak stare, jaki ask, jaka glebokosc,
  * jaki najlepszy bid pojawil sie w --track sekund (czy bylaby szansa wyjsc z zyskiem).

Uzycie:
  python sniper.py                       # 1 min nasluchu, 20 s sledzenia
  python sniper.py --minutes 5 --track 30
  python sniper.py --live --stake 1.0    # prawdziwe zlecenia (klucze w env)
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
UA = {"User-Agent": "sniper/1.0"}


import http.client

_CONN = {}


def _get(url, params=None, timeout=5):
    """GET z podtrzymanym polaczeniem TLS (keep-alive) - mniejsze opoznienie niz urllib."""
    parts = urllib.parse.urlsplit(url)
    path = parts.path + (("?" + parts.query) if parts.query else "")
    if params:
        path += ("&" if "?" in path else "?") + urllib.parse.urlencode(params)
    host = parts.netloc
    conn = _CONN.get(host)
    if conn is None:
        conn = http.client.HTTPSConnection(host, timeout=timeout)
        _CONN[host] = conn
    try:
        conn.request("GET", path, headers={"User-Agent": UA["User-Agent"],
                                             "Connection": "keep-alive"})
        resp = conn.getresponse()
        body = resp.read()
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        return json.loads(body)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        _CONN.pop(host, None)
        raise


def book(token):
    """(best_bid, bid_size, best_ask, ask_size) lub None."""
    try:
        b = _get(f"{CLOB}/book", {"token_id": token})
    except Exception:
        return None
    bids = b.get("bids") or []
    asks = b.get("asks") or []
    bb = max((float(x["price"]) for x in bids), default=0.0)
    ba = min((float(x["price"]) for x in asks), default=0.0)
    bsz = sum(float(x["size"]) for x in bids if abs(float(x["price"]) - bb) < 1e-9)
    asz = sum(float(x["size"]) for x in asks if abs(float(x["price"]) - ba) < 1e-9)
    return bb, bsz, ba, asz


def fresh_markets(max_age_s, limit=100):
    data = _get(f"{GAMMA}/markets", {"closed": "false", "active": "true", "limit": limit,
                                     "order": "createdAt", "ascending": "false"})
    now = time.time()
    out = []
    for m in data or []:
        created = m.get("createdAt") or m.get("creationDate")
        try:
            ts = time.mktime(time.strptime(str(created)[:19], "%Y-%m-%dT%H:%M:%S"))
        except Exception:
            continue
        age = now - ts
        if age > max_age_s:
            continue
        try:
            toks = json.loads(m["clobTokenIds"])
            outs = json.loads(m["outcomes"])
        except Exception:
            continue
        if len(toks) != 2 or len(outs) != 2:
            continue
        out.append({"slug": m.get("slug"), "age": age, "vol": float(m.get("volume") or 0),
                    "toks": toks, "outs": outs})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=1.0, help="jak dlugo nasluchiwac")
    ap.add_argument("--max-age", type=float, default=180, help="maks. wiek rynku (s)")
    ap.add_argument("--max-ask", type=float, default=0.15, help="kupuj tylko ponizej tej ceny")
    ap.add_argument("--min-depth", type=float, default=1.0, help="min. sztuk po asku")
    ap.add_argument("--track", type=float, default=20.0, help="ile sekund sledzic bid")
    ap.add_argument("--poll", type=float, default=2.0, help="co ile sekund skanowac")
    ap.add_argument("--max-check", type=int, default=15, help="ile nowych rynkow sprawdzac na obrot")
    ap.add_argument("--fast", action="store_true", help="minimalne opoznienie: poll 0.25s, mniej rynkow")
    ap.add_argument("--stake", type=float, default=1.0)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--out", default="sniper_log.jsonl")
    args = ap.parse_args()
    if args.fast:
        args.poll = 0.25
        args.max_check = 6
        args.max_age = min(args.max_age, 120)

    print(f"== SNIPER {'LIVE' if args.live else 'DRY'} == max_age={args.max_age:.0f}s "
          f"max_ask={args.max_ask:.2f} stake={args.stake:.2f} track={args.track:.0f}s")
    broker = None
    if args.live:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import bot_v2_dry_v3 as bot
        broker = bot.LiveBroker()
    seen, hits = set(), 0
    end = time.time() + args.minutes * 60.0
    while time.time() < end:
        try:
            mk = fresh_markets(args.max_age)
        except Exception as e:
            print(f"  [gamma] {e!r}")
            mk = []
        mk = [m for m in mk if m["slug"] not in seen][:args.max_check]
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(6) as pool:
            books = list(pool.map(lambda mm: (book(mm["toks"][0]), book(mm["toks"][1])), mk))
        for m, (b0, b1) in zip(mk, books):
            if m["slug"] in seen:
                continue
            seen.add(m["slug"])
            if not b0 or not b1:
                continue
            for tok, (bb, bs, ba, asz), other_bid in ((m["toks"][0], b0, b1[0]),
                                                      (m["toks"][1], b1, b0[0])):
                if ba <= 0 or ba > args.max_ask or asz < args.min_depth:
                    continue
                if bb > 0.02 or other_bid > 0.02:
                    continue          # ktoras strona juz wyceniona -> to nie "goly" rynek
                hits += 1
                t0 = time.time()
                print(f"\n[STRZAL] {m['slug'][:52]} wiek={m['age']:.1f}s ask={ba:.3f} "
                      f"glebokosc={asz:.1f} szt")
                if args.live and broker:
                    try:
                        import bot_v2_dry_v3 as bot
                        res = broker.buy_no(tok, args.stake, ba, bot.get_tick_size(tok), 0.0)
                        print("   [LIVE]", res)
                    except Exception as e:
                        print("   [LIVE ERR]", repr(e))
                best = 0.0
                while time.time() - t0 < args.track:
                    time.sleep(2.0)
                    nb = book(tok)
                    if nb and nb[0] > best:
                        best = nb[0]
                        if best >= 0.2:
                            break
                pnl_pct = (best - ba) / ba * 100.0 if ba > 0 else 0.0
                rec = {"slug": m["slug"], "age_s": round(m["age"], 1), "ask": ba,
                       "depth": asz, "best_bid_seen": best,
                       "secs": round(time.time() - t0, 1),
                       "pnl_pct_if_sold": round(pnl_pct, 1)}
                with open(args.out, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec) + "\n")
                print(f"   najlepszy bid po {rec['secs']:.0f}s: {best:.3f} -> {pnl_pct:+.0f}% "
                      f"(papier, przed oplatami)")
        time.sleep(args.poll)
    print(f"\nkoniec: sprawdzone rynki={len(seen)} strzaly={hits} -> {args.out}")
    if not hits:
        print("brak strzalow: albo nie ma golych rynkow, albo Twoje opoznienie jest za duze")


if __name__ == "__main__":
    main()
