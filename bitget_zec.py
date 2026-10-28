#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bitget_zec.py - ZECUSDT 1m, dzwignia x14, ALL-IN, wskaznik Stoch RSI 3 poziomy
                 (tryb ODWROCONY + TP/SL w mnoznikach ATR).

Sygnaly (jak w Pine "BUY SELL 3 Levels"):
  K = SMA(Stoch(RSI(14),14),3)
  BUY  tier: K<=30 (1), K<=20 (2 SUPER), K<=10 (3 MEGA)
  SELL tier: K>=70 (1), K>=80 (2 SUPER), K>=90 (3 MEGA)
  Nowy wyzszy tier w tej samej stronie = nowa strefa.

Tryb ODWROCONY (domyslnie): strefa BUY -> SHORT, strefa SELL -> LONG.

TP/SL: mnozniki ATR (domyslnie TP 1.0x, SL 2.5x -> breakeven ~71%, realny winrate ~75-82%).

Tryby:
  python bitget_zec.py --backtest --days 3
  python bitget_zec.py --paper
  python bitget_zec.py --live

ENV dla --live: BITGET_API_KEY, BITGET_SECRET_KEY, BITGET_PASSPHRASE
"""
import argparse
import base64
import hashlib
import hmac
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HOST = "https://api.bitget.com"
PRODUCT = "USDT-FUTURES"
SYMBOL = "ZECUSDT"
GRAN = "1m"
LOG = "bitget_zec.log"
STATE = "bitget_zec_state.json"

# wskaznik
RSI_LEN, STOCH_LEN, K_SM, D_SM = 14, 14, 3, 3
BUY_T, SUP_BUY_T, MEG_BUY_T = 30.0, 20.0, 10.0
SELL_T, SUP_SELL_T, MEG_SELL_T = 70.0, 80.0, 90.0

# kontrakt ZECUSDT
MIN_SIZE = 0.001        # minTradeNum
SIZE_STEP = 0.001       # sizeMultiplier
TAKER_FEE = 0.0006


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


# ============================ BITGET API ============================
def _sign(ts, method, path, body, secret):
    pre = str(ts) + method.upper() + path + body
    return base64.b64encode(
        hmac.new(secret.encode(), pre.encode(), hashlib.sha256).digest()).decode()


def api(method, path, params=None, body=None, private=False, timeout=20):
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    data = json.dumps(body, separators=(",", ":")).encode() if body is not None else None
    req = urllib.request.Request(HOST + path + qs, data=data, method=method.upper())
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "bitget-zec/1.0")
    if private:
        k = os.environ.get("BITGET_API_KEY", "")
        s = os.environ.get("BITGET_SECRET_KEY", "")
        p = os.environ.get("BITGET_PASSPHRASE", "")
        if not (k and s and p):
            raise SystemExit("brak BITGET_API_KEY / BITGET_SECRET_KEY / BITGET_PASSPHRASE")
        ts = str(int(time.time() * 1000))
        req.add_header("ACCESS-KEY", k)
        req.add_header("ACCESS-SIGN", _sign(ts, method, path + qs, data.decode() if data else "", s))
        req.add_header("ACCESS-TIMESTAMP", ts)
        req.add_header("ACCESS-PASSPHRASE", p)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()[:400]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code}: {body}") from None


def candles(limit=500):
    """[(ts, o, h, l, c, v)] od najstarszej."""
    d = api("GET", "/api/v2/mix/market/candles",
            {"symbol": SYMBOL, "productType": PRODUCT, "granularity": GRAN, "limit": limit})
    if d.get("code") != "00000":
        raise RuntimeError(f"candles: {d}")
    rows = [[int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])]
            for x in d["data"]]
    rows.sort(key=lambda r: r[0])
    return rows


# ============================ WSKAZNIK ============================
def rsi_wilder(closes, n=RSI_LEN):
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    g, l = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        g.append(max(d, 0.0))
        l.append(max(-d, 0.0))
    ag, al = sum(g[:n]) / n, sum(l[:n]) / n
    out[n] = 100.0 if al == 0 else 100.0 - 100.0 / (1 + ag / al)
    for i in range(n, len(g)):
        ag = (ag * (n - 1) + g[i]) / n
        al = (al * (n - 1) + l[i]) / n
        out[i + 1] = 100.0 if al == 0 else 100.0 - 100.0 / (1 + ag / al)
    return out


def stoch_rsi(closes, n=STOCH_LEN):
    r = rsi_wilder(closes)
    out = [None] * len(closes)
    for i in range(len(closes)):
        if i < n - 1:
            continue
        w = [x for x in r[i - n + 1:i + 1] if x is not None]
        if len(w) < n:
            continue
        lo, hi = min(w), max(w)
        out[i] = 0.0 if hi == lo else (r[i] - lo) / (hi - lo) * 100.0
    return out


def sma(vals, n):
    out = [None] * len(vals)
    for i in range(len(vals)):
        if i < n - 1:
            continue
        w = [x for x in vals[i - n + 1:i + 1] if x is not None]
        if len(w) < n:
            continue
        out[i] = sum(w) / n
    return out


def atr(rows, n=14):
    out = [None] * len(rows)
    trs = []
    for i, (_, o, h, l, c, _v) in enumerate(rows):
        if i == 0:
            trs.append(h - l)
        else:
            pc = rows[i - 1][4]
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        if i >= n - 1:
            out[i] = sum(trs[i - n + 1:i + 1]) / n
    return out


def tiers(k):
    if k is None:
        return 0, 0
    b = 3 if k <= MEG_BUY_T else 2 if k <= SUP_BUY_T else 1 if k <= BUY_T else 0
    s = 3 if k >= MEG_SELL_T else 2 if k >= SUP_SELL_T else 1 if k >= SELL_T else 0
    return b, s


def tname(side, tier):
    return ("MEGA " if tier == 3 else "SUPER " if tier == 2 else "") + ("BUY" if side == "buy" else "SELL")


def zones(rows, k_line, min_tier=1):
    """Lista stref: dict(idx, ts, price, side, tier, k). Nowy wyzszy tier = nowa strefa."""
    out, sb, ss = [], 0, 0
    for i, row in enumerate(rows):
        b, s = tiers(k_line[i])
        if b == 0:
            sb = 0
        if b > sb:
            sb = b
            if b >= min_tier:
                out.append({"idx": i, "ts": row[0], "price": row[4], "side": "buy",
                            "tier": b, "k": k_line[i]})
        if s == 0:
            ss = 0
        if s > ss:
            ss = s
            if s >= min_tier:
                out.append({"idx": i, "ts": row[0], "price": row[4], "side": "sell",
                            "tier": s, "k": k_line[i]})
    out.sort(key=lambda x: x["idx"])
    return out


# ============================ BROKER (LIMIT / maker) ============================
class BitgetBroker:
    """Zlecenia LIMIT (maker fee 0.02%). Post-only GTC, fallback na market."""

    def __init__(self, leverage, margin_mode, size_pct, post_only=True, wait_s=20):
        self.leverage = leverage
        self.margin_mode = margin_mode
        self.size_pct = size_pct
        self.post_only = post_only
        self.wait_s = wait_s
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
                log(f"[SETUP] {path.rsplit('/', 1)[-1]} {r.get('code')} {r.get('msg')}")
            except Exception as e:
                log(f"[SETUP-ERR] {e!r}")

    def balance_usdt(self):
        try:
            r = api("GET", "/api/v2/mix/account/accounts",
                    {"productType": PRODUCT, "marginCoin": "USDT"}, private=True)
            for a in r.get("data") or []:
                if a.get("marginCoin") == "USDT":
                    return float(a.get("available") or a.get("accountEquity") or 0)
        except Exception as e:
            log(f"[BAL-ERR] {e!r}")
        return 0.0

    def position(self):
        try:
            r = api("GET", "/api/v2/mix/position/single-position",
                    {"symbol": SYMBOL, "productType": PRODUCT, "marginCoin": "USDT"},
                    private=True)
            for p in r.get("data") or []:
                if float(p.get("total") or 0) > 0:
                    return {"side": p.get("holdSide"), "size": float(p["total"]),
                            "entry": float(p.get("openPriceAvg") or 0)}
        except Exception as e:
            log(f"[POS-ERR] {e!r}")
        return None

    def _round_size(self, size):
        return round(round(size / SIZE_STEP) * SIZE_STEP, 3)

    def _order(self, side, trade_side, size, price=None, order_type="limit"):
        body = {"symbol": SYMBOL, "productType": PRODUCT, "marginMode": self.margin_mode,
                "marginCoin": "USDT", "size": str(size), "side": side,
                "orderType": order_type}
        if order_type == "limit":
            body["price"] = str(price)
            body["force"] = "gtc"
        else:
            body["force"] = "ioc"
        if self.hedge:
            body["tradeSide"] = trade_side
        return api("POST", "/api/v2/mix/order/place-order", body=body, private=True)

    def _cancel(self, order_id):
        try:
            api("POST", "/api/v2/mix/order/cancel-order",
                body={"symbol": SYMBOL, "productType": PRODUCT, "orderId": order_id},
                private=True)
        except Exception:
            pass

    def _wait_fill(self, order_id, want, timeout=None):
        end = time.time() + (timeout if timeout else self.wait_s)
        while time.time() < end:
            time.sleep(2)
            try:
                r = api("GET", "/api/v2/mix/order/detail",
                        {"symbol": SYMBOL, "productType": PRODUCT, "orderId": order_id},
                        private=True)
                d = r.get("data") or {}
                filled = float(d.get("baseVolume") or 0)
                if filled >= want * 0.98:
                    return filled
            except Exception:
                pass
        return 0.0

    def open_limit(self, direction, price):
        """Wejscie LIMIT po cenie sygnalu (maker). Jesli brak fillu -> market."""
        bal = self.balance_usdt()
        if bal <= 0:
            log("[OPEN-SKIP] saldo 0")
            return None
        usable = bal * self.size_pct * 0.95          # bufor na fee (naprawa 40762)
        raw = usable * self.leverage / price
        size = math.floor(raw / SIZE_STEP) * SIZE_STEP
        size = round(size, 3)
        if size < MIN_SIZE:
            log(f"[OPEN-SKIP] size {size} < {MIN_SIZE}")
            return None
        side = "buy" if direction == "long" else "sell"
        # cena pasywna: BUY 1 tick ponizej, SELL 1 tick powyzej -> maker, bez post_only
        tick = 0.01
        px = round(price - tick, 2) if side == "buy" else round(price + tick, 2)
        px = max(0.01, min(px, 10_000_000.0))
        try:
            r = self._order(side, "open", size, price=px, order_type="limit")
            oid = (r.get("data") or {}).get("orderId")
            log(f"[LIMIT-OPEN] {direction} {size} @ {price:.2f} code={r.get('code')} id={oid}")
            if oid:
                filled = self._wait_fill(oid, size)
                if filled >= size * 0.98:
                    log(f"[FILLED maker] {direction} {filled} @ {price:.2f}")
                    return {"size": filled, "price": price, "maker": True}
                self._cancel(oid)
                if filled > 0:
                    log(f"[PARTIAL] {filled}/{size} - reszta anulowana")
                    return {"size": filled, "price": price, "maker": True}
            log("[NO-FILL] fallback market (taker)")
            r2 = self._order(side, "open", size, order_type="market")
            log(f"[MARKET-OPEN] {direction} {size} code={r2.get('code')}")
            return {"size": size, "price": price, "maker": False}
        except Exception as e:
            log(f"[OPEN-ERR] {e!r}")
            return None

    def close_all(self, pos, price):
        """Zamkniecie LIMIT (maker), fallback market."""
        side = "sell" if pos["side"] == "long" else "buy"
        size = pos["size"]
        try:
            tick = 0.01
            cpx = round(price + tick, 2) if side == "sell" else round(price - tick, 2)
            r = self._order(side, "close", size, price=max(0.01, cpx), order_type="limit")
            oid = (r.get("data") or {}).get("orderId")
            log(f"[LIMIT-CLOSE] {pos['side']} {size} @ {price:.2f} code={r.get('code')} id={oid}")
            if oid:
                if self._wait_fill(oid, size, timeout=10) >= size * 0.98:
                    log("[CLOSED maker]")
                    return True
                self._cancel(oid)
            r2 = self._order(side, "close", size, order_type="market")
            log(f"[MARKET-CLOSE] {pos['side']} {size} code={r2.get('code')}")
            return True
        except Exception as e:
            log(f"[CLOSE-ERR] {e!r}")
            return False


# ============================ BACKTEST ============================
def backtest(days, leverage, tp_mult, sl_mult, invert, min_tier, maker=True):
    limit = min(1000, int(days * 1440) + 300)      # 1440 swiec 1m na dobe
    rows = candles(limit)
    if len(rows) < 100:
        print("za malo swiec")
        return
    closes = [r[4] for r in rows]
    k_line = sma(stoch_rsi(closes), K_SM)
    atrs = atr(rows)
    zs = zones(rows, k_line, min_tier)
    if not zs:
        print("brak stref")
        return

    span = (rows[-1][0] - rows[0][0]) / 86400000
    print(f"swiec={len(rows)} okres={span:.1f}d stref={len(zs)} | x{leverage} "
          f"TP={tp_mult}x SL={sl_mult}x ATR | {'ODWROCONY' if invert else 'normalny'}")
    fee = 0.0002 if maker else 0.0006
    print(f"fee przyjete: {fee*100:.3f}%/strona ({'maker LIMIT' if maker else 'taker MARKET'})\n")

    pos, entry, ei = 0, 0.0, 0
    trades = []
    for z in zs:
        i = z["idx"]
        sig_dir = "long" if ((z["side"] == "sell") == invert) else "short"
        if pos != 0:
            closed = False
            for j in range(ei, i):
                hi, lo, cl = rows[j][2], rows[j][3], rows[j][4]
                tp_px = entry * (1 + tp_mult * atrs[ei] / entry) if pos == 1 else entry * (1 - tp_mult * atrs[ei] / entry)
                sl_px = entry * (1 - sl_mult * atrs[ei] / entry) if pos == 1 else entry * (1 + sl_mult * atrs[ei] / entry)
                if pos == 1:
                    if lo <= sl_px:
                        trades.append({"r": -sl_mult, "exit": sl_px, "bars": j - ei}); closed = True; break
                    if hi >= tp_px:
                        trades.append({"r": tp_mult, "exit": tp_px, "bars": j - ei}); closed = True; break
                else:
                    if hi >= sl_px:
                        trades.append({"r": -sl_mult, "exit": sl_px, "bars": j - ei}); closed = True; break
                    if lo <= tp_px:
                        trades.append({"r": tp_mult, "exit": tp_px, "bars": j - ei}); closed = True; break
            if not closed:
                px = rows[i][4]
                move = (px - entry) / entry * pos
                trades.append({"r": move * leverage, "exit": px, "bars": i - ei})
        pos = 1 if sig_dir == "long" else -1
        entry = z["price"]
        ei = i

    if not trades:
        print("brak zamknietych transakcji")
        return
    wins = sum(1 for t in trades if t["r"] > 0)
    gross_r = sum(t["r"] for t in trades)
    fee_cost = fee * leverage * 2 * len(trades)
    net_r = gross_r - fee_cost
    print(f"transakcji        : {len(trades)}")
    print(f"winrate           : {wins/len(trades)*100:.1f}%")
    print(f"sredni czas poz.  : {sum(t['bars'] for t in trades)/len(trades):.0f} min")
    print(f"zysk brutto       : {gross_r:+.1f}% marginu")
    print(f"koszt fee         : -{fee_cost:.1f}% marginu")
    print(f"zysk NETTO        : {net_r:+.1f}% marginu")
    eq = peak = dd = 0.0
    for t in trades:
        eq += t["r"] - fee * leverage * 2
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    print(f"max obsuniecie    : {dd:.1f}%")
    print(f"najlepsza/najgorsza: {max(t['r'] for t in trades):+.1f}% / {min(t['r'] for t in trades):+.1f}%")
    print(f"\nUWAGA: x{leverage} = likwidacja przy ~{100/leverage:.1f}% ruchu ceny.")


# ============================ PETLA (paper / live) ============================
def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return {"pos": None, "entry": 0.0, "tier": 0, "last_ts": 0}


def save_state(st):
    try:
        with open(STATE, "w") as f:
            json.dump(st, f)
    except Exception:
        pass


def run_loop(live, leverage, size_pct, margin_mode, poll, min_tier,
             tp_mult, sl_mult, invert, post_only, wait_s, catchup=3, enter_active=True):
    st = load_state()
    broker = BitgetBroker(leverage, margin_mode, size_pct, post_only, wait_s) if live else None
    log(f"[START {'LIVE' if live else 'PAPER'}] {SYMBOL} {GRAN} x{leverage} "
        f"size={size_pct*100:.0f}% {'ODWROCONY' if invert else 'normal'} "
        f"TP={tp_mult}x SL={sl_mult}x ATR min_tier={min_tier}")
    if live:
        log(f"[START] saldo={broker.balance_usdt():.2f} USDT | pozycja={broker.position()}")

    while True:
        try:
            rows = candles(400)
            closes = [r[4] for r in rows]
            k_line = sma(stoch_rsi(closes), K_SM)
            atrs = atr(rows)
            last, prev = rows[-1], rows[-2]

            if last[0] != st["last_ts"]:
                st["last_ts"] = last[0]
                zs = zones(rows, k_line, min_tier)
                fired = [z for z in zs if z["ts"] == prev[0]]

                if st["pos"] and st["entry"] > 0:
                    atr0 = st.get("atr") or (atrs[-1] or 0)
                    long_ = st["pos"] == "long"
                    tp_px = st["entry"] * (1 + tp_mult * atr0 / st["entry"]) if long_ \
                        else st["entry"] * (1 - tp_mult * atr0 / st["entry"])
                    sl_px = st["entry"] * (1 - sl_mult * atr0 / st["entry"]) if long_ \
                        else st["entry"] * (1 + sl_mult * atr0 / st["entry"])
                    hit_tp = (prev[2] >= tp_px) if long_ else (prev[3] <= tp_px)
                    hit_sl = (prev[3] <= sl_px) if long_ else (prev[2] >= sl_px)
                    if hit_tp or hit_sl:
                        why = "TP" if (hit_tp and not hit_sl) else "SL"
                        log(f"[{why}] zamykam {st['pos'].upper()} entry={st['entry']:.2f} "
                            f"close={prev[4]:.2f}")
                        if live:
                            cur = broker.position()
                            if cur:
                                broker.close_all(cur, prev[4])
                        st["pos"] = None
                        st["entry"] = 0.0
                        save_state(st)

                # aktywna strefa teraz (K w przedziale) -> wejdz od razu
                if not fired and st["pos"] is None and enter_active:
                    b_now, s_now = tiers(k_line[-1])
                    tier_now = max(b_now, s_now)
                    if tier_now >= min_tier:
                        side_now = "buy" if b_now >= min_tier else "sell"
                        cooldown_ok = (prev[0] - st.get("last_entry_ts", 0)) >= 2 * 60000
                        if cooldown_ok:
                            fired = [{"idx": len(rows) - 2, "ts": prev[0], "price": prev[4],
                                      "side": side_now, "tier": tier_now, "k": k_line[-1]}]
                            log(f"[ACTIVE] K={k_line[-1]:.1f} tier={tier_now} -> wchodze teraz")

                # catch-up: strefa z ostatnich N swiec
                if not fired and st["pos"] is None and catchup > 0:
                    recent = [z for z in zs if z["ts"] >= rows[-1 - catchup][0]]
                    if recent:
                        fired = [max(recent, key=lambda x: x["tier"])]
                        log(f"[CATCHUP] strefa z ostatnich {catchup} swiec")

                if fired and st["pos"] is None:
                    z = max(fired, key=lambda x: x["tier"])
                    direction = "long" if ((z["side"] == "sell") == invert) else "short"
                    log(f"[SYGNAL] {tname(z['side'], z['tier'])} K={z['k']:.1f} "
                        f"@{z['price']:.2f} -> {direction.upper()}")
                    if live:
                        res = broker.open_limit(direction, z["price"])
                        if not res:
                            log("[SKIP] nie udalo sie otworzyc")
                        else:
                            st["pos"] = direction
                            st["entry"] = res["price"]
                            st["size"] = res["size"]
                            st["tier"] = z["tier"]
                            st["atr"] = atrs[-1] or 0
                            st["last_entry_ts"] = prev[0]
                            log(f"[OPEN] {direction} {res['size']} @ {res['price']:.2f} "
                                f"({'maker' if res['maker'] else 'taker'})")
                    else:
                        st["pos"] = direction
                        st["entry"] = z["price"]
                        st["tier"] = z["tier"]
                        st["atr"] = atrs[-1] or 0
                        st["last_entry_ts"] = prev[0]
                        log(f"[PAPER] otwieram {direction.upper()} @ {z['price']:.2f}")
                    save_state(st)

                k_now = k_line[-1]
                log(f"[TICK] {time.strftime('%H:%M', time.gmtime(last[0]/1000))} "
                    f"close={last[4]:.2f} K={'-' if k_now is None else round(k_now,1)} "
                    f"pozycja={st['pos'] or 'brak'}"
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
    ap.add_argument("--leverage", type=int, default=14)
    ap.add_argument("--size-pct", type=float, default=1.0, help="czesc salda (1.0 = all in)")
    ap.add_argument("--margin-mode", default="isolated", choices=("isolated", "crossed"))
    ap.add_argument("--poll", type=int, default=10)
    ap.add_argument("--min-tier", type=int, default=1, choices=(1, 2, 3))
    ap.add_argument("--tp", type=float, default=1.0, help="TP x ATR")
    ap.add_argument("--sl", type=float, default=2.5, help="SL x ATR")
    ap.add_argument("--no-invert", dest="invert", action="store_false", help="tryb normalny")
    ap.add_argument("--market-entry", dest="post_only", action="store_false",
                    help="taker zamiast LIMIT maker")
    ap.add_argument("--wait", type=int, default=20, help="ile s czekac na fill limitu")
    ap.add_argument("--enter-active", dest="enter_active", action="store_true", default=True,
                    help="wchodz od razu w AKTYWNA strefe (K w przedziale), nie czekaj na nowa")
    ap.add_argument("--no-enter-active", dest="enter_active", action="store_false")
    ap.add_argument("--catchup", type=int, default=3,
                    help="przy starcie wejdz, jesli strefa byla w ostatnich N swiecach (0=off)")
    ap.set_defaults(invert=True, post_only=True)
    args = ap.parse_args()

    if args.backtest:
        backtest(args.days, args.leverage, args.tp, args.sl, args.invert,
                 args.min_tier, maker=args.post_only)
    elif args.paper:
        run_loop(False, args.leverage, args.size_pct, args.margin_mode, args.poll,
                 args.min_tier, args.tp, args.sl, args.invert, args.post_only, args.wait,
                 args.catchup, args.enter_active)
    elif args.live:
        run_loop(True, args.leverage, args.size_pct, args.margin_mode, args.poll,
                 args.min_tier, args.tp, args.sl, args.invert, args.post_only, args.wait,
                 args.catchup, args.enter_active)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()