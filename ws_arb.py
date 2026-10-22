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
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]   # KLUCZOWE: lista, nie string
    print(f"tagi: {len(tag_list)}")
    mono_c, multi_c, dup_c, events = mono.collect(tag_list, pages)
    pairs, index = [], {}
    for slug, lines, y, n in mono_c:
        idx = len(pairs)
        pairs.append({"label": f"{slug} {lines}", "y": y, "n": n})
        index.setdefault(y, []).append(idx)
        index.setdefault(n, []).append(idx)
    print(f"eventy: {events} | par MONO: {len(pairs)} | tokenow: {len(index)}")
    return pairs, index


def sizing(ya, na, bankroll, dy=None, dn=None):
    """Ile akcji kupic: min. 1 USD/noga, max bankroll ORAZ glebokosc ksiag."""
    if ya <= 0 or na <= 0:
        return None
    n_min = max(1.0 / ya, 1.0 / na)      # minimum 1 USD na noge
    n_max = bankroll / (ya + na)
    if dy:
        n_max = min(n_max, dy)
    if dn:
        n_max = min(n_max, dn)
    if n_max < n_min:
        return None
    n = n_max
    cost = n * (ya + na)
    fee = n * 0.05 * (ya * (1 - ya) + na * (1 - na))
    return {"n": n, "cost": cost, "payout": n, "profit": n - cost - fee}


def check_pair(p, asks, min_edge):
    qy = asks.get(p["y"], (0.0, 0.0))
    qn = asks.get(p["n"], (0.0, 0.0))
    ay = qy[0] if isinstance(qy, (tuple, list)) else qy
    an = qn[0] if isinstance(qn, (tuple, list)) else qn
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


async def run_ws(tags, pages, min_edge, live, stake, bankroll, min_depth=1.0):
    try:
        import websockets
    except ImportError:
        print("brak modulu websockets. Zainstaluj: pip install websockets")
        return
    pairs, index = pairs_from_events(tags, pages, min_edge, min_depth)
    if not pairs:
        print("brak kandydatow")
        return
    ids = list(index.keys())
    asks = {}
    hits = 0
    url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    async with websockets.connect(url, ping_interval=20, max_size=2 ** 23) as ws:
        for i in range(0, len(ids), 400):
            chunk = ids[i:i + 400]
            await ws.send(json.dumps({"assets_ids": chunk, "type": "market"}))
            await asyncio.sleep(0.2)
        print(f"subskrypcja: {len(ids)} tokenow w {max(1, (len(ids) + 399) // 400)} paczkach")
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
                        lv = [(float(a["price"]), float(a.get("size") or 0)) for a in asks_list]
                        best = min(p for p, _ in lv)
                        size = sum(sz for p, sz in lv if abs(p - best) < 1e-9)
                        asks[tok] = (best, size)
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
                        qy, qn = asks.get(p['y']), asks.get(p['n'])
                        ya, na = qy[0], qn[0]
                        sz = sizing(ya, na, bankroll, qy[1], qn[1])
                        info = (f"| N={sz['n']:.2f} akcji (depth {qy[1]:.0f}/{qn[1]:.0f}), "
                                f"koszt ${sz['cost']:.2f}, zysk ${sz['profit']:.2f}") if sz                             else "| za drogo / za mala glebokosc"
                        print(f"[ARB] {p['label'][:44]} netto {net * 100:.1f}% "
                              f"(yes={ya:.3f} no={na:.3f}) {info}")
                        if live and sz:
                            await execute(p, ya, na, sz)


async def execute(p, ya, na, sz):
    """Kupno obu nog w ROWNEJ liczbie akcji (market order, min ~1 USD/noga)."""
    try:
        import bot_v2_dry_v3 as bot
    except ImportError:
        print("  brak bot_v2_dry_v3.py - nie moge wykonac")
        return
    broker = bot.LiveBroker()
    n = sz["n"]
    for tok, price in ((p["y"], ya), (p["n"], na)):
        usd = round(n * price, 2)
        try:
            r = broker.buy_no(tok, usd, price, bot.get_tick_size(tok), 0.0)
            print("  [LIVE]", str(r)[:140])
        except Exception as e:
            print("  [LIVE ERR]", repr(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default=mono.ALL_TAGS)
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--min-edge", type=float, default=0.01)
    ap.add_argument("--stake", type=float, default=1.0)
    ap.add_argument("--bankroll", type=float, default=4.17)
    ap.add_argument("--min-depth", type=float, default=1.0,
                    help="min. liczba akcji po asku (5 = odsiewa pyl)")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--dry", action="store_true", help="tylko wykrywanie (domyslne)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())
    asyncio.run(run_ws(args.tags, args.pages, args.min_edge, args.live, args.stake,
                       args.bankroll, args.min_depth))


if __name__ == "__main__":
    main()
