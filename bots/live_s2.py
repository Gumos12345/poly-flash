#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LIVE — S2_TP70 na wszystkie rynki 5m/15m (7 monet), bankroll 50$, stawka 1.25$, drabinka +1%/+1%.
=================================================================================================
Ten sam sygnał co w dry-runie 2 (S2_TP70): model v3 (fair mieszane z mid rynku) + opłata takera
w przewadze + filtr spreadu (≤6c) + filtr głębokości (3x stawka) + persist 2 cykle, wyjście TP po bid ≥ 0.70.

TRYBY (zawsze zaczynaj od --check, potem --paper):
  python3 live_s2.py --check                     # logowanie + saldo + wykrywanie rynków, ZERO zleceń
  python3 live_s2.py --paper                     # pełna pętla na żywych książkach, zlecenia SYMULOWANE
  I_UNDERSTAND_RISK=1 python3 live_s2.py --live --yes    # PRAWDZIWE zlecenia FOK

BEZPIECZNIKI (w kodzie, nie do obejścia flagą):
  * --max-order (domyślnie = stawka 1.25$) - twardy limit jednego zlecenia
  * --max-open (3) - maks. otwartych pozycji
  * dzienny stop: przy stracie > --daily-stop (10%) kapitału bot przestaje wchodzić do końca doby
  * jedna pozycja na (wariant, rynek); po TP ten rynek jest zablokowany do końca okna
  * BRAK ponowień: niejednoznaczna odpowiedź = pozycja "CHECK", zero kolejnych prób na tym rynku
  * kapitał liczony jak w paper (bankroll + zrealizowany PnL); wygrane z rozliczeń odbierasz w UI
    Polymarket ("Claim"), bo inaczej nie wchodzą do obrotu
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
import poly_dryrun_engine as E  # noqa: E402

# ------------------------------- KONFIG WARIANTU (S2_TP70) ------------------------------
V = dict(id=1, name="S2_TP70_LIVE", tfs=("5m", "15m"), min_px=0.10, max_px=0.90,
         min_fair=0.45, edge=0.04, model="v3", w_mkt=0.15, vol_cushion=1.05,
         tp=0.70, sl=None, max_pos=99, persist=2, depth_x=3, max_spread=0.06,
         timing={"5m": (0, 300), "15m": (0, 900)})
LAD = dict(kind="ladder", start_stake=1.25, step_bank=0.01, step_stake=0.01,
           down=False, min_stake=1.25, max_stake=10.0)
BOOK_FILE = os.path.join(ROOT, "state", "live_s2.json")


# ------------------------------- ZLECENIA (py-clob-client-v2) ---------------------------
class Broker:
    def __init__(self, live=False):
        self.live = live
        self.sdk = self.client = None
        self.bal = None
        if live:
            self.connect()

    def connect(self):
        try:
            import py_clob_client_v2 as sdk
        except ImportError:
            sys.exit("Brak SDK. W Termuxie: pip install py-clob-client-v2")
        pk = os.environ.get("PM_PRIVATE_KEY")
        if not pk:
            sys.exit("Ustaw PM_PRIVATE_KEY (klucz prywatny portfela).")
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
                sys.exit("Nie udało się uzyskać kluczy API: %r" % (ex,))
        tmp.set_api_creds(creds)
        self.sdk, self.client = sdk, tmp
        print("Połączono z CLOB. Klucze API: OK")

    def balance(self):
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
                    self.bal = float(v) / 1e6 if float(v) > 1000 else float(v)
                    return self.bal
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
                mk = float(r.get("makingAmount") or 0)      # USDC wydane
                tk = float(r.get("takingAmount") or 0)      # udziały kupione
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
            msg = str(getattr(ex, "error_msg", "") or ex)[:90]
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
            msg = str(getattr(ex, "error_msg", "") or ex)[:90]
            if isinstance(code, int) and 400 <= code < 500:
                return {"status": "rejected", "msg": msg}
            return {"status": "unknown", "msg": "%s: %s" % (type(ex).__name__, msg)}


# ------------------------------- KSIĘGA + LOGIKA -------------------------------
def now_s():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


class LiveRun:
    def __init__(self, live, bank=50.0, max_order=1.25, max_open=3, daily_stop=0.10, sleep=2.0):
        self.live = live
        self.max_order = max_order
        self.max_open = max_open
        self.daily_stop = daily_stop
        self.sleep = sleep
        V["ladder"] = dict(LAD, start_stake=1.25)
        V["start_stake"] = 1.25
        self.eng = E.Engine([V], "live_s2")          # dane + model + księga (VBook)
        self.book = self.eng.books[1]
        self.book.lad["start_stake"] = 1.25
        self.eng.start_bank = bank
        self.book.start_bank = bank
        self.state_path = os.path.join(ROOT, "state", "live_s2.json")
        self.state = {"start": time.time(), "bank": bank, "day": "", "day_pnl": 0.0,
                      "halt": False, "blocked": {}, "streak": {}}
        self.broker = Broker(live)
        self.load()

    # --- stan
    def load(self):
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path) as f:
                    d = json.load(f)
                self.state.update({k: d.get(k, self.state[k]) for k in self.state})
                if d.get("book"):
                    self.book.load(d["book"])
                print("Wczytano stan: realizowane %.2f$, otwarte %d" % (self.book.realized, len(self.book.positions)))
            except Exception as ex:
                print("Stan nieczytelny (%r) - start od zera" % (ex,))

    def save(self):
        self.state["book"] = self.book.dump()
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f)
        os.replace(tmp, self.state_path)

    # --- decyzja
    def pick(self, ctxs, now):
        if self.book.halted:
            return None
        st, lvl = self.book.stake_now()
        if st <= 0 or st > self.book.equity() or st > self.max_order:
            return None
        if len(self.book.positions) >= self.max_open:
            return None
        best = None
        for (asset, tf), c in ctxs.items():
            if tf not in V["tfs"]:
                continue
            lo, hi = V["timing"][tf]
            if not (lo <= c.elapsed <= hi) or c.rem < 8:
                continue
            if self.eng.feed.spot_age(asset) > 5:
                continue
            slug = "%s-updown-%s-%d" % (asset.lower(), tf, c.start)
            if any(pp["slug"] == slug for pp in self.book.positions.values()) \
                    or now < self.state["blocked"].get(slug, 0):
                continue
            p_up, _s = E.model_probs(c, V["model"], V["w_mkt"], V["vol_cushion"])
            for side in ("Up", "Down"):
                p = p_up if side == "Up" else 1.0 - p_up
                ask = c.ask.get(side)
                if ask is None:
                    continue
                if not (V["min_px"] <= ask <= V["max_px"]) or p < V["min_fair"]:
                    continue
                edge = E.net_edge(p, ask)
                if edge < V["edge"] or edge > 0.35:
                    continue
                sp = c.spread.get(side)
                if sp is None or sp > V["max_spread"]:
                    continue
                if c.depth(side) < V["depth_x"] * st / max(ask, 0.01):
                    continue
                k = (slug, side)
                self.state["streak"][k] = self.state["streak"].get(k, 0) + 1
                if self.state["streak"][k] < V["persist"]:
                    continue
                if best is None or edge > best[0]:
                    best = (edge, c, side, p, ask, slug)
        return best

    def open_pos(self, hit, now):
        edge, c, side, p, ask, slug = hit
        st, lvl = self.book.stake_now()
        m = self.eng.mk.market(slug, now)
        if not m:
            return
        worst = min(0.97, ask + 0.02)
        res = self.broker.buy(c.tokens[side], st, worst, m)
        if res["status"] == "rejected":
            print("[%s] ODRZUCONE %s %s %s: %s" % (now_s(), c.asset, c.tf, side, res.get("msg", "")[:60]))
            self.state["blocked"][slug] = now + 30
            self.save()
            return
        if res["status"] == "unknown":
            print("[%s] NIEPEWNE %s %s %s: %s -> pozycja CHECK, zero ponowień"
                  % (now_s(), c.asset, c.tf, side, res.get("msg", "")[:60]))
            self.state["blocked"][slug] = now + 86400
            self.save()
            return
        spent, shares = res["spent"], res["shares"]
        fee = shares * E.fee_ps(spent / max(shares, 1e-9))
        key = "1|%s" % slug
        self.book.positions[key] = dict(
            key=key, asset=c.asset, tf=c.tf, side=side, slug=slug, start=int(c.start), end=int(c.end),
            tok=c.tokens[side], entry=round(spent / shares, 5), shares=round(shares, 6),
            cost=round(spent + fee, 6), stake=round(st, 4), lvl=lvl, p=round(p, 4),
            edge=round(edge, 4), t_open=round(now, 1), status="open", tp=V["tp"], sl=None,
            spr=round(c.spread.get(side) or 0.0, 4), rem_at_open=round(c.rem, 1),
            bank_in=round(self.book.equity(), 2), model=V["model"])
        self.save()
        print("[%s] %s KUPNO %-4s %-3s %-4s @%.3f p=%.3f edge=%.3f stawka=%.2f$ -> %.2f udziałów (id %s)"
              % (now_s(), "LIVE" if self.live else "PAPER", c.asset, c.tf, side,
                 spent / shares, p, edge, st, shares, res.get("id", "")[:10]))

    def manage(self, now):
        for key, p in list(self.book.positions.items()):
            if p["status"] != "open":
                continue
            if now >= p["end"] + 2:
                r = self.eng.resolve(p["slug"], p["asset"], p["start"], p["end"], now)
                if r:
                    win = p["side"] == r
                    pnl = (p["shares"] - p["cost"]) if win else -p["cost"]
                    self.close(p, pnl, "WIN" if win else "LOSS", 1.0 if win else 0.0, now)
                continue
            bk = self.eng.mk.book(p["tok"])
            if not bk or not bk["bids"]:
                continue
            bid = bk["bids"][0][0]
            if V["tp"] and bid >= V["tp"]:
                m = self.eng.mk.market(p["slug"], now) or {}
                res = self.broker.sell(p["tok"], p["shares"], max(0.01, bid - 0.02), m)
                if res["status"] == "filled":
                    got = res["proceeds"]
                    self.close(p, got - p["shares"] * E.fee_ps(bid) - p["cost"], "TP", bid, now)
                elif res["status"] == "unknown":
                    p["status"] = "check"
                    self.save()
                    print("[%s] SPRZEDAŻ NIEPEWNA %s - sprawdź ręcznie" % (now_s(), p["slug"]))

    def close(self, p, pnl, kind, px, now):
        p.update(status="closed", exit=kind, exit_px=px, pnl=round(pnl, 6),
                 hold=round(now - p["t_open"], 1))
        self.book.realized += pnl
        self.book.closed.append(p)
        self.book.positions.pop(p["key"], None)
        self.book.peak_equity = max(self.book.peak_equity, self.book.equity())
        self.state["day_pnl"] = self.state.get("day_pnl", 0.0) + pnl
        self.state["blocked"][p["slug"]] = now + 86400
        self.save()
        print("[%s] ZAMKNIĘTE %-4s %-3s %-4s %-4s %+7.2f$ | kapitał %.2f$ | PnL dnia %+.2f$"
              % (now_s(), p["asset"], p["tf"], p["side"], kind, pnl, self.book.equity(),
                 self.state["day_pnl"]))
        if self.state["day_pnl"] <= -self.daily_stop * self.state["bank"] and not self.state["halt"]:
            self.state["halt"] = True
            print("!!! DZIENNY STOP: strata %.2f$ > %.0f%% bankrolla - koniec wejść do jutra (UTC)"
                  % (-self.state["day_pnl"], self.daily_stop * 100))
            self.save()

    def run(self, minutes=None):
        print("START %s | S2_TP70 | wszystkie 5m/15m | bankroll %.2f$ stawka %.2f$ | "
              "drabinka +%.0f%%/+%.0f%% UP | max_order %.2f$ max_open %d"
              % ("LIVE" if self.live else "PAPER", self.state["bank"], LAD["start_stake"],
                 LAD["step_stake"] * 100, LAD["step_bank"] * 100, self.max_order, self.max_open))
        dl = time.time() + minutes * 60 if minutes else None
        cyc = 0
        while True:
            now = time.time()
            if dl and now > dl:
                break
            d = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if self.state.get("day") != d:
                self.state.update(day=d, day_pnl=0.0, halt=False)
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
                    print("[%s] cykl %d | ctx=%d | kapitał %.2f$ | otwarte %d | zamkn. %d | req err %d"
                          % (now_s(), cyc, len(ctxs), self.book.equity(),
                             len(self.book.positions), len(self.book.closed), self.eng.mk.err))
            except KeyboardInterrupt:
                print("przerwano")
                break
            except Exception as ex:
                print("[%s] ERR %r" % (now_s(), ex))
            time.sleep(self.sleep)
        self.save()
        print("Zapisano stan:", self.state_path)


# ------------------------------- START -------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="LIVE S2_TP70 (5m/15m, 7 monet)")
    ap.add_argument("--check", action="store_true", help="logowanie + saldo + rynki (zero zleceń)")
    ap.add_argument("--paper", action="store_true", help="pełna pętla, zlecenia symulowane (domyślne)")
    ap.add_argument("--live", action="store_true", help="PRAWDZIWE zlecenia (wymaga I_UNDERSTAND_RISK=1 i --yes)")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--bank", type=float, default=50.0)
    ap.add_argument("--stake", type=float, default=1.25)
    ap.add_argument("--max-order", type=float, default=1.25)
    ap.add_argument("--max-open", type=int, default=3)
    ap.add_argument("--daily-stop", type=float, default=0.10)
    ap.add_argument("--minutes", type=float, default=0.0)
    ap.add_argument("--sleep", type=float, default=2.0)
    a = ap.parse_args(argv)
    LAD["start_stake"] = a.stake
    LAD["min_stake"] = a.stake

    if a.check:
        b = Broker(live=True)
        bal = b.balance()
        print("Saldo widoczne w SDK: %s" % (("%.2f $ " % bal) if bal is not None else "nieznane (sprawdź saldo w UI)"))
        eng = E.Engine([V], "live_s2_check")
        feed, mk = eng.feed, eng.mk
        feed.refresh_spot()
        now = time.time()
        ctxs = eng.build_ctxs(now)
        print("Rynki znalezione: %d (7 monet x 5m/15m)" % len(ctxs))
        for (asset, tf), c in sorted(ctxs.items()):
            p_up, _ = E.model_probs(c, V["model"], V["w_mkt"], V["vol_cushion"])
            side = "Up" if p_up >= 0.5 else "Down"
            p = p_up if side == "Up" else 1 - p_up
            ask = c.ask.get(side)
            edge = E.net_edge(p, ask) if ask is not None else None
            sp = c.spread.get(side)
            ok = (ask is not None and V["min_px"] <= ask <= V["max_px"] and p >= V["min_fair"]
                  and edge is not None and V["edge"] <= edge <= 0.35 and sp is not None
                  and sp <= V["max_spread"])
            print("  %-4s %-3s %-4s ask=%s bid=%s spread=%s p=%.3f edge=%s -> %s"
                  % (asset, tf, side,
                     ("%.3f" % ask) if ask is not None else "-",
                     ("%.3f" % c.bid[side]) if c.bid.get(side) is not None else "-",
                     ("%.3f" % sp) if sp is not None else "-", p,
                     ("%+.3f" % edge) if edge is not None else "-",
                     "SYGNAŁ" if ok else "-"))
        print("\n--check OK. Zero zleceń. Następny krok: python3 live_s2.py --paper")
        return 0

    if a.live:
        if os.environ.get("I_UNDERSTAND_RISK") != "1" or not a.yes:
            print("""\nZATRZYMANE. Aby wysyłać PRAWDZIWE zlecenia, musisz świadomie potwierdzić:
  I_UNDERSTAND_RISK=1 python3 live_s2.py --live --yes --bank 50 --stake 1.25

Zanim to zrobisz, uruchom najpierw:
  1) python3 live_s2.py --check        (logowanie, saldo, rynki - zero zleceń)
  2) python3 live_s2.py --paper         (24-48 h na żywych książkach, bez pieniędzy)
Limity w tym przebiegu: max_order %.2f$, max_open %d, dzienny stop %.0f%% kapitału.
""" % (a.max_order, a.max_open, a.daily_stop * 100))
            return 2
        print("UWAGA: PRAWDZIWE ZLECENIA. Stawka %.2f$, max_order %.2f$, max_open %d, stop dzienny %.0f%%"
              % (a.stake, a.max_order, a.max_open, a.daily_stop * 100))

    run = LiveRun(a.live, bank=a.bank, max_order=a.max_order, max_open=a.max_open,
                  daily_stop=a.daily_stop, sleep=a.sleep)
    run.run(minutes=a.minutes or None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
