#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bitget_bot.py - bot BTCUSDT 5m pod Bitget wg wskaznika "BUY SELL 3 Levels".

LOGIKA (jak w Pine, wersja STREFOWA - bez filtrow, ktore dotycza tylko statystyk):
  Stoch RSI (RSI 14 -> stoch 14 -> K=SMA3, D=SMA3)
  BUY :  K <= 30 (tier 1), K <= 20 (tier 2 SUPER), K <= 10 (tier 3 MEGA)
  SELL:  K >= 70 (tier 1), K >= 80 (tier 2 SUPER), K >= 90 (tier 3 MEGA)
  Nowa strefa = pojawienie sie tieru wyzszego niz poprzednio w tej samej stronie.
  Wejscie: strefa BUY -> LONG, strefa SELL -> SHORT (przy flippie zamyka przeciwna).

TRYBY:
  python bitget_bot.py --backtest --days 3       # test na historii, bez zlecen
  python bitget_bot.py --paper                   # petla na zywo, bez zlecen
  python bitget_bot.py --live                    # PRAWDZIWE zlecenia (klucze w env)

ENV (dla --live):
  BITGET_API_KEY, BITGET_SECRET_KEY, BITGET_PASSPHRASE
"""
import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HOST = "https://api.bitget.com"
PRODUCT = "USDT-FUTURES"
SYMBOL = "BTCUSDT"
GRAN = "5m"
LOG = "bitget_bot.log"

# --- parametry wskaznika (domyslne jak w Pine) ---
RSI_LEN = 14
STOCH_LEN = 14
K_SMOOTH = 3
D_SMOOTH = 3
SELL_T, SUPER_SELL_T, MEGA_SELL_T = 70.0, 80.0, 90.0
BUY_T, SUPER_BUY_T, MEGA_BUY_T = 30.0, 20.0, 10.0


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# ===========================================================================
# BITGET API (v2, HMAC-SHA256)
# ===========================================================================
def _sign(ts, method, path, body, secret):
    pre = str(ts) + method.upper() + path + body
    mac = hmac.new(secret.encode(), pre.encode(), hashlib.sha256).digest()
    return base64.b64encode(mac).decode()


def api(method, path, params=None, body=None, private=False, timeout=20):
    """Wywolanie API Bitget. path z parametrami dla GET, body dict dla POST."""
    qs = ""
    if params:
        qs = "?" + urllib.parse.urlencode(params)
    url = HOST + path + qs
    data = None
    if body is not None:
        data = json.dumps(body, separators=(",", ":")).encode()
    req = urllib.request.Request(url, data=data, method=method.upper())
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "bitget-bot/1.0")
    if private:
        key = os.environ.get("BITGET_API_KEY", "")
        secret = os.environ.get("BITGET_SECRET_KEY", "")
        passphrase = os.environ.get("BITGET_PASSPHRASE", "")
        if not (key and secret and passphrase):
            raise SystemExit("brak BITGET_API_KEY / BITGET_SECRET_KEY / BITGET_PASSPHRASE")
        ts = str(int(time.time() * 1000))
        pre_body = data.decode() if data else ""
        req.add_header("ACCESS-KEY", key)
        req.add_header("ACCESS-SIGN", _sign(ts, method, path + qs, pre_body, secret))
        req.add_header("ACCESS-TIMESTAMP", ts)
        req.add_header("ACCESS-PASSPHRASE", passphrase)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def candles(limit=300):
    """Swiece 5m: [(ts, open, high, low, close, vol)] od najstarszej."""
    d = api("GET", "/api/v2/mix/market/candles",
            {"symbol": SYMBOL, "productType": PRODUCT, "granularity": GRAN, "limit": limit})
    if d.get("code") != "00000":
        raise RuntimeError(f"candles: {d}")
    rows = [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])]
            for x in d["data"]]
    rows.sort(key=lambda r: r[0])
    return rows


# ===========================================================================
# WSKAZNIK: Stoch RSI (jak w Pine)
# ===========================================================================
def rsi_wilder(closes, n=RSI_LEN):
    """RSI Wildera; lista tej samej dlugosci co closes, None na poczatku."""
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    out[n] = 100.0 if al == 0 else 100.0 - 100.0 / (1 + ag / al)
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
        out[i + 1] = 100.0 if al == 0 else 100.0 - 100.0 / (1 + ag / al)
    return out


def stoch_rsi(closes, n=STOCH_LEN):
    """Surowy Stoch RSI: (rsi - min) / (max - min) * 100."""
    r = rsi_wilder(closes)
    out = [None] * len(closes)
    for i in range(len(closes)):
        if i < n - 1:
            continue
        win = [x for x in r[i - n + 1:i + 1] if x is not None]
        if len(win) < n:
            continue
        lo, hi = min(win), max(win)
        out[i] = 0.0 if hi == lo else (r[i] - lo) / (hi - lo) * 100.0
    return out


def sma(vals, n):
    out = [None] * len(vals)
    for i in range(len(vals)):
        if i < n - 1:
            continue
        win = [x for x in vals[i - n + 1:i + 1] if x is not None]
        if len(win) < n:
            continue
        out[i] = sum(win) / n
    return out


def ema(vals, n):
    out = [None] * len(vals)
    k = 2.0 / (n + 1)
    prev = None
    for i, v in enumerate(vals):
        if prev is None:
            if i >= n - 1:
                prev = sum(vals[i - n + 1:i + 1]) / n
                out[i] = prev
            continue
        prev = v * k + prev * (1 - k)
        out[i] = prev
    return out


def atr(rows, n=14):
    out = [None] * len(rows)
    trs = []
    for i, (ts, o, h, l, c, v) in enumerate(rows):
        if i == 0:
            trs.append(h - l)
        else:
            pc = rows[i - 1][4]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        if i >= n - 1:
            out[i] = sum(trs[i - n + 1:i + 1]) / n
    return out


def tiers(k):
    """(buyTier, sellTier) dla wartosci K."""
    if k is None:
        return 0, 0
    b = 3 if k <= MEGA_BUY_T else 2 if k <= SUPER_BUY_T else 1 if k <= BUY_T else 0
    s = 3 if k >= MEGA_SELL_T else 2 if k >= SUPER_SELL_T else 1 if k >= SELL_T else 0
    return b, s


def tier_name(side, tier):
    return ("MEGA " if tier == 3 else "SUPER " if tier == 2 else "") + ("BUY" if side == "buy" else "SELL")


def signals(rows, min_tier=1):
    """
    Zwraca liste sygnalow: dict(ts, price, side, tier, k).
    Logika stref (jak w Pine): nowy tier > poprzedni widziany w tej stronie -> sygnal.
    """
    closes = [r[4] for r in rows]
    k_line = sma(stoch_rsi(closes), K_SMOOTH)
    out = []
    seen_buy = 0
    seen_sell = 0
    for i, row in enumerate(rows):
        b, s = tiers(k_line[i])
        if b == 0:
            seen_buy = 0
        if b > seen_buy:
            if b >= min_tier:
                out.append({"ts": row[0], "idx": i, "price": row[4], "side": "buy",
                            "tier": b, "k": k_line[i]})
            seen_buy = b
        if s == 0:
            seen_sell = 0
        if s > seen_sell:
            if s >= min_tier:
                out.append({"ts": row[0], "idx": i, "price": row[4], "side": "sell",
                            "tier": s, "k": k_line[i]})
            seen_sell = s
    return out, k_line


# ===========================================================================
# BROKER: Bitget futures
# ===========================================================================
class BitgetBroker:
    def __init__(self, leverage, margin_mode, size_pct):
        self.leverage = leverage
        self.margin_mode = margin_mode
        self.size_pct = size_pct
        self.hedge = False
        self._setup()

    def _setup(self):
        for path, body in (
            ("/api/v2/mix/account/set-margin-mode",
             {"symbol": SYMBOL, "productType": PRODUCT, "marginCoin": "USDT",
              "marginMode": self.margin_mode}),
            ("/api/v2/mix/account/set-leverage",
             {"symbol": SYMBOL, "productType": PRODUCT, "marginCoin": "USDT",
              "leverage": str(self.leverage), "holdSide": "long"}),
            ("/api/v2/mix/account/set-leverage",
             {"symbol": SYMBOL, "productType": PRODUCT, "marginCoin": "USDT",
              "leverage": str(self.leverage), "holdSide": "short"}),
        ):
            try:
                r = api("POST", path, body=body, private=True)
                log(f"[SETUP] {path.split('/')[-1]} -> {r.get('code')} {r.get('msg')}")
            except Exception as e:
                log(f"[SETUP-ERR] {path} {e!r}")

    def balance_usdt(self):
        r = api("GET", "/api/v2/mix/account/accounts",
                {"productType": PRODUCT, "marginCoin": "USDT"}, private=True)
        for a in r.get("data") or []:
            if a.get("marginCoin") == "USDT":
                return float(a.get("available") or a.get("accountEquity") or 0)
        return 0.0

    def position(self):
        r = api("GET", "/api/v2/mix/position/single-position",
                {"symbol": SYMBOL, "productType": PRODUCT, "marginCoin": "USDT"}, private=True)
        for p in r.get("data") or []:
            if float(p.get("total") or 0) > 0:
                return {"side": p.get("holdSide"), "size": float(p["total"]),
                        "entry": float(p.get("openPriceAvg") or 0)}
        return None

    def _order(self, side, trade_side, size):
        body = {"symbol": SYMBOL, "productType": PRODUCT, "marginMode": self.margin_mode,
                "marginCoin": "USDT", "size": str(size), "side": side,
                "orderType": "market", "force": "ioc"}
        if self.hedge:
            body["tradeSide"] = trade_side
        return api("POST", "/api/v2/mix/order/place-order", body=body, private=True)

    def close(self, pos):
        side = "sell" if pos["side"] == "long" else "buy"
        r = self._order(side, "close", pos["size"])
        log(f"[CLOSE] {pos['side']} {pos['size']} -> {r.get('code')} {r.get('msg')}")
        return r

    def open(self, direction, price):
        bal = self.balance_usdt()
        notional = bal * self.size_pct * self.leverage
        size = notional / price
        # zaokraglenie do 4 miejsc (volumePlace dla BTCUSDT)
        size = round(size, 4)
        if size < 0.0001:
            log(f"[OPEN-SKIP] size {size} < minTradeNum")
            return None
        side = "buy" if direction == "long" else "sell"
        r = self._order(side, "open", size)
        log(f"[OPEN] {direction} {size} BTC (~${notional:.0f} notional) -> {r.get('code')} {r.get('msg')}")
        return r


# ===========================================================================
# BACKTEST (na swiecach z Bitget)
# ===========================================================================
def backtest(days, leverage, fee_rate=0.0006, min_tier=1):
    limit = min(1000, int(days * 288) + 250)      # 288 swiec 5m na dobe
    rows = candles(limit)
    if len(rows) < 60:
        print("za malo swiec")
        return
    sig, k_line = signals(rows, min_tier)
    if not sig:
        print("brak sygnalow w tej probce")
        return

    span = (rows[-1][0] - rows[0][0]) / 86400000
    print(f"swiec: {len(rows)} | okres: {span:.1f} dni")
    print(f"sygnalow: {len(sig)} (na {span:.1f} dni)\n")

    pos = 0
    entry = 0.0
    entry_ts = 0
    trades = []
    for s in sig:
        if pos != 0:
            gross = (s["price"] - entry) / entry * pos * leverage * 100
            fee_cost = fee_rate * leverage * 2 * 100      # round-trip na marginie
            trades.append({"dir": pos, "entry": entry, "exit": s["price"],
                           "gross": gross, "net": gross - fee_cost,
                           "bars": (s["ts"] - entry_ts) // 300000})
        pos = 1 if s["side"] == "buy" else -1
        entry = s["price"]
        entry_ts = s["ts"]
        print(f"  {time.strftime('%m-%d %H:%M', time.gmtime(s['ts']/1000))}  "
              f"{tier_name(s['side'], s['tier']):11s} K={s['k']:5.1f}  cena={s['price']:.1f}")

    if not trades:
        print("\nbrak zamknietych transakcji (jeden sygnal bez przeciwnego)")
        return
    wins = sum(1 for t in trades if t["net"] > 0)
    tot = sum(t["net"] for t in trades)
    gross_sum = sum(t["gross"] for t in trades)
    avg_bars = sum(t["bars"] for t in trades) / len(trades)
    eq, peak, dd = 0.0, 0.0, 0.0
    for t in trades:
        eq += t["net"]
        peak = max(peak, eq)
        dd = min(dd, eq - peak)

    print(f"\n=== WYNIK (dzwignia x{leverage}, fee {fee_rate*100:.2f}%/strona) ===")
    print(f"transakcji         : {len(trades)}")
    print(f"winrate            : {wins/len(trades)*100:.1f}%")
    print(f"sredni czas pozycji: {avg_bars*5:.0f} min ({avg_bars:.1f} swiec)")
    print(f"zysk brutto        : {gross_sum:+.1f}% marginu")
    print(f"koszt fee          : {gross_sum - tot:+.1f}% marginu")
    print(f"zysk netto         : {tot:+.1f}% marginu")
    print(f"max obsuniecie     : {dd:.1f}%")
    print(f"najlepsza/najgorsza: {max(t['net'] for t in trades):+.1f}% / {min(t['net'] for t in trades):+.1f}%")


# ===========================================================================
# PETLA (paper / live)
# ===========================================================================
def run_loop(live, leverage, size_pct, margin_mode, poll, min_tier=1):
    broker = BitgetBroker(leverage, margin_mode, size_pct) if live else None
    if live:
        log(f"[START LIVE] x{leverage} {margin_mode} size={size_pct*100:.0f}% salda "
            f"| saldo={broker.balance_usdt():.2f} USDT")
    else:
        log(f"[START PAPER] x{leverage} size={size_pct*100:.0f}%")

    last_ts = 0
    pos = None
    while True:
        try:
            rows = candles(400)
            sig, k_line = signals(rows, min_tier)
            last, prev = rows[-1], rows[-2]
            if last[0] != last_ts:
                last_ts = last[0]
                fired = [s for s in sig if s["ts"] == prev[0]]
                if fired:
                    s = max(fired, key=lambda x: x["tier"])
                    want = "long" if s["side"] == "buy" else "short"
                    log(f"[SYGNAL] {tier_name(s['side'], s['tier'])} K={s['k']:.1f} "
                        f"cena={s['price']:.1f} -> {want.upper()}")
                    if want != pos:
                        if live:
                            cur = broker.position()
                            if cur:
                                broker.close(cur)
                            broker.open(want, s["price"])
                        else:
                            log(f"[PAPER] {'zamykam ' + pos.upper() if pos else 'brak pozycji'} "
                                f"-> otwieram {want.upper()} @ {s['price']:.1f}")
                        pos = want
                k_now = k_line[-1]
                log(f"[TICK] {time.strftime('%H:%M', time.gmtime(last[0]/1000))} "
                    f"close={last[4]:.1f} K={'-' if k_now is None else round(k_now,1)} "
                    f"pozycja={pos or 'brak'}"
                    + (f" saldo={broker.balance_usdt():.2f}" if live else ""))
        except KeyboardInterrupt:
            log("[STOP] Ctrl+C")
            break
        except Exception as e:
            log(f"[ERR] {e!r}")
        try:
            time.sleep(poll)
        except KeyboardInterrupt:
            log("[STOP] Ctrl+C")
            break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--paper", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--days", type=float, default=3.0)
    ap.add_argument("--leverage", type=int, default=52)
    ap.add_argument("--size-pct", type=float, default=1.0, help="czesc salda (1.0 = all in)")
    ap.add_argument("--margin-mode", default="isolated", choices=("isolated", "crossed"))
    ap.add_argument("--poll", type=int, default=20)
    ap.add_argument("--min-tier", type=int, default=1, choices=(1, 2, 3),
                    help="1=BUY/SELL, 2=SUPER+, 3=tylko MEGA")
    args = ap.parse_args()

    if args.backtest:
        backtest(args.days, args.leverage, min_tier=args.min_tier)
    elif args.paper:
        run_loop(False, args.leverage, args.size_pct, args.margin_mode, args.poll, args.min_tier)
    elif args.live:
        run_loop(True, args.leverage, args.size_pct, args.margin_mode, args.poll, args.min_tier)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
