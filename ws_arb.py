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


def pairs_from_events(tags, pages, min_edge, min_depth, max_sum=0.95, fetch_mo=False):
    """Pary MONO + DUP. max_sum = gorny limit sumy cen (budzet / min. akcji)."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]   # KLUCZOWE: lista, nie string
    print(f"tagi: {len(tag_list)}")
    mono_c, multi_c, dup_c, events = mono.collect(tag_list, pages)
    pairs, index = [], {}
    for slug, lines, y, n in mono_c:
        idx = len(pairs)
        pairs.append({"label": f"{slug} {lines}", "y": y, "n": n})
        index.setdefault(y, []).append(idx)
        index.setdefault(n, []).append(idx)
    n_mono = len(pairs)

    # --- DUP: to samo pytanie w roznych eventach: YES(A) + NO(B) ---
    seen_pair = set()
    for q, items in dup_c.items():
        if len(items) < 2:
            continue
        for i in range(len(items)):
            s1, y1, n1, py1, pn1 = items[i]
            for j in range(len(items)):
                if i == j:
                    continue
                s2, y2, n2, py2, pn2 = items[j]
                if s1 == s2 or py1 <= 0 or pn2 <= 0 or py1 + pn2 > max_sum:
                    continue
                key = (y1, n2)
                if key in seen_pair:
                    continue
                seen_pair.add(key)
                idx = len(pairs)
                pairs.append({"label": f"DUP {str(s1)[:16]} vs {str(s2)[:16]}", "y": y1, "n": n2})
                index.setdefault(y1, []).append(idx)
                index.setdefault(n2, []).append(idx)

    print(f"eventy: {events} | par MONO: {n_mono} | par DUP: {len(pairs) - n_mono} "
          f"| tokenow: {len(index)}")

    if not fetch_mo:
        for pr in pairs:
            pr["mo"] = 5.0
        print(f"min_order_size: 5.0 (domyslnie; --fetch-mo sprawdza per rynek)")
        return pairs, index

    # min_order_size per rynek: WS go nie niesie, wiec pobieramy raz przez REST
    toks = {t for pr in pairs for t in (pr["y"], pr["n"])}

    def _mo(t):
        try:
            b = mono.get(f"{mono.CLOB}/book", {"token_id": t}, timeout=8)
            return t, float(b.get("min_order_size") or 5.0)
        except Exception:
            return t, 5.0

    from concurrent.futures import ThreadPoolExecutor as _TPE
    with _TPE(20) as pool:
        mo = dict(pool.map(_mo, toks))
    for pr in pairs:
        pr["mo"] = max(mo.get(pr["y"], 5.0), mo.get(pr["n"], 5.0))
    from collections import Counter
    print(f"min_order_size w parach: {dict(Counter(pr['mo'] for pr in pairs))}")
    return pairs, index


def sizing(ya, na, bankroll, dy=None, dn=None, min_shares=0.0):
    """Ile akcji kupic: min. 1 USD/noga, max bankroll ORAZ glebokosc ksiag."""
    if ya <= 0 or na <= 0:
        return None
    n_min = max(min_shares, 1.0 / ya, 1.0 / na)   # min. z rynku (min_order_size) i 1 USD/noga
    n_max = bankroll / (ya + na)
    if dy:
        n_max = min(n_max, dy)
    if dn:
        n_max = min(n_max, dn)
    if n_max < n_min:
        return None
    n = float(int(n_max))                # calkowite akcje
    if n < n_min:
        return None
    cost = n * (ya + na)
    fee = n * 0.05 * (ya * (1 - ya) + na * (1 - na))
    return {"n": n, "cost": cost, "payout": n, "profit": n - cost - fee}


def check_pair(p, asks, min_edge, min_depth=1.0):
    qy = asks.get(p["y"], (0.0, 0.0))
    qn = asks.get(p["n"], (0.0, 0.0))
    ay = qy[0] if isinstance(qy, (tuple, list)) else qy
    an = qn[0] if isinstance(qn, (tuple, list)) else qn
    if ay <= 0 or an <= 0:
        return None
    sy = qy[1] if isinstance(qy, (tuple, list)) else 0.0
    sn = qn[1] if isinstance(qn, (tuple, list)) else 0.0
    # min_order_size per rynek sprawdzamy w sizing()
    if min_depth > 0 and (sy < min_depth or sn < min_depth):
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
        net = check_pair(p, asks, 0.01, 0)   # w selftescie brak depth
        ok = (net is not None) == expect
        print(f"  ask_yes={asks['tok_yes']:.2f} ask_no={asks['tok_no']:.2f} "
              f"-> {'ARB netto ' + format(net * 100, '.1f') + '%' if net else 'brak'} "
              f"{'OK' if ok else 'BLAD'}")
    return 0


async def run_ws(tags, pages, min_edge, live, stake, bankroll, min_depth=1.0,
                min_shares=0.0, max_sum=0.95, max_trades=1, compound=True,
                fetch_mo=False, per_event=False):
    try:
        import websockets
    except ImportError:
        print("brak modulu websockets. Zainstaluj: pip install websockets")
        return
    pairs, index = pairs_from_events(tags, pages, min_edge, min_depth, max_sum, fetch_mo)
    if not pairs:
        print("brak kandydatow")
        return
    ids = list(index.keys())
    asks = {}
    last = {}          # ostatnio sprawdzone ceny pary (mniej CPU -> pingi nie gina)
    done = set()        # jedna egzekucja na pare (bez powtorek co tick)
    trades_done = 0     # licznik wykonanych par (limit przez --max-trades)
    paper_pnl = 0.0     # symulowany zysk (dry)
    paper_bank = bankroll
    url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    async def session(ws):
        nonlocal paper_pnl, paper_bank, trades_done   # KLUCZOWE: inaczej UnboundLocalError
        for i in range(0, len(ids), 400):
            await ws.send(json.dumps({"assets_ids": ids[i:i + 400], "type": "market"}))
            await asyncio.sleep(0.2)
        print(f"subskrypcja: {len(ids)} tokenow w {max(1, (len(ids) + 399) // 400)} paczkach")
        import time as _t
        _last = _t.time()
        _msgs = 0
        async for raw in ws:
            _msgs += 1
            if _t.time() - _last > 60:
                print(f"[STAT] dziala | wiadomosci={_msgs} | tokenow z cena={len(asks)}")
                _last, _msgs = _t.time(), 0
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
                        best = min(pr for pr, _ in lv)
                        size = sum(sz for pr, sz in lv if abs(pr - best) < 1e-9)
                        mo = float(it.get("min_order_size") or 5.0)
                        prev = asks.get(tok)
                        asks[tok] = (best, size, mo)
                        if not prev or abs(prev[0] - best) > 1e-9:
                            touched.add(tok)
                elif et == "price_change":
                    for ch in it.get("changes") or []:
                        tok = ch.get("asset_id")
                        if tok and ch.get("price"):
                            touched.add(tok)
            for tok in touched:
                for idx in index.get(tok, []):
                    pair = pairs[idx]
                    net = check_pair(pair, asks, min_edge, min_depth)
                    if not net:
                        continue
                    qy, qn = asks.get(pair['y']), asks.get(pair['n'])
                    if last.get(idx) == (qy[0], qn[0]):
                        continue
                    last[idx] = (qy[0], qn[0])
                    ya, na = qy[0], qn[0]
                    need = max(min_shares, pair.get("mo", 5.0))
                    sz = sizing(ya, na, paper_bank if not live else bankroll,
                                qy[1], qn[1], need)
                    if sz:
                        info = (f"| N={sz['n']:.0f} akcji (depth {qy[1]:.0f}/{qn[1]:.0f}), "
                                f"koszt ${sz['cost']:.2f}, zysk ${sz['profit']:.2f}")
                    else:
                        mo_p = pair.get("mo", 5.0)
                        n_dol = max(1.0 / ya, 1.0 / na)      # 1 USD na noge
                        need = max(min_shares, mo_p, n_dol)
                        cost_need = need * (ya + na)
                        info = (f"| ODRZUCONE: potrzeba {need:.1f} akcji "
                                f"(min rynku {mo_p:.0f}, 1 USD/noga {n_dol:.1f}), "
                                f"koszt ${cost_need:.2f} > bankroll ${bankroll:.2f}")
                    print(f"[ARB] {pair['label'][:44]} netto {net * 100:.1f}% "
                          f"(yes={ya:.3f} no={na:.3f}) {info}")
                    key = pair['label'].split(' ')[0] if per_event else pair['label']
                    if sz and not live and key not in done:
                        done.add(key)
                        paper_pnl += sz['profit']
                        if compound:
                            paper_bank += sz['profit']
                        print(f"   [PAPER] para #{len(done)} zysk ${sz['profit']:+.2f} | "
                              f"bankroll ${paper_bank:.2f} | razem ${paper_pnl:+.2f}")
                        continue
                    if live and sz and key not in done:
                        if max_trades and trades_done >= max_trades:
                            print(f"   [LIMIT] max {max_trades} transakcji osiagniety - nie kupuje")
                            done.add(key)
                            continue
                        done.add(key)
                        trades_done += 1
                        print(f"   [ONCE] para {trades_done}/{max_trades or 'inf'}")
                        await execute(pair, ya, na, sz, qy[1], qn[1])

    while True:
        try:
            async with websockets.connect(url, ping_interval=10, ping_timeout=30,
                                          open_timeout=30, max_size=2 ** 23,
                                          close_timeout=5) as ws:
                await session(ws)
            print("[WS] sesja zakonczona -> reconnect")
        except Exception as e:
            print(f"[WS] rozlaczone ({e!r}) -> reconnect za 5 s")
        await asyncio.sleep(5)


async def execute(p, ya, na, sz, dy=0.0, dn=0.0):
    """Kupno obu nog w ROWNEJ liczbie akcji (market order, min ~1 USD/noga)."""
    try:
        import bot_v2_dry_v3 as bot
    except ImportError:
        print("  brak bot_v2_dry_v3.py - nie moge wykonac")
        return
    broker = bot.LiveBroker()
    n = sz["n"]
    first = None
    # najpierw noga z ciensza ksiazka (latwiej zniknie), gruba na koncu
    legs = sorted([(p["y"], ya, dy), (p["n"], na, dn)], key=lambda x: x[2])
    for i, (tok, price, _depth) in enumerate(legs):
        usd = round(n * price, 2)
        try:
            r = broker.buy_no(tok, usd, price, bot.get_tick_size(tok), 0.0)
            ok = isinstance(r, dict) and r.get("ok")
            print("  [LIVE]", str(r)[:140])
        except Exception as e:
            ok, r = False, None
            print("  [LIVE ERR]", repr(e))
        if i == 0 and ok:
            first = (tok, float(r.get("shares") or 0.0))
        if i == 1 and not ok and first and first[1] > 0:
            # AWARYJNIE: druga noga nie weszla -> sprzedaj pierwsza
            print("  [UNWIND] druga noga nie weszla, sprzedaje pierwsza")
            try:
                from py_clob_client.clob_types import MarketOrderArgs
                from py_clob_client.order_builder.constants import SELL
                bid = bot.get_bid(first[0])
                mo = MarketOrderArgs(token_id=first[0], amount=first[1], side=SELL,
                                     price=round(max(0.01, bid), 4),
                                     order_type=broker.OrderType.FAK)
                r2 = broker.client.post_order(broker.client.create_market_order(mo),
                                              broker.OrderType.FAK)
                print("  [UNWIND]", str(r2)[:140])
            except Exception as e:
                print("  [UNWIND ERR] sprzedaj recznie:", repr(e))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default=mono.ALL_TAGS)
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--min-edge", type=float, default=0.01)
    ap.add_argument("--stake", type=float, default=1.0)
    ap.add_argument("--bankroll", type=float, default=4.17)
    ap.add_argument("--min-shares", type=float, default=5.0,
                    help="min. liczba akcji na noge (Polymarket: 5)")
    ap.add_argument("--per-event", action="store_true",
                    help="licz tylko jedna pare na mecz (realistyczny PnL)")
    ap.add_argument("--fetch-mo", action="store_true",
                    help="pobierz min_order_size per rynek (wolny bootstrap, domyslnie 5)")
    ap.add_argument("--compound", action="store_true", default=True,
                    help="dry: dokladaj zysk do bankrolla (all-in symulacja)")
    ap.add_argument("--no-compound", dest="compound", action="store_false")
    ap.add_argument("--max-trades", type=int, default=1,
                    help="ile par kupic w tej sesji (0 = bez limitu)")
    ap.add_argument("--max-sum", type=float, default=0.95,
                    help="gorny limit sumy cen pary (budzet / min. akcji)")
    ap.add_argument("--min-depth", type=float, default=1.0,
                    help="min. liczba akcji po asku (5 = odsiewa pyl)")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--dry", action="store_true", help="tylko wykrywanie (domyslne)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())
    asyncio.run(run_ws(args.tags, args.pages, args.min_edge, args.live, args.stake,
                       args.bankroll, args.min_depth, args.min_shares, args.max_sum,
                       args.max_trades, args.compound, args.fetch_mo, args.per_event))


if __name__ == "__main__":
    main()
