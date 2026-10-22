#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ws_arb.py - arbitraz liczony na kazdym ticku z WebSocketu (zamiast REST co 3 min).

Wymaga:  pip install websockets
Uruchomienie:
  python ws_arb.py --dry                  # tylko wykrywanie (domyslnie)
  python ws_arb.py --selftest             # test logiki bez sieci
  python ws_arb.py --live --stake 1       # kupno obu nog (market, min ~1 USD/noga)

Jak dziala:
 1) REST: pobiera eventy, buduje drabinki linii (Over/Under, handicapy) i pary
    (YES taniej linii + NO trudniejszej linii) -> kandydaci.
 2) WS: subskrybuje tokeny kandydatow, trzyma best ask kazdego tokenu.
 3) Po kazdym ticku przelicza sumy par; jesli 1-(ask_yes+ask_no)-fee >= prog -> [ARB].
"""
import argparse
import asyncio
import json
import sys

import mono  # reuse: collect(), ask(), fees


def pairs_from_events(tags, pages, min_edge, min_depth):
    """Buduje liste par (label, tok_yes, tok_no) oraz mape token -> indeksy par."""
    mono_c, multi_c, dup_c, events = mono.collect(tags, pages)
    pairs, index = [], {}
    for slug, lines, y, n in mono_c:
        idx = len(pairs)
        pairs.append({"label": f"{slug} {lines}", "y": y, "n": n})
        index.setdefault(y, []).append(idx)
        index.setdefault(n, []).append(idx)
    print(f"eventy: {events} | par MONO: {len(pairs)} | tokenow: {len(index)}")
    return pairs, index


def check_pair(p, asks, min_edge):
    ay = asks.get(p["y"], 0.0)
    an = asks.get(p["n"], 0.0)
    if ay <= 0 or an <= 0:
        return None
    edge = 1.0 - (ay + an)
    fee = 0.05 * (ay * (1 - ay) + an * (1 - an))
    net = edge - fee
    return net if net >= min_edge else None


def selftest():
    print("== SELFTEST (bez sieci) ==")
    p = {"label": "test over/under", "y": "tok_yes", "n": "tok_no"}
    cases = [({"tok_yes": 0.40, "tok_no": 0.55}, True),
             ({"tok_yes": 0.50, "tok_no": 0.50}, False),
             ({"tok_yes": 0.30, "tok_no": 0.60}, True),
             ({"tok_yes": 0.00, "tok_no": 0.60}, False)]
    for asks, expect in cases:
        net = check_pair(p, asks, 0.01)
        ok = (net is not None) == expect
        print(f"  ask_yes={asks['tok_yes']:.2f} ask_no={asks['tok_no']:.2f} "
              f"-> {'ARB netto ' + format(net * 100, '.1f') + '%' if net else 'brak'} "
              f"{'OK' if ok else 'BLAD'}")
    return 0


async def run_ws(tags, pages, min_edge, live, stake):
    try:
        import websockets
    except ImportError:
        print("brak modulu websockets. Zainstaluj: pip install websockets")
        return
    pairs, index = pairs_from_events(tags, pages, min_edge, 1)
    if not pairs:
        print("brak kandydatow")
        return
    ids = list(index.keys())[:2000]
    asks = {}
    hits = 0
    url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    async with websockets.connect(url, ping_interval=20, max_size=2 ** 23) as ws:
        await ws.send(json.dumps({"assets_ids": ids, "type": "market"}))
        print(f"subskrypcja: {len(ids)} tokenow")
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            items = msg if isinstance(msg, list) else [msg]
            touched = set()
            for it in items:
                et = it.get("event_type")
                if et == "book":
                    tok = it.get("asset_id")
                    asks_list = it.get("asks") or []
                    if tok and asks_list:
                        asks[tok] = min(float(a["price"]) for a in asks_list)
                        touched.add(tok)
                elif et == "price_change":
                    for ch in it.get("changes") or []:
                        tok = ch.get("asset_id")
                        if tok and ch.get("price"):
                            touched.add(tok)
                if not touched:
                    continue
            for tok in touched:
                for idx in index.get(tok, []):
                    p = pairs[idx]
                    net = check_pair(p, asks, min_edge)
                    if net:
                        hits += 1
                        print(f"[ARB] {p['label'][:50]} netto {net * 100:.1f}% "
                              f"(yes={asks.get(p['y']):.3f} no={asks.get(p['n']):.3f})")
                        if live:
                            await execute(p, asks, stake)


async def execute(p, asks, stake):
    """Kupno obu nog market orderem (min ~1 USD / noga)."""
    try:
        import bot_v2_dry_v3 as bot
    except ImportError:
        print("  brak bot_v2_dry_v3.py - nie moge wykonac")
        return
    broker = bot.LiveBroker()
    for tok, key in ((p["y"], "y"), (p["n"], "n")):
        try:
            r = broker.buy_no(tok, stake, asks[tok], bot.get_tick_size(tok), 0.0)
            print("  [LIVE]", str(r)[:140])
        except Exception as e:
            print("  [LIVE ERR]", repr(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default=mono.ALL_TAGS)
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--min-edge", type=float, default=0.01)
    ap.add_argument("--stake", type=float, default=1.0)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--dry", action="store_true", help="tylko wykrywanie (domyslne)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())
    asyncio.run(run_ws(args.tags, args.pages, args.min_edge, args.live, args.stake))


if __name__ == "__main__":
    main()
