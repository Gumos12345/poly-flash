#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
arb_updown.py - arbitraz na rynkach "up or down" (metoda bota $313 -> $2.38M).

IDEA (punkty 2 i 3 z analizy):
  W oknie 5m ceny Up+Down powinny sumowac sie do ~1.00.
  Gdy Bitcoin ruszy, Polymarket czesto NIE nadaza: jedna strona tania,
  druga juz droga -> suma < 1.00. Kupujesz OBIE, jedna zawsze placi $1.
  Zysk = 1.00 - (ask_up + ask_down) - fee.

Uzycie:
  python arb_updown.py
  python arb_updown.py --min-edge 0.03
  python arb_updown.py --live            # env POLY_*
"""
import argparse
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict

BITGET = "https://api.bitget.com"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
ASSETS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "HYPE", "ZEC"]
LOG = "arb_updown.log"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get(url, params=None, timeout=10):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "arb-updown/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def prices():
    want = {f"{a}USDT": a for a in ASSETS}
    d = get(f"{BITGET}/api/v2/spot/market/tickers")
    out = {}
    for row in d.get("data") or []:
        if row.get("symbol") in want:
            try:
                out[want[row["symbol"]]] = float(row["lastPr"])
            except (KeyError, ValueError):
                pass
    return out


def markets():
    now, out = time.time(), {}
    rows = []
    for off in (0, 100, 200, 300):
        d = get(f"{GAMMA}/markets", {"closed": "false", "limit": 100, "offset": off,
                                     "order": "createdAt", "ascending": "false"})
        if not d:
            break
        rows += d
    for m in rows:
        slug = m.get("slug") or ""
        for a in ASSETS:
            if f"{a.lower()}-updown-5m-" not in slug:
                continue
            try:
                toks = json.loads(m["clobTokenIds"])
                outs = json.loads(m["outcomes"])
                ets = float(slug.rsplit("-", 1)[1])
            except Exception:
                continue
            if len(toks) != 2 or len(outs) != 2 or ets < now:
                continue
            tmap = {str(outs[i]).strip().lower(): str(toks[i]) for i in range(2)}
            if "up" not in tmap or "down" not in tmap:
                continue
            prev = out.get(a)
            if prev is None or ets < prev["end"]:
                out[a] = {"slug": slug, "up": tmap["up"], "down": tmap["down"],
                          "end": ets, "asset": a}
    return out


def ask(token):
    """ASK = cena kupna; CLOB ma ODWROCONA semantyke -> side=sell."""
    try:
        return float(get(f"{CLOB}/price", {"token_id": token, "side": "sell"}).get("price") or 0)
    except Exception:
        return 0.0


def fee(p, rate=0.07):
    return rate * p * (1.0 - p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--min-edge", type=float, default=0.02)
    ap.add_argument("--shares", type=float, default=5, help="akcji na noge")
    ap.add_argument("--poll", type=float, default=2.0)
    args = ap.parse_args()

    broker = bot = None
    if args.live:
        import bot_v2_dry_v3 as bot
        broker = bot.LiveBroker()
        log("[LIVE] prawdziwe zlecenia")

    hist = defaultdict(list)
    best = defaultdict(lambda: 9.9)
    hits = defaultdict(int)
    scanned = 0
    log(f"START szukam sumy (ask_up+ask_down+fee) < {1 - args.min_edge:.3f} | {len(ASSETS)} aktywow")

    while True:
        try:
            now = time.time()
            px = prices()
            mk = markets()
            scanned += 1
            for a, p in px.items():
                hist[a].append((now, p))
                while hist[a] and now - hist[a][0][0] > 60:
                    hist[a].pop(0)

            for a, m in mk.items():
                ua, da = ask(m["up"]), ask(m["down"])
                if ua <= 0 or da <= 0:
                    continue
                total = ua + da
                cost = total + fee(ua) + fee(da)
                edge = 1.0 - cost
                if total < best[a]:
                    best[a] = total
                if edge >= args.min_edge:
                    hits[a] += 1
                    move = 0.0
                    if hist[a]:
                        move = (px.get(a, 0) - hist[a][0][1]) / hist[a][0][1] * 100
                    log(f"ARB {a}: up={ua:.3f} down={da:.3f} suma={total:.3f} "
                        f"koszt={cost:.3f} ZYSK={edge * 100:+.1f}% | ruch {move:+.2f}% | "
                        f"zostalo {m['end'] - now:.0f}s")
                    if args.live and broker:
                        for tok, pr in ((m["up"], ua), (m["down"], da)):
                            try:
                                r = broker.buy_no(tok, args.shares * pr, pr,
                                                  bot.get_tick_size(tok), fee(pr))
                                log(f"   [LIVE] {str(r)[:90]}")
                            except Exception as e:
                                log(f"   [LIVE ERR] {e!r}")

            if scanned % 30 == 0:
                line = " ".join(f"{a}:{best[a]:.3f}" for a in sorted(best))
                log(f"skan #{scanned} | min sumy: {line}")
        except KeyboardInterrupt:
            log("[STOP] Ctrl+C")
            break
        except Exception as e:
            log(f"[ERR] {e!r}")
        time.sleep(args.poll)


if __name__ == "__main__":
    main()