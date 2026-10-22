#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mono.py - arbitraz na uporzadkowanych rynkach (drabinki progów i linie).

Warunek: w jednym evencie sa rynki o tej samej tresci, rozniace sie liczba
(np. over 2.5 / 3.5 / 4.5, spread -1.5 / -2.5, BTC powyzej 100k/110k/120k).
Wtedy kupujesz YES na latwiejszym progu + NO na trudniejszym -> wyplata >= 1.

Uzycie:
  python mono.py                                   # sporty + crypto/pogoda/polityka
  python mono.py --tags nba,nfl --min-edge 0.03
  python mono.py --tags crypto,politics --pages 1 -v
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default=ALL_TAGS)
    ap.add_argument("--pages", type=int, default=1)
    ap.add_argument("--min-edge", type=float, default=0.02)
    ap.add_argument("--min-depth", type=float, default=1.0)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    print(f"== MONO SCAN == tagi: {len(tags)} | prog netto {args.min_edge:.2f}")
    pending, events = [], 0
    for tag in tags:
        for pg in range(args.pages):
            try:
                evs = get(f"{GAMMA}/events", {"closed": "false", "tag_slug": tag, "limit": 100,
                                              "offset": pg * 100, "order": "volume",
                                              "ascending": "false"})
            except Exception:
                break
            for ev in evs or []:
                events += 1
                groups = {}
                for m in ev.get("markets", []):
                    if m.get("closed") or m.get("archived"):
                        continue
                    q = m.get("question") or ""
                    ln = num(q)
                    if ln is None:
                        continue
                    try:
                        toks = json.loads(m["clobTokenIds"])
                        outs = json.loads(m["outcomes"])
                    except Exception:
                        continue
                    if len(toks) != 2 or len(outs) != 2:
                        continue
                    d = direction_of(q, m.get("sportsMarketType"))
                    if d is None:
                        continue
                    tmpl = re.sub(r"-?\d+(?:\.\d+)?", "#", q).strip().lower()
                    groups.setdefault((tmpl, d), []).append((ln, m["slug"], toks[0], toks[1]))
                for (tmpl, d), grp in groups.items():
                    if len(grp) < 2:
                        continue
                    grp.sort(key=lambda x: x[0])
                    for i in range(len(grp) - 1):
                        l1, s1, y1, n1 = grp[i]
                        l2, s2, y2, n2 = grp[i + 1]
                        if l1 == l2:
                            continue
                        tok_yes, tok_no = (y1, n2) if d == "lower_easier" else (y2, n1)
                        pending.append((ev.get("slug"), tmpl, l1, l2, tok_yes, tok_no))

    print(f"eventow: {events} | par do sprawdzenia: {len(pending)}")
    if not pending:
        print("brak drabinek progow w tych tagach")
        return

    with ThreadPoolExecutor(12) as pool:
        res = list(pool.map(lambda p: (ask(p[4]), ask(p[5])), pending))

    found = []
    for p, ((a1, d1), (a2, d2)) in zip(pending, res):
        ev_slug, tmpl, l1, l2, _, _ = p
        if a1 <= 0 or a2 <= 0 or min(d1, d2) < args.min_depth:
            continue
        edge = 1.0 - (a1 + a2)
        fee = 0.05 * (a1 * (1 - a1) + a2 * (1 - a2))
        net = edge - fee
        if args.verbose and net > -0.05:
            print(f"  {str(ev_slug)[:26]:26s} {tmpl[:20]:20s} {l1}/{l2} "
                  f"suma={a1+a2:.3f} net={net:+.3f} d={min(d1,d2):.0f}")
        if net >= args.min_edge:
            found.append((net, ev_slug, tmpl, l1, l2, a1, a2, d1, d2))

    found.sort(key=lambda x: -x[0])
    for net, ev_slug, tmpl, l1, l2, a1, a2, d1, d2 in found:
        print(f"\n[ARB-MONO] {ev_slug} | {tmpl[:44]}")
        print(f"   YES({a1:.3f} x{d1:.0f}) linia {l1} + NO({a2:.3f} x{d2:.0f}) linia {l2}"
              f" = {a1+a2:.3f} | brutto {(1-(a1+a2))*100:.1f}% netto {net*100:.1f}%"
              f" | max {min(d1,d2):.0f} par")
    print(f"\nokazji po fee: {len(found)} / {len(pending)} par")
    if not found:
        print("brak niespojnosci powyzej progu - rynek trzyma monotonicznosc")


if __name__ == "__main__":
    main()
