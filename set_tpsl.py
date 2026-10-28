#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""set_tpsl.py - ustawia TP/SL na Bitget dla ISTNIEJACEJ pozycji.
Probuje 3 wariantow endpointu i wypisuje pelna odpowiedz API."""
import sys
import time
import bitget_zec as z

TP_MULT, SL_MULT = 1.0, 2.5


def main():
    pos = None
    # pozycja (bez kluczy sie nie da -> prywatne)
    try:
        r = z.api("GET", "/api/v2/mix/position/single-position",
                  {"symbol": z.SYMBOL, "productType": z.PRODUCT, "marginCoin": "USDT"},
                  private=True)
        print("RAW position:", str(r)[:300])
        for p in r.get("data") or []:
            if float(p.get("total") or 0) > 0:
                pos = {"side": p.get("holdSide"), "size": float(p["total"]),
                       "entry": float(p.get("openPriceAvg") or 0)}
    except Exception as e:
        print("BLAD odczytu pozycji:", repr(e))
        return

    if not pos:
        print("brak otwartej pozycji")
        return
    print("pozycja:", pos)

    rows = z.candles(60)
    a = z.atr(rows)[-1] or 0
    e = pos["entry"]
    long_ = pos["side"] == "long"
    tp = round(e + TP_MULT * a, 2) if long_ else round(e - TP_MULT * a, 2)
    sl = round(e - SL_MULT * a, 2) if long_ else round(e + SL_MULT * a, 2)
    print(f"ATR={a:.2f} -> TP={tp} SL={sl}")

    variants = [
        ("A place-pos-tpsl (holdSide)",
         "/api/v2/mix/order/place-pos-tpsl",
         {"marginCoin": "USDT", "productType": z.PRODUCT, "symbol": z.SYMBOL,
          "holdSide": pos["side"],
          "stopSurplusTriggerPrice": str(tp), "stopSurplusTriggerType": "mark_price",
          "stopSurplusExecutePrice": "0",
          "stopLossTriggerPrice": str(sl), "stopLossTriggerType": "mark_price",
          "stopLossExecutePrice": "0"}),
        ("B place-pos-tpsl (planType single)",
         "/api/v2/mix/order/place-pos-tpsl",
         {"marginCoin": "USDT", "productType": z.PRODUCT, "symbol": z.SYMBOL,
          "holdSide": pos["side"], "planType": "pos_profit",
          "triggerPrice": str(tp), "triggerType": "mark_price", "executePrice": "0"}),
        ("C place-tpsl-order (plan)",
         "/api/v2/mix/order/place-tpsl-order",
         {"marginCoin": "USDT", "productType": z.PRODUCT, "symbol": z.SYMBOL,
          "holdSide": pos["side"], "planType": "pos_loss",
          "triggerPrice": str(sl), "triggerType": "mark_price", "executePrice": "0"}),
    ]

    for name, path, body in variants:
        print(f"\n--- {name} ---")
        print("body:", body)
        try:
            r = z.api("POST", path, body=body, private=True)
            print("ODP:", r)
        except Exception as ex:
            print("ERR:", repr(ex))
        time.sleep(1)


if __name__ == "__main__":
    main()