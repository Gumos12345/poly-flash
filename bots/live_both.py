#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIVE BOTH — oba boty naraz w JEDNYM procesie, tryb ANTI (odwrotność modelu).
Bankroll 50 $ (25 $ na bota), stawka 1.25 $, drabinka +1%/+1% UP.

Użycie:
    python3 live_both.py --check        # saldo + rynki, zero zleceń
    python3 live_both.py --paper        # paper trading na żywych książkach
    I_UNDERSTAND_RISK=1 python3 live_both.py --live --yes   # PRAWDZIWE zlecenia

Wyjście: Ctrl+C lub pkill -f live_both.py
"""

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import poly_dryrun_engine as E

# ------------------------------------------------------------------ PRESETY ANTI (odwrotność modelu)
TP70_ANTI = dict(model="v3", w_mkt=0.15, vol_cushion=1.05, min_px=0.10, max_px=0.90,
                 min_fair=0.45, edge=0.04, persist=2, depth_x=3, max_spread=0.06,
                 tp=0.70, sl=None, anti=True)
MIN40_ANTI = dict(model="v1", w_mkt=0.0, vol_cushion=1.0, min_px=0.40, max_px=0.85,
                  min_fair=0.40, edge=0.05, persist=0, depth_x=0, max_spread=None,
                  tp=0.80, sl=None, anti=True)

LAD = dict(kind="ladder", start_stake=1.25, step_bank=0.01, step_stake=0.01,
           down=False, min_stake=1.25, max_stake=10.0)

BOOK_FILE_A = os.path.join(ROOT, "state", "live_both_a.json")
BOOK_FILE_B = os.path.join(ROOT, "state", "live_both_b.json")


# ------------------------------------------------------------------ BROKER (py-clob-client-v2)
class Broker:
    def __init__(self, live=False):
        self.live = live
        self.sdk = self.client = None
        if live:
            self.connect()

    def connect(self):
        try:
            import py_clob_client_v2 as sdk
        except ImportError:
            sys.exit("Brak SDK: pip install py-clob-client-v2")
        pk = os.environ.get("PM_PRIVATE_KEY")
        if not pk:
            sys.exit("Ustaw PM_PRIVATE_KEY")
        kw = {"host": E.CLOB, "chain_id": 137, "key": pk}
        if os.environ.get("PM_FUNDER"):
            kw["funder"] = os.environ["PM_FUNDER"]
            kw["signature_type"] = int(os.environ.get("PM_SIG_TYPE", "3"))
        tmp = sdk.ClobClient(**kw)
        creds = None
        for fn in ("derive_api_key", "derive_api_creds", "create_or_derive_api_creds"):
            f = getattr(tmp, fn, None)
            if not f:
                continue
            try:
                c = f()
                if getattr(c, "api_key", None) or (isinstance(c, dict) and c.get("apiKey")):
                    creds = c
                    break
            except Exception:
                continue
        if creds is None:
            try:
                creds = tmp.create_api_key()
            except Exception as ex:
                sys.exit("Brak kluczy API: %r" % (ex,))
        tmp.set_api_creds(creds)
        self.sdk, self.client = sdk, tmp
        print("Połączono z CLOB. Klucze API: OK")

    def balance(self):
        """Zwraca saldo USDC w dolarach albo None."""
        if not self.live:
            return None
        for fn in ("get_balance", "get_balance_allowance"):
            f = getattr(self.client, fn, None)
            if not f:
                continue
            try:
                b = f()
                v = b.get("balance") if isinstance(b, dict) else getattr(b, "balance", None)
                if v is not None:
                    return float(v) / 1e6 if float(v) > 1000 else float(v)
            except Exception:
                continue
        return None

    def buy(self, tok, usd, worst, m):
        if not self.live:
            return {"status": "filled", "spent": usd, "shares": usd / max(worst, 1e-6), "id": "PAPER"}
        sdk = self.sdk
        try:
            try:
                args = sdk.MarketOrderArgs(token_id=tok, amount=usd, side=sdk.Side.BUY,
                                           price=worst, order_type=sdk.OrderType.FOK)
            except TypeError:
                args = sdk.MarketOrderArgs(token_id=tok, amount=usd, side=sdk.Side.BUY,
                                           order_type=sdk.OrderType.FOK)
            tick = m.get("orderPriceMinTickSize")
            opts = sdk.PartialCreateOrderOptions(tick_size="%g" % float(tick)) if tick else None
            r = self.client.create_and_post_market_order(order_args=args, options=opts,
                                                         order_type=sdk.OrderType.FOK)
            if not isinstance(r, dict):
                r = dict(getattr(r, "__dict__", {}) or {})
            st = str(r.get("status", "")).lower()
            if r.get("success") and st in ("matched", "filled"):
                mk = float(r.get("makingAmount") or 0)
                tk = float(r.get("takingAmount") or 0)
                if mk > 0 and tk > 0:
                    return {"status": "filled", "spent": mk, "shares": tk, "id": r.get("orderID", "")}
                return {"status": "filled", "spent": usd, "shares": usd / max(worst, 1e-6),
                        "id": r.get("orderID", ""), "est": True}
            err = str(r.get("errorMsg") or "")
            if r.get("success") is False or err:
                return {"status": "rejected", "msg": err or st or "odrzucone"}
            return {"status": "unknown", "msg": "status=%s" % st}
        except Exception as ex:
            code = getattr(ex, "status_code", None)
            msg = str(getattr(ex, "error_msg", "ex") or ex)[:90]
            if isinstance(code, int) and 400 <= code < 500:
                return {"status": "rejected", "msg": msg}
            return {"status": "unknown", "msg": "%s: %s" % (type(ex).__name__, msg)}

    def sell(self, tok, shares, minpx, m):
        if not self.live:
            return {"status": "filled", "proceeds": shares * minpx, "id": "PAPER"}
        sdk = self.sdk
        try:
            try:
                args = sdk.MarketOrderArgs(token_id=tok, amount=shares, side=sdk.Side.SELL,
                                           price=minpx, order_type=sdk.OrderType.FOK)
            except TypeError:
                args = sdk.MarketOrderArgs(token_id=tok, amount=shares, side=sdk.Side.SELL,
                                           order_type=sdk.OrderType.FOK)
            tick = m.get("orderPriceMinTickSize")
            opts = sdk.PartialCreateOrderOptions(tick_size="%g" % float(tick)) if tick else None
            r = self.client.create_and_post_market_order(order_args=args, options=opts,
                                                         order_type=sdk.OrderType.FOK)
            if not isinstance(r, dict):
                r = dict(getattr(r, "__dict__", {}) or {})
            st = str(r.get("status", "")).lower()
            if r.get("success") and st in ("matched", "filled"):
                got = float(r.get("takingAmount") or 0)
                return {"status": "filled", "proceeds": got if got > 0 else shares * minpx,
                        "id": r.get("orderID", "")}
            err = str(r.get("errorMsg") or "")
            if r.get("success") is False or err:
                return {"status": "rejected", "msg": err or st or "odrzucone"}
            return {"status": "unknown", "msg": "status=%s" % st}
        except Exception as ex:
            code = getattr(ex, "status_code", None)
            msg = str(getattr(ex, "error_msg", "ex") or ex)[:90]
            if isinstance(code, int) and 400 <= code < 500:
                return {"status": "rejected", "msg": msg}
            return {"status": "unknown", "msg": "%s: %s" % (type(ex).__name__, msg)}


# ------------------------------------------------------------------ OBY BOTY W JEDNYM PROCESIE
class BothRun:
    def __init__(self, live, bank_a=25.0, bank_b=25.0, max_order=1.25, max_open=4,
                 daily_stop=0.5, sleep=2.0):
        self.live = live
        self.max_order = max_order
        self.max_open = max_open
        self.daily_stop = daily_stop
        self.sleep = sleep

        va = dict(id=1, name="A_TP70_ANTI", tfs=("5m", "15m"))
        va.update(TP70_ANTI)
        va["ladder"] = dict(LAD)
        va["start_stake"] = 1.25

        vb = dict(id=2, name="B_MIN40_ANTI", tfs=("5m", "15m"))
        vb.update(MIN40_ANTI)
        vb["ladder"] = dict(LAD)
        vb["start_stake"] = 1.25

        self.eng = E.Engine([va, vb], "live_both")
        self.books = self.eng.books
        self.books[1].start_bank = bank_a
        self.books[2].start_bank = bank_b
        self.state_path_a = BOOK_FILE_A
        self.state_path_b = BOOK_FILE_B
        self.state = {"start": time.time(), "bank_a": bank_a, "bank_b": bank_b,
                      "day": "", "day_pnl_a": 0.0, "day_pnl_b": 0.0, "halt": False,
                      "blocked": {}, "streak": {}}
        self.broker = Broker(live)
        self.load()

    def load(self):
        for sp, b in ((self.state_path_a, self.books[1]), (self.state_path_b, self.books[2])):
            if os.path.exists(sp):
                try:
                    with open(sp) as f:
                        d = json.load(f)
                    if d.get("book"):
                        b.load(d["book"])
                    print("Wczytano stan %s: realizowane %.2f$, otwarte %d"
                          % (sp, b.realized, len(b.positions)))
                except Exception as ex:
                    print("Stan %s nieczytelny (%r) - start od zera" % (sp, ex))

    def save(self):
        for sp, b in ((self.state_path_a, self.books[1]), (self.state_path_b, self.books[2])):
            d = {"book": b.dump(), "halted": b.halted}
            tmp = sp + ".tmp"
            with open(tmp, "w") as f:
                json.dump(d, f)
            os.replace(tmp, sp)

    def now_s(self):
        return datetime.now(timezone.utc).strftime("%H:%M:%S")

    def pick(self, ctxs, now):
        """Zwraca (edge, b, c, side, p, ask, slug, st, lvl) dla najlepszego sygnału anti."""
        best = None
        for b in self.books.values():
            if b.halted:
                continue
            st, lvl = b.stake_now()
            if st <= 0 or st > b.equity() or st > self.max_order:
                continue
            if len(b.positions) >= self.max_open:
                continue
            v = b.v
            for (asset, tf), c in ctxs.items():
                if tf not in v["tfs"]:
                    continue
                lo, hi = v["timing"][tf]
                if not (lo <= c.elapsed <= hi) or c.rem < 8:
                    continue
                if self.eng.feed.spot_age(asset) > 5:
                    continue
                slug = "%s-updown-%s-%d" % (asset.lower(), tf, c.start)
                if any(pp["slug"] == slug for pp in b.positions.values()) or now < self.state["blocked"].get(slug, 0):

                    continue
                p_up, _s = E.model_probs(c, v["model"], v["w_mkt"], v["vol_cushion"])
                sides = []
                for side in ("Up", "Down"):
                    p = p_up if side == "Up" else 1.0 - p_up
                    ask = c.ask.get(side)
                    if ask is None:
                        continue
                    if not (v["min_px"] <= ask <= v["max_px"]):
                        continue
                    if p < v["min_fair"]:
                        continue
                    edge = E.net_edge(p, ask)
                    if edge > 0.35:
                        continue
                    sp = c.spread.get(side)
                    if sp is not None and sp > (v["max_spread"] if v.get("max_spread") else 0.20):
                        continue
                    if v.get("depth_x") and c.depth(side) < v["depth_x"] * st / max(ask, 0.01):
                        continue
                    sides.append((edge, side, p, ask))
                if not sides:
                    continue
                # ANTI: bierzemy stronę PRZECIWNEJ do najlepszej (najwyższej edge)
                sides.sort(key=lambda x: -x[0])
                edge_n, side_n, p_n, ask_n = sides[0]
                side_o = "Down" if side_n == "Up" else "Up"
                p_o = 1.0 - p_n
                ask_o = c.ask.get(side_o)
                if ask_o is None:
                    continue
                if not (v["min_px"] <= ask_o <= v["max_px"]):
                    continue
                sp_o = c.spread.get(side_o)
                if sp_o is not None and sp_o > (v["max_spread"] if v.get("max_spread") else 0.20):
                    continue
                if v.get("depth_x") and c.depth(side_o) < v["depth_x"] * st / max(ask_o, 0.01):
                    continue
                k = (slug, side_o)
                self.state["streak"][k] = self.state["streak"].get(k, 0) + 1
                if v.get("persist") and self.state["streak"][k] < v["persist"]:
                    continue
                if best is None or edge_n > best[0]:
                    best = (edge_n, b, c, side_o, p_o, ask_o, slug, st, lvl)
        return best

    def open_pos(self, hit, now):
        edge, b, c, side, p, ask, slug, st, lvl = hit
        m = self.eng.mk.market(slug, now)
        if not m:
            return
        worst = min(0.97, ask + 0.02)
        res = self.broker.buy(c.tokens[side], st, worst, m)
        if res["status"] == "rejected":
            print("[%s] ODRZUCONE %s %s %s: %s" % (self.now_s(), c.asset, c.tf, side,
                                                  res.get("msg", "")[:60]))
            self.state["blocked"][slug] = now + 30
            self.save()
            return
        if res["status"] == "unknown":
            print("[%s] NIEPEWNE %s %s %s: %s -> CHECK, zero ponowień"
                  % (self.now_s(), c.asset, c.tf, side, res.get("msg", "")[:60]))
            self.state["blocked"][slug] = now + 86400
            self.save()
            return
        spent, shares = res["spent"], res["shares"]
        fee = shares * E.fee_ps(spent / max(shares, 1e-9))
        key = "%d|%s" % (b.id, slug)
        b.positions[key] = dict(key=key, asset=c.asset, tf=c.tf, side=side, slug=slug,
                                start=int(c.start), end=int(c.end), tok=c.tokens[side],
                                entry=round(spent / shares, 5), shares=round(shares, 6),
                                cost=round(spent + fee, 6), stake=round(st, 4), lvl=lvl,
                                p=round(p, 4), edge=round(edge, 4), t_open=round(now, 1),
                                status="open", tp=v_tp(b), sl=None,
                                spr=round(c.spread.get(side) or 0.0, 4),
                                rem_at_open=round(c.rem, 1),
                                bank_in=round(b.equity(), 2), model=b.v.get("model", "v1"))
        self.save()
        print("[%s] %s KUPNO %-4s %-3s %-4s %-4s @%.3f p=%.3f edge=%.3f stawka=%.2f$ -> %.2f udziałów (id %s)"
              % (self.now_s(), "LIVE" if self.live else "PAPER", c.asset, c.tf, side,
                 "ANTI", ask, p, edge, st, shares, res.get("id", "")[:10]))

    def manage(self, now):
        for b in self.books.values():
            for key, p in list(b.positions.items()):
                if p["status"] != "open":
                    continue
                if now >= p["end"] + 2:
                    r = self.eng.resolve(p["slug"], p["asset"], p["start"], p["end"], now)
                    if r:
                        win = p["side"] == r
                        pnl = (p["shares"] - p["cost"]) if win else -p["cost"]
                        self.close(b, p, pnl, "WIN" if win else "LOSS", 1.0 if win else 0.0, now)
                    continue
                bk = self.eng.mk.book(p["tok"])
                if not bk or not bk["bids"]:
                    continue
                bid = bk["bids"][0][0]
                tp = p.get("tp")
                if tp and bid >= tp:
                    m = self.eng.mk.market(p["slug"], now) or {}
                    res = self.broker.sell(p["tok"], p["shares"], max(0.01, bid - 0.02), m)
                    if res["status"] == "filled":
                        got = res["proceeds"]
                        self.close(b, p, got - p["shares"] * E.fee_ps(bid) - p["cost"], "TP", bid, now)
                    elif res["status"] == "unknown":
                        p["status"] = "check"
                        self.save()
                        print("[%s] SPRZEDAŻ NIEPEWNA %s - sprawdź ręcznie" % (self.now_s(), p["slug"]))

    def close(self, b, p, pnl, kind, px, now):
        p.update(status="closed", exit=kind, exit_px=px, pnl=round(pnl, 6),
                 hold=round(now - p["t_open"], 1))
        b.realized += pnl
        b.closed.append(p)
        b.positions.pop(p["key"], None)
        b.peak_equity = max(b.peak_equity, b.equity())
        if b.id == 1:
            self.state["day_pnl_a"] = self.state.get("day_pnl_a", 0.0) + pnl
        else:
            self.state["day_pnl_b"] = self.state.get("day_pnl_b", 0.0) + pnl
        self.state["blocked"][p["slug"]] = now + 86400
        self.save()
        print("[%s] ZAMKNIĘTE %-4s %-3s %-4s %-4s %+7.2f$ | kapitał %.2f$ | PnL dnia A %+.2f$ B %+.2f$"
              % (self.now_s(), p["asset"], p["tf"], p["side"], kind, pnl, b.equity(),
                 self.state["day_pnl_a"], self.state["day_pnl_b"]))
        if b.id == 1 and self.state["day_pnl_a"] <= -self.daily_stop * self.state["bank_a"]:
            self.state["halt"] = True
        if b.id == 2 and self.state["day_pnl_b"] <= -self.daily_stop * self.state["bank_b"]:
            self.state["halt"] = True
        if self.state["halt"]:
            print("!!! DZIENNY STOP: koniec wejść do jutra UTC")
            self.save()

    def table(self):
        L = []
        L.append("LIVE BOTH ANTI  %s UTC" % time.strftime("%H:%M:%S", time.gmtime()))
        L.append("-" * 80)
        total_n = 0
        total_pnl = 0.0
        for b in (self.books[1], self.books[2]):
            s = b.stats()
            total_n += s["n"]
            total_pnl += s["pnl"]
            L.append("%-6s n=%-3d WR=%5.1f%% PnL=%+7.2f$ ret=%+6.1f%% DD=%5.1f%% otw=%d stawka=%.2f$ kapitał=%.2f$"
                     % (b.name[:6], s["n"], s["wr"], s["pnl"], s["pnl"] / b.start_bank * 100,
                        s["dd"], s["open"], s["stake"], b.equity()))
        L.append("-" * 80)
        L.append("RAZEM: n=%d  PnL=%+.2f$  |  dziennie A %+.2f$  B %+.2f$  |  bankroll 50 $"
                 % (total_n, total_pnl, self.state["day_pnl_a"], self.state["day_pnl_b"]))
        L.append("max_order %.2f$  max_open %d/daily_stop %.0f%%  ANTI=ON"
                 % (self.max_order, self.max_open, self.daily_stop * 100))
        return "\n".join(L)

    def run(self, minutes=None):
        print("START BOTH ANTI | bankroll A $%.2f B $%.2f | stawka $1.25 | drabinka +1%/+1% UP | "
              "max_order $%.2f | max_open %d | dzienny stop %.0f%%"
              % (self.state["bank_a"], self.state["bank_b"], self.max_order,
                 self.max_open, self.daily_stop * 100))
        dl = time.time() + minutes * 60 if minutes else None
        cyc = 0
        while True:
            now = time.time()
            if dl and now > dl:
                break
            d = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if self.state.get("day") != d:
                self.state.update(day=d, day_pnl_a=0.0, day_pnl_b=0.0, halt=False)
            try:
                ctxs = self.eng.build_ctxs(now)
                self.manage(now)
                if not self.state["halt"]:
                    hit = self.pick(ctxs, now)
                    if hit:
                        self.open_pos(hit, now)
                cyc += 1
                if cyc % 30 == 0:
                    self.save()
                    print(self.table())
            except KeyboardInterrupt:
                print("przerwano")
                break
            except Exception as ex:
                print("[%s] ERR %r" % (self.now_s(), ex))
            time.sleep(self.sleep)
        self.save()
        print(self.table())
        print("Zapisano stany:", self.state_path_a, "i", self.state_path_b)


# ------------------------------------------------------------------ MAIN
def main(argv=None):
    ap = argparse.ArgumentParser(description="LIVE BOTH ANTI (5m/15m, 7 monet)")
    ap.add_argument("--check", action="store_true", help="saldo + rynki, zero zleceń")
    ap.add_argument("--paper", action="store_true", help="paper trading (domyślne)")
    ap.add_argument("--live", action="store_true", help="PRAWDZIWE zlecenia (wymaga I_UNDERSTAND_RISK=1 i --yes)")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--bank-a", type=float, default=25.0, help="bankroll bota A ($)")
    ap.add_argument("--bank-b", type=float, default=25.0, help="bankroll bota B ($)")
    ap.add_argument("--stake", type=float, default=1.25, help="stawka startowa ($)")
    ap.add_argument("--max-order", type=float, default=1.25, help="twardy limit jednego zlecenia ($)")
    ap.add_argument("--max-open", type=int, default=4, help="maks. otwartych pozycji na bota")
    ap.add_argument("--daily-stop", type=float, default=0.5, help="dzienny stop (0.5 = -50%%)")
    ap.add_argument("--minutes", type=float, default=0.0, help="auto-stop po minutach")
    ap.add_argument("--sleep", type=float, default=2.0, help="przerwa między cyklami (s)")
    args = ap.parse_args(argv)

    if args.check:
        b = Broker(live=True)
        bal = b.balance()
        print("Saldo widoczne w SDK: %s" % (("%.2f $" % bal) if bal is not None else "nieznane (sprawdź w UI)"))
        eng = E.Engine([dict(id=1, name="X", tfs=("5m", "15m"))], "check")
        eng.feed.refresh_spot()
        ctxs = eng.build_ctxs(time.time())
        print("Rynki znalezione: %d" % len(ctxs))
        for (asset, tf), c in sorted(ctxs.items()):
            p_up, _ = E.model_probs(c, "v3", 0.15, 1.05)
            print("  %-4s %-3s ask=%s bid=%s p=%.3f" % (asset, tf,
                     ("%.3f" % c.ask["Up"]) if c.ask["Up"] else "-",
                     ("%.3f" % c.bid["Up"]) if c.bid["Up"] else "-", p_up))
        print("--check OK. Zero zleceń.")
        return 0

    if args.live:
        if os.environ.get("I_UNDERSTAND_RISK") != "1" or not args.yes:
            print("""ZATRZYMANE. Użyj:
  I_UNDERSTAND_RISK=1 python3 live_both.py --live --yes --bank-a 25 --bank-b 25
Najpierw: python3 live_both.py --check""")
            return 2
        print("UWAGA: PRAWDZIWE ZLECENIA. Bankroll A $%.2f B $%.2f | max_order $%.2f | max_open %d | stop %.0f%%"
              % (args.bank_a, args.bank_b, args.max_order, args.max_open, args.daily_stop * 100))

    run = BothRun(args.live, bank_a=args.bank_a, bank_b=args.bank_b,
                  max_order=args.max_order, max_open=args.max_open,
                  daily_stop=args.daily_stop, sleep=args.sleep)
    run.run(minutes=args.minutes or None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
