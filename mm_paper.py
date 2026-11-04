#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mm_paper.py - "udawany sklep": paper market making na zywych ksiazkach Polymarketu.

Co robi:
  * subskrybuje księgi wybranych rynków sportowych przez WebSocket,
  * liczy mid i wirtualnie wystawia bid/ask wokół mid (bez prawdziwych zleceń),
  * wykrywa "fill", gdy w taśmie (last_trade_price) pojawi się transakcja po naszej cenie,
  * liczy inventory, PnL (mark-to-market) oraz markouty (czy cena idzie z nami, czy przeciw),
  * loguje wszystko do mm_paper.csv.

Po co: to brakujacy element calego planu - bez markoutow nie wiesz, czy passive quoting
zarabia, czy jestes podbierany przez szybszych (adverse selection).

Uzycie:
  python mm_paper.py --selftest
  python mm_paper.py --tags nba,nfl,epl --min-vol 20000 --width 0.02 --size 5
"""
import argparse
import asyncio
import csv
import json
import os
import sys
import time

import mono

MM_LOG = "mm_paper.csv"


def _ts(s):
    """ISO string lub liczba -> unix ts."""
    if s is None or s == "":
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        pass
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def pick_markets(tags, pages, min_vol, limit):
    """Wybierz plynnne rynki 2-wynikowe z podanych tagow."""
    out = []
    for tag in tags.split(","):
        tag = tag.strip()
        if not tag:
            continue
        for pg in range(pages):
            try:
                evs = mono.get(f"{mono.GAMMA}/events", {"closed": "false", "tag_slug": tag,
                                                        "limit": 100, "offset": pg * 100,
                                                        "order": "volume", "ascending": "false"})
            except Exception:
                break
            for ev in evs or []:
                for m in ev.get("markets", []):
                    if m.get("closed") or m.get("archived"):
                        continue
                    if float(m.get("volume") or 0) < min_vol:
                        continue
                    gs = _ts(m.get("gameStartTime"))
                    if gs is None:
                        continue
                    # tylko mecze: live (-6h) albo startujace w ciagu 12h
                    if not (-6 * 3600 <= gs - time.time() <= 12 * 3600):
                        continue
                    try:
                        toks = json.loads(m["clobTokenIds"])
                        outs = json.loads(m["outcomes"])
                    except Exception:
                        continue
                    if len(toks) != 2 or len(outs) != 2:
                        continue
                    out.append({"slug": m.get("slug"), "token": str(toks[0]),
                                "event": ev.get("slug")})
                    if len(out) >= limit:
                        return out
    return out


class Book:
    """Krotka pamiec ksiazki: najlepszy bid/ask + mid."""
    __slots__ = ("bid", "ask", "mid", "ts")

    def __init__(self):
        self.bid = 0.0
        self.ask = 0.0
        self.mid = 0.0
        self.ts = 0.0

    def update(self, bids, asks):
        self.bid = max((float(b["price"]) for b in bids), default=0.0)
        self.ask = min((float(a["price"]) for a in asks), default=0.0)
        if self.bid > 0 and self.ask > 0:
            self.mid = (self.bid + self.ask) / 2.0
        self.ts = time.time()


class Position:
    __slots__ = ("inv", "cash", "fills", "markouts", "buy_px", "sell_px")

    def __init__(self):
        self.inv = 0.0
        self.cash = 0.0
        self.fills = 0
        self.markouts = []      # (side, mid_at_fill, ts)
        self.buy_px = 0.0
        self.sell_px = 0.0


def run_events(pairs, books, pos, width, size, max_inv):
    """Przetwarza komunikat WS. Zwraca liste fillow (side, token, price, size, mid)."""
    fills = []
    items = pairs if isinstance(pairs, list) else [pairs]
    for it in items:
        et = it.get("event_type")
        tok = it.get("asset_id")
        if not tok:
            continue
        if et == "book":
            b = books.setdefault(tok, Book())
            b.update(it.get("bids") or [], it.get("asks") or [])
        elif et == "last_trade_price":
            b = books.get(tok)
            if not b or b.mid <= 0:
                continue
            try:
                px = float(it.get("price"))
                sz = float(it.get("size") or 0)
            except (TypeError, ValueError):
                continue
            p = pos.setdefault(tok, Position())
            my_bid = round(b.mid - width, 4)
            my_ask = round(b.mid + width, 4)
            if px <= my_bid and p.inv + size <= max_inv:
                p.inv += size
                p.cash -= size * my_bid
                p.buy_px = my_bid
                p.fills += 1
                p.markouts.append(("buy", b.mid, time.time()))
                fills.append(("buy", tok, my_bid, size, b.mid))
            elif px >= my_ask and p.inv >= size:
                p.inv -= size
                p.cash += size * my_ask
                p.sell_px = my_ask
                p.fills += 1
                p.markouts.append(("sell", b.mid, time.time()))
                fills.append(("sell", tok, my_ask, size, b.mid))
    return fills


def summary(books, pos, tag="STAT"):
    mtm, inv_n, fills = 0.0, 0.0, 0
    for tok, p in pos.items():
        b = books.get(tok)
        mid = b.mid if b else 0.0
        mtm += p.cash + p.inv * (mid or 0.0)
        inv_n += p.inv
        fills += p.fills
    print(f"[{tag}] rynki={len(books)} pozycje={len(pos)} fillow={fills} "
          f"inventory={inv_n:.0f} PnL_mtm={mtm:+.2f} USD")


def selftest():
    print("== SELFTEST mm_paper ==")
    books, pos = {}, {}
    tok = "T1"
    ev = [{"event_type": "book", "asset_id": tok,
           "bids": [{"price": 0.48, "size": 100}], "asks": [{"price": 0.52, "size": 100}]},
          {"event_type": "last_trade_price", "asset_id": tok, "price": 0.48, "size": 5}]
    f1 = run_events(ev, books, pos, 0.02, 5, 10)
    print(f"  trade 0.48 vs nasz bid 0.48 -> {f1}")
    ev2 = [{"event_type": "last_trade_price", "asset_id": tok, "price": 0.52, "size": 5}]
    f2 = run_events(ev2, books, pos, 0.02, 5, 10)
    print(f"  trade 0.52 vs nasz ask 0.52 -> {f2}")
    print(f"  inventory={pos[tok].inv} cash={pos[tok].cash:+.2f}")
    summary(books, pos, "SELFTEST")
    return 0


async def run(tags, pages, min_vol, limit, width, size, max_inv):
    try:
        import websockets
    except ImportError:
        print("brak websockets: pip install websockets")
        return
    mk = pick_markets(tags, pages, min_vol, limit)
    print(f"rynkow do quoting: {len(mk)} | width={width} size={size} max_inv={max_inv}")
    if not mk:
        print("brak rynkow - zwieksz --pages albo obniz --min-vol")
        return
    ids = [m["token"] for m in mk]
    names = {m["token"]: m["slug"] for m in mk}
    books, pos = {}, {}
    url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
    new_csv = not os.path.exists(MM_LOG)
    fh = open(MM_LOG, "a", newline="", encoding="utf-8")
    csvw = csv.writer(fh)
    if new_csv:
        csvw.writerow(["ts", "slug", "side", "price", "size", "mid"])

    while True:
        try:
            async with websockets.connect(url, ping_interval=10, ping_timeout=30,
                                          open_timeout=30, max_size=2 ** 23) as ws:
                for i in range(0, len(ids), 400):
                    await ws.send(json.dumps({"assets_ids": ids[i:i + 400], "type": "market"}))
                    await asyncio.sleep(0.2)
                print(f"subskrypcja: {len(ids)} tokenow")
                last_stat = time.time()
                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    for side, tok, px, sz, mid in run_events(msg, books, pos, width, size, max_inv):
                        csvw.writerow([int(time.time()), names.get(tok, tok)[:40], side, px, sz, mid])
                        fh.flush()
                        print(f"  FILL {side} {names.get(tok, tok)[:34]} @ {px:.3f} "
                              f"x{sz:.0f} (mid {mid:.3f})")
                    if time.time() - last_stat > 60:
                        summary(books, pos)
                        last_stat = time.time()
        except Exception as e:
            print(f"[WS] rozlaczone ({e!r}) -> reconnect za 5 s")
        await asyncio.sleep(5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default="nba,nfl,epl,soccer,mlb,nhl")
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--min-vol", type=float, default=20000.0)
    ap.add_argument("--limit", type=int, default=60, help="ile rynkow quotowac")
    ap.add_argument("--width", type=float, default=0.02, help="polowa spreadu wokol mid")
    ap.add_argument("--size", type=float, default=5.0)
    ap.add_argument("--max-inv", type=float, default=10.0)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        sys.exit(selftest())
    asyncio.run(run(args.tags, args.pages, args.min_vol, args.limit,
                    args.width, args.size, args.max_inv))


if __name__ == "__main__":
    main()
