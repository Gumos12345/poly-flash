#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diag_tpsl2.py - 4 brakujace kombinacje (poprzednie 8 odpada)."""
import time
import bitget_zec as z

TP_MULT, SL_MULT = 1.0, 2.5


def get_pos():
    r = z.api("GET", "/api/v2/mix/position/single-position",
              {"symbol": z.SYMBOL, "productType": z.PRODUCT, "marginCoin": "USDT"},
              private=True)
    for p in r.get("data") or []:
        if float(p.get("total") or 0) > 0:
            return {"side": p.get("holdSide"), "size": float(p["total"]),
                    "entry": float(p.get("openPriceAvg") or 0)}
    return None


def t(name, path, body):
    print(f"\n[{name}]")
    try:
        r = z.api("POST", path, body=body, private=True)
        print(f"   -> {r.get('code')} {r.get('msg')}")
        if r.get("code") == "00000":
            print("   *** DZIALA ***")
            return True
    except Exception as e:
        print(f"   -> {str(e)[:170]}")
    return False


def main():
    pos = get_pos()
    if not pos:
        print("brak pozycji")
        return
    print("pozycja:", pos)
    a = z.atr(z.candles(60))[-1] or 0
    e = pos["entry"]
    long_ = pos["side"] == "long"
    tp = round(e + TP_MULT * a, 2) if long_ else round(e - TP_MULT * a, 2)
    sl = round(e - SL_MULT * a, 2) if long_ else round(e + SL_MULT * a, 2)
    print(f"ATR={a:.2f} TP={tp} SL={sl}")

    base = {"marginCoin": "USDT", "productType": z.PRODUCT, "symbol": z.SYMBOL}
    stops = {"stopSurplusTriggerPrice": str(tp), "stopSurplusTriggerType": "mark_price",
             "stopSurplusExecutePrice": str(tp),
             "stopLossTriggerPrice": str(sl), "stopLossTriggerType": "mark_price",
             "stopLossExecutePrice": str(sl)}
    ok = []

    # A) pos-tpsl BEZ delegateType, z stopSurplus/stopLoss  <-- najpewniej to
    if t("A pos-tpsl bez delegateType", "/api/v2/mix/order/place-pos-tpsl",
         {**base, "holdSide": pos["side"], **stops}):
        ok.append("A")
    time.sleep(1)

    # B) j.w. + marginMode isolated
    if t("B pos-tpsl + marginMode", "/api/v2/mix/order/place-pos-tpsl",
         {**base, "marginMode": "isolated", "holdSide": pos["side"], **stops}):
        ok.append("B")
    time.sleep(1)

    # C) plan holdSide lowercase (short), pos_profit
    if t("C plan holdSide=short", "/api/v2/mix/order/place-tpsl-order",
         {**base, "holdSide": pos["side"], "planType": "pos_profit",
          "triggerPrice": str(tp), "triggerType": "mark_price", "executePrice": str(tp)}):
        ok.append("C")
    time.sleep(1)

    # D) plan + delegateType=position
    if t("D plan delegateType=position", "/api/v2/mix/order/place-tpsl-order",
         {**base, "holdSide": pos["side"], "delegateType": "position",
          "planType": "pos_profit", "triggerPrice": str(tp),
          "triggerType": "mark_price", "executePrice": str(tp)}):
        ok.append("D")

    print("\n=== WYNIK ===")
    print("dzialajace:", ok if ok else "ZADEN")


if __name__ == "__main__":
    main()