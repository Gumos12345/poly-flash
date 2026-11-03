#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sprawdza klucze do Polymarket: adres z klucza, saldo i KTORY signature_type dziala.
===================================================================================
Uzycie (w Termuxie, po ustawieniu PM_PRIVATE_KEY):
    python3 keys_check.py                       # sprawdzi typy 0, 2, 3
    python3 keys_check.py --funder 0xADRES      # wskaz portfel z USDC (proxy z UI)

Co robi dla kazdego typu:
  1) liczy adres EOA z klucza prywatnego (eth_account)
  2) laczy sie z CLOB z signature_type i funder
  3) probuje pobrac klucze API (derive/create) i SALDO USDC
Wynik: wypisz TYLKO TYP, przy ktorym widac Twoje saldo - jego uzyj w PM_SIG_TYPE.
"""
import argparse
import os
import sys

HOST = "https://clob.polymarket.com"
CHAIN = 137


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--funder", default=os.environ.get("PM_FUNDER", ""))
    ap.add_argument("--types", default="0,2,3")
    a = ap.parse_args()
    pk = os.environ.get("PM_PRIVATE_KEY", "").strip()
    if not pk:
        sys.exit("Brak PM_PRIVATE_KEY. Ustaw: export PM_PRIVATE_KEY='0x...'")
    if not pk.startswith("0x"):
        pk = "0x" + pk
    try:
        from eth_account import Account
        eoa = Account.from_key(pk).address
        print("Adres z klucza (EOA): %s" % eoa)
    except Exception as ex:
        eoa = None
        print("Nie udalo sie policzyc adresu z klucza (%r) - kontynuuje" % (ex,))
    funder = (a.funder or "").strip()
    print("Funder (PM_FUNDER): %s" % (funder or "(nie podany - uzyje adresu EOA)"))
    if funder and eoa and funder.lower() != eoa.lower():
        print("  -> funder != EOA: to normalne dla portfela proxy (Polymarket UI).")
    try:
        import py_clob_client_v2 as sdk
    except ImportError:
        sys.exit("Brak SDK: pip install py-clob-client-v2")

    for t in [x.strip() for x in a.types.split(",") if x.strip()]:
        st = int(t)
        print("\n=== signature_type=%d ===" % st)
        kw = {"host": HOST, "chain_id": CHAIN, "key": pk, "signature_type": st}
        if funder:
            kw["funder"] = funder
        elif eoa:
            kw["funder"] = eoa
        try:
            c = sdk.ClobClient(**kw)
        except Exception as ex:
            print("  klient nie wstal: %r" % (ex,))
            continue
        creds = None
        for fn in ("create_or_derive_api_creds", "derive_api_key", "derive_api_creds"):
            f = getattr(c, fn, None)
            if not f:
                continue
            try:
                creds = f()
                if creds is not None:
                    break
            except Exception as ex:
                print("  %s: %s" % (fn, str(ex)[:90]))
        if creds is None:
            print("  brak kluczy API -> ten typ nie zadziala")
            continue
        try:
            c.set_api_creds(creds)
        except Exception as ex:
            print("  set_api_creds: %s" % str(ex)[:90])
            continue
        print("  klucze API: OK")
        bal = None
        for fn in ("get_balance", "get_balance_allowance"):
            f = getattr(c, fn, None)
            if not f:
                continue
            try:
                r = f()
                if isinstance(r, dict):
                    bal = r.get("balance", r)
                else:
                    bal = getattr(r, "balance", r)
                break
            except Exception as ex:
                print("  %s: %s" % (fn, str(ex)[:90]))
        if bal is not None:
            try:
                v = float(bal)
                v = v / 1e6 if v > 1000 else v
                print("  SALDO USDC: %.2f $" % v)
                if v > 0.5:
                    print("  >>> TEN TYP ZADZIALA. Ustaw: export PM_SIG_TYPE=%d" % st)
            except Exception:
                print("  saldo: %r" % (bal,))
        else:
            print("  salda nie udalo sie odczytac (to nie musi byc blad - sprawdz w UI)")
    print("\nGotowe. Wybierz typ, przy ktorym widac Twoje USDC, i ustaw PM_SIG_TYPE na niego.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
