#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diag_tpsl.py - testuje 8 wariantow TP/SL na Bitget i wypisuje, ktory dziala."""
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


def try_variant(name, path, body):
    print(f"\n[{name}]")
    try:
        r = z.api("POST", path, body=body, private=True)
        code, msg = r.get("code"), r.get("msg")
        print(f"   -> code={code} msg={msg}")
        if code == "00000":
            print("   *** DZIALA ***")
            return True
    except Exception as e:
        print(f"   -> ERR {str(e)[:180]}")
    return False


def main():
    pos = get_pos()
    if not pos:
        print("brak pozycji - otworz pozycje i uruchom ponownie")
        return
    print("pozycja:", pos)
    a = z.atr(z.candles(60))[-1] or 0
    e = pos["entry"]
    long_ = pos["side"] == "long"
    tp = round(e + TP_MULT * a, 2) if long_ else round(e - TP_MULT * a, 2)
    sl = round(e - SL_MULT * a, 2) if long_ else round(e + SL_MULT * a, 2)
    print(f"ATR={a:.2f} TP={tp} SL={sl}")

    base = {"marginCoin": "USDT", "productType": z.PRODUCT, "symbol": z.SYMBOL}
    ok = []

    # 1) place-pos-tpsl, holdSide long/short, delegateType all
    if try_variant("1 pos-tpsl delegateType=all", "/api/v2/mix/order/place-pos-tpsl",
                   {**base, "marginMode": "isolated", "holdSide": pos["side"],
                    "delegateType": "all",
                    "stopSurplusTriggerPrice": str(tp), "stopSurplusTriggerType": "mark_price",
                    "stopSurplusExecutePrice": str(tp),
                    "stopLossTriggerPrice": str(sl), "stopLossTriggerType": "mark_price",
                    "stopLossExecutePrice": str(sl)}):
        ok.append("1")
    time.sleep(1)

    # 2) place-tpsl-order, holdSide uppercase
    if try_variant("2 plan holdSide=SHORT/LONG", "/api/v2/mix/order/place-tpsl-order",
                   {**base, "holdSide": pos["side"].upper(), "planType": "pos_profit",
                    "triggerPrice": str(tp), "triggerType": "mark_price",
                    "executePrice": str(tp), "size": str(pos["size"])}):
        ok.append("2")
    time.sleep(1)

    # 3) place-tpsl-order, holdSide = buy/sell (strona zlecenia zamykajacego)
    close_side = "sell" if long_ else "buy"
    if try_variant(f"3 plan holdSide={close_side}", "/api/v2/mix/order/place-tpsl-order",
                   {**base, "holdSide": close_side, "planType": "pos_profit",
                    "triggerPrice": str(tp), "triggerType": "mark_price",
                    "executePrice": str(tp), "size": str(pos["size"])}):
        ok.append("3")
    time.sleep(1)

    # 4) place-tpsl-order bez holdSide, z tradeSide=close
    if try_variant("4 plan tradeSide=close", "/api/v2/mix/order/place-tpsl-order",
                   {**base, "tradeSide": "close", "planType": "pos_profit",
                    "triggerPrice": str(tp), "triggerType": "mark_price",
                    "executePrice": str(tp), "size": str(pos["size"])}):
        ok.append("4")
    time.sleep(1)

    # 5) place-pos-tpsl bez delegateType, z planType
    if try_variant("5 pos-tpsl planType pos_profit", "/api/v2/mix/order/place-pos-tpsl",
                   {**base, "holdSide": pos["side"], "planType": "pos_profit",
                    "triggerPrice": str(tp), "triggerType": "mark_price",
                    "executePrice": str(tp)}):
        ok.append("5")
    time.sleep(1)

    # 6) place-order z presetStopSurplusPrice / presetStopLossPrice
    for name, extra in (
        ("6a preset SL przy close", {"presetStopLossPrice": str(sl)}),
        ("6b preset TP+SL", {"presetStopSurplusPrice": str(tp), "presetStopLossPrice": str(sl)}),
    ):
        body = {**base, "marginMode": "isolated", "size": str(pos["size"]),
                "side": close_side, "orderType": "limit", "force": "gtc",
                "price": str(round(tp if long_ else tp, 2)), **extra}
        if try_variant(name, "/api/v2/mix/order/place-order", body):
            ok.append(name)
        time.sleep(1)

    print("\n=== WYNIK ===")
    print("dzialajace warianty:", ok if ok else "ZADEN")
    if ok:
        print("Wklej mi ten numer - wdrozę go do bota.")


if __name__ == "__main__":
    main()