#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mono.py - arbitraz na niespojnosci linii w jednym meczu (bez przewidywania wyniku).

Fakt matematyczny: P(over 2.5 goli) >= P(over 3.5 goli). Zawsze.
Jesli rynek wycenia over 2.5 po 0.40, a over 3.5 po 0.55, to kupujesz:
  YES(over 2.5) po 0.40  +  NO(over 3.5) po 0.45   -> koszt 0.85
Wyplata:
  total <= 2   -> NO(over 3.5) placi 1
  total = 3    -> oba place 2
  total >= 4   -> YES(over 2.5) placi 1
Czyli ZAWSZE >= 1.0 za koszt 0.85 -> zysk 17.6% bez ryzyka.

To samo dla spreadow: P(krycie -1.5) >= P(krycie -3.5).

Uzycie:
  python mono.py --tags nba,nfl,epl,soccer --pages 3
  python mono.py --min-edge 0.03 -v
"""
import argparse
import json
import re
import time
import urllib.parse
import urllib.request

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


def get(url, params=None, timeout=15):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "mono/1.0"})
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
    """Wyciaga liczbe z pytania: 'Over 2.5' -> 2.5 ; 'Celtics (-3.5)' -> -3.5"""
    m = re.search(r"(-?\d+(?:\.\d+)?)", text or "")
    return float(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags", default="nba,nfl,mlb,epl,soccer,ucl,la-liga,serie-a,bundesliga,nhl")
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--min-edge", type=float, default=0.01)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    print(f"== MONO SCAN == tagi: {args.tags} | prog {args.min_edge:.2f}")
    found = 0
    checked = 0
    for tag in [t.strip() for t in args.tags.split(",") if t.strip()]:
        for pg in range(args.pages):
            try:
                evs = get(f"{GAMMA}/events", {"closed": "false", "tag_slug": tag, "limit": 100,
                                              "offset": pg * 100, "order": "volume",
                                              "ascending": "false"})
            except Exception as e:
                print(f"  [{tag}] {e!r}")
                break
            for ev in evs or []:
                totals, spreads = [], []
                for m in ev.get("markets", []):
                    if m.get("closed") or m.get("archived"):
                        continue
                    st = (m.get("sportsMarketType") or "").lower()
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
                    if "total" in st and "over" in q.lower():
                        totals.append((ln, m["slug"], toks[0], toks[1]))
                    elif "spread" in st:
                        spreads.append((ln, m["slug"], toks[0], toks[1]))
                for name, group in (("totals", totals), ("spreads", spreads)):
                    if len(group) < 2:
                        continue
                    group.sort(key=lambda x: x[0])
                    for i in range(len(group) - 1):
                        l1, s1, y1, n1 = group[i]
                        l2, s2, y2, n2 = group[i + 1]
                        if l1 == l2:
                            continue
                        checked += 1
                        # kierunek parowania zalezy od typu rynku:
                        # totals: latwiejsza = mniejsza linia -> YES(l1) + NO(l2)
                        # spreads: latwiejsza = wieksza (mniej ujemna) -> YES(l2) + NO(l1)
                        if name == "spreads":
                            tok_yes, tok_no = y2, n1
                        else:
                            tok_yes, tok_no = y1, n2
                        a1, d1 = ask(tok_yes)
                        a2, d2 = ask(tok_no)
                        if a1 <= 0 or a2 <= 0:
                            continue
                        edge = 1.0 - (a1 + a2)
                        fee = 0.05 * (a1 * (1 - a1) + a2 * (1 - a2))   # taker 5% sport
                        net = edge - fee
                        if args.verbose:
                            print(f"  {ev.get('slug','')[:30]:30s} {name:7s} L{l1}<{l2} "
                                  f"YES={a1:.3f}+NO={a2:.3f}={a1+a2:.3f} edge={edge:+.3f} "
                                  f"net={net:+.3f}")
                        if net >= args.min_edge:
                            found += 1
                            print(f"\n[ARB-MONO] {ev.get('slug','')} ({name})")
                            print(f"   kup YES({a1:.3f} x{d1:.0f}) + NO({a2:.3f} x{d2:.0f}) "
                                  f"= {a1+a2:.3f} -> wyplata >=1.0, brutto {edge*100:.1f}% "
                                  f"netto {net*100:.1f}% | max {min(d1,d2):.0f} par")
    print(f"\nsprawdzonych par: {checked} | okazji: {found}")
    if not found:
        print("brak niespojnosci - rynek trzyma monotonicznosc (to normalne przy plynnych rynkach)")


if __name__ == "__main__":
    main()
