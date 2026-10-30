#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
arb_bt.py - BACKTEST ARBITRAZU na faktycznych transakcjach Polymarketu.

Dane: Data API /trades (realne ceny i czasy wykonania, nie mid!).
Logika: w oknie czasowym (domyslnie 60 s) sprawdzamy, czy dalo sie kupic YES i NO
        jednoczesnie tak, ze cena_yes + cena_no + fee < 1.

  * bierzemy transakcje BUY po obu stronach (BUY = ktos zaplacil ask),
  * min cena BUY Yes i min cena BUY No w oknie = dolna granica askow,
  * edge = 1 - (p_yes + p_no) - fee.

To jest GORNA granica: prawdziwe aski mogly byc wyzej, ale jesli transakcje
poszly po takich cenach, to takie ceny istnialy.

Uzycie:
  python arb_bt.py --days 7 --max-markets 200
  python arb_bt.py --days 30 --max-markets 400 --window 120
"""
import argparse
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

GAMMA = "https://gamma-api.polymarket.com"
DATA = "https://data-api.polymarket.com"


def get(url, params=None, timeout=25):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "arb-bt/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def closed_markets(days, max_markets, min_vol):
    """Zamkniete rynki 2-wynikowe z ostatnich N dni."""
    cutoff = time.time() - days * 86400
    iso_min = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(cutoff))
    iso_max = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out, seen = [], set()
    for page in range(40):
        try:
            ms = get(f"{GAMMA}/markets", {"closed": "true", "limit": 100,
                                          "offset": page * 100,
                                          "end_date_min": iso_min,
                                          "end_date_max": iso_max,
                                          "order": "volume", "ascending": "false"})
        except Exception:
            break
        if not ms:
            break
        new = 0
        for m in ms:
            cid = m.get("conditionId")
            slug = m.get("slug")
            if not cid or not slug or slug in seen:
                continue
            seen.add(slug)
            if not m.get("closed"):
                continue
            if float(m.get("volume") or 0) < min_vol:
                continue
            try:
                outs = json.loads(m.get("outcomes") or "[]")
            except Exception:
                continue
            if len(outs) != 2:
                continue
            end = m.get("endDate") or m.get("closedTime")
            try:
                ts = time.mktime(time.strptime(str(end)[:19], "%Y-%m-%dT%H:%M:%S"))
            except Exception:
                continue
            if ts < cutoff:
                continue
            out.append({"cid": cid, "slug": slug, "vol": float(m.get("volume") or 0),
                        "outs": outs})
            new += 1
            if len(out) >= max_markets:
                return out
        if new == 0:
            break
    return out


def trades(cid, max_trades=2000):
    """Transakcje rynku (paginacja po 500)."""
    out = []
    for off in range(0, max_trades, 500):
        try:
            t = get(f"{DATA}/trades", {"market": cid, "limit": 500, "offset": off})
        except Exception:
            break
        if not t:
            break
        out += t
        if len(t) < 500:
            break
    return out


def fee(p):
    """Taker fee per share (sport 5%)."""
    return 0.05 * p * (1.0 - p)


def closed_events(days, max_events, min_vol):
    """Zamkniete eventy z ostatnich N dni, z listą rynków (do drabinek)."""
    cutoff = time.time() - days * 86400
    iso_min = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(cutoff))
    iso_max = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out, seen = [], set()
    for page in range(40):
        try:
            evs = get(f"{GAMMA}/events", {"closed": "true", "limit": 100, "offset": page * 100,
                                          "end_date_min": iso_min, "end_date_max": iso_max,
                                          "order": "volume", "ascending": "false"})
        except Exception:
            break
        if not evs:
            break
        new = 0
        for ev in evs:
            slug = ev.get("slug")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            ms = []
            for m in ev.get("markets", []):
                cid = m.get("conditionId")
                q = m.get("question") or ""
                if not cid or not m.get("closed"):
                    continue
                ms.append({"cid": cid, "q": q,
                           "smt": (m.get("sportsMarketType") or "").lower(),
                           "vol": float(m.get("volume") or 0)})
            if len(ms) < 2:
                continue
            out.append({"slug": slug, "markets": ms})
            new += 1
            if len(out) >= max_events:
                return out
        if new == 0:
            break
    return out


def _num(txt):
    import re
    m = re.search(r"(-?\d+(?:\.\d+)?)", txt or "")
    return float(m.group(1)) if m else None


def ladder_pairs(ev):
    """Pary (YES latwiejsza linia, NO trudniejsza linia) w jednym evencie."""
    import re
    groups = {}
    for m in ev["markets"]:
        ln = _num(m["q"])
        if ln is None:
            continue
        ql = m["q"].lower()
        if "spread" in m["smt"] or "handicap" in ql:
            direction = "higher_easier"
        elif any(w in ql for w in ("over", "above", "at least", "more than")):
            direction = "lower_easier"
        elif any(w in ql for w in ("under", "below", "less than", "fewer")):
            direction = "higher_easier"
        else:
            continue
        tmpl = re.sub(r"-?\d+(?:\.\d+)?", "#", m["q"]).lower()
        groups.setdefault((tmpl, direction), []).append((ln, m))

    pairs = []
    for (tmpl, d), grp in groups.items():
        if len(grp) < 2:
            continue
        grp.sort(key=lambda x: x[0])
        for i in range(len(grp) - 1):
            l1, m1 = grp[i]
            l2, m2 = grp[i + 1]
            if l1 == l2:
                continue
            # YES latwiejsza, NO trudniejsza
            if d == "lower_easier":
                yes_m, no_m = m1, m2
            else:
                yes_m, no_m = m2, m1
            pairs.append({"yes": yes_m, "no": no_m, "lines": f"{l1}/{l2}", "d": d})
    return pairs


def trades_map(cid, max_trades=2000, min_size=5.0):
    """outcomeIndex -> [(ts, price)] dla transakcji BUY."""
    out = {0: [], 1: []}
    for off in range(0, max_trades, 500):
        try:
            t = get(f"{DATA}/trades", {"market": cid, "limit": 500, "offset": off})
        except Exception:
            break
        if not t:
            break
        for x in t:
            if x.get("side") != "BUY":
                continue
            try:
                if float(x.get("size") or 0) < min_size:
                    continue
                out[int(x.get("outcomeIndex"))].append(
                    (int(x["timestamp"]), float(x["price"]), float(x.get("size") or 0)))
            except Exception:
                pass
        if len(t) < 500:
            break
    return out


def analyse_ladder(pair, window, min_edge, min_size=5.0):
    ty = trades_map(pair["yes"]["cid"], min_size=min_size)
    tn = trades_map(pair["no"]["cid"], min_size=min_size)
    if not ty[0] or not tn[1]:
        return None
    start = min(r[0] for r in ty[0] + tn[1])
    stop = max(r[0] for r in ty[0] + tn[1])
    hits = []
    t = start
    while t <= stop:
        cy = [(p, sz) for ts, p, sz in ty[0] if t <= ts <= t + window]
        cn = [(p, sz) for ts, p, sz in tn[1] if t <= ts <= t + window]
        if cy and cn:
            py = min(p for p, _ in cy)
            pn = min(p for p, _ in cn)
            dy = sum(sz for p, sz in cy if abs(p - py) < 1e-9)
            dn = sum(sz for p, sz in cn if abs(p - pn) < 1e-9)
            edge = 1.0 - (py + pn) - (fee(py) + fee(pn))
            if edge >= min_edge:
                depth = min(dy, dn)
                hits.append({"edge": edge, "depth": depth, "usd": depth * edge})
        t += window
    if not hits:
        return None
    best = max(hits, key=lambda h: h["usd"])
    return {"best": best["edge"], "n": len(hits), "usd": best["usd"],
            "depth": best["depth"], "usd_total": sum(h["usd"] for h in hits)}


def run_mono(days, max_events, window, min_edge, min_size=5.0):
    evs = closed_events(days, max_events, 5000)
    print(f"eventow do analizy: {len(evs)}")
    all_edges, markets_with, all_usd = [], 0, []
    for ev in evs:
        for pr in ladder_pairs(ev):
            r = analyse_ladder(pr, window, min_edge, min_size)
            if r:
                markets_with += 1
                all_edges += [r["best"]] * r["n"]
                all_usd.append(r["usd_total"])
                print(f"  {r['best']*100:6.2f}%  depth={r['depth']:5.0f}  "
                      f"zysk=${r['usd']:6.2f}  {ev['slug'][:30]:30s} {pr['lines']}")
    if not all_edges:
        print("BRAK arbitrazy na drabinkach w tej probce")
        return
    print(f"\npar z arbitrazem : {markets_with}")
    print(f"okien z arbitrazem: {len(all_edges)}")
    print(f"sredni edge      : {sum(all_edges)/len(all_edges)*100:+.2f}%")
    print(f"mediana edge     : {sorted(all_edges)[len(all_edges)//2]*100:+.2f}%")
    print(f"okazji na dzien  : {len(all_edges)/days:.1f}")
    print(f"zysk lacznie     : ${sum(all_usd):.2f} (na {len(all_usd)} parach)")
    print(f"zysk na dzien    : ${sum(all_usd)/days:.2f}")


def analyse(market, window, min_edge):
    """Szuka okien, w ktorych YES+NO dalo sie kupic ponizej 1."""
    tr = trades(market["cid"])
    if len(tr) < 10:
        return None
    buys = defaultdict(list)      # outcomeIndex -> [(ts, price)]
    for x in tr:
        if x.get("side") != "BUY":
            continue
        try:
            buys[int(x.get("outcomeIndex"))].append((int(x["timestamp"]), float(x["price"])))
        except Exception:
            continue
    if 0 not in buys or 1 not in buys:
        return None

    def best_within(rows, t0, t1):
        sub = [p for ts, p in rows if t0 <= ts <= t1]
        return min(sub) if sub else None

    start = min(ts for rows in buys.values() for ts, _ in rows)
    stop = max(ts for rows in buys.values() for ts, _ in rows)
    hits = []
    t = start
    while t <= stop:
        py = best_within(buys[0], t, t + window)
        pn = best_within(buys[1], t, t + window)
        if py and pn:
            cost = py + pn
            f = fee(py) + fee(pn)
            edge = 1.0 - cost - f
            if edge >= min_edge:
                hits.append({"t": t, "py": py, "pn": pn, "edge": edge})
        t += window
    if not hits:
        return None
    return {"slug": market["slug"], "vol": market["vol"], "hits": hits,
            "best": max(h["edge"] for h in hits), "n": len(hits)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--max-markets", type=int, default=200)
    ap.add_argument("--min-vol", type=float, default=5000.0)
    ap.add_argument("--window", type=int, default=60, help="okno w sekundach")
    ap.add_argument("--min-edge", type=float, default=0.01)
    ap.add_argument("--mode", choices=("mono", "pair", "both"), default="mono",
                    help="mono = drabinki linii (jak bot), pair = YES+NO w jednym rynku")
    args = ap.parse_args()

    if args.mode == "mono":
        print(f"== BACKTEST ARBITRAZU: DRABINKI LINII (realne transakcje) ==")
        print(f"dni={args.days} | max eventow={args.max_markets} | okno={args.window}s "
              f"| min edge={args.min_edge:.2f}")
        run_mono(args.days, args.max_markets, args.window, args.min_edge)
        return

    print(f"== BACKTEST ARBITRAZU (realne transakcje) ==")
    print(f"dni={args.days} | max rynkow={args.max_markets} | okno={args.window}s "
          f"| min edge={args.min_edge:.2f}")
    mk = closed_markets(args.days, args.max_markets, args.min_vol)
    print(f"rynkow do analizy: {len(mk)}")
    if not mk:
        print("brak rynkow - zwieksz --days albo obniz --min-vol")
        return

    results, done = [], 0
    with ThreadPoolExecutor(10) as pool:
        for r in pool.map(lambda m: analyse(m, args.window, args.min_edge), mk):
            done += 1
            if done % 25 == 0:
                print(f"  sprawdzone {done}/{len(mk)}...")
            if r:
                results.append(r)

    print()
    if not results:
        print("BRAK arbitrazy w tej probce (przy oknie %ds i progu %.2f)" % (args.window, args.min_edge))
        return

    results.sort(key=lambda x: -x["best"])
    total_hits = sum(r["n"] for r in results)
    edges = [h["edge"] for r in results for h in r["hits"]]
    print(f"rynkow z arbitrazem : {len(results)} / {len(mk)}")
    print(f"okien z arbitrazem  : {total_hits}")
    print(f"sredni edge         : {sum(edges)/len(edges)*100:+.2f}%")
    print(f"mediana edge        : {sorted(edges)[len(edges)//2]*100:+.2f}%")
    print(f"maksymalny edge     : {max(edges)*100:+.2f}%")
    print(f"okazji na dzien     : {total_hits/args.days:.1f}")
    print()
    print("TOP 10 rynkow:")
    for r in results[:10]:
        print(f"  {r['best']*100:6.2f}%  n={r['n']:3d}  vol={r['vol']:9.0f}  {r['slug'][:52]}")


if __name__ == "__main__":
    main()
