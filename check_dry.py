#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_dry.py - raport z dry runu bota (bot_v2_dry_fixed.py / bot_v2_dry_v3.py)
==============================================================================
Czyta positions_v2_dry.json + trades_v2_dry.json, nic nie zmienia, nie handluje.
Pokazuje: ile pozycji otwartych, ile rozstrzygnietych, winrate, PnL, ile kasy
jest zamrozone i ile jeszcze wejsc zmiesci sie w bankrollu (domyslnie $4.17).

Uzycie (Termux):
    python3 check_dry.py                  # auto-szuka plikow stanu
    python3 check_dry.py --bankroll 4.17  # inny bankroll
    python3 check_dry.py --dir ~/poly-flash
"""
import argparse
import json
import os
import sys
import time

POS = "positions_v2_dry.json"
TRD = "trades_v2_dry.json"


def load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def find_state_dir(explicit=None):
    """Katalog z plikami stanu: --dir, cwd, katalog skryptu, ~/poly-flash, plytki search w $HOME."""
    cands = []
    if explicit:
        cands.append(os.path.expanduser(explicit))
    cands.append(os.getcwd())
    cands.append(os.path.dirname(os.path.abspath(__file__)))
    home = os.path.expanduser("~")
    cands.append(os.path.join(home, "poly-flash"))
    cands.append(os.path.join(home, "poly_flash"))
    for d in cands:
        if d and (os.path.exists(os.path.join(d, POS)) or os.path.exists(os.path.join(d, TRD))):
            return d
    for root, dirs, files in os.walk(home):
        dirs[:] = [x for x in dirs if not x.startswith(".") and x != "node_modules"]
        if root.count(os.sep) - home.count(os.sep) > 2:
            dirs[:] = []
            continue
        if POS in files or TRD in files:
            return root
    return None


def money(x):
    return f"{x:+.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bankroll", type=float, default=4.17,
                    help="ile USD masz na koncie (domyslnie 4.17)")
    ap.add_argument("--dir", default=None, help="katalog z positions_v2_dry.json")
    ap.add_argument("--size", type=float, default=1.0, help="stawka na trade (SIZE_USD)")
    args = ap.parse_args()

    d = find_state_dir(args.dir)
    print("=" * 62)
    print(" DRY RUN - RAPORT")
    print("=" * 62)
    if not d:
        print("Nie znalazlem positions_v2_dry.json / trades_v2_dry.json.")
        print("Uruchom bota w trybie dry:  python3 bot_v2_dry_fixed.py --dry")
        print("albo wskaz katalog:         python3 check_dry.py --dir ~/poly-flash")
        return 1

    pf, tf = os.path.join(d, POS), os.path.join(d, TRD)
    print(f"katalog : {d}")
    print(f"pozycje : {pf}  {'[jest]' if os.path.exists(pf) else '[BRAK]'}")
    print(f"trades  : {tf}  {'[jest]' if os.path.exists(tf) else '[BRAK]'}")
    if os.path.exists(tf):
        mt = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(tf)))
        print(f"mtime   : {mt}")

    positions = load(pf, {})
    trades = load(tf, [])
    if isinstance(positions, list):
        positions = {p.get("slug", str(i)): p for i, p in enumerate(positions)}
    if not isinstance(trades, list):
        trades = []

    closed = [t for t in trades if t.get("settled", True)]
    wins = [t for t in closed if float(t.get("pnl_usd") or 0.0) > 0]
    losses = [t for t in closed if float(t.get("pnl_usd") or 0.0) < 0]
    pnl = sum(float(t.get("pnl_usd") or 0.0) for t in closed)
    obrot = sum(float(t.get("cost") or 0.0) for t in closed)
    n = len(closed)

    print("\n-- ZAMKNIETE (rozstrzygniete) " + "-" * 34)
    if not n:
        print("  brak rozstrzygnietych pozycji (dry run jeszcze nic nie rozliczyl)")
    else:
        wr = len(wins) / n * 100.0
        print(f"  transakcji     : {n}")
        print(f"  trafione       : {len(wins)}  ({wr:.1f}%)   nietrafione: {len(losses)}")
        print(f"  PnL netto      : {money(pnl)} USD")
        print(f"  obrot (koszt)  : {obrot:.2f} USD")
        print(f"  ROI            : {(pnl / obrot * 100.0) if obrot else 0.0:+.1f}%")
        print(f"  srednio/trade  : {money(pnl / n)} USD")
        best = max(closed, key=lambda t: float(t.get("pnl_usd") or 0.0))
        worst = min(closed, key=lambda t: float(t.get("pnl_usd") or 0.0))
        print(f"  najlepszy      : {money(float(best.get('pnl_usd') or 0))} "
              f"(NO {float(best.get('entry_no') or 0):.3f}) {str(best.get('slug'))[:44]}")
        print(f"  najgorszy      : {money(float(worst.get('pnl_usd') or 0))} "
              f"(NO {float(worst.get('entry_no') or 0):.3f}) {str(worst.get('slug'))[:44]}")
        print("  ostatnie 5:")
        for t in sorted(closed, key=lambda x: int(x.get("ts") or 0))[-5:]:
            ts = time.strftime("%m-%d %H:%M", time.localtime(int(t.get("ts") or 0)))
            print(f"    {ts}  NO {float(t.get('entry_no') or 0):.3f}  "
                  f"{float(t.get('shares') or 0):5.2f} szt  "
                  f"{money(float(t.get('pnl_usd') or 0))} USD  {str(t.get('slug'))[:38]}")

    now = time.time()
    locked = sum(float(p.get("usd") or 0.0) for p in positions.values())
    shares = sum(float(p.get("shares") or 0.0) for p in positions.values())
    print("\n-- OTWARTE (zamrozona kasa) " + "-" * 32)
    print(f"  pozycji        : {len(positions)}")
    print(f"  zamrozone      : {locked:.2f} USD")
    print(f"  sztuki NO      : {shares:.2f}")
    print(f"  wyplata, gdy wszystkie NO wygraja: {shares:.2f} USD "
          f"-> zysk {shares - locked:+.2f} USD")
    if positions:
        entries = [float(p.get("entry_no") or 0.0) for p in positions.values()]
        print(f"  sredni entry NO: {sum(entries) / len(entries):.3f}")
        ages = [(now - float(p.get("ts_open") or now)) / 86400.0 for p in positions.values()]
        print(f"  wiek pozycji   : srednio {sum(ages) / len(ages):.1f} dni, "
              f"najstarsza {max(ages):.1f} dni")
        print("  szczegoly:")
        for p in sorted(positions.values(), key=lambda x: int(x.get("ts_open") or 0)):
            ts = time.strftime("%m-%d %H:%M", time.localtime(int(p.get("ts_open") or 0)))
            print(f"    {ts}  NO {float(p.get('entry_no') or 0):.3f}  "
                  f"{float(p.get('shares') or 0):5.2f} szt  "
                  f"${float(p.get('usd') or 0):.2f}  {str(p.get('timing')):4s} "
                  f"{str(p.get('group')):9s} {str(p.get('slug'))[:36]}")

    print("\n-- BUDZET " + "-" * 49)
    bank = args.bankroll
    free = bank - locked
    koszt = args.size * 1.02  # stawka + fee + pol spreadu
    max_new = int(free // koszt) if koszt > 0 else 0
    print(f"  bankroll        : {bank:.2f} USD")
    print(f"  zamrozone       : {locked:.2f} USD")
    print(f"  wolne           : {free:+.2f} USD")
    print(f"  nowych pozycji po {koszt:.2f} USD: {max(0, max_new)}")
    if free < koszt:
        print("  UWAGA: wolne srodki < koszt wejscia -> bot nie otworzy nowej pozycji")
    if pnl < 0:
        print(f"  UWAGA: dry run jest na minusie ({pnl:+.2f} USD)")

    print("\n-- WERDYKT " + "-" * 48)
    if n < 10:
        print(f"  Za mala proba ({n} rozstrzygniec) - to jeszcze nie wynik strategii,")
        print("  tylko los. Nie zmieniaj stawki na podstawie takiego PnL.")
    else:
        wr = len(wins) / n * 100.0
        print(f"  Probka {n} rozstrzygniec, winrate {wr:.1f}%, PnL {pnl:+.2f} USD.")
        if pnl > 0 and wr >= 50:
            print("  Sygnal zgodny z backtestem - strategia dziala na zywo (paper).")
        else:
            print("  Sygnal NIE potwierdza backtestu - nie zwiekszaj stawki.")
    print(f"  Przy bankrollu {bank:.2f} USD i {koszt:.2f} USD/wejscie: "
          f"max {max(0, int(bank // koszt))} pozycji rownoczesnie.")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())

