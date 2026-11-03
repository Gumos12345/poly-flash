#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
poly_dryrun_engine.py — WIELOWARIUNTOWY DRY-RUN (paper trading) dla Polymarket 5m/15m Up/Down
=============================================================================================
Silnik bez zależności (tylko stdlib: urllib/json/math/threading), więc działa też w Termuxie
bez `pip install`. Dane te same co w najr_live_UP_HOLD.py:
  * spot: data-api.binance.vision (fallback OKX -> Coinbase -> Kraken; api.binance.com bywa blokowane)
  * zmienność: klines 1m (mieszanka krótkiego i długiego okna, jak fin_vol w bocie)
  * rynki: Gamma ?slug={coin}-updown-{tf}-{start}  (start z nazwy sluga, nie z endDate)
  * orderbooki: CLOB /book (pełna głębokość; fill liczony po kolei po poziomach)
  * rozliczenie: Gamma ?slug=...&closed=true (outcomePrices 0/1); fallback TWAP60 z klines 1s

RÓŻNICA względem najr_live_UP_HOLD.py: tam wszystkie warianty dzielą JEDEN globalny CFG.
Tutaj każdy wariant ma WŁASNE parametry, własny bankroll i własną drabinkę stawki — można
równolegle testować max/min szansę, okna wejścia, model, TP, filtry jakości w jednym przebiegu.

Użycie:  python3 dryrun1_master.py [--report|--reset|--list|--minutes N|--bank 50|--stake 1.25]
"""

import argparse
import csv
import json
import math
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.request import Request, urlopen

# ------------------------------------------------------------------ KONFIG GLOBALNY
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
BN = "https://data-api.binance.vision"
OKX = "https://www.okx.com"
CB = "https://api.coinbase.com"
KR = "https://api.kraken.com"

UA = ("Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")

ASSETS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "XRP": "XRPUSDT",
          "DOGE": "DOGEUSDT", "BNB": "BNBUSDT", "HYPE": "HYPEUSDT"}
OKX_SYM = {"BTC": "BTC-USDT", "ETH": "ETH-USDT", "SOL": "SOL-USDT", "XRP": "XRP-USDT",
           "DOGE": "DOGE-USDT", "BNB": "BNB-USDT", "HYPE": "HYPE-USDT"}
CB_SYM = {"BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD", "XRP": "XRP-USD",
          "DOGE": "DOGE-USD", "BNB": "BNB-USD", "HYPE": "HYPE-USD"}
KR_SYM = {"BTC": "XBTUSD", "ETH": "ETHUSD", "SOL": "SOLUSD", "XRP": "XRPUSD",
          "DOGE": "XDGUSD", "BNB": "BNBUSD"}
PERIOD = {"5m": 300, "15m": 900}
FEE_RATE = 0.07          # crypto: fee = 0.07 * p * (1-p) na udział
SHRINK = 0.90            # ściągnięcie p do 0.5 (grube ogony), jak w bocie


def http_json(url, timeout=8.0, tries=2, headers=None):
    """GET -> json z ponowieniem; bez zależności zewnętrznych."""
    h = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        h.update(headers)
    last = None
    for i in range(tries):
        try:
            with urlopen(Request(url, headers=h), timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            last = e
            time.sleep(0.2 * (i + 1))
    raise last


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def t5_cdf(x):
    """Studenta t, 5 st. swobody (grubsze ogony = mniejsza pewność przy tym samym z)."""
    th = math.atan(x / math.sqrt(5.0))
    s, c = math.sin(th), math.cos(th)
    return 0.5 + (th + s * c * (1.0 + 2.0 / 3.0 * c * c)) / math.pi


def fee_ps(price):
    """Opłata takera na 1 udział: feeRate * p * (1-p)."""
    p = min(0.9999, max(0.0001, float(price)))
    return FEE_RATE * p * (1.0 - p)


def walk_fill(levels, budget):
    """Kupno za `budget` po kolejnych poziomach ask -> (shares, spent, avg_px)."""
    shares = spent = 0.0
    for px, size in levels:
        if px <= 0 or size <= 0:
            continue
        cash = px * size
        need = budget - spent
        if cash >= need:
            shares += need / px
            spent = budget
            break
        shares += size
        spent += cash
    if shares <= 0:
        return None
    return shares, spent, spent / shares


def walk_sell(levels, shares):
    """Sprzedaż `shares` po kolejnych poziomach bid -> (proceeds, avg_px)."""
    got = sold = 0.0
    for px, size in levels:
        if px <= 0 or size <= 0:
            continue
        take = min(size, shares - sold)
        if take <= 0:
            break
        got += take * px
        sold += take
        if sold >= shares - 1e-9:
            break
    if sold <= 0:
        return None
    return got, got / sold


# ------------------------------------------------------------------ DANE: SPOT + ZMIENNOŚĆ
class Feed:
    """Spot (batch) + klines + zmienność. Cache: spot 0 s, zmienność 90 s."""

    def __init__(self):
        self.spot, self.spot_ts = {}, {}
        self.vol_c, self.open_c = {}, {}
        self.ok = {"spot": "-", "vol": "-"}

    def refresh_spot(self, assets=None):
        assets = [a for a in (assets or list(ASSETS)) if a in ASSETS]
        got = {}
        try:
            syms = json.dumps([ASSETS[a] for a in assets], separators=(",", ":"))
            data = http_json(BN + "/api/v3/ticker/price?symbols=" + syms, timeout=5)
            m = {d["symbol"]: float(d["price"]) for d in data}
            got = {a: m[ASSETS[a]] for a in assets if ASSETS[a] in m}
        except Exception:
            pass
        if len(got) < len(assets):
            for a in assets:
                if a in got:
                    continue
                px = None
                try:
                    px = float(http_json(OKX + "/api/v5/market/ticker?instId=" + OKX_SYM[a], timeout=5)["data"][0]["last"])
                except Exception:
                    try:
                        px = float(http_json(CB + "/v2/prices/" + CB_SYM[a] + "/spot", timeout=5)["data"]["amount"])
                    except Exception:
                        if a in KR_SYM:
                            try:
                                px = float(list(http_json(KR + "/0/public/Ticker?pair=" + KR_SYM[a], timeout=5)["result"].values())[0]["c"][0])
                            except Exception:
                                px = None
                if px:
                    got[a] = px
        now = time.time()
        for a, p in got.items():
            self.spot[a], self.spot_ts[a] = p, now
        self.ok["spot"] = "%d/%d" % (len(got), len(assets))
        return got

    def spot_age(self, asset):
        return time.time() - self.spot_ts.get(asset, 0.0)

    def klines(self, asset, interval="1m", limit=240, end_ms=None):
        url = "%s/api/v3/klines?symbol=%s&interval=%s&limit=%d" % (BN, ASSETS[asset], interval, limit)
        if end_ms:
            url += "&endTime=%d" % int(end_ms)
        return http_json(url, timeout=8)

    def vol(self, asset, now=None):
        """(sigma_short, sigma_long, sigma_mix) w log-cena/sqrt(sek): mieszanka 60 barów i całego dnia."""
        now = now or time.time()
        c = self.vol_c.get(asset)
        if c and now - c[0] < 90:
            return c[1], c[2], c[3]
        try:
            pairs = [(int(k[0]) / 1000.0, float(k[4])) for k in self.klines(asset, "1m", 240)]
        except Exception:
            return None
        rs = []
        for i in range(1, len(pairs)):
            dt = pairs[i][0] - pairs[i - 1][0]
            a, b = pairs[i - 1][1], pairs[i][1]
            if 0 < dt <= 300 and a > 0 and b > 0:
                rs.append((math.log(b / a), dt))
        if len(rs) < 20:
            return None

        def var(x):
            return sum(r * r for r, _ in x) / max(1e-9, sum(d for _, d in x))

        v_s, v_l = var(rs[-60:]), var(rs)
        floor = 1.5e-4 ** 2
        out = (math.sqrt(max(v_s, floor)), math.sqrt(max(v_l, floor)),
               math.sqrt(max(0.6 * v_s + 0.4 * v_l, floor)))
        self.vol_c[asset] = (now, out[0], out[1], out[2])
        self.ok["vol"] = "OK"
        return out

    def open_price(self, asset, start):
        """Cena otwarcia okna: open świecy 1m zaczynającej się w `start`."""
        key = (asset, int(start))
        if key in self.open_c:
            return self.open_c[key]
        try:
            for k in self.klines(asset, "1m", 3, end_ms=(int(start) + 120) * 1000):
                if int(k[0]) // 1000 == int(start):
                    self.open_c[key] = float(k[1])
                    return self.open_c[key]
        except Exception:
            pass
        return None

    def twap60(self, asset, end_ts):
        """Przybliżenie Chainlink TWAP60: średnia z 60 świec 1s kończących się na `end_ts`."""
        try:
            cl = [float(k[4]) for k in self.klines(asset, "1s", 60, end_ms=int(end_ts) * 1000 - 1)]
            if cl:
                return sum(cl) / len(cl)
        except Exception:
            pass
        return None


# ------------------------------------------------------------------ DANE: RYNKI + ORDERBOOKI
class Markets:
    def __init__(self, book_ttl=2.5, mkt_ttl=30.0, workers=6):
        self.mkt_c, self.book_c = {}, {}
        self.book_ttl, self.mkt_ttl = book_ttl, mkt_ttl
        self.pool = ThreadPoolExecutor(max_workers=workers)
        self.err = self.req = 0

    @staticmethod
    def window(tf, now):
        per = PERIOD[tf]
        st = int(now // per * per)
        return st, st + per

    def market(self, slug, now=None):
        now = now or time.time()
        c = self.mkt_c.get(slug)
        if c and now - c[0] < self.mkt_ttl:
            return c[1]
        m = None
        try:
            d = http_json("%s/markets?slug=%s" % (GAMMA, slug), timeout=6)
            if d:
                m = d[0]
        except Exception:
            self.err += 1
        self.req += 1
        self.mkt_c[slug] = (now, m)
        if len(self.mkt_c) > 600:
            for k in list(self.mkt_c)[:200]:
                self.mkt_c.pop(k, None)
        return m

    @staticmethod
    def tokens(m):
        try:
            outs = [str(o).lower() for o in json.loads(m.get("outcomes") or "[]")]
            toks = json.loads(m.get("clobTokenIds") or "[]")
            return {("Up" if o == "up" else "Down"): toks[i]
                    for i, o in enumerate(outs) if i < len(toks) and o in ("up", "down")}
        except Exception:
            return {}

    def book(self, token, now=None):
        now = now or time.time()
        c = self.book_c.get(token)
        if c and now - c[0] < self.book_ttl:
            return c[1]
        b = None
        try:
            d = http_json("%s/book?token_id=%s" % (CLOB, token), timeout=6)
            asks = sorted((float(x["price"]), float(x["size"])) for x in d.get("asks", []))
            bids = sorted(((float(x["price"]), float(x["size"])) for x in d.get("bids", [])), reverse=True)
            b = {"asks": asks, "bids": bids}
        except Exception:
            self.err += 1
        self.req += 1
        self.book_c[token] = (now, b)
        if len(self.book_c) > 800:
            for k in list(self.book_c)[:300]:
                self.book_c.pop(k, None)
        return b

    def prefetch(self, tokens, now=None):
        now = now or time.time()
        todo = [t for t in tokens
                if not (self.book_c.get(t) and now - self.book_c[t][0] < self.book_ttl)]
        if todo:
            list(self.pool.map(lambda x: (x, self.book(x, now)), todo))

    def resolution(self, slug):
        """'Up' / 'Down' / None (nierozstrzygnięty)."""
        try:
            d = http_json("%s/markets?slug=%s&closed=true" % (GAMMA, slug), timeout=6)
        except Exception:
            return None
        if not d:
            return None
        m = d[0]
        if not m.get("closed"):
            return None
        try:
            outs = [str(o).lower() for o in json.loads(m.get("outcomes") or "[]")]
            px = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
        except Exception:
            return None
        if len(outs) == 2 and len(px) == 2 and max(px) >= 0.99:
            return "Up" if outs[px.index(max(px))] == "up" else "Down"
        return None


# ------------------------------------------------------------------ KONTEKST RYNKU (na cykl)
class Ctx:
    """Jeden (asset, tf) w cyklu: model + książka obu stron."""

    def __init__(self, asset, tf, now, spot, open_px, vol, books, tokens):
        self.asset, self.tf = asset, tf
        self.start, self.end = Markets.window(tf, now)
        self.rem = max(1.0, self.end - now)
        self.elapsed = now - self.start
        self.spot, self.open = spot, open_px
        self.sig_s, self.sig_l, self.sig = vol
        self.books, self.tokens = books, tokens
        self.d = math.log(spot / open_px) if open_px else 0.0
        self.z = self.d / (self.sig * math.sqrt(self.rem))
        self.ask, self.bid, self.mid, self.spread = {}, {}, {}, {}
        for side in ("Up", "Down"):
            b = books.get(side) or {}
            asks, bids = b.get("asks") or [], b.get("bids") or []
            self.ask[side] = asks[0][0] if asks else None
            self.bid[side] = bids[0][0] if bids else None
        # brak bidów po jednej stronie: dolna granica bid = 1 - ask(drugiej strony) (brak arbitrażu).
        # Bez tego filtr spreadu przepuszczał jednostronne/dziurawe książki (fałszywa "przewaga" 15-18c).
        for side, comp in (("Up", "Down"), ("Down", "Up")):
            if self.bid[side] is None and self.ask.get(comp) is not None:
                self.bid[side] = max(0.0, 1.0 - self.ask[comp])
        for side in ("Up", "Down"):
            if self.ask[side] is not None and self.bid[side] is not None:
                self.mid[side] = (self.ask[side] + self.bid[side]) / 2
                self.spread[side] = self.ask[side] - self.bid[side]
            else:
                self.mid[side] = self.ask[side]
                self.spread[side] = None
        b = books.get("Up") or {}
        bid_sz = sum(s for _, s in (b.get("bids") or [])[:5])
        ask_sz = sum(s for _, s in (b.get("asks") or [])[:5])
        self.imb = bid_sz / (bid_sz + ask_sz) if bid_sz + ask_sz > 0 else None

    def depth(self, side, levels=5):
        b = self.books.get(side) or {}
        return sum(s for _, s in (b.get("asks") or [])[:levels])


def model_probs(ctx, kind="v1", w_mkt=0.0, vol_cushion=1.0):
    """P(Up). v1 = normalny + shrink (jak s_bin). v2 = v1 + ogony t5 + zmienność krótka/długa.
    v3 = v2 + mikrostruktura (fair mieszane z mid rynku). Zwraca (p_up, sigma)."""
    sig = ctx.sig * vol_cushion
    cdf = norm_cdf
    if kind in ("v2", "v3"):
        w = min(1.0, max(0.0, 1.0 - ctx.rem / PERIOD[ctx.tf]))
        k = 0.35 + 0.65 * w
        sig = (k * ctx.sig_s + (1.0 - k) * ctx.sig_l) * vol_cushion
        cdf = t5_cdf
    z = ctx.d / (max(sig, 1e-9) * math.sqrt(ctx.rem))
    p = 0.5 + (cdf(z) - 0.5) * SHRINK
    if kind == "v3" and w_mkt > 0:
        mkt = ctx.mid.get("Up")
        if mkt is not None:
            p = (1.0 - w_mkt) * p + w_mkt * mkt
    return min(0.995, max(0.005, p)), sig


def net_edge(p, ask):
    """Przewaga netto po opłacie takera."""
    return p - ask - fee_ps(ask)


# ------------------------------------------------------------------ WARIANT = WŁASNA KSIĘGA
DEFAULT_LADDER = {
    "kind": "ladder",     # ladder | fixed | prop
    "start_bank": 50.0,
    "start_stake": 1.25,
    "step_bank": 0.50,    # +50% bankrolla na poziom: 50 -> 75 -> 112.5 = 1.25 / 1.875 / 2.8125
    "step_stake": 0.50,   # stawka +50% na poziom
    "down": False,        # False = stawka tylko rośnie (UP), True = rośnie i maleje (UD)
    "min_stake": 1.25,
    "max_stake": 60.0,
    "pct": 0.025,         # kind=prop: % kapitału na zakład
}


def ladder_stake(lad, bank, peak_level=0):
    """Poziom = floor(log(bank/start_bank)/log(1+step_bank)); stawka = start_stake*(1+step_stake)^poziom.
    Każdy próg bankrolla = przeliczenie ("reset") stawki."""
    kind = lad.get("kind", "ladder")
    b0 = max(1e-9, lad["start_bank"])
    if kind == "fixed":
        return lad["start_stake"], 0
    if kind == "prop":
        st = bank * lad.get("pct", 0.025)
        return max(lad["min_stake"], min(lad["max_stake"], st)), 0
    step_b = max(1e-4, lad["step_bank"])
    try:
        lvl = int(math.floor(math.log(max(bank, 1e-9) / b0) / math.log(1.0 + step_b)))
    except ValueError:
        lvl = 0
    if not lad.get("down", False):
        lvl = max(lvl, peak_level)          # UP: stawka nie spada
    st = lad["start_stake"] * (1.0 + lad.get("step_stake", 0.0)) ** lvl
    return max(lad["min_stake"], min(lad["max_stake"], st)), lvl


class VBook:
    """Księga wariantu: bankroll, stawka, pozycje, zamknięte transakcje, statystyki."""

    def __init__(self, v, start_bank=50.0):
        self.v, self.id, self.name = v, v["id"], v["name"]
        self.lad = dict(DEFAULT_LADDER)
        self.lad.update(v.get("ladder") or {})
        self.lad["start_bank"] = start_bank
        if v.get("start_stake"):
            self.lad["start_stake"] = v["start_stake"]
        self.start_bank = start_bank
        self.peak_level = 0
        self.positions, self.closed = {}, []
        self.realized = 0.0
        self.peak_equity = start_bank
        self.max_dd = 0.0
        self.blocked_until = {}
        self.sig_hist = {}
        self.halted = False

    def equity(self):
        return self.start_bank + self.realized

    def stake_now(self):
        st, lvl = ladder_stake(self.lad, self.equity(),
                               0 if self.lad.get("down") else self.peak_level)
        if not self.lad.get("down"):
            self.peak_level = max(self.peak_level, lvl)
        return st, lvl

    def dump(self):
        return {"id": self.id, "name": self.name, "realized": self.realized,
                "positions": list(self.positions.values()), "closed": self.closed[-500:],
                "peak_level": self.peak_level, "peak_equity": self.peak_equity,
                "max_dd": self.max_dd, "halted": self.halted}

    def load(self, d):
        self.realized = float(d.get("realized", 0.0) or 0.0)
        self.positions = {p["key"]: p for p in d.get("positions", [])}
        self.closed = d.get("closed", [])
        self.peak_level = int(d.get("peak_level", 0) or 0)
        self.peak_equity = float(d.get("peak_equity", self.start_bank) or self.start_bank)
        self.max_dd = float(d.get("max_dd", 0.0) or 0.0)
        self.halted = bool(d.get("halted", False))

    def stats(self):
        cl = self.closed
        n = len(cl)
        wins = sum(1 for t in cl if t["pnl"] > 0)
        pnl = sum(t["pnl"] for t in cl)
        staked = sum(t["cost"] for t in cl)
        run = pk = self.start_bank
        dd = 0.0
        for t in cl:
            run += t["pnl"]
            pk = max(pk, run)
            dd = max(dd, (pk - run) / pk if pk > 0 else 0.0)
        st, lvl = self.stake_now()
        per_tf, per_asset = {}, {}
        for t in cl:
            a = per_tf.setdefault(t["tf"], {"n": 0, "w": 0, "pnl": 0.0})
            a["n"] += 1
            a["w"] += 1 if t["pnl"] > 0 else 0
            a["pnl"] += t["pnl"]
            b = per_asset.setdefault(t["asset"], {"n": 0, "w": 0, "pnl": 0.0})
            b["n"] += 1
            b["w"] += 1 if t["pnl"] > 0 else 0
            b["pnl"] += t["pnl"]
        return {
            "id": self.id, "name": self.name, "n": n, "wins": wins, "losses": n - wins,
            "wr": (wins / n * 100.0) if n else 0.0, "pnl": pnl,
            "roi": (pnl / staked * 100.0) if staked > 0 else 0.0,
            "ret": (pnl / self.start_bank * 100.0) if self.start_bank else 0.0,
            "staked": staked, "equity": self.equity(), "dd": dd * 100.0,
            "stake": st, "lvl": lvl, "open": len(self.positions),
            "avg_px": statistics.fmean([t["entry"] for t in cl]) if cl else 0.0,
            "avg_edge": statistics.fmean([t["edge"] for t in cl]) if cl else 0.0,
            "tp_n": sum(1 for t in cl if t["exit"] == "TP"),
            "per_tf": per_tf, "per_asset": per_asset,
            "avg_hold": statistics.fmean([t["hold"] for t in cl]) if cl else 0.0,
        }


# ------------------------------------------------------------------ SILNIK
class Engine:
    def __init__(self, variants, set_name, start_bank=50.0, params=None):
        self.variants = variants
        self.set_name = set_name
        self.start_bank = start_bank
        self.params = params or {}
        self.feed = Feed()
        self.mk = Markets(book_ttl=self.params.get("book_ttl", 2.5),
                          mkt_ttl=self.params.get("mkt_ttl", 30.0),
                          workers=self.params.get("workers", 6))
        self.books = {v["id"]: VBook(v, start_bank) for v in variants}
        self.res_cache, self.res_ts = {}, {}
        self.ask_hist = {}
        self.root = os.path.dirname(os.path.abspath(__file__))
        self.state_path = os.path.join(self.root, "state", "%s.json" % set_name)
        self.csv_path = os.path.join(self.root, "reports", "%s_report.csv" % set_name)
        self.md_path = os.path.join(self.root, "reports", "%s_report.md" % set_name)
        self.tr_path = os.path.join(self.root, "reports", "%s_trades.jsonl" % set_name)
        self.events = []
        self.cycle = 0
        self.t0 = time.time()
        self.last_ctx = {}
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)

    # ---------- stan
    def save(self):
        d = {"ver": 1, "set": self.set_name, "start": self.t0, "start_bank": self.start_bank,
             "books": {str(k): b.dump() for k, b in self.books.items()}}
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f)
        os.replace(tmp, self.state_path)

    def load(self):
        if not os.path.exists(self.state_path):
            return False
        try:
            with open(self.state_path) as f:
                d = json.load(f)
        except Exception:
            return False
        for k, bd in (d.get("books") or {}).items():
            b = self.books.get(int(k))
            if b:
                b.load(bd)
        self.t0 = d.get("start", self.t0)
        return True

    def reset(self):
        for b in self.books.values():
            b.realized, b.positions, b.closed = 0.0, {}, []
            b.peak_level, b.peak_equity, b.max_dd, b.halted = 0, self.start_bank, 0.0, False
        for p in (self.state_path, self.csv_path, self.md_path, self.tr_path):
            if os.path.exists(p):
                os.remove(p)
        self.t0 = time.time()
        self.save()

    def log(self, msg):
        self.events.append("%s %s" % (datetime.now(timezone.utc).strftime("%H:%M:%S"), msg))
        self.events = self.events[-40:]

    # ---------- konteksty rynków
    def build_ctxs(self, now):
        """Aktywne okna 5m/15m -> spot/zmienność/orderbooki -> Ctx."""
        tfs = sorted({tf for v in self.variants for tf in v["tfs"]})
        assets = sorted({a for v in self.variants for a in (v.get("assets") or list(ASSETS))})
        self.feed.refresh_spot(assets)
        reqs = []
        for tf in tfs:
            st, end = Markets.window(tf, now)
            for a in assets:
                reqs.append((a, tf, st, end))

        def one(r):
            a, tf, st, end = r
            slug = "%s-updown-%s-%d" % (a.lower(), tf, st)
            try:
                m = self.mk.market(slug, now)
            except Exception:
                m = None
            return r, self.feed.open_price(a, st), m, slug

        jobs = []
        for (a, tf, st, end), op, m, slug in self.mk.pool.map(one, reqs):
            if not m or m.get("closed"):
                continue
            if self.feed.spot_age(a) > 6:
                continue
            spot = self.feed.spot.get(a)
            if not spot or not op:
                continue
            toks = self.mk.tokens(m)
            if len(toks) < 2:
                continue
            jobs.append((a, tf, st, end, spot, op, toks))
        if jobs:
            uniq = sorted({j[0] for j in jobs})
            vol = dict(zip(uniq, self.mk.pool.map(self.feed.vol, uniq)))
            self.mk.prefetch([t for j in jobs for t in j[6].values()], now)
            ctxs = {}
            for (a, tf, st, end, spot, op, toks) in jobs:
                if not vol.get(a):
                    continue
                books = {s: self.mk.book(t) for s, t in toks.items()}
                if not books.get("Up") or not books.get("Down"):
                    continue
                ctxs[(a, tf)] = Ctx(a, tf, now, spot, op, vol[a], books, toks)
        else:
            ctxs = {}
        self.last_ctx = ctxs
        return ctxs

    def resolve(self, slug, asset, start, end, now):
        """Wynik rynku: najpierw oficjalny (Gamma), po 20 s fallback TWAP60 vs open."""
        c = self.res_cache.get(slug)
        if c:
            return c
        if now - self.res_ts.get(slug, 0) < 5:
            return None
        self.res_ts[slug] = now
        r = self.mk.resolution(slug)
        if r:
            self.res_cache[slug] = r
            return r
        if now > end + 20:
            tw, op = self.feed.twap60(asset, end), self.feed.open_price(asset, start)
            if tw and op:
                return "Up" if tw > op else "Down"
        return None

    # ---------- zamknięcia
    def _close(self, b, p, pnl, exit_kind, px, now):
        p.update(status="closed", exit=exit_kind, exit_px=px, pnl=round(pnl, 6),
                 hold=round(now - p["t_open"], 1))
        b.realized += pnl
        b.closed.append(p)
        b.positions.pop(p["key"], None)
        eq = b.equity()
        b.peak_equity = max(b.peak_equity, eq)
        b.max_dd = max(b.max_dd, (b.peak_equity - eq) / b.peak_equity if b.peak_equity > 0 else 0.0)
        b.blocked_until[p["slug"]] = now + float(b.v.get("cooldown", 0) or 0)
        if b.v.get("dd_halt") and b.max_dd >= b.v["dd_halt"] and not b.halted:
            b.halted = True
            self.log("HALT %s: drawdown %.1f%%" % (b.name, b.max_dd * 100))
        try:
            with open(self.tr_path, "a") as f:
                f.write(json.dumps({"t": round(now, 1), "variant": b.name, "asset": p["asset"],
                                    "tf": p["tf"], "side": p["side"], "entry": round(p["entry"], 4),
                                    "exit": exit_kind, "exit_px": round(px or 0, 4),
                                    "pnl": round(pnl, 4), "stake": round(p["stake"], 3),
                                    "p": round(p["p"], 4), "edge": round(p["edge"], 4),
                                    "hold": p["hold"], "bank": round(eq, 2)}) + "\n")
        except Exception:
            pass

    def manage(self, now):
        """TP / stop-loss / rozliczenie pozycji."""
        for b in self.books.values():
            for key, p in list(b.positions.items()):
                if p["status"] != "open":
                    continue
                if now >= p["end"] + 2:
                    r = self.resolve(p["slug"], p["asset"], p["start"], p["end"], now)
                    if r:
                        win = p["side"] == r
                        self._close(b, p, (p["shares"] - p["cost"]) if win else -p["cost"],
                                    "WIN" if win else "LOSS", 1.0 if win else 0.0, now)
                    elif now > p["end"] + 240:
                        self._close(b, p, -p["cost"], "VOID", None, now)
                    continue
                bk = self.mk.book(p["tok"])
                if not bk or not bk["bids"]:
                    continue
                bid = bk["bids"][0][0]
                tp = p.get("tp")
                if tp and bid >= tp:
                    r2 = walk_sell(bk["bids"], p["shares"])
                    if r2:
                        proceeds, avg = r2
                        self._close(b, p, proceeds - p["shares"] * fee_ps(avg) - p["cost"], "TP", avg, now)
                        continue
                sl = p.get("sl")
                if sl and bid <= p["entry"] * (1.0 - sl) and p["rem_at_open"] > 30:
                    r2 = walk_sell(bk["bids"], p["shares"])
                    if r2:
                        proceeds, avg = r2
                        self._close(b, p, proceeds - p["shares"] * fee_ps(avg) - p["cost"], "STOP", avg, now)

    def _ask_hist(self, key, ask, now):
        h = [(t, a) for t, a in (self.ask_hist.get(key) or []) if now - t < 40]
        h.append((now, ask))
        self.ask_hist[key] = h
        old = [a for t, a in h if now - t >= 25]
        return old[0] if old else None

    # ---------- wejścia
    def consider(self, b, ctxs, now):
        """Ocena wariantu w cyklu: czy wchodzimy (i gdzie). Zwraca liczbę wejść."""
        v = b.v
        if b.halted:
            return 0
        st, lvl = b.stake_now()
        if st > b.equity() or st <= 0:
            return 0
        if len(b.positions) >= int(v.get("max_pos", 7)):
            return 0
        win_cnt = {}
        for p in b.positions.values():
            win_cnt[(p["tf"], p["start"])] = win_cnt.get((p["tf"], p["start"]), 0) + 1
        best = None
        for (asset, tf), c in ctxs.items():
            if tf not in v["tfs"] or (v.get("assets") and asset not in v["assets"]):
                continue
            lo, hi = (v.get("timing") or {}).get(tf, (0, PERIOD[tf]))
            if not (lo <= c.elapsed <= hi):
                continue
            if c.rem < float(v.get("min_rem", 8)):
                continue
            if v.get("max_rem") and c.rem > v["max_rem"]:
                continue
            if self.feed.spot_age(asset) > 5:
                continue
            slug = "%s-updown-%s-%d" % (asset.lower(), tf, c.start)
            if slug in b.positions or now < b.blocked_until.get(slug, 0):
                continue
            if v.get("max_per_window") and win_cnt.get((tf, c.start), 0) >= v["max_per_window"]:
                continue
            p_up, _s = model_probs(c, v.get("model", "v1"), v.get("w_mkt", 0.0), v.get("vol_cushion", 1.0))
            for side in ((v["side"],) if v.get("side") else ("Up", "Down")):
                p = p_up if side == "Up" else 1.0 - p_up
                ask = c.ask.get(side)
                if ask is None:
                    continue
                if not (float(v.get("min_px", 0.02)) <= ask <= float(v.get("max_px", 0.95))):
                    continue
                if p < float(v.get("min_fair", 0.0)):
                    continue
                edge = net_edge(p, ask)
                if edge < float(v.get("edge", 0.03)):
                    continue
                sp = c.spread.get(side)
                if sp is not None and sp > 0.20:
                    continue                     # TWARDA ochrona jakości danych: dziurawa książka
                if edge > float(v.get("edge_cap", 0.35)):
                    continue                     # "za piękne, by było prawdziwe" = stary/cienki kurs
                if v.get("max_spread") is not None and (c.spread.get(side) or 0.0) > float(v["max_spread"]):
                    continue
                if v.get("depth_x") and c.depth(side) < float(v["depth_x"]) * st / max(ask, 0.01):
                    continue
                if v.get("imb_filter") is not None:
                    if c.imb is None or (side == "Up" and c.imb < float(v["imb_filter"])) or \
                            (side == "Down" and c.imb > 1.0 - float(v["imb_filter"])):
                        continue
                if v.get("anti_chase"):
                    old = self._ask_hist((asset, tf, c.start, side), ask, now)
                    if old is not None and ask - old > float(v["anti_chase"]):
                        continue
                if v.get("persist"):
                    key = (asset, tf, c.start, side)
                    h = [(t, e) for t, e in b.sig_hist.get(key, []) if now - t < 90]
                    h.append((now, edge))
                    b.sig_hist[key] = h
                    need = int(v["persist"])
                    if len(h) < need or min(e for _, e in h[-need:]) < float(v.get("edge", 0.03)):
                        continue
                if best is None or edge > best[0]:
                    best = (edge, c, side, p, ask)
        if best is None:
            return 0
        edge, c, side, p, ask = best
        fill = walk_fill((c.books.get(side) or {}).get("asks") or [], st)
        if not fill:
            return 0
        shares, spent, avg = fill
        fee = shares * fee_ps(avg)
        slug = "%s-updown-%s-%d" % (c.asset.lower(), c.tf, c.start)
        b.positions["%d|%s" % (b.id, slug)] = {
            "key": "%d|%s" % (b.id, slug), "asset": c.asset, "tf": c.tf, "side": side, "slug": slug,
            "start": int(c.start), "end": int(c.end), "tok": c.tokens[side],
            "entry": round(avg, 5), "shares": round(shares, 6), "cost": round(spent + fee, 6),
            "stake": round(st, 4), "lvl": lvl, "p": round(p, 4), "edge": round(edge, 4),
            "t_open": round(now, 1), "status": "open", "tp": v.get("tp"), "sl": v.get("sl"),
            "spr": round(c.spread.get(side) or 0.0, 4), "rem_at_open": round(c.rem, 1),
            "bank_in": round(b.equity(), 2), "model": v.get("model", "v1"),
        }
        self.log("OPEN %-24s %s %s %-4s @%.3f p=%.3f edge=%.3f $%.2f"
                 % (b.name, c.asset, c.tf, side, avg, p, edge, st))
        return 1

    # ---------- pętla / raporty
    def heartbeat(self):
        top = sorted(self.books.values(), key=lambda b: -b.equity())[:3]
        parts = ["%s $%.2f n=%d" % (b.name[:20], b.equity(), len(b.closed)) for b in top]
        print("[%s] cykl %d | %s | %s | spot %s vol %s | req %d err %d" % (
            datetime.now(timezone.utc).strftime("%H:%M:%S"), self.cycle, self.set_name,
            " ; ".join(parts), self.feed.ok["spot"], self.feed.ok["vol"], self.mk.req, self.mk.err),
            flush=True)

    def run(self, minutes=None, sleep=2.0):
        self.load()
        self.save()
        deadline = self.t0 + minutes * 60 if minutes else None
        print("START %s | warianty: %d | bankroll $%.2f | stan: %s"
              % (self.set_name, len(self.variants), self.start_bank, os.path.relpath(self.state_path)),
              flush=True)
        while True:
            now = time.time()
            if deadline and now > deadline:
                print("KONIEC czasu (%.0f min)" % minutes, flush=True)
                break
            try:
                ctxs = self.build_ctxs(now)
                self.manage(now)
                for b in self.books.values():
                    self.consider(b, ctxs, now)
                self.cycle += 1
                if self.cycle % 10 == 0:
                    self.save()
                    self.heartbeat()
            except KeyboardInterrupt:
                print("przerwano", flush=True)
                break
            except Exception as e:
                self.log("ERR %r" % (e,))
            time.sleep(sleep)
        self.save()
        return self.report()

    def table(self):
        hdr = ("#", "wariant", "n", "W/L", "WR%", "PnL$", "ROI%", "ret%", "DD%", "kapital",
               "stawka", "lvl", "otw", "px", "edge", "TP")
        out = [hdr]
        for b in sorted(self.books.values(), key=lambda x: x.id):
            r = b.stats()
            out.append((str(r["id"]), r["name"][:26], str(r["n"]), "%d/%d" % (r["wins"], r["losses"]),
                        "%5.1f" % r["wr"], "%+7.2f" % r["pnl"], "%+6.1f" % r["roi"],
                        "%+6.1f" % r["ret"], "%4.1f" % r["dd"], "%6.2f" % r["equity"],
                        "%5.2f" % r["stake"], str(r["lvl"]), str(r["open"]),
                        "%.3f" % r["avg_px"], "%+.3f" % r["avg_edge"], str(r["tp_n"])))
        widths = [max(len(str(x[i])) for x in out) for i in range(len(hdr))]
        lines = []
        for i, r in enumerate(out):
            lines.append("  ".join(str(v).ljust(widths[j]) if j == 1 else str(v).rjust(widths[j])
                                   for j, v in enumerate(r)))
            if i == 0:
                lines.append("  ".join("-" * w for w in widths))
        return "\n".join(lines)

    def report(self):
        rows = [b.stats() for b in sorted(self.books.values(), key=lambda x: x.id)]
        txt = ["", "=" * 122,
               "%s — %d wariantów, bankroll startowy $%.2f" % (self.set_name, len(rows), self.start_bank),
               "=" * 122, self.table(), ""]
        ranked = sorted([r for r in rows if r["n"]], key=lambda r: -r["pnl"])
        if ranked:
            b = ranked[0]
            txt.append("NAJLEPSZY: %s | n=%d WR=%.1f%% PnL=$%+.2f (%.1f%% kapitału) DD=%.1f%% stawka=$%.2f"
                       % (b["name"], b["n"], b["wr"], b["pnl"], b["ret"], b["dd"], b["stake"]))
        txt.append("Zamkniętych transakcji: %d | czas: %.0f min | zapytania: %d (błędy %d)"
                   % (sum(r["n"] for r in rows), (time.time() - self.t0) / 60.0, self.mk.req, self.mk.err))
        out = "\n".join(txt)
        print(out, flush=True)
        self.write_csv(ranked)
        self.write_md(ranked)
        return out

    def write_csv(self, rows):
        cols = ["id", "name", "n", "wins", "losses", "wr", "pnl", "roi", "ret", "dd", "equity",
                "stake", "lvl", "open", "avg_px", "avg_edge", "tp_n", "avg_hold", "staked"]
        extra = ["model", "min_px", "max_px", "edge", "min_fair", "tp", "sl", "persist",
                 "imb_filter", "depth_x", "max_spread", "timing", "ladder"]
        with open(self.csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols + extra)
            for r in rows:
                b = self.books[r["id"]]
                v = b.v
                w.writerow([round(r[c], 4) if isinstance(r[c], float) else r[c] for c in cols] + [
                    v.get("model", ""), v.get("min_px", ""), v.get("max_px", ""), v.get("edge", ""),
                    v.get("min_fair", ""), v.get("tp", ""), v.get("sl", ""), v.get("persist", ""),
                    v.get("imb_filter", ""), v.get("depth_x", ""), v.get("max_spread", ""),
                    json.dumps(v.get("timing") or {}), json.dumps(b.lad)])
        return self.csv_path

    def write_md(self, rows):
        L = ["# %s — wyniki dry-runu" % self.set_name, "",
             "Start: %s UTC | bankroll startowy: **$%.2f** | wariantów: **%d** | transakcji: **%d**"
             % (datetime.fromtimestamp(self.t0, timezone.utc).strftime("%Y-%m-%d %H:%M"),
                self.start_bank, len(self.books), sum(r["n"] for r in rows)), "",
             "> Paper trading na żywych orderbookach Polymarket (CLOB) i cenach Binance. Zero prawdziwych "
             "zleceń. Fill po kolejnych poziomach książki, opłata takera 0.07·p·(1−p), rozliczenie z Gammy.", "",
             "## Ranking (po PnL)", "",
             "| # | wariant | n | W/L | WR% | PnL $ | ROI% | zwrot% | DD% | kapitał | stawka | otw | śr.px | śr.edge | TP |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            L.append("| %d | %s | %d | %d/%d | %.1f | %+.2f | %+.1f | %+.1f | %.1f | %.2f | %.2f | %d | %.3f | %+.3f | %d |"
                     % (r["id"], r["name"], r["n"], r["wins"], r["losses"], r["wr"], r["pnl"],
                        r["roi"], r["ret"], r["dd"], r["equity"], r["stake"], r["open"],
                        r["avg_px"], r["avg_edge"], r["tp_n"]))
        L += ["", "## Rozbicie 5m vs 15m", "", "| wariant | tf | n | W | PnL $ |", "|---|---|---|---|---|"]
        for r in rows:
            for tf, a in sorted(r["per_tf"].items()):
                L.append("| %s | %s | %d | %d | %+.2f |" % (r["name"][:24], tf, a["n"], a["w"], a["pnl"]))
        L += ["", "## Parametry wariantów", "",
              "| # | wariant | model | px pasmo | edge | fair min | TP | SL | timing | drabinka | filtry |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for b in sorted(self.books.values(), key=lambda x: x.id):
            v, lad = b.v, b.lad
            lad_s = ("%+.0f%%/%+.0f%%%s" % (lad["step_stake"] * 100, lad["step_bank"] * 100,
                                            "" if lad["down"] else " UP")) \
                if lad["kind"] == "ladder" else lad["kind"]
            filt = ", ".join("%s=%s" % (k, v[k]) for k in
                             ("persist", "imb_filter", "depth_x", "max_spread", "anti_chase",
                              "vol_cushion", "w_mkt", "dd_halt") if v.get(k))
            L.append("| %d | %s | %s | %.2f–%.2f | %.3f | %.2f | %s | %s | %s | %s | %s |"
                     % (v["id"], v["name"], v.get("model", "v1"), v.get("min_px", 0), v.get("max_px", 1),
                        v.get("edge", 0), v.get("min_fair", 0),
                        "-" if v.get("tp") is None else "%.2f" % v["tp"],
                        "-" if not v.get("sl") else "%.0f%%" % (v["sl"] * 100),
                        json.dumps(v.get("timing") or {}), lad_s, filt or "—"))
        with open(self.md_path, "w") as f:
            f.write("\n".join(L) + "\n")
        return self.md_path


# ------------------------------------------------------------------ CLI
def variant_line(v):
    return "  %2d. %-28s model=%-2s px[%.2f-%.2f] edge=%.3f fair>=%.2f tp=%-4s %s" % (
        v["id"], v["name"][:28], v.get("model", "v1"), v.get("min_px", 0.02), v.get("max_px", 0.95),
        v.get("edge", 0.03), v.get("min_fair", 0.0),
        "-" if v.get("tp") is None else "%.2f" % v["tp"], json.dumps(v.get("timing") or {}))


def cli(variants, set_name, argv=None):
    """Wspólny start dla dryrun1_master.py / dryrun2_master.py."""
    ap = argparse.ArgumentParser(description="Wielowariantowy dry-run Polymarket (%s)" % set_name)
    ap.add_argument("--report", action="store_true", help="tabela z zapisanego stanu i wyjście")
    ap.add_argument("--reset", action="store_true", help="wyzeruj stan/statystyki")
    ap.add_argument("--minutes", type=float, default=0, help="auto-stop po tylu minutach")
    ap.add_argument("--bank", type=float, default=50.0, help="bankroll startowy na wariant ($)")
    ap.add_argument("--stake", type=float, default=1.25, help="stawka startowa ($)")
    ap.add_argument("--sleep", type=float, default=2.0, help="przerwa między cyklami (s)")
    ap.add_argument("--list", action="store_true", help="tylko lista wariantów")
    args = ap.parse_args(argv)
    for v in variants:
        v.setdefault("ladder", {})
        if not v.get("start_stake"):
            v["start_stake"] = args.stake
        v["ladder"].setdefault("start_stake", v["start_stake"])
        v["ladder"].setdefault("min_stake", v["start_stake"])
    if args.list:
        print("%s — %d wariantów" % (set_name, len(variants)))
        for v in variants:
            print(variant_line(v))
        return None
    eng = Engine(variants, set_name, start_bank=args.bank)
    if args.reset:
        eng.reset()
        print("Stan wyzerowany:", eng.state_path)
    if args.report:
        eng.load()
        return eng.report()
    print("%s — %d wariantów:" % (set_name, len(variants)))
    for v in variants:
        print(variant_line(v))
    return eng.run(minutes=args.minutes or None, sleep=args.sleep)


if __name__ == "__main__":
    print("To jest silnik. Uruchom: python3 dryrun1_master.py  albo  python3 dryrun2_master.py")
