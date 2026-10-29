#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
poly_multi.py - multi-asset BTC/ETH/SOL/XRP/DOGE/BNB updown 5m.

Cechy (jak w botach z r/crypto, ale nasze):
  * 6 aktywow rownolegle, kazde niezaleznie,
  * 3 niezalezne sygnaly, wymagana zgoda >=2,
  * harmonogram godzinowy: bot uczy sie, w ktorych godzinach ma edge,
  * trzymanie do rozstrzygniecia ALBO wyjscie po bidzie,
  * pelne statystyki: transakcje, winrate, PnL, per godzina, CSV.

Sygnaly:
  S1 momentum  : skok ceny BTC/ETH/... >= threshold w oknie N s
  S2 zgoda     : kierunek zgodny z 2 ostatnimi pomiarami (brak zawahania)
  S3 cena rynku: ask <= max_entry (rynek jeszcze nie zdazyl podniesc ceny)

Tryby:
  python poly_multi.py                     # paper
  python poly_multi.py --hold-to-end       # trzymaj do rozstrzygniecia
  python poly_multi.py --live              # realne zlecenia (env: POLY_*)
"""
import argparse
import csv
import json
import os
import time
import urllib.parse
import urllib.request
from collections import deque, defaultdict

BITGET = "https://api.bitget.com"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
ASSETS = ["BTC", "ETH", "SOL", "XRP", "DOGE", "BNB", "HYPE", "ZEC"]
LOG = "poly_multi.log"
CSV = "poly_multi_trades.csv"
HOURS = "poly_multi_hours.json"


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get(url, params=None, timeout=10):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "poly-multi/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def prices():
    """{asset: cena} z Bitget spot (jedno zapytanie na wszystkie)."""
    want = {f"{a}USDT": a for a in ASSETS}
    d = get(f"{BITGET}/api/v2/spot/market/tickers")
    out = {}
    for row in d.get("data") or []:
        sym = row.get("symbol", "")
        if sym in want:
            try:
                out[want[sym]] = float(row["lastPr"])
            except (KeyError, ValueError):
                pass
    return out


def updown_markets():
    """{(asset, tf): {slug, tokens:{up,down}, end}} dla aktywnych rynkow 5m."""
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
            tag = f"{a.lower()}-updown-5m-"
            if tag not in slug:
                continue
            try:
                toks = json.loads(m["clobTokenIds"])
                outs = json.loads(m["outcomes"])
            except Exception:
                continue
            if len(toks) != 2 or len(outs) != 2:
                continue
            tmap = {str(outs[i]).strip().lower(): str(toks[i]) for i in range(2)}
            if "up" not in tmap or "down" not in tmap:
                continue
            # timestamp okna jest w slug: <asset>-updown-5m-<unix_ts_konca>
            try:
                ets = float(slug.rsplit("-", 1)[1])
            except (ValueError, IndexError):
                continue
            dt = ets - now
            if dt < -60:
                continue                       # okno juz minelo
            key = (a, "5m")
            # preferuj AKTYWNE okno (konczy sie w ciagu 15 min)
            score = 0 if 0 <= dt <= 900 else 1
            prev = out.get(key)
            if prev is None or (score, abs(dt)) < (prev["_score"], abs(prev["_dt"])):
                out[key] = {"slug": slug, "tokens": {"up": tmap["up"], "down": tmap["down"]},
                            "end": ets, "asset": a, "_score": score, "_dt": dt}
    for v in out.values():
        v.pop("_score", None)
    return out


def px(token, side):
    try:
        return float(get(f"{CLOB}/price", {"token_id": token, "side": side}).get("price") or 0)
    except Exception:
        return 0.0


def fee(p, rate=0.07):
    return rate * p * (1.0 - p)


def resolved(slug, side):
    try:
        d = get(f"{GAMMA}/markets", {"slug": slug})
        m = d[0] if isinstance(d, list) and d else None
        if not m or not m.get("closed"):
            return None
        outs = [str(o).strip().lower() for o in json.loads(m["outcomes"])]
        pr = json.loads(m["outcomePrices"])
        return 1.0 if float(pr[outs.index(side)]) > 0.5 else 0.0
    except Exception:
        return None


class Stats:
    """Statystyki globalne + per godzina (harmonogram)."""

    def __init__(self):
        self.trades = self.wins = self.losses = 0
        self.pnl = 0.0
        self.by_hour = defaultdict(lambda: {"w": 0, "l": 0, "pnl": 0.0})
        self.by_asset = defaultdict(lambda: {"w": 0, "l": 0, "pnl": 0.0})
        if os.path.exists(HOURS):
            try:
                with open(HOURS) as f:
                    for h, v in json.load(f).items():
                        self.by_hour[int(h)] = v
            except Exception:
                pass
        if not os.path.exists(CSV):
            with open(CSV, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(["ts", "slug", "asset", "side", "entry", "exit",
                                        "shares", "cost", "pnl", "result", "reason", "hour"])

    def save_hours(self):
        try:
            with open(HOURS, "w") as f:
                json.dump({str(k): v for k, v in self.by_hour.items()}, f)
        except Exception:
            pass

    def record(self, tr, exit_px, reason):
        sh, cost, entry = tr["shares"], tr["cost"], tr["entry"]
        proceeds = sh * exit_px * (1 - fee(exit_px))
        pnl = proceeds - cost
        res = "win" if pnl > 0 else ("loss" if pnl < 0 else "flat")
        hour = time.localtime().tm_hour
        self.trades += 1
        self.pnl += pnl
        if res == "win":
            self.wins += 1
            self.by_hour[hour]["w"] += 1
            self.by_asset[tr["asset"]]["w"] += 1
        elif res == "loss":
            self.losses += 1
            self.by_hour[hour]["l"] += 1
            self.by_asset[tr["asset"]]["l"] += 1
        self.by_hour[hour]["pnl"] += pnl
        self.by_asset[tr["asset"]]["pnl"] += pnl
        self.save_hours()
        with open(CSV, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([int(time.time()), tr["slug"], tr["asset"], tr["side"],
                                    round(entry, 4), round(exit_px, 4), round(sh, 4),
                                    round(cost, 4), round(pnl, 4), res, reason, hour])
        log(f"  ZAMKNIETE {tr['asset']} {tr['side'].upper()} {entry:.3f}->{exit_px:.3f} "
            f"PnL=${pnl:+.3f} ({reason}) | {self.summary()}")

    def hour_ok(self, hour, min_n=3):
        """Czy w tej godzinie warto grac (po min_n transakcjach i dodatnim PnL)."""
        h = self.by_hour.get(hour)
        if not h:
            return True
        n = h["w"] + h["l"]
        if n < min_n:
            return True
        return h["pnl"] > 0

    @property
    def winrate(self):
        d = self.wins + self.losses
        return 100.0 * self.wins / d if d else 0.0

    def summary(self):
        return (f"n={self.trades} W/L={self.wins}/{self.losses} "
                f"WR={self.winrate:.1f}% PnL=${self.pnl:+.3f}")


def fair_value(move_pct, secs_left, window_total=300):
    """
    Ile NAPRAWDE warte jest 'Up' po ruchu move_pct w pozostalym czasie.
    Model: pozostaly czas decyduje o wariancji. Maly ruch na poczatku = ~50%.
    Im blizej konca i im wiekszy ruch, tym blizej 1.0/0.0.
    """
    frac = max(0.0, min(1.0, secs_left / window_total))     # ile czasu zostalo
    # im wiecej czasu zostalo, tym mniejsza pewnosc ze ruch sie utrzyma
    conf = (1.0 - frac) ** 0.5
    # ruch w % -> odchylenie (0.2% => ~0.5 sigma)
    sigma = abs(move_pct) / 0.2
    prob = 0.5 + min(0.45, 0.5 * conf * min(1.0, sigma / 2.0))
    return prob if move_pct > 0 else 1.0 - prob


def signals_agree(hist, window, threshold, asset_px):
    """
    3 niezalezne sygnaly -> wymagana zgoda >=2.
    Zwraca 'up'/'down'/None.
    """
    if len(hist) < 3:
        return None
    t0, p0 = hist[0]
    move = asset_px - p0
    if abs(move) < threshold:
        return None
    vote_up = 0
    vote_dn = 0
    # S1: momentum w oknie
    if move > 0:
        vote_up += 1
    else:
        vote_dn += 1
    # S2: zgoda - ostatnie 2 pomiary w tym samym kierunku
    if len(hist) >= 3:
        d1 = hist[-1][1] - hist[-2][1]
        d2 = hist[-2][1] - hist[-3][1]
        if d1 > 0 and d2 > 0:
            vote_up += 1
        elif d1 < 0 and d2 < 0:
            vote_dn += 1
    # S3: sila skoku (>1.5x threshold = mocny)
    if abs(move) >= threshold * 1.5:
        if move > 0:
            vote_up += 1
        else:
            vote_dn += 1
    if vote_up >= 2 and vote_up > vote_dn:
        return "up"
    if vote_dn >= 2 and vote_dn > vote_up:
        return "down"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--hold-to-end", dest="hold_to_end", action="store_true", default=True,
                    help="trzymaj do rozstrzygniecia (domyslnie TAK)")
    ap.add_argument("--no-hold", dest="hold_to_end", action="store_false")
    ap.add_argument("--threshold", type=float, default=0.002, help="skok jako %% ceny (0.002=0.2%%)")
    ap.add_argument("--window", type=int, default=20)
    ap.add_argument("--max-entry", type=float, default=0.80)
    ap.add_argument("--exit-bid", type=float, default=0.90)
    ap.add_argument("--stop-bid", type=float, default=0.40)
    ap.add_argument("--hold", type=int, default=150)
    ap.add_argument("--stake", type=float, default=2.0)
    ap.add_argument("--cooldown", type=int, default=45)
    ap.add_argument("--min-hours-n", type=int, default=3)
    ap.add_argument("--min-edge", type=float, default=0.04,
                    help="min. przewaga fair-ask (0.04 = 4 centy)")
    ap.add_argument("--max-open", type=int, default=2,
                    help="max pozycji naraz (aktywa sa skorelowane!)")
    ap.add_argument("--poll", type=float, default=2.0)
    args = ap.parse_args()

    broker = bot = None
    if args.live:
        import bot_v2_dry_v3 as bot
        broker = bot.LiveBroker()
        log("[LIVE] prawdziwe zlecenia")
    else:
        log("[PAPER] symulacja")

    st = Stats()
    hist = {a: deque() for a in ASSETS}
    open_pos = {}          # asset -> tr
    last_entry = {a: 0.0 for a in ASSETS}
    mk_cache = {"ts": 0.0, "mk": {}}
    log(f"START aktywa={ASSETS} thr={args.threshold*100:.2f}% win={args.window}s "
        f"max_entry={args.max_entry} stake=${args.stake} hold_to_end={args.hold_to_end}")

    while True:
        try:
            now = time.time()
            pxs = prices()
            if not pxs:
                time.sleep(args.poll)
                continue
            for a, p in pxs.items():
                hist[a].append((now, p))
                while hist[a] and now - hist[a][0][0] > args.window:
                    hist[a].popleft()

            if now - mk_cache["ts"] > 30:
                mk_cache["mk"] = updown_markets()
                mk_cache["ts"] = now
            mks = mk_cache["mk"]
            if mks and int(now) % 120 == 1:
                far = [v for v in mks.values() if v["_dt"] is None or v["_dt"] > 900]
                if len(far) == len(mks):
                    d0 = next(iter(mks.values()))
                    log(f"UWAGA: brak aktywnego okna 5m (najblizsze za {d0['_dt']/60:.0f} min) "
                        f"- sprawdz zegar systemowy")

            # --- zarzadzanie pozycjami ---
            for a in list(open_pos.keys()):
                tr = open_pos[a]
                if args.hold_to_end:
                    out = resolved(tr["slug"], tr["side"])
                    if out is not None:
                        st.record(tr, out, "rozstrzygniecie")
                        del open_pos[a]
                    continue
                bid = px(tr["token"], "sell")
                held = now - tr["ts"]
                if bid <= 0:
                    st.record(tr, tr["entry"] * 0.5, "brak bidu")
                    del open_pos[a]
                elif bid >= args.exit_bid:
                    st.record(tr, bid, "TP")
                    del open_pos[a]
                elif bid <= args.stop_bid:
                    st.record(tr, bid, "SL")
                    del open_pos[a]
                elif held > args.hold and bid > tr["entry"] * 1.03:
                    st.record(tr, bid, "czas+zysk")
                    del open_pos[a]
                elif held > args.hold * 4:
                    st.record(tr, bid, "czas-awaryjnie")   # tylko po 4x czasie
                    del open_pos[a]

            # --- nowe wejscia ---
            hour = time.localtime().tm_hour
            if st.hour_ok(hour, args.min_hours_n):
                for a in ASSETS:
                    if len(open_pos) >= args.max_open:
                        break
                    if a in open_pos or (a, "5m") not in mks:
                        continue
                    if now - last_entry[a] < args.cooldown:
                        continue
                    mk = mks[(a, "5m")]
                    if mk["end"] - now < 45:
                        continue          # nie wchodz w ostatnie 45 s rynku
                    side = signals_agree(hist[a], args.window, args.threshold, pxs[a])
                    if not side:
                        continue
                    token = mk["tokens"][side]
                    ask = px(token, "buy")
                    p0 = hist[a][0][1]
                    move_pct = (pxs[a] - p0) / p0 * 100.0
                    secs_left = mk["end"] - now
                    fair = fair_value(abs(move_pct) if side == "up" else -abs(move_pct), secs_left)
                    edge = fair - ask
                    if not (0 < ask <= args.max_entry):
                        continue
                    if edge < args.min_edge:
                        if int(now) % 60 == 0:
                            log(f"  {a} {side.upper()} pominięte: fair={fair:.2f} ask={ask:.2f} "
                                f"edge={edge:+.3f} < {args.min_edge}")
                        continue
                    log(f"  {a} fair={fair:.2f} ask={ask:.2f} EDGE={edge:+.3f}")
                    shares = args.stake / ask
                    cost = args.stake + shares * fee(ask)
                    tr = {"ts": now, "slug": mk["slug"], "asset": a, "side": side,
                          "token": token, "entry": ask, "shares": shares, "cost": cost}
                    open_pos[a] = tr
                    last_entry[a] = now
                    log(f"KUPNO {a} {side.upper()} {shares:.2f} akcji @ {ask:.3f} "
                        f"koszt=${cost:.3f} | {mk['slug'][-14:]}")
                    if args.live and broker:
                        try:
                            r = broker.buy_no(token, args.stake, ask,
                                              bot.get_tick_size(token), fee(ask))
                            log(f"  [LIVE] {str(r)[:100]}")
                        except Exception as e:
                            log(f"  [LIVE ERR] {e!r}")
            elif int(now) % 60 == 0:
                log(f"godzina {hour} zablokowana (ujemny PnL) | {st.summary()}")

            if int(now) % 120 == 0:
                log(f"NASLUCH {len(mks)} rynkow | otwarte={len(open_pos)} | {st.summary()}")

        except KeyboardInterrupt:
            log("[STOP] Ctrl+C")
            break
        except Exception as e:
            log(f"[ERR] {e!r}")
        time.sleep(args.poll)

    print("\n=== PODSUMOWANIE ===")
    print(st.summary())
    print("\nper aktywo:")
    for a, v in sorted(st.by_asset.items()):
        n = v["w"] + v["l"]
        print(f"  {a:5s} n={n:3d} W/L={v['w']}/{v['l']} PnL=${v['pnl']:+.3f}")
    print("\nper godzina:")
    for h, v in sorted(st.by_hour.items()):
        n = v["w"] + v["l"]
        if n:
            print(f"  {h:02d}:00 n={n:3d} W/L={v['w']}/{v['l']} PnL=${v['pnl']:+.3f}")


if __name__ == "__main__":
    main()