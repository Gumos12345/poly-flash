#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mono.py (v2) - trzy klasy arbitrazu na jednym skanie:

  MONO     - drabinka linii w evencie (Over/Under, handicapy): KAZDA para L1<L2
             -> kup YES(L1) + NO(L2); wyplata >= 1 w kazdym scenariuszu.
  MULTI    - grupa wielowynikowa (n>=3): suma YES < 1 ALBO suma NO < n-1.
  DUP      - to samo pytanie w roznych eventach: YES(A) + NO(B) < 1.

Kazdy wynik podawany brutto i NETTO po taker fee 5% (sport).

Uzycie:
  python mono.py                          # wszystkie tagi, 1 strona
  python mono.py --pages 3 --min-edge 0.01 --min-depth 1
  python mono.py --tags soccer,epl -v
"""
import argparse
import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
ALL_TAGS = ("nba,nfl,mlb,nhl,wnba,cbb,cfb,epl,soccer,la-liga,serie-a,bundesliga,"
            "ligue-1,ucl,mls,tennis,ufc,golf,f1,boxing,cricket,rugby,cs2,lol,"
            "crypto,politics,weather,economics,geopolitics")


def get(url, params=None, timeout=12):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "mono/2.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def ask(token):
    try:
        b = get(f"{CLOB}/book", {"token_id": token})
    except Exception:
        return 0.0, 0.0
    lv = b.get("asks") or []
    if not lv:
        return 0.0, 0.0
    best = min(float(x["price"]) for x in lv)
    size = sum(float(x["size"]) for x in lv if abs(float(x["price"]) - best) < 1e-9)
    return best, size


def num(text):
    m = re.search(r"(-?\d+(?:\.\d+)?)", text or "")
    return float(m.group(1)) if m else None


def norm(text):
    t = (text or "").lower()
    t = re.sub(r"[^a-z0-9.# ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def direction_of(question, sports_type):
    ql = (question or "").lower()
    st = (sports_type or "").lower()
    if "spread" in st or "handicap" in ql:
        return "higher_easier"
    if any(w in ql for w in ("over", "above", "at least", "higher than",
                             "more than", "or more")):
        return "lower_easier"
    if any(w in ql for w in ("under", "below", "less than", "or fewer")):
        return "higher_easier"
    return None


def collect(tags, pages):
    """Zwraca (mono_cands, multi_cands, dup_groups, n_events)."""
    mono, multi, dup = [], [], {}
    events = 0

    def fetch(task):
        tag, pg = task
        try:
            return get(f"{GAMMA}/events", {"closed": "false", "tag_slug": tag, "limit": 100,
                                          "offset": pg * 100, "order": "volume",
                                          "ascending": "false"}) or []
        except Exception:
            return []

    tasks = [(t, pg) for t in tags for pg in range(pages)]
    with ThreadPoolExecutor(8) as pool:
        fetched = list(pool.map(fetch, tasks))

    if True:
        if True:
            for evs in fetched:
              for ev in evs:
                events += 1
                ladders, ml = {}, []
                for m in ev.get("markets", []):
                    if m.get("closed") or m.get("archived"):
                        continue
                    q = m.get("question") or ""
                    ln = num(q)
                    try:
                        toks = json.loads(m["clobTokenIds"])
                        outs = json.loads(m["outcomes"])
                    except Exception:
                        continue
                    if len(toks) != 2 or len(outs) != 2:
                        continue
                    no_i = outs.index("No") if "No" in outs else 1
                    y_tok, n_tok = toks[1 - no_i], toks[no_i]
                    try:
                        pr = json.loads(m.get("outcomePrices") or "[]")
                        ypx, npx = float(pr[1 - no_i]), float(pr[no_i])
                    except Exception:
                        ypx, npx = 0.0, 0.0
                    if ln is None:
                        dup.setdefault(norm(q), []).append((ev.get("slug"), y_tok, n_tok, ypx, npx))
                        if " win" in q.lower():
                            ml.append((q, y_tok, n_tok))
                        continue
                    d = direction_of(q, m.get("sportsMarketType"))
                    if d:
                        tmpl = re.sub(r"-?\d+(?:\.\d+)?", "#", q).strip().lower()
                        ladders.setdefault((tmpl, d), []).append((ln, y_tok, n_tok, ypx, npx))
                for (tmpl_g, d), grp in ladders.items():
                    if len(grp) < 2:
                        continue
                    grp.sort(key=lambda x: x[0])
                    local = []
                    for i in range(len(grp)):
                        for j in range(i + 1, len(grp)):
                            l1, y1, n1, p1y, p1n = grp[i]
                            l2, y2, n2, p2y, p2n = grp[j]
                            if l1 == l2:
                                continue
                            # totals/over: latwiejsza = mniejsza linia -> YES(l1)+NO(l2)
                            # spreads/under: latwiejsza = wieksza linia -> YES(l2)+NO(l1)
                            if d == "lower_easier":
                                ty, tn, py, pn = y1, n2, p1y, p2n
                            else:
                                ty, tn, py, pn = y2, n1, p2y, p1n
                            if py <= 0 or pn <= 0 or py + pn > 1.06:
                                continue
                            local.append((py + pn, f"{l1}/{l2}", ty, tn))
                    local.sort(key=lambda x: x[0])
                    for _, lines, y1, n2 in local[:6]:
                        if len(mono) >= 4000:
                            break
                        mono.append((ev.get("slug"), lines, y1, n2))
                if len(ml) >= 3:
                    multi.append((ev.get("slug"), ml))
    return mono, multi, dup, events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default=ALL_TAGS)
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--min-edge", type=float, default=0.01)
    ap.add_argument("--min-depth", type=float, default=1.0)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    print(f"== MONO v2 == tagi {len(tags)} | prog netto {args.min_edge:.3f} "
          f"| depth>= {args.min_depth:.0f}")
    mono, multi, dup, events = collect(tags, args.pages)
    print(f"eventy: {events} | MONO par: {len(mono)} | MULTI grup: {len(multi)} "
          f"| DUP pytan: {len(dup)}")

    found = []
    with ThreadPoolExecutor(12) as pool:
        res = list(pool.map(lambda c: (ask(c[2]), ask(c[3])), mono))
    for (slug, lines, _, _), ((a1, d1), (a2, d2)) in zip(mono, res):
        if a1 <= 0 or a2 <= 0 or min(d1, d2) < args.min_depth:
            continue
        edge = 1.0 - (a1 + a2)
        fee = 0.05 * (a1 * (1 - a1) + a2 * (1 - a2))
        net = edge - fee
        if net >= args.min_edge:
            found.append((net, "MONO", slug, lines, a1, a2, min(d1, d2)))

    for slug, grp in multi:
        n = len(grp)
        ya = [ask(y) for _, y, _ in grp]
        na = [ask(nt) for _, _, nt in grp]
        sy = sum(p for p, _ in ya)
        sn = sum(p for p, _ in na)
        dy = min((s for _, s in ya), default=0)
        dn = min((s for _, s in na), default=0)
        if sy > 0 and dy >= args.min_depth:
            net = (1.0 - sy) - 0.05 * sy
            if net >= args.min_edge:
                found.append((net, f"MULTI-YES n={n}", slug, f"suma YES={sy:.3f}", sy / n, 0, dy))
        if sn > 0 and dn >= args.min_depth:
            net = ((n - 1) - sn) - 0.05 * sn
            if net >= args.min_edge:
                found.append((net, f"MULTI-NO n={n}", slug, f"suma NO={sn:.3f}", sn / n, 0, dn))

    dup_cands = []
    for q, items in dup.items():
        if len(items) < 2:
            continue
        pairs = [(i, j) for i in range(len(items)) for j in range(len(items)) if i != j]
        for i, j in pairs[:6]:
            s1, y1, _, py1, _ = items[i]
            s2, _, n2, _, pn2 = items[j]
            if py1 <= 0 or pn2 <= 0 or py1 + pn2 > 1.06:
                continue
            dup_cands.append((q, s1, s2, y1, n2))
    if dup_cands:
        print(f"DUP par do sprawdzenia (po filtrze cen): {len(dup_cands)}")
        with ThreadPoolExecutor(12) as pool:
            dres = list(pool.map(lambda c: (ask(c[3]), ask(c[4])), dup_cands))
        for (q, s1, s2, _, _), ((ay, dy), (an, dn)) in zip(dup_cands, dres):
            if ay <= 0 or an <= 0 or min(dy, dn) < args.min_depth:
                continue
            net = (1.0 - (ay + an)) - 0.05 * (ay * (1 - ay) + an * (1 - an))
            if net >= args.min_edge:
                found.append((net, "DUP", f"{s1} vs {s2}", q[:40], ay, an, min(dy, dn)))

    found.sort(key=lambda x: -x[0])
    for net, kind, slug, info, a1, a2, depth in found[:40]:
        print(f"\n[{kind}] {str(slug)[:56]}")
        print(f"   {info} | netto {net*100:.1f}% | ceny {a1:.3f}/{a2:.3f} | max {depth:.0f} par")
    print(f"\nokazji: {len(found)}")
    if not found:
        print("brak okazji powyzej progu")


if __name__ == "__main__":
    main()
