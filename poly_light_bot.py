#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
poly_light_bot.py v2 - BTC updown 5m na Polymarkecie, sygnal z Bitget.

CO ROBI:
  1. Czyta cene BTC z Bitget co 1 s (spot ticker).
  2. Trzyma okno ostatnich N sekund -> wykrywa skok >= THRESHOLD USD.
  3. Bierze AKTYWNY rynek "btc-updown-5m" z Polymarketu (Gamma).
  4. Mapuje kierunek przez pole `outcomes` (Up/Down), nie po indeksie.
  5. Kupuje token po best ASK, jesli ask <= MAX_ENTRY.
  6. Wychodzi po best BID: TP (EXIT_BID), czas (HOLD_SEC) albo brak plynnosci.
  7. Liczy transakcje, winrate, PnL, zapisuje do CSV i loguje.

TRYBY:
  python poly_light_bot.py            # paper (bez zlecen)
  python poly_light_bot.py --live     # realne zlecenia (wymaga kluczy w env)

ENV --live: POLY_PRIVATE_KEY, POLYMARKET_DEPOSIT_WALLET, POLY_SIGNATURE_TYPE
"""
import argparse
import csv
import json
import os
import time
import urllib.parse
import urllib.request
from collections import deque

BITGET = "https://api.bitget.com"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
LOG = "poly_light.log"
CSV = "poly_light_trades.csv"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get(url, params=None, timeout=10):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "poly-light/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def btc_price():
    d = get(f"{BITGET}/api/v2/spot/market/tickers", {"symbol": "BTCUSDT"})
    return float(d["data"][0]["lastPr"])


def find_market():
    """Aktywny rynek BTC updown 5m: {slug, tokens:{'Up':id,'Down':id}, end}."""
    d = get(f"{GAMMA}/markets", {"closed": "false", "limit": 100,
                                 "order": "createdAt", "ascending": "false"})
    now = time.time()
    best = None
    for m in d or []:
        slug = m.get("slug") or ""
        if "btc-updown-5m" not in slug:
            continue
        try:
            toks = json.loads(m["clobTokenIds"])
            outs = json.loads(m["outcomes"])
        except Exception:
            continue
        if len(toks) != 2 or len(outs) != 2:
            continue
        end = m.get("endDate")
        try:
            ets = time.mktime(time.strptime(str(end)[:19], "%Y-%m-%dT%H:%M:%S"))
        except Exception:
            ets = now + 300
        if ets < now:
            continue
        tokens = {str(outs[i]).strip().lower(): str(toks[i]) for i in range(2)}
        if "up" not in tokens or "down" not in tokens:
            continue
        cand = {"slug": slug, "tokens": {"up": tokens["up"], "down": tokens["down"]},
                "end": ets}
        if best is None or ets < best["end"]:
            best = cand
    return best


def price_of(token, side):
    """side='buy' -> best ask (koszt kupna), side='sell' -> best bid (cena sprzedazy)."""
    try:
        d = get(f"{CLOB}/price", {"token_id": token, "side": side})
        return float(d.get("price") or 0)
    except Exception:
        return 0.0


def taker_fee(price, rate=0.07):
    """Fee Polymarket: rate * p * (1-p) na akcje."""
    return rate * price * (1.0 - price)


class Tracker:
    """Statystyki: transakcje, winrate, PnL."""

    def __init__(self):
        self.trades = 0
        self.wins = 0
        self.losses = 0
        self.pnl = 0.0
        self.open_pos = None
        if not os.path.exists(CSV):
            with open(CSV, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(["ts_open", "ts_close", "slug", "side", "entry",
                                        "exit", "shares", "cost", "pnl_usd", "result", "reason"])

    def open(self, pos):
        self.open_pos = pos

    def close(self, exit_px, reason):
        p = self.open_pos
        if not p:
            return
        proceeds = p["shares"] * exit_px * (1 - taker_fee(exit_px))
        pnl = proceeds - p["cost"]
        result = "win" if pnl > 0 else ("loss" if pnl < 0 else "flat")
        self.trades += 1
        self.pnl += pnl
        if result == "win":
            self.wins += 1
        elif result == "loss":
            self.losses += 1
        with open(CSV, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([p["ts"], int(time.time()), p["slug"], p["side"],
                                    round(p["entry"], 4), round(exit_px, 4),
                                    round(p["shares"], 4), round(p["cost"], 4),
                                    round(pnl, 4), result, reason])
        log(f"  ZAMKNIETE {p['side'].upper()} entry={p['entry']:.3f} exit={exit_px:.3f} "
            f"PnL=${pnl:+.3f} ({reason})")
        self.open_pos = None

    @property
    def winrate(self):
        decided = self.wins + self.losses
        return 100.0 * self.wins / decided if decided else 0.0

    def summary(self):
        return (f"transakcji={self.trades} win={self.wins} loss={self.losses} "
                f"winrate={self.winrate:.1f}% PnL=${self.pnl:+.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--threshold", type=float, default=2.0)
    ap.add_argument("--window", type=int, default=15)
    ap.add_argument("--max-entry", type=float, default=0.80)
    ap.add_argument("--exit-bid", type=float, default=0.92)
    ap.add_argument("--stop-bid", type=float, default=0.45)
    ap.add_argument("--hold", type=int, default=120)
    ap.add_argument("--stake", type=float, default=2.0)
    ap.add_argument("--cooldown", type=int, default=60)
    ap.add_argument("--poll", type=float, default=1.0)
    args = ap.parse_args()

    broker = bot = None
    if args.live:
        import bot_v2_dry_v3 as bot
        broker = bot.LiveBroker()
        log("[LIVE] prawdziwe zlecenia")
    else:
        log("[PAPER] symulacja")

    hist, tr = deque(), Tracker()
    last_entry = 0.0
    mk_cache = {"ts": 0.0, "mk": None}
    log(f"START thr=${args.threshold} win={args.window}s max_entry={args.max_entry} "
        f"exit={args.exit_bid} stop={args.stop_bid} stake=${args.stake}")

    while True:
        try:
            px = btc_price()
            now = time.time()
            hist.append((now, px))
            while hist and now - hist[0][0] > args.window:
                hist.popleft()

            if now - mk_cache["ts"] > 30:
                mk_cache["mk"] = find_market()
                mk_cache["ts"] = now
            mk = mk_cache["mk"]

            if tr.open_pos:
                p = tr.open_pos
                bid = price_of(p["token"], "sell")
                held = now - p["ts"]
                if bid <= 0:
                    tr.close(p["entry"] * 0.5, "brak bidu")
                elif bid >= args.exit_bid:
                    tr.close(bid, "TP")
                elif bid <= args.stop_bid:
                    tr.close(bid, "SL")
                elif held > args.hold:
                    tr.close(bid, "czas")
                elif mk and mk["end"] <= now:
                    tr.close(bid, "rynek zamkniety")
                if tr.open_pos:
                    log(f"  POZYCJA {p['side'].upper()} entry={p['entry']:.3f} bid={bid:.3f} "
                        f"({held:.0f}s) | {tr.summary()}")
                    time.sleep(args.poll)
                    continue

            if mk and len(hist) >= 2 and now - last_entry > args.cooldown:
                move = px - hist[0][1]
                if abs(move) >= args.threshold:
                    side = "up" if move > 0 else "down"
                    token = mk["tokens"][side]
                    ask = price_of(token, "buy")
                    log(f"SKOK BTC {move:+.2f}$ -> {side.upper()} ask={ask:.3f} | {mk['slug']}")
                    if 0 < ask <= args.max_entry:
                        shares = args.stake / ask
                        cost = args.stake + shares * taker_fee(ask)
                        tr.open({"ts": int(now), "slug": mk["slug"], "side": side,
                                 "token": token, "entry": ask, "shares": shares,
                                 "cost": cost})
                        last_entry = now
                        log(f"  KUPNO {side.upper()} {shares:.2f} akcji @ {ask:.3f} "
                            f"koszt=${cost:.3f}")
                        if args.live and broker:
                            try:
                                r = broker.buy_no(token, args.stake, ask,
                                                  bot.get_tick_size(token), taker_fee(ask))
                                log(f"  [LIVE] {str(r)[:110]}")
                            except Exception as e:
                                log(f"  [LIVE ERR] {e!r}")
                    else:
                        log(f"  odrzucone: ask {ask:.3f} > {args.max_entry}")
            elif int(now) % 30 == 0:
                log(f"NASLUCH BTC=${px:,.2f} rynek={'OK' if mk else 'brak'} | {tr.summary()}")

        except KeyboardInterrupt:
            log("[STOP] Ctrl+C")
            break
        except Exception as e:
            log(f"[ERR] {e!r}")
        time.sleep(args.poll)


if __name__ == "__main__":
    main()