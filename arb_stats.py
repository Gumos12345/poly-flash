#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
arb_stats.py - statystyki arbitrazu z logow dry runu (to zastepuje backtest,
ktorego nie da sie zrobic: Polymarket nie daje historycznych ksiazek zlecen).

Czyta pliki ws_arb*.log i liczy:
  * ile par bot kupil ([PAPER])
  * zysk calkowity, sredni, mediana, min/max
  * ile alertow [ARB] bylo i ile odrzucono (za drogo / za mala glebokosc)
  * rozklad odrzucen (powody)
  * projekcje: ile par dziennie i jaki zysk przy N dniach reinwestycji

Uzycie:
  python arb_stats.py                    # wszystkie ws_arb*.log w katalogu
  python arb_stats.py ws_arb24.log
  python arb_stats.py --days 7 --pairs-per-day 4
"""
import argparse
import glob
import re
import statistics


def parse(path):
    pairs, arbs, rejected, reasons = [], 0, 0, {}
    netto = []
    with open(path, encoding='utf-8', errors='ignore') as fh:
        for line in fh:
            if '[PAPER]' in line:
                m = re.search(r'zysk \$([+-][0-9.]+).*bankroll \$([0-9.]+).*razem \$([+-][0-9.]+)', line)
                if m:
                    pairs.append({"profit": float(m.group(1)),
                                  "bankroll": float(m.group(2)),
                                  "total": float(m.group(3))})
            elif '[ARB]' in line:
                arbs += 1
                m = re.search(r'netto ([+-][0-9.]+)%', line)
                if m:
                    netto.append(float(m.group(1)))
                if 'ODRZUCONE' in line:
                    rejected += 1
                    r = line.split('ODRZUCONE:')[1].strip()
                    key = re.sub(r'[0-9.,]+', 'N', r)[:60]
                    reasons[key] = reasons.get(key, 0) + 1
    return pairs, arbs, rejected, reasons, netto


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--pairs-per-day", type=float, default=4.0)
    args = ap.parse_args()

    files = args.files or sorted(glob.glob("ws_arb*.log"))
    if not files:
        print("brak plikow ws_arb*.log w tym katalogu")
        return

    print("=" * 62)
    print(f"STATYSTYKI ARBITRAZU z {len(files)} plik(ow) logu")
    print("=" * 62)

    all_pairs, tot_arbs, tot_rej = [], 0, 0
    for f in files:
        try:
            pairs, arbs, rejected, reasons, netto = parse(f)
        except FileNotFoundError:
            continue
        tot_arbs += arbs
        tot_rej += rejected
        all_pairs += pairs
        if pairs:
            print(f"\n{f}:")
            print(f"  par kupionych : {len(pairs)}")
            print(f"  zysk          : {sum(p['profit'] for p in pairs):+.2f} USD")
            print(f"  bankroll koncowy: {pairs[-1]['bankroll']:.2f} USD")
        if reasons:
            print("  powody odrzucen:")
            for k, v in sorted(reasons.items(), key=lambda x: -x[1])[:4]:
                print(f"    {v:4d}x  {k}")

    print("\n" + "=" * 62)
    print("PODSUMOWANIE")
    print("=" * 62)
    if not all_pairs:
        print("brak kupionych par ([PAPER]) - bot nie znalazl okazji w budzecie")
        return

    profits = [p["profit"] for p in all_pairs]
    total = sum(profits)
    start_bank = all_pairs[0]["bankroll"] - all_pairs[0]["profit"]
    print(f"par kupionych     : {len(all_pairs)}")
    print(f"alertow ARB       : {tot_arbs} (odrzuconych: {tot_rej})")
    print(f"zysk calkowity    : {total:+.2f} USD")
    print(f"bankroll start    : {start_bank:.2f} USD")
    print(f"zwrot             : {total / start_bank * 100:+.1f}%")
    print(f"sredni zysk/para  : {statistics.mean(profits):+.2f} USD")
    print(f"mediana zysku/par : {statistics.median(profits):+.2f} USD")
    print(f"min / max         : {min(profits):+.2f} / {max(profits):+.2f} USD")

    print("\n" + "=" * 62)
    print(f"PROJEKCJA: {args.pairs_per_day:.0f} par/dzien, {args.days} dni, reinwestycja")
    print("=" * 62)
    avg_pct = statistics.mean(p["profit"] / max(p["bankroll"] - p["profit"], 1e-9) for p in all_pairs) * 100
    print(f"sredni zwrot na pare: {avg_pct:+.1f}% kapitalu")
    bank = start_bank
    for d in range(1, args.days + 1):
        for _ in range(int(args.pairs_per_day)):
            bank *= (1 + avg_pct / 100.0)
        print(f"  dzien {d}: {bank:8.2f} USD  ({bank / start_bank:5.2f}x)")

    print()
    if len(all_pairs) < 10:
        print(f"!!! PROBKA ZA MALA: {len(all_pairs)} par. Projekcja powyzej to matematyka,")
        print("    nie prognoza. Potrzeba >=20-30 par, zeby cokolwiek wnioskowac.")
    print("UWAGA: symulacja zaklada wypelnienie obu nog po asku (leg risk = realnie 70-80%).")


if __name__ == "__main__":
    main()
