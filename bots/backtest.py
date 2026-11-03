#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BACKTEST obu dry-runów na danych historycznych Polymarket + Binance.
====================================================================
Co robi: dla każdego okna 5m/15m w wybranym zakresie odtwarza warunki z backtestu na żywo:
  * cena rynkowa: CLOB /prices-history (startTs..endTs, fidelity=1 -> punkty co ~60 s)
  * model: Binance 1m (open okna + close w chwili snapshotu + zmienność z 240 barów)
  * wejście/TP/SL/rozliczenie: DOKŁADNIE ta sama logika i te same 67 wariantów co w dry-runach
    (import VARIANTS z dryrun1_master.py i dryrun2_master.py)
  * wynik: BACKTEST.html (ta sama "piękna tabela") + reports/BACKTEST.csv

Użycie:
  python3 backtest.py --days 1                       # ostatnia doba, BTC/ETH/SOL, 5m+15m
  python3 backtest.py --days 7 --assets BTC,ETH      # tydzień, 2 monety (dłużej)
  python3 backtest.py --hours 4 --assets BTC --tfs 5m
  python3 backtest.py --days 1 --resume              # dokończ po przerwaniu (cache na dysku)

OGRANICZENIA (uczciwie):
  1. prices-history to cena transakcyjna/środek, NIE książka -> brak głębokości; poślizg modelowany
     stałym parametrem --slip (domyślnie 1c). Filtr głębokości (depth_x) jest więc nieaktywny.
  2. Rozdzielczość czasu to ~60 s, więc okna wejścia typu "po 2 min" mają 2-3 punkty decyzyjne.
  3. Wynik rynku bierzemy z Gammy (outcomePrices 0/1) - to jest prawda, nie aproksymacja.
"""
import argparse
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import poly_dryrun_engine as E  # noqa: E402
import report_rich as R  # noqa: E402
import dryrun1_master as D1  # noqa: E402
import dryrun2_master as D2  # noqa: E402

CACHE = os.path.join(ROOT, "backtest_cache")
FEE = E.FEE_RATE


def gj(url, timeout=12, tries=3):
    last = None
    for i in range(tries):
        try:
            return E.http_json(url, timeout=timeout, tries=1)
        except Exception as ex:
            last = ex
            time.sleep(0.4 * (i + 1))
    raise last


def cpath(asset, tf, st):
    return os.path.join(CACHE, "%s_%s_%d.json" % (asset, tf, st))


def fetch_window(asset, tf, st, per, slip):
    """Zwraca dict z historia ceny Up i wynikiem rynku (albo None gdy okna nie ma)."""
    p = cpath(asset, tf, st)
    if os.path.exists(p):
        try:
            with open(p) as f:
                d = json.load(f)
            if d.get("ok"):
                return d
        except Exception:
            pass
    slug = "%s-updown-%s-%d" % (asset.lower(), tf, st)
    out = {"ok": False, "slug": slug, "asset": asset, "tf": tf, "start": st, "end": st + per}
    try:
        mk = gj("%s/markets?slug=%s&closed=true" % (E.GAMMA, slug))
        if not mk:
            return None
        m = mk[0]
        outs = [str(o).lower() for o in json.loads(m.get("outcomes") or "[]")]
        px = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
        toks = json.loads(m.get("clobTokenIds") or "[]")
        if len(outs) != 2 or len(px) != 2 or len(toks) != 2:
            return None
        up_i = outs.index("up")
        win = "Up" if px[up_i] > px[1 - up_i] else "Down"
        h = gj("%s/prices-history?market=%s&startTs=%d&endTs=%d&fidelity=1"
               % (E.CLOB, toks[up_i], st, st + per))
        hist = [[int(x["t"]), float(x["p"])] for x in (h.get("history") or [])
                if st <= int(x["t"]) <= st + per]
        if len(hist) < 2:
            return None
        out.update(ok=True, win=win, hist=hist)
        with open(p, "w") as f:
            json.dump(out, f)
        return out
    except Exception:
        return None


def klines_range(asset, since, until):
    """Klines 1m [since-240min, until] -> lista (ts, open, close). Cache w pamięci."""
    key = (asset, since // 3600, until // 3600)
    if key in KL:
        return KL[key]
    out = []
    t0 = int(since - 240 * 60)
    while t0 < until:
        try:
            d = gj("%s/api/v3/klines?symbol=%s&interval=1m&limit=1000&startTime=%d"
                   % (E.BN, E.ASSETS[asset], t0 * 1000))
        except Exception:
            break
        if not d:
            break
        for k in d:
            out.append((int(k[0]) // 1000, float(k[1]), float(k[4])))
        t0 = int(d[-1][0]) // 1000 + 60
        if len(d) < 1000:
            break
    KL[key] = out
    return out


KL = {}


def vol_at(kl, t):
    """Zmienność (short, long, mix) z barów do chwili t - jak Feed.vol."""
    rows = [(ts, c) for ts, _o, c in kl if ts <= t][-240:]
    rs = []
    for i in range(1, len(rows)):
        dt = rows[i][0] - rows[i - 1][0]
        a, b = rows[i - 1][1], rows[i][1]
        if dt == 60 and a > 0 and b > 0:
            rs.append((math.log(b / a), dt))
    if len(rs) < 20:
        return None

    def var(x):
        return sum(r * r for r, _ in x) / max(1e-9, sum(d for _, d in x))
    vs, vl = var(rs[-60:]), var(rs)
    fl = 1.5e-4 ** 2
    return (math.sqrt(max(vs, fl)), math.sqrt(max(vl, fl)), math.sqrt(max(0.6 * vs + 0.4 * vl, fl)))


def open_close_at(kl, st, t):
    """Cena otwarcia okna (open świecy st) i spot w chwili t (close świecy <= t)."""
    o = None
    c = None
    lim = int(t // 60 * 60)
    for ts, op, cl in kl:
        if ts == st and o is None:
            o = op
        if st + 60 <= ts <= lim:
            c = cl
    if o is None or c is None:
        return None, None
    return o, c


def build_ctxs(w, kl, slip):
    """Syntetyczne Ctx dla każdego punktu historii (książka: ask=px+slip, bid=px-slip)."""
    out = []
    per = E.PERIOD[w["tf"]]
    for t, pu in w["hist"]:
        if not (w["start"] < t < w["end"] - 5):
            continue
        op, spot = open_close_at(kl, w["start"], t)
        if not op or not spot:
            continue
        vol = vol_at(kl, t)
        if not vol:
            continue
        books = {"Up": {"asks": [(min(0.999, pu + slip), 1e6)], "bids": [(max(0.001, pu - slip), 1e6)]},
                 "Down": {"asks": [(min(0.999, 1 - pu + slip), 1e6)],
                          "bids": [(max(0.001, 1 - pu - slip), 1e6)]}}
        c = E.Ctx(w["asset"], w["tf"], t, spot, op, vol, books, {"Up": "sim", "Down": "sim"})
        out.append((c, t))
    return out


def gate(v, c, prev):
    """Filtry wejścia - ta sama logika co Engine.consider (bez książki: brak imb/depth/anti-chase)."""
    tf = c.tf
    if tf not in v["tfs"]:
        return None
    if v.get("assets") and c.asset not in v["assets"]:
        return None
    lo, hi = (v.get("timing") or {}).get(tf, (0, E.PERIOD[tf]))
    if not (lo <= c.elapsed <= hi):
        return None
    if c.rem < float(v.get("min_rem", 8)):
        return None
    if v.get("max_rem") and c.rem > v["max_rem"]:
        return None
    p_up, _s = E.model_probs(c, v.get("model", "v1"), v.get("w_mkt", 0.0), v.get("vol_cushion", 1.0))
    best = None
    for side in ((v["side"],) if v.get("side") else ("Up", "Down")):
        p = p_up if side == "Up" else 1.0 - p_up
        ask = c.ask.get(side)
        if ask is None:
            continue
        if not (float(v.get("min_px", 0.02)) <= ask <= float(v.get("max_px", 0.95))):
            continue
        if p < float(v.get("min_fair", 0.0)):
            continue
        edge = E.net_edge(p, ask)
        if edge < float(v.get("edge", 0.03)):
            continue
        sp = c.spread.get(side)
        if sp is not None and sp > 0.20:
            continue
        if edge > float(v.get("edge_cap", 0.35)):
            continue
        if v.get("max_spread") is not None and (sp or 0.0) > float(v["max_spread"]):
            continue
        if v.get("persist"):
            if prev is None or prev < float(v.get("edge", 0.03)):
                continue
        if best is None or edge > best[0]:
            best = (edge, side, p, ask)
    return best


def run_variant(v, wins_ctx, bank=50.0):
    """Symulacja jednego wariantu na wszystkich oknach. Zwraca VBook z zamkniętymi transakcjami."""
    b = E.VBook(v, bank)
    for w, snaps in wins_ctx:
        if not snaps:
            continue
        lo, hi = (v.get("timing") or {}).get(w["tf"], (0, E.PERIOD[w["tf"]]))
        if not any(lo <= c.elapsed <= hi for c, _t in snaps):
            continue
        prev_edge = None
        for i, (c, t) in enumerate(snaps):
            st, lvl = b.stake_now()
            if st <= 0 or st > b.equity():
                break                    # brak kapitalu na stawke (na zywo tez nie wchodzimy)
            hit = gate(v, c, prev_edge)
            if hit is None:
                p_up, _s = E.model_probs(c, v.get("model", "v1"), v.get("w_mkt", 0.0), v.get("vol_cushion", 1.0))
                side = "Up" if p_up >= 0.5 else "Down"
                p = p_up if side == "Up" else 1 - p_up
                a = c.ask.get(side)
                prev_edge = E.net_edge(p, a) if a is not None else None
                continue
            edge, side, p, ask = hit
            prev_edge = edge
            shares = st / ask
            fee = shares * E.fee_ps(ask)
            cost = st + fee
            tp, sl = v.get("tp"), v.get("sl")
            pnl = None
            tj = snaps[-1][1]          # domyslnie: moment rozliczenia (gdy nie ma TP/SL)
            exit_kind = exit_px = None
            for j in range(i + 1, len(snaps)):
                cj, tj = snaps[j]
                bid = cj.bid.get(side)
                if bid is None:
                    continue
                if tp and bid >= tp:
                    pnl = shares * bid - shares * E.fee_ps(bid) - cost
                    exit_kind, exit_px = "TP", bid
                    break
                if sl and bid <= ask * (1.0 - sl) and c.rem > 30:
                    pnl = shares * bid - shares * E.fee_ps(bid) - cost
                    exit_kind, exit_px = "STOP", bid
                    break
            if pnl is None:
                win = side == w["win"]
                pnl = (shares - cost) if win else -cost
                exit_kind, exit_px = ("WIN" if win else "LOSS"), (1.0 if win else 0.0)
            b.realized += pnl
            eq = b.equity()
            b.peak_equity = max(b.peak_equity, eq)
            b.max_dd = max(b.max_dd, (b.peak_equity - eq) / b.peak_equity if b.peak_equity > 0 else 0.0)
            b.closed.append(dict(
                key="%d|%s" % (b.id, w["slug"]), asset=w["asset"], tf=w["tf"], side=side,
                slug=w["slug"], start=w["start"], end=w["end"], tok="sim", entry=round(ask, 5),
                shares=round(shares, 6), cost=round(cost, 6), stake=round(st, 4), lvl=lvl,
                p=round(p, 4), edge=round(edge, 4), t_open=float(t), status="closed", tp=tp, sl=sl,
                spr=round(c.spread.get(side) or 0.0, 4), rem_at_open=round(c.rem, 1),
                bank_in=round(b.equity() - pnl, 2), model=v.get("model", "v1"),
                exit=exit_kind, exit_px=exit_px, pnl=round(pnl, 6), hold=float(tj - t)))
            break
    return b


def main(argv=None):
    ap = argparse.ArgumentParser(description="Backtest obu dry-runow na danych historycznych")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--days", type=float, default=1.0, help="ile dni wstecz (domyslnie 1)")
    g.add_argument("--hours", type=float, default=0.0, help="ile godzin wstecz (nadpisuje --days)")
    ap.add_argument("--until", type=float, default=0.0, help="koniec zakresu (epoch s; 0 = teraz)")
    ap.add_argument("--assets", default="BTC,ETH,SOL")
    ap.add_argument("--tfs", default="5m,15m")
    ap.add_argument("--slip", type=float, default=0.01, help="poslizg/ask premium na punkt (domyslnie 1c)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--sets", default="both", choices=["both", "1", "2"])
    ap.add_argument("--limit", type=int, default=0, help="max okien (test)")
    ap.add_argument("--bank", type=float, default=50.0)
    a = ap.parse_args(argv)

    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    until = a.until or time.time()
    span = a.hours * 3600 if a.hours else a.days * 86400
    since = until - span
    assets = [x.strip().upper() for x in a.assets.split(",") if x.strip()]
    tfs = [x.strip() for x in a.tfs.split(",") if x.strip()]
    todo = []
    for tf in tfs:
        per = E.PERIOD[tf]
        st = int(until // per * per) - per
        while st >= int(since // per * per):
            for asset in assets:
                todo.append((asset, tf, st))
            st -= per
    if a.limit:
        todo = todo[:a.limit]
    print("BACKTEST: %d okien (%s) | %s -> %s | slip %.0fc | cache: %s"
          % (len(todo), ",".join(tfs), time.strftime("%m-%d %H:%M", time.gmtime(since)),
             time.strftime("%m-%d %H:%M", time.gmtime(until)), a.slip * 100, os.path.relpath(CACHE)))

    wins = []
    done = [0]
    t0 = time.time()

    def one(job):
        asset, tf, st = job
        r = fetch_window(asset, tf, st, E.PERIOD[tf], a.slip)
        done[0] += 1
        if done[0] % 40 == 0 or done[0] == len(todo):
            print("  pobrano %d/%d (%.0f s)" % (done[0], len(todo), time.time() - t0), flush=True)
        return r

    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        for r in ex.map(one, todo):
            if r and r.get("ok"):
                wins.append(r)
    if not wins:
        print("Brak danych - okna nie istnieja albo API odrzucilo. Sprobuj innego zakresu.")
        return 1
    print("OK: %d okien z historia cen (%.1f%% pokrycia)" % (len(wins), 100.0 * len(wins) / len(todo)))

    kl = {}
    for asset in assets:
        kl[asset] = klines_range(asset, since, until)
        print("  klines %-4s: %d barow 1m" % (asset, len(kl[asset])))

    wins_ctx = []
    for w in wins:
        snaps = build_ctxs(w, kl[w["asset"]], a.slip)
        if snaps:
            wins_ctx.append((w, snaps))
    print("ctx gotowe: %d okien, %d punktow decyzyjnych" % (len(wins_ctx), sum(len(s) for _w, s in wins_ctx)))

    sets = []
    if a.sets in ("both", "1"):
        sets.append(("BACKTEST — przebieg 1 (25 wariantów)", D1.VARIANTS))
    if a.sets in ("both", "2"):
        sets.append(("BACKTEST — przebieg 2 (42 warianty)", D2.VARIANTS))
    blocks, allm = [], []
    for title, vs in sets:
        ms = []
        for v in vs:
            b = run_variant(v, wins_ctx, a.bank)
            m = R.metrics(b, since)
            m["set"] = title.split("(")[0].strip()
            ms.append(m)
        ms.sort(key=lambda m: -m["pnl"])
        allm += ms
        n = sum(m["n"] for m in ms)
        pnl = sum(m["pnl"] for m in ms)
        print("\n%s: wariantow=%d transakcji=%d suma=%+.2f$" % (title, len(ms), n, pnl))
        for m in ms[:8]:
            print("  %-26s n=%-4d WR=%5.1f%% pnl=%+8.2f$ PF=%-6s DD=%.1f%%"
                  % (m["name"], m["n"], m["wr"], m["pnl"],
                     ("inf" if math.isinf(m["pf"]) else "%.2f" % m["pf"]), m["dd"]))
        blocks.append((title, ms))

    H = ["<!doctype html><html lang=pl><head><meta charset=utf-8>",
         "<meta name=viewport content='width=device-width,initial-scale=1'>",
         "<title>BACKTEST — Polymarket 5m/15m</title><style>" + R.CSS + "</style>",
         "<script>" + R.JS + "</script></head><body>",
         "<header><h1>BACKTEST historyczny — <span>oba dry-runy</span></h1>",
         "<div class=sub>Zakres: <b>%s → %s UTC</b> &nbsp;•&nbsp; %d okien (%s, %s) &nbsp;•&nbsp; "
         "poślizg %0.0f c &nbsp;•&nbsp; bankroll $%.0f/wariant &nbsp;•&nbsp; wygenerowano %s UTC</div></header>"
         % (time.strftime("%Y-%m-%d %H:%M", time.gmtime(since)),
            time.strftime("%Y-%m-%d %H:%M", time.gmtime(until)), len(wins_ctx),
            ",".join(tfs), ",".join(assets), a.slip * 100, a.bank,
            time.strftime("%Y-%m-%d %H:%M", time.gmtime()))]
    tot_n = sum(m["n"] for m in allm)
    tot_p = sum(m["pnl"] for m in allm)
    H.append('<div class=cards>')
    for title, ms in blocks:
        n = sum(m["n"] for m in ms)
        p = sum(m["pnl"] for m in ms)
        best = max(ms, key=lambda m: m["pnl"])
        H.append('<div class=card><div class=k>%s</div><div class="v %s">%+.2f $</div>'
                 '<div class=x>%d transakcji</div></div>' % (title.split("—")[-1].strip(),
                                                             R.cls(p), p, n))
        H.append('<div class=card><div class=k>najlepszy</div><div class="v %s">%+.2f $</div>'
                 '<div class=x>%s (n=%d)</div></div>' % (R.cls(best["pnl"]), best["pnl"],
                                                          best["name"], best["n"]))
    H.append('</div>')
    H.append("<div class=note><b>Jak czytać:</b> to symulacja na prawdziwych cenach transakcyjnych "
             "Polymarketu (prices-history, ~60 s) i wynikach rozliczeń z Gammy. Książka jest uproszczona "
             "(ask = cena + poślizg, bid = cena − poślizg), więc warianty z filtrem głębokości/imbalance "
             "zachowują się tu łagodniej niż na żywo.</div>")
    for title, ms in blocks:
        H.append("<h2>%s <small>— %d transakcji, suma %+.2f $</small></h2>"
                 % (title, sum(m["n"] for m in ms), sum(m["pnl"] for m in ms)))
        H.append(R.table_main(ms, "Wszystkie warianty — pełne statystyki (backtest)"))
    H.append("</body></html>")
    out = os.path.join(ROOT, "BACKTEST.html")
    with open(out, "w") as f:
        f.write("\n".join(H))
    keys = ["set", "id", "name", "model", "v_min_px", "v_max_px", "v_edge", "tp", "sl", "n", "wins",
            "losses", "wr", "wr_lo", "wr_hi", "be_wr", "wr_edge", "pnl", "roi", "ret", "exp", "payoff",
            "pf", "sd", "tstat", "sortino", "kelly", "dd", "dd_abs", "rec", "bw", "bl", "avg_px",
            "med_px", "avg_p", "avg_edge", "hold", "rem_in", "tp_n"]
    import csv as _csv
    with open(os.path.join(ROOT, "reports", "BACKTEST.csv"), "w", newline="") as f:
        w = _csv.writer(f)
        w.writerow(keys)
        for m in allm:
            w.writerow([m.get(k) for k in keys])
    print("\nzapisano: %s oraz reports/BACKTEST.csv | transakcji razem: %d, suma %+.2f$"
          % (os.path.relpath(out), tot_n, tot_p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
