#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OBA dry-runy w JEDNYM procesie (wspólne ceny/książki) - ok. 2x szybciej i 2x mniej zapytań.
Stany: state/dryrun1.json + state/dryrun2.json (te same pliki co przy osobnych procesach,
więc RAPORT.html i --report działają bez zmian).

  python3 dryrun_both.py --bank 50 --stake 1.25 --sleep 2
  python3 dryrun_both.py --reset ...        # zeruje oba
  python3 dryrun_both.py --minutes 480 ...  # auto-stop
"""
import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import poly_dryrun_engine as E  # noqa: E402
import dryrun1_master as D1  # noqa: E402
import dryrun2_master as D2  # noqa: E402


def prep(variants, stake):
    for v in variants:
        v.setdefault("ladder", {})
        if not v.get("start_stake"):
            v["start_stake"] = stake
        v["ladder"].setdefault("start_stake", v["start_stake"])
        v["ladder"].setdefault("min_stake", v["start_stake"])
    return variants


def main(argv=None):
    ap = argparse.ArgumentParser(description="Oba dry-runy w jednym procesie")
    ap.add_argument("--bank", type=float, default=50.0)
    ap.add_argument("--stake", type=float, default=1.25)
    ap.add_argument("--sleep", type=float, default=2.0)
    ap.add_argument("--minutes", type=float, default=0.0)
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--prefix", default="")
    a = ap.parse_args(argv)

    e1 = E.Engine(prep(D1.VARIANTS, a.stake), a.prefix + "dryrun1", start_bank=a.bank)
    e2 = E.Engine(prep(D2.VARIANTS, a.stake), a.prefix + "dryrun2", start_bank=a.bank)
    if a.reset:
        e1.reset()
        e2.reset()
        print("stan wyzerowany:", e1.state_path, "+", e2.state_path)
    e1.load()
    e2.load()
    e1.save()
    e2.save()
    # klucz: DRUGI przebieg korzysta z tych samych danych (ceny, klines, orderbooki, rozliczenia)
    e2.feed, e2.mk = e1.feed, e1.mk

    deadline = e1.t0 + a.minutes * 60 if a.minutes else None
    print("START OBA | %d + %d wariantów | bankroll $%.2f | stawka $%.2f | jedno źródło danych"
          % (len(e1.variants), len(e2.variants), a.bank, a.stake), flush=True)
    cyc = 0
    while True:
        now = time.time()
        if deadline and now > deadline:
            print("KONIEC czasu", flush=True)
            break
        try:
            ctxs = e1.build_ctxs(now)      # buduje konteksty dla sumy wariantów obu zestawów
            for eng in (e1, e2):
                eng.manage(now)
                for b in eng.books.values():
                    eng.consider(b, ctxs, now)
            cyc += 1
            if cyc % 10 == 0:
                e1.save()
                e2.save()
                n1 = sum(len(b.closed) for b in e1.books.values())
                n2 = sum(len(b.closed) for b in e2.books.values())
                p1 = sum(b.realized for b in e1.books.values())
                p2 = sum(b.realized for b in e2.books.values())
                print("[%s] cykl %d | ctx=%d | run1 %d zamkn. %+.2f$ | run2 %d zamkn. %+.2f$ | req %d err %d"
                      % (time.strftime("%H:%M:%S", time.gmtime()), cyc, len(ctxs), n1, p1, n2, p2,
                         e1.mk.req, e1.mk.err), flush=True)
        except KeyboardInterrupt:
            print("przerwano", flush=True)
            break
        except Exception as ex:
            print("ERR %r" % (ex,), flush=True)
        time.sleep(a.sleep)
    e1.save()
    e2.save()
    print("zapisano stan obu przebiegów", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
