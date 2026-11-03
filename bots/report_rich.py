#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RAPORT.html — pełne statystyki obu dry-runów (jeden samodzielny plik: CSS+JS w środku).
Uruchomienie: python3 report_rich.py   ->  RAPORT.html  (+ reports/RAPORT.csv)
"""
import csv
import json
import math
import os
import statistics as st
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import poly_dryrun_engine as E  # noqa: E402
import dryrun1_master  # noqa: E402
import dryrun2_master  # noqa: E402

BANK = 50.0


def wilson(w, n, z=1.96):
    if n <= 0:
        return (0.0, 0.0)
    p = w / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - r) / d) * 100, min(1.0, (c + r) / d) * 100)


def streaks(pnls):
    bw = bl = cw = cl = 0
    for p in pnls:
        if p > 0:
            cw, cl = cw + 1, 0
        else:
            cl, cw = cl + 1, 0
        bw, bl = max(bw, cw), max(bl, cl)
    return bw, bl, (cw if pnls else 0), (cl if pnls else 0)


def metrics(b, set_start):
    """Pelny zestaw metryk wariantu z jego zamknietych transakcji + stanu księgi."""
    cl = b.closed
    n = len(cl)
    pnls = [t["pnl"] for t in cl]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    cost = sum(t["cost"] for t in cl)
    pnl = sum(pnls)
    eq = b.equity()
    gp, gl = sum(wins), -sum(losses)
    avg_w = st.fmean(wins) if wins else 0.0
    avg_l = st.fmean(losses) if losses else 0.0
    payoff = (avg_w / abs(avg_l)) if avg_l else float("inf")
    pf = (gp / gl) if gl > 0 else float("inf")
    be_wr = (abs(avg_l) / (avg_w + abs(avg_l)) * 100) if (avg_w + abs(avg_l)) else 0.0
    wr = (len(wins) / n * 100) if n else 0.0
    lo, hi = wilson(len(wins), n)
    sd = st.pstdev(pnls) if n > 1 else 0.0
    mean = pnl / n if n else 0.0
    tstat = (mean / (sd / math.sqrt(n))) if (n > 1 and sd > 0) else 0.0
    down = [p for p in pnls if p < 0]
    dsd = st.pstdev(down) if len(down) > 1 else 0.0
    sortino = (mean / dsd) if dsd else float("inf") if n else 0.0
    # krzywa kapitalu / drawdown
    run = peak = BANK
    dd = 0.0
    dd_abs = 0.0
    curve = []
    for p in pnls:
        run += p
        peak = max(peak, run)
        dd = max(dd, (peak - run) / peak if peak > 0 else 0.0)
        dd_abs = max(dd_abs, peak - run)
        curve.append(run)
    bw, bl, cw, cl_ = streaks(pnls)
    kelly = (wr / 100 - (1 - wr / 100) / payoff) * 100 if payoff and payoff != float("inf") else 0.0
    hours = max(1e-6, (time.time() - set_start) / 3600.0)
    stake_now, lvl = b.stake_now()
    ex = {}
    for t in cl:
        ex[t["exit"]] = ex.get(t["exit"], 0) + 1
    tf = {}
    for t in cl:
        a = tf.setdefault(t["tf"], {"n": 0, "w": 0, "pnl": 0.0})
        a["n"] += 1
        a["w"] += 1 if t["pnl"] > 0 else 0
        a["pnl"] += t["pnl"]
    side = {}
    for t in cl:
        a = side.setdefault(t["side"], {"n": 0, "w": 0, "pnl": 0.0})
        a["n"] += 1
        a["w"] += 1 if t["pnl"] > 0 else 0
        a["pnl"] += t["pnl"]
    ast = {}
    for t in cl:
        a = ast.setdefault(t["asset"], {"n": 0, "w": 0, "pnl": 0.0})
        a["n"] += 1
        a["w"] += 1 if t["pnl"] > 0 else 0
        a["pnl"] += t["pnl"]
    return dict(
        id=b.id, name=b.name, n=n, wins=len(wins), losses=len(losses), wr=wr, wr_lo=lo, wr_hi=hi,
        pnl=pnl, cost=cost, roi=(pnl / cost * 100 if cost else 0.0), ret=(pnl / BANK * 100),
        exp=mean, exp_pct=(mean / (cost / n) * 100 if n and cost else 0.0),
        avg_w=avg_w, avg_l=avg_l, payoff=payoff, pf=pf, be_wr=be_wr, wr_edge=wr - be_wr,
        sd=sd, tstat=tstat, sortino=sortino, kelly=kelly,
        dd=dd * 100, dd_abs=dd_abs, rec=(pnl / dd_abs if dd_abs else float("inf")),
        bw=bw, bl=bl, cw=cw, cl=cl_,
        eq=eq, stake_now=stake_now, lvl=lvl, open=len(b.positions),
        open_cost=sum(p["cost"] for p in b.positions.values()),
        avg_px=(st.fmean([t["entry"] for t in cl]) if n else 0.0),
        med_px=(st.median([t["entry"] for t in cl]) if n else 0.0),
        px_min=(min(t["entry"] for t in cl) if n else 0.0),
        px_max=(max(t["entry"] for t in cl) if n else 0.0),
        avg_p=(st.fmean([t["p"] for t in cl]) if n else 0.0),
        avg_edge=(st.fmean([t["edge"] for t in cl]) if n else 0.0),
        edge_real=(pnl / cost * 100 if cost else 0.0),
        hold=(st.fmean([t["hold"] for t in cl]) if n else 0.0),
        med_hold=(st.median([t["hold"] for t in cl]) if n else 0.0),
        rem_in=(st.fmean([t["rem_at_open"] for t in cl]) if n else 0.0),
        spr=(st.fmean([t.get("spr") or 0 for t in cl]) if n else 0.0),
        rate=(n / hours), tf=tf, side=side, ast=ast, ex=ex,
        model=b.v.get("model", "v1"), v_min_px=b.v.get("min_px"), v_max_px=b.v.get("max_px"),
        v_edge=b.v.get("edge"), tp=b.v.get("tp"), sl=b.v.get("sl"),
        timing=json.dumps(b.v.get("timing") or {}, separators=(",", ":")),
        lad="%s %+.0f%%/%+.0f%%%s" % (b.lad["kind"], b.lad["step_stake"] * 100,
                                      b.lad["step_bank"] * 100, "" if b.lad["down"] else " UP")
        if b.lad["kind"] == "ladder" else b.lad["kind"],
        start=set_start,
    )


def f(v, fmt="{:.2f}", dash="—"):
    if v is None:
        return dash
    if isinstance(v, float) and (math.isinf(v) or math.isnan(v)):
        return "∞" if math.isinf(v) else dash
    try:
        return fmt.format(v)
    except Exception:
        return str(v)


def cls(v):
    return "pos" if isinstance(v, (int, float)) and v > 0 else ("neg" if isinstance(v, (int, float)) and v < 0 else "")


COLS = [
    ("#", lambda m: m["id"], "{:d}"),
    ("wariant", lambda m: m["name"], None),
    ("model", lambda m: m["model"], None),
    ("px pasmo", lambda m: "%.2f–%.2f" % (m["v_min_px"], m["v_max_px"]), None),
    ("edge", lambda m: m["v_edge"], "{:.3f}"),
    ("TP", lambda m: ("HOLD" if m["tp"] is None else "%.2f" % m["tp"]), None),
    ("SL", lambda m: ("—" if not m["sl"] else "%.0f%%" % (m["sl"] * 100)), None),
    ("drabinka", lambda m: m["lad"], None),
    ("n", lambda m: m["n"], "{:d}"),
    ("W/L", lambda m: "%d/%d" % (m["wins"], m["losses"]), None),
    ("WR %", lambda m: m["wr"], "{:.1f}"),
    ("95% CI", lambda m: "%.0f–%.0f" % (m["wr_lo"], m["wr_hi"]) if m["n"] else "—", None),
    ("BE WR %", lambda m: m["be_wr"], "{:.1f}"),
    ("WR−BE", lambda m: m["wr_edge"], "{:+.1f}"),
    ("śr. cena", lambda m: m["avg_px"], "{:.3f}"),
    ("med. cena", lambda m: m["med_px"], "{:.3f}"),
    ("śr. p", lambda m: m["avg_p"], "{:.3f}"),
    ("śr. edge", lambda m: m["avg_edge"], "{:+.3f}"),
    ("PnL $", lambda m: m["pnl"], "{:+.2f}"),
    ("ROI %", lambda m: m["roi"], "{:+.1f}"),
    ("zwrot %", lambda m: m["ret"], "{:+.1f}"),
    ("exp $/trade", lambda m: m["exp"], "{:+.3f}"),
    ("PF", lambda m: m["pf"], "{:.2f}"),
    ("payoff", lambda m: m["payoff"], "{:.2f}"),
    ("Kelly %", lambda m: m["kelly"], "{:+.1f}"),
    ("t-stat", lambda m: m["tstat"], "{:+.1f}"),
    ("Sortino", lambda m: m["sortino"], "{:.2f}"),
    ("DD %", lambda m: m["dd"], "{:.1f}"),
    ("DD $", lambda m: -m["dd_abs"], "{:+.2f}"),
    ("recovery", lambda m: m["rec"], "{:.2f}"),
    ("seria W", lambda m: m["bw"], "{:d}"),
    ("seria L", lambda m: m["bl"], "{:d}"),
    ("śr. czas", lambda m: m["hold"], "{:.0f}s"),
    ("otw", lambda m: m["open"], "{:d}"),
    ("stawka $", lambda m: m["stake_now"], "{:.2f}"),
    ("kapitał $", lambda m: m["eq"], "{:.2f}"),
]


def table_main(rows, caption):
    out = ['<div class="wrap"><table class="main" id="t%d">' % (abs(hash(caption)) % 100000),
           '<caption>%s</caption><thead><tr>' % caption]
    for i, (h, _g, _f) in enumerate(COLS):
        out.append('<th onclick="srt(this,%d,0)">%s</th>' % (i, h))
    out.append("</tr></thead><tbody>")
    for m in rows:
        tds = []
        for i, (h, g, fmt) in enumerate(COLS):
            try:
                val = g(m)
            except Exception:
                val = None
            txt = f(val, fmt) if fmt else (val if val is not None else "—")
            num = val if isinstance(val, (int, float)) else ""
            c = cls(val) if h in ("PnL $", "ROI %", "zwrot %", "exp $/trade", "WR−BE", "Kelly %", "t-stat", "DD $", "śr. edge") else ""
            if h == "wariant":
                tds.append('<td class="nm" data-sort="%s">%s</td>' % (val, val))
            else:
                tds.append('<td class="%s" data-sort="%s">%s</td>' % (c, num, txt))
        out.append("<tr>" + "".join(tds) + "</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)


def table_simple(headers, rows, caption, num_from=1):
    pass  # id tabeli z hasha
    out = ['<div class="wrap small"><table class="main" id="s%d">' % (abs(hash(caption)) % 1000000),
           '<caption>%s</caption><thead><tr>' % caption]
    for i, h in enumerate(headers):
        out.append('<th onclick="srt(this,%d,0)">%s</th>' % (i, h) if i >= num_from else '<th>%s</th>' % h)
    out.append("</tr></thead><tbody>")
    for r in rows:
        tds = []
        for i, v in enumerate(r):
            if i < num_from:
                tds.append('<td class="nm" data-sort="%s">%s</td>' % (v, v))
            else:
                num = v if isinstance(v, (int, float)) else ""
                c = cls(v) if isinstance(v, (int, float)) else ""
                tds.append('<td class="%s" data-sort="%s">%s</td>' % (c, num, v))
        out.append("<tr>" + "".join(tds) + "</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)


def agg(rows, keyf, label):
    """Agregacja po dowolnym kluczu: n, W, WR, PnL, sr. cena, sr. edge, DD sumaryczny."""
    g = {}
    for m in rows:
        for k, a in (m["tf"].items() if keyf == "tf" else
                     m["side"].items() if keyf == "side" else
                     m["ast"].items() if keyf == "asset" else
                     m["ex"].items() if keyf == "exit" else []):
            d = g.setdefault(k, {"n": 0, "w": 0, "pnl": 0.0})
            if keyf == "exit":
                d["n"] += a
            else:
                d["n"] += a["n"]
                d["w"] += a["w"]
                d["pnl"] += a["pnl"]
    out = []
    for k, d in sorted(g.items(), key=lambda kv: -kv[1]["pnl"]):
        wr = (d["w"] / d["n"] * 100) if d["n"] else 0.0
        out.append((k if keyf != "exit" else k, d["n"], d["w"], round(wr, 1),
                    round(d["pnl"], 2), round(d["pnl"] / d["n"], 3) if d["n"] else 0.0))
    return out, label


def grouped(rows, keyf, lbl, caption):
    """Grupowanie WARIANTÓW po cesze (max_px, min_px, timing, tp, edge, model, drabinka).
    Sumuje transakcje po wszystkich wariantach danej grupy."""
    g = {}
    for m in rows:
        k = keyf(m)
        d = g.setdefault(k, {"n": 0, "w": 0, "pnl": 0.0, "cost": 0.0, "names": 0})
        d["n"] += m["n"]
        d["w"] += m["wins"]
        d["pnl"] += m["pnl"]
        d["cost"] += m["cost"]
        d["names"] += 1
    out = []
    for k, d in sorted(g.items(), key=lambda kv: -kv[1]["pnl"]):
        wr = (d["w"] / d["n"] * 100) if d["n"] else 0.0
        out.append((k, d["names"], d["n"], d["w"], round(wr, 1), round(d["pnl"], 2),
                    round(d["pnl"] / d["cost"] * 100, 1) if d["cost"] else 0.0,
                    round(d["pnl"] / d["n"], 3) if d["n"] else 0.0))
    return table_simple(
        [lbl, "wariantów", "n", "W", "WR %", "PnL $", "ROI %", "exp $/trade"], out, caption)

CSS = """
:root{--bg:#0b0f16;--bg2:#111823;--card:#151d2b;--line:#22304a;--txt:#e6edf7;--dim:#8ba0bd;
--pos:#3ddc97;--neg:#ff6b81;--acc:#5aa9ff;--warn:#ffcc66}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 600px at 20% -10%,#16233a 0%,#0b0f16 55%) fixed;
color:var(--txt);font:14px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif}
header{padding:26px 20px 8px;max-width:1900px;margin:0 auto}
h1{margin:0;font-size:26px;letter-spacing:.2px}
h1 span{color:var(--acc)}
.sub{color:var(--dim);margin-top:6px;font-size:13px}
h2{max-width:1900px;margin:26px auto 10px;padding:0 20px;font-size:19px}
h2 small{color:var(--dim);font-weight:400;font-size:13px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;max-width:1900px;margin:18px auto;padding:0 20px}
.card{background:linear-gradient(180deg,#172132,#131a27);border:1px solid var(--line);border-radius:14px;padding:12px 14px}
.card .k{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.08em}
.card .v{font-size:22px;font-weight:650;margin-top:4px;font-variant-numeric:tabular-nums}
.card .x{color:var(--dim);font-size:11px;margin-top:2px}
.wrap{max-width:1900px;margin:0 auto 18px;padding:0 20px;overflow:auto;border-radius:14px}
table{border-collapse:separate;border-spacing:0;width:100%;background:var(--bg2);border:1px solid var(--line);
border-radius:14px;overflow:hidden;font-variant-numeric:tabular-nums}
caption{caption-side:top;text-align:left;padding:10px 12px;color:var(--dim);font-size:12px;background:#0e1521;
border-bottom:1px solid var(--line);letter-spacing:.04em;text-transform:uppercase}
th{position:sticky;top:0;z-index:2;background:#101a29;color:#a9c0dd;font-size:11px;font-weight:600;
text-transform:uppercase;letter-spacing:.05em;padding:8px 9px;text-align:right;white-space:nowrap;
border-bottom:1px solid var(--line);cursor:pointer;user-select:none}
th:hover{color:#fff;background:#152238}
td{padding:7px 9px;text-align:right;white-space:nowrap;border-bottom:1px solid #1a2534;font-size:12.5px}
td.nm{text-align:left;font-weight:600;color:#d7e6fb}
tbody tr:nth-child(even){background:#131b28}
tbody tr:hover{background:#1a2740}
.pos{color:var(--pos);font-weight:600}.neg{color:var(--neg);font-weight:600}
.small td,.small th{font-size:12px;padding:6px 9px}
.note{max-width:1900px;margin:0 auto 40px;padding:0 20px;color:var(--dim);font-size:12.5px}
.note b{color:#cfe0f5}
.badge{display:inline-block;padding:1px 7px;border-radius:999px;font-size:11px;border:1px solid var(--line);color:var(--dim)}
"""

JS = """
function num(t){var v=t.getAttribute('data-sort');if(v===''||v===null)return NaN;var f=parseFloat(v);return isNaN(f)?NaN:f;}
function srt(th,col,isNum){
 var tb=th.closest('table').tBodies[0]; var rows=[].slice.call(tb.rows);
 var dir=th.getAttribute('data-dir')==='asc'?-1:1;
 th.closest('tr').querySelectorAll('th').forEach(function(h){h.removeAttribute('data-dir')});
 th.setAttribute('data-dir',dir===1?'desc':'asc');
 rows.sort(function(a,b){
  var x=a.cells[col].getAttribute('data-sort'), y=b.cells[col].getAttribute('data-sort');
  var nx=parseFloat(x), ny=parseFloat(y);
  if(!isNaN(nx)&&!isNaN(ny))return (nx-ny)*dir;
  return (x||'').localeCompare(y||'')*dir;
 });
 rows.forEach(function(r){tb.appendChild(r)});
}
"""


def load_books(set_name, variants):
    p = os.path.join(ROOT, "state", set_name + ".json")
    if not os.path.exists(p):
        return [], time.time()
    with open(p) as fh:
        d = json.load(fh)
    books = []
    for v in variants:
        b = E.VBook(v, BANK)
        bd = (d.get("books") or {}).get(str(v["id"]))
        if bd:
            b.load(bd)
        books.append(b)
    return books, d.get("start", time.time())


def main():
    sets = [("Przebieg 1 — warianty zamówione", "dryrun1", dryrun1_master.VARIANTS),
            ("Przebieg 2 — poprawa przewagi, jakości i skuteczności BIN", "dryrun2", dryrun2_master.VARIANTS)]
    data = []
    for title, name, variants in sets:
        books, start = load_books(name, variants)
        if not books:
            continue
        ms = [metrics(b, start) for b in books]
        ms.sort(key=lambda m: -m["pnl"])
        data.append((title, name, ms, start))
    if not data:
        print("Brak stanu (state/dryrun*.json) — najpierw uruchom dry-runy.")
        return

    H = ["<!doctype html><html lang=pl><head><meta charset=utf-8>",
         "<meta name=viewport content='width=device-width,initial-scale=1'>",
         "<title>Polymarket 5m/15m — dry-runy</title><style>" + CSS + "</style>",
         "<script>" + JS + "</script></head><body>",
         "<header><h1>Polymarket 5m/15m — <span>dry-runy wariantowe</span></h1>",
         "<div class=sub>Bankroll startowy <b>$%.2f</b> na wariant &nbsp;•&nbsp; stawka startowa <b>$1.25</b> "
         "(2.5%% kapitału) &nbsp;•&nbsp; drabinka: 50→1.25, 75→1.875, 112.5→2.8125 (poziom = +50%% kapitału) "
         "&nbsp;•&nbsp; paper trading na żywych książkach (CLOB) i cenach Binance, opłata 0.07·p·(1−p) "
         "&nbsp;•&nbsp; wygenerowano %s UTC</div></header>"
         % (BANK, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"))]

    # --- karty KPI dla obu przebiegów
    H.append('<div class=cards>')
    for title, name, ms, start in data:
        n = sum(m["n"] for m in ms)
        pnl = sum(m["pnl"] for m in ms)
        best = max(ms, key=lambda m: m["pnl"])
        worst = min(ms, key=lambda m: m["pnl"])
        wr = (sum(m["wins"] for m in ms) / n * 100) if n else 0.0
        hrs = (time.time() - start) / 3600.0
        H.append('<div class=card><div class=k>%s</div><div class="v %s">%+.2f $</div>'
                 '<div class=x>%d wariantów • %d transakcji • %.1f%% WR • %.1f h</div></div>'
                 % (title.split("—")[0].strip() + " PnL", cls(pnl), pnl, len(ms), n, wr, hrs))
        H.append('<div class=card><div class=k>%s — najlepszy</div><div class="v %s">%+.2f $</div>'
                 '<div class=x>%s (n=%d, %.1f%% WR)</div></div>'
                 % (title.split("—")[0].strip(), cls(best["pnl"]), best["pnl"], best["name"], best["n"], best["wr"]))
        H.append('<div class=card><div class=k>%s — najgorszy</div><div class="v %s">%+.2f $</div>'
                 '<div class=x>%s (n=%d, %.1f%% WR)</div></div>'
                 % (title.split("—")[0].strip(), cls(worst["pnl"]), worst["pnl"], worst["name"], worst["n"], worst["wr"]))
    H.append("</div>")

    # --- sekcje per przebieg
    for title, name, ms, start in data:
        n = sum(m["n"] for m in ms)
        pnl = sum(m["pnl"] for m in ms)
        H.append("<h2>%s <small>— %d wariantów, %d transakcji, suma %+.2f $, start %s UTC</small></h2>"
                 % (title, len(ms), n, pnl, datetime.fromtimestamp(start, timezone.utc).strftime("%H:%M")))
        H.append("<div class=note>Kliknij nagłówek kolumny, aby sortować. „WR−BE” &gt; 0 = wariant zarabia "
                 "mimo wszystko; „95% CI” = przedział ufności win-rate (Wilson).</div>")
        H.append(table_main(ms, "Wszystkie warianty — pełne statystyki"))
        H.append("<h2>Grupowanie ustawień <small>— transakcje zsumowane po wszystkich wariantach grupy</small></h2>")
        H.append(grouped(ms, lambda m: m["lad"], "drabinka stawki", "Wpływ drabinki stawki"))
        H.append(grouped(ms, lambda m: "%.2f–%.2f" % (m["v_min_px"], m["v_max_px"]), "pasmo szansy",
                         "Wpływ pasma ceny wejścia (min–max szansa)"))
        H.append(grouped(ms, lambda m: m["timing"], "okno wejścia", "Wpływ okna wejścia (elapsed sekundy)"))
        H.append(grouped(ms, lambda m: "HOLD" if m["tp"] is None else "TP %.2f" % m["tp"], "wyjście",
                         "Wpływ take-profit"))
        H.append(grouped(ms, lambda m: "edge %.3f" % m["v_edge"], "próg edge", "Wpływ progu przewagi"))
        H.append(grouped(ms, lambda m: "model " + m["model"], "model", "Wpływ modelu (v1/v2/v3)"))
        for keyf, lbl, cap in (("tf", "interwał", "Rozbicie 5m vs 15m"),
                               ("side", "strona", "Rozbicie Up vs Down"),
                               ("asset", "aktywo", "Rozbicie po aktywach"),
                               ("exit", "typ wyjścia", "Sposób zamknięcia")):
            rows, _ = agg(ms, keyf, lbl)
            H.append(table_simple([lbl, "n", "W", "WR %", "PnL $", "exp $/trade"],
                                  [[r[0], r[1], r[2], r[3], r[4], r[5]] for r in rows], cap))

    H.append("<div class=note><b>Metodologia.</b> Wejście po ask z CLOB, fill po kolejnych poziomach książki "
             "(realny poślizg), opłata takera 0.07·p·(1−p) na udział. Wyjście: TP po bid, stop-loss, albo "
             "rozliczenie rynku wg Gammy (outcomePrices 0/1); fallback TWAP60 z klines 1s. Drabinka stawki "
             "przelicza się co każdy próg wzrostu kapitału. <b>Uwaga:</b> to wyniki papierowe; przy n&lt;30 "
             "na wariant to jeszcze szum — zostaw przebiegi na dłużej i porównuj po kilkuset transakcjach.</div>")
    H.append("</body></html>")

    out = os.path.join(ROOT, "RAPORT.html")
    with open(out, "w") as fh:
        fh.write("\n".join(H))

    # --- CSV zbiorczy
    csvp = os.path.join(ROOT, "reports", "RAPORT.csv")
    keys = ["set", "id", "name", "model", "v_min_px", "v_max_px", "v_edge", "tp", "sl", "lad", "timing",
            "n", "wins", "losses", "wr", "wr_lo", "wr_hi", "be_wr", "wr_edge", "pnl", "roi", "ret",
            "exp", "avg_w", "avg_l", "payoff", "pf", "sd", "tstat", "sortino", "kelly", "dd", "dd_abs",
            "rec", "bw", "bl", "avg_px", "med_px", "px_min", "px_max", "avg_p", "avg_edge", "hold",
            "med_hold", "rem_in", "spr", "rate", "open", "open_cost", "stake_now", "lvl", "eq"]
    with open(csvp, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(keys)
        for title, name, ms, start in data:
            for m in ms:
                row = []
                for k in keys:
                    if k == "set":
                        row.append(name)
                    else:
                        v = m.get(k)
                        row.append(round(v, 6) if isinstance(v, float) and not math.isinf(v) else v)
                w.writerow(row)
    print("zapisano:", out)
    print("zapisano:", csvp)
    for title, name, ms, start in data:
        n = sum(m["n"] for m in ms)
        pnl = sum(m["pnl"] for m in ms)
        print("  %-8s wariantów=%d transakcji=%d suma=%+.2f$" % (name, len(ms), n, pnl))


if __name__ == "__main__":
    main()
