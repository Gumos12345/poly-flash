#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Polymarket bot v3 - FADE LONGSHOT + HOLD DO ROZSTRZYGNIECIA (stawka 1 USD)
============================================================================
Strategia:
  * Wejscie: kup NO, gdy YES w przedziale [LONG_LO, LONG_HI] (0.15-0.50).
  * Wyjscie: trzymaj do rozstrzygniecia (zero oplaty sprzedazy, zero spreadu na wyjsciu).
  * Filtr czasu: wejscie pre-game tylko do PRE_GAME_WINDOW_H godzin przed startem
    (domyslnie 2 h) albo live do LIVE_WINDOW_H godzin po starcie.
  * Filtr dnia: SAME_DAY_ONLY = True -> wchodzimy tylko wtedy, gdy mecz konczy sie
    przed lokalna polnoca, czyli rozstrzygniecie nastepuje tego samego dnia.

Tryby:
  python3 bot_v2_dry_v3.py --scan       # skan rynkow + EV (bez handlu)
  python3 bot_v2_dry_v3.py --explain    # dlaczego bot odrzuca rynki (zliczone powody)
  python3 bot_v2_dry_v3.py --pre-hours 24 --scan   # test: poszerz okno pre-game (tylko na ten przebieg)
  python3 bot_v2_dry_v3.py --once       # jeden przebieg: otworz pozycje, pokaz PnL
  python3 bot_v2_dry_v3.py --report     # otwarte pozycje + PnL biezacy (mark-to-market)
  python3 bot_v2_dry_v3.py --dry        # petla na zywo, bez prawdziwych zlecen
  python3 bot_v2_dry_v3.py --live       # PRAWDZIWE zlecenia (wymaga kluczy w env)
  python3 bot_v2_dry_v3.py --backtest   # backtest na bt_cache2.json

Env dla --live:
  POLY_PRIVATE_KEY                            (wymagany)
  POLYMARKET_DEPOSIT_WALLET lub POLY_FUNDER   (adres portfela z USDC)
  POLY_SIGNATURE_TYPE                         (0=EOA, 1=Polymarket proxy [domyslny], 2=gnosis safe)

Zmiany v3 wzgledem v2:
  * SAME_DAY_ONLY: gwarancja rozstrzygniecia tego samego dnia (koniec meczu < lokalna polnoc).
  * _settle_positions: wygrana tylko przy outcome >= 0.99, porazka <= 0.01, 0.5/0.5 -> void/refund
    (wczesniej 0.5 liczone jako wygrana).
  * Mark-to-market: petla pokazuje tez PnL niezrealizowany (wczesniej PnL=0 do rozstrzygniecia).
  * Ctrl+C podczas sleep konczy prace czysto (wczesniej traceback).
  * Backtest stosuje te sama polityke czasu co live (okno 2 h pre + same-day).
  * Rynek po endDate jest pomijany (nie otwieramy trupow).
  * KLUCZOWA POPRAWKA: rynki meczowe Polymarket maja czesto 2 NAZWANE wyniki (nazwy druzyn,
    Over/Under) i NIE MAJA tokenu "No". v2 pomijal je wszystkie (warunek `"No" in outs`),
    przez co bot nie mogl kupic ANI JEDNEGO rynku sportowego. v3 obsluguje pair_mode:
    longshot = strona z nizsza cena, kupujemy druga strone (ekwiwalent kupna NO).
  * _ts() przyjmuje tez timestampy liczbowe (wczesniej gs=None w backtescie -> 0 tradow).
  * --fetch-history: buduje bt_cache2.json (w repo nie bylo ani cache, ani fetch_history.py,
    wiec --backtest nie mial na czym pracowac).
  * --once i --report, --explain, --pre-hours, --max-hours.
  * KOREKTA CEN: CLOB /price ma ODWROCONA semantyke parametru side — /price?side=sell
    zwraca best ASK, a /price?side=buy best BID (sprawdzone na zywym API). v2 kupowal
    po BID (za tanio) i wycenial pozycje po ASK (za drogo) -> dry PnL byl zawyzony.
    v3 ma get_ask()/get_bid() i wycenia po mid, z fallbackiem na cene Gamma przy pustym booku.
  * Log nie jest buforowany przy przekierowaniu do pliku (sys.stdout line_buffering).
"""



import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
import re
import statistics
import threading
import sys
import time
from datetime import datetime, timedelta, timezone

try:                      # log ma sie pojawiac od razu takze przy przekierowaniu do pliku
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

try:
    import requests
except ImportError:  # fallback dla czystych instalacji Pythona (Termux)
    import urllib.parse
    import urllib.request

    class _Response:
        def __init__(self, body): self._body = body
        def json(self): return json.loads(self._body)

    class _Requests:
        @staticmethod
        def get(url, params=None, timeout=20):
            if params:
                url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={"User-Agent": "bot-v2/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return _Response(resp.read())
    requests = _Requests()

# ===========================================================================
# KONFIG
# ===========================================================================
CLOB_HOST = "https://clob.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"
DATA_API_HOST = "https://data-api.polymarket.com"

# --- koszty ---
FEE_RATE_SPORTS = 0.05      # taker fee dla sportu. Maks. przy p=0.50.
FEE_RATE_DEFAULT = 0.04     # polityka/finanse/tech/inne

# FeeRate wg kategorii (docs.polymarket.com/trading/fees):
#   peak fee / 100 szt @ p=0.50: crypto=$1.75 -> 0.07 | sports=$1.25 -> 0.05
#   finance/politics/tech=$1.00 -> 0.04 | econ/culture/weather/other=$1.25 -> 0.05
#   geopolitics/world = FEE-FREE -> 0.00
FEE_BY_TAG = {
    "crypto": 0.07,
    "sports": 0.05, "nba": 0.05, "nfl": 0.05, "soccer": 0.05, "mlb": 0.05, "nhl": 0.05,
    "politics": 0.04, "tech": 0.04, "business": 0.04, "finance": 0.04, "mentions": 0.04,
    "economy": 0.05, "economics": 0.05, "pop-culture": 0.05, "culture": 0.05,
    "science": 0.05, "weather": 0.05, "other": 0.05,
    "world": 0.00, "geopolitics": 0.00,
}

# Tagi sportï¿½w (Gamma tag_slug). Nieistniejï¿½cy slug = pusta lista, bot go pomija.
ALL_SPORTS_TAGS = [
    "sports", "nba", "nfl", "mlb", "nhl", "wnba", "cbb", "cfb",
    "soccer", "epl", "la-liga", "serie-a", "bundesliga", "ligue-1", "ucl", "mls",
    "tennis", "ufc", "mma", "boxing", "cricket", "golf", "f1", "rugby",
    "esports", "cs2", "lol", "dota-2", "valorant",
]


def expand_tags(tag):
    """'all' / 'all-sports' -> peï¿½na lista; 'nba,mlb' -> ['nba','mlb']; 'sports' -> ['sports']."""
    if isinstance(tag, (list, tuple, set)):
        tag = ",".join(str(x) for x in tag)
    t = (tag or "sports").strip().lower()
    if t in ("all", "all-sports", "allsports"):
        return list(ALL_SPORTS_TAGS)
    return [x.strip() for x in t.split(",") if x.strip()]


def fee_for_tag(tag):
    """Taker feeRate dla kategorii (tag_slug). Wiele tagï¿½w sportowych -> stawka sportowa."""
    tags = expand_tags(tag)
    if len(tags) > 1:
        return FEE_RATE_SPORTS
    return FEE_BY_TAG.get((tag or "").lower(), FEE_RATE_DEFAULT)


ASSUMED_SPREAD = 0.02       # zakï¿½adany spread (bid..ask) na tokenie, w cenie
COST_MARGIN = 0.005         # dodatkowy margines bezpieczeï¿½stwa (0.5 pp)

# --- strategia (FADE LONGSHOT) ---
LONG_LO = 0.15              # dolna granica YES, w ktï¿½rej wchodzimy
LONG_HI = 0.50              # gï¿½rna granica YES (FLB najsilniejszy w 0.15-0.50)
HAIRCUT = 0.50              # q_est = p * HAIRCUT (longshoty przecenione ~2x wg danych)
MIN_EDGE = 0.02             # minimalna EV na $1 stawki, ï¿½eby wejï¿½ï¿½ (2%)
MAX_HOLD_DAYS = 90          # nie wchodï¿½, jeï¿½eli rynek rozstrzyga siï¿½ pï¿½ï¿½niej niï¿½ za tyle dni
LIVE_WINDOW_H = 6           # mecz = "live", gdy startowaï¿½ w ostatnich N godzinach
PRE_GAME_WINDOW_H = 2       # pre-game: tylko mecze zaczynajï¿½ce siï¿½ w ciï¿½gu N godzin

# --- rozstrzygniecie tego samego dnia ---
SAME_DAY_ONLY = True        # True: wchodz tylko, gdy pozycja rozstrzygnie sie szybko (patrz nizej)
SAME_CALENDAR_DAY = False   # True: dodatkowo wymagaj rozstrzygniecia przed lokalna polnoca
MAX_HOURS_TO_RESOLVE = 10.0 # pozycja musi sie rozstrzygnac w ciagu tylu godzin od wejscia
SAME_DAY_GRACE_H = 2.5      # bufor na rozliczenie po koncu meczu (godziny)
# typowy czas trwania meczu (godziny) - do oszacowania momentu rozstrzygniecia
SPORT_DURATION_H = {
    "soccer": 2.0, "epl": 2.0, "la-liga": 2.0, "serie-a": 2.0, "bundesliga": 2.0,
    "ligue-1": 2.0, "ucl": 2.0, "mls": 2.0,
    "cfb": 4.0, "mlb": 3.5, "nfl": 3.5, "nba": 2.5, "f1": 2.5,
    "ufc": 2.0, "golf": 6.0, "tennis": 2.5,
}
DEFAULT_DURATION_H = 3.5    # gdy nie znamy dyscypliny

# --- rozmiar / pętla ---
# Stawka 1 USD (żądanie użytkownika). Zlecenia market FAK przechodzą po 1 USD
# (potwierdzone w live); min_order_size z /book dotyczy zleceń limit, nie market.
SIZE_USD = 1.0
MAX_POSITIONS = 13
LOOP_SLEEP = 60             # sekundy miï¿½dzy skanami
ACTIVE_MARKET_LIMIT_PER_TAG = 2000   # cap na tag (byï¿½o 10000 -> setki ï¿½ï¿½daï¿½ na skan)
ACTIVE_EVENT_OFFSET_LIMIT = 2000     # cap offsetu eventï¿½w
GAMMA_RETRY = 3                      # prï¿½by na ï¿½ï¿½danie Gamma
GAMMA_BACKOFF = 5.0                  # sekundy miï¿½dzy prï¿½bami
MARKETS_CACHE_TTL = 300.0            # sekundy waï¿½noï¿½ci cache rynkï¿½w pï¿½tli
FETCH_HISTORY_PAGES = 15   # ile stron eventow (x100) na tag przy budowie bt_cache
FETCH_HISTORY_FIDELITY = 5  # rozdzielczosc historii cen (minuty); 1 = 1 min (duzo danych)
BT_MIN_VOL = 5000.0          # backtest: pomijaj rynki z wolumenem < 5k (nieplynne ligi)
BT_BY_TAG = False            # True -> rozbicie wyniku per liga (ustawiane przez --by-tag)
BT_USE_POLICY = True         # backtest stosuje te sama polityke grup/lig co live

TRADING_MARKET_GROUP = "spread"      # zachowane dla kompatybilnoï¿½ci starszych raportï¿½w
ONE_POSITION_PER_EVENT = False       # wiele rï¿½ï¿½nych rynkï¿½w z jednego eventu
MIN_ACTIVE_VOL = 100.0               # min wolumen rynku w pï¿½tli handlowej

# ï¿½cisï¿½a lista tagï¿½w, ktï¿½re bot skanuje. Soccer i jego ligi majï¿½ wspï¿½lnï¿½ politykï¿½.
TRADE_TAGS = ["soccer", "epl", "la-liga", "serie-a", "bundesliga", "ligue-1", "ucl", "mls",
              "cfb", "mlb", "nfl", "f1", "ufc", "golf", "nba"]
SOCCER_TAGS = {"soccer", "epl", "la-liga", "serie-a", "bundesliga", "ligue-1", "ucl", "mls"}
PRE_MARKET_POLICY = {
    "soccer": {"spread", "other"}, "epl": {"spread", "other"},
    "la-liga": {"spread", "other"}, "serie-a": {"spread", "other"},
    "bundesliga": {"spread", "other"}, "ligue-1": {"spread", "other"},
    "ucl": {"spread", "other"}, "mls": {"spread", "other"},
    "cfb": {"spread", "moneyline"}, "mlb": {"totals"},
    "nfl": {"spread", "other"}, "f1": {"other", "moneyline"},
    "ufc": {"other"}, "golf": {"moneyline"}, "nba": {"spread"},
}
LIVE_SOCCER_MARKETS = {"spread", "other"}
BLOCKED_SPORT_TAGS = {
    "wnba", "nhl", "tennis", "esports", "table-tennis",
    "cs2", "valorant", "dota-2", "league-of-legends", "lol",
    "boxing", "rugby", "cricket", "cbb"
}

# --- pliki ---
VALIDATION_FILE = "strategy_validation.json"
BT_CACHE = "bt_cache2.json"
POSITIONS_FILE_DRY = "positions_v2_dry.json"
TRADES_FILE_DRY = "trades_v2_dry.json"
POSITIONS_FILE_LIVE = "positions_v2.json"
TRADES_FILE_LIVE = "trades_v2.json"


# ===========================================================================
# MODEL KOSZTï¿½W I EV
# ===========================================================================
def taker_fee(shares: float, price: float, fee_rate: float) -> float:
    """Opï¿½ata taker Polymarket: shares * rate * p * (1-p). Zwraca USD."""
    if price <= 0 or price >= 1:
        return 0.0
    return shares * fee_rate * price * (1.0 - price)


def estimate_true_prob(p: float) -> float:
    """
    Estymata PRAWDZIWEGO prawdopodobieï¿½stwa, ï¿½e YES wygra, przy cenie p.
    Longshoty (p<=0.5) sï¿½ przecenione -> mnoï¿½ymy przez HAIRCUT.
    Faworyci (p>0.5) traktowani jako ~dobrze wycenieni (lekkie niedoszacowanie).
    """
    if p <= 0.5:
        return max(0.0, p * HAIRCUT)
    return min(1.0, 0.5 + (p - 0.5) * 1.05)


def ev_buy_no(p: float, fee_rate: float, spread: float) -> tuple:
    """
    Wartoï¿½ï¿½ oczekiwana kupna NO, gdy YES kosztuje p (per 1 sztuka).
    Zwraca (ev_usd, ev_frac), gdzie ev_frac = ev / koszt (zwrot na stawkï¿½).
    """
    q = estimate_true_prob(p)                 # P(YES wygra)
    no_price = 1.0 - p
    cost = no_price + taker_fee(1.0, no_price, fee_rate) + spread / 2.0
    if cost <= 0 or cost >= 1:
        return (0.0, 0.0)
    ev = (1.0 - q) * (1.0 - cost) - q * cost  # wygrana gdy NO, przegrana gdy YES
    return (ev, ev / cost)


def ev_buy_yes(p: float, fee_rate: float, spread: float) -> tuple:
    """Wartoï¿½ï¿½ oczekiwana kupna YES przy cenie p (do wariantu favorite)."""
    q = estimate_true_prob(p)
    cost = p + taker_fee(1.0, p, fee_rate) + spread / 2.0
    if cost <= 0 or cost >= 1:
        return (0.0, 0.0)
    ev = q * (1.0 - cost) - (1.0 - q) * cost
    return (ev, ev / cost)


def breakeven_winrate(tp_move: float, sl_move: float, cost_per_share: float) -> float:
    """Prï¿½g opï¿½acalnoï¿½ci (winrate) dla symetrycznego TP/SL (do porï¿½wnaï¿½)."""
    net_win = tp_move - cost_per_share
    net_loss = sl_move + cost_per_share
    if net_win <= 0:
        return 1.0
    return net_loss / (net_win + net_loss)


# ===========================================================================
# API
# ===========================================================================
def _j(v):
    """Gamma zwraca clobTokenIds/outcomes jako string JSON."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return None
    return v


def get_price_history(token_id: str, fidelity: int = 1):
    """Historia cen (ts w sekundach, cena) z CLOB /prices-history."""
    try:
        r = requests.get(
            f"{CLOB_HOST}/prices-history",
            params={"market": token_id, "interval": "max", "fidelity": fidelity},
            timeout=25,
        )
        data = r.json().get("history", [])
        return [(int(x["t"]), float(x["p"])) for x in data]
    except Exception:
        return []


def get_ask(token_id: str) -> float:
    """Cena KUPNA = best ASK. UWAGA: CLOB ma odwrotna semantyke parametru side:
    /price?side=sell zwraca best ASK, /price?side=buy zwraca best BID (sprawdzone na zywym API)."""
    return get_price(token_id, "sell")


def get_bid(token_id: str) -> float:
    """Cena SPRZEDAZY (wycena pozycji) = best BID -> /price?side=buy."""
    return get_price(token_id, "buy")


def get_price(token_id: str, side: str = "buy"):
    """Best price z /price. side="buy" -> best BID, side="sell" -> best ASK (tak dziala CLOB)."""
    try:
        r = requests.get(f"{CLOB_HOST}/price",
                         params={"token_id": token_id, "side": side}, timeout=15)
        return float(r.json().get("price", 0.0))
    except Exception:
        return 0.0


def get_tick_size(token_id: str) -> float:
    """Tick size rynku z CLOB /tick-size (0.1 / 0.01 / 0.001 / 0.0001)."""
    try:
        r = requests.get(f"{CLOB_HOST}/tick-size",
                         params={"token_id": token_id}, timeout=15)
        return float(r.json().get("tick_size", 0.01))
    except Exception:
        return 0.01


def _ts(s):
    """ISO string -> unix ts (sekundy, UTC). CLOB/Gamma zwracajï¿½ sekundy."""
    if s is None or s == "":
        return None
    if isinstance(s, (int, float)):
        return float(s)
    try:
        return float(s)          # timestamp liczbowy zapisany jako string
    except (TypeError, ValueError):
        pass
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _fetch_resolved_one(m):
    """Dopeï¿½nia rynek rozstrzygniï¿½ty o historiï¿½ cen (do rï¿½wnolegï¿½ego map)."""
    m["history"] = get_price_history(m["yes_token"], fidelity=1)
    return m


def fetch_resolved_markets(tag="sports", max_pages=40, min_vol=1000.0):
    """Rynki rozstrzygniï¿½te z Gamma (do backtestu); historia cen rï¿½wnolegle."""
    out, seen = [], set()
    for page in range(max_pages):
        try:
            r = requests.get(f"{GAMMA_HOST}/events", params={
                "closed": "true", "tag_slug": tag, "limit": 100, "offset": page * 100,
                "order": "volume", "ascending": "false",
            }, timeout=25)
            evs = r.json()
        except Exception as e:
            print(f"[Gamma stop] resolved page={page}: {e}")
            break
        if not evs:
            break
        for ev in evs:
            for m in ev.get("markets", []):
                slug = m.get("slug")
                if not slug or slug in seen or not m.get("closed"):
                    continue
                seen.add(slug)
                if float(m.get("volume") or 0.0) < min_vol:
                    continue
                toks = _j(m.get("clobTokenIds")) or []
                outs = _j(m.get("outcomes")) or []
                if not toks or len(outs) != len(toks) or len(toks) < 2:
                    continue
                if "No" in outs:
                    ni = outs.index("No")
                    m["yes_token"] = str(toks[1 - ni])
                    m["no_token"] = str(toks[ni])
                    m["no_idx"] = ni
                    m["pair_mode"] = False
                elif len(toks) == 2:
                    # rynek 2-wynikowy bez tokenu "No" (nazwy druzyn, Over/Under):
                    # kupno drugiego wyniku = ekonomiczny odpowiednik kupna NO na longshocie
                    m["pair_mode"] = True
                    m["outcome_tokens"] = [[outs[0], str(toks[0])], [outs[1], str(toks[1])]]
                    m["yes_token"] = str(toks[0])
                    m["no_token"] = str(toks[1])
                    m["no_idx"] = 1
                else:
                    continue
                m["source_tags"] = [tag]
                m["_event"] = ev.get("slug") or ev.get("title")
                m["_event_id"] = ev.get("id")
                out.append(m)
        if len(evs) < 100:
            break
    with ThreadPoolExecutor(20) as pool:
        out = list(pool.map(_fetch_resolved_one, out))
    return [m for m in out if m.get("history")]


def _gamma_events(params):
    """GET /events z retry + backoff (Gamma potrafi zrywaï¿½ poï¿½ï¿½czenie)."""
    for attempt in range(GAMMA_RETRY):
        try:
            r = requests.get(f"{GAMMA_HOST}/events", params=params, timeout=25)
            return r.json()
        except Exception as e:
            if attempt == GAMMA_RETRY - 1:
                print(f"[Gamma stop] {params.get('tag_slug')} offset={params.get('offset')}: {e!r}"[:180])
                return []
            time.sleep(GAMMA_BACKOFF * (attempt + 1))
    return []


def _fetch_active_one(tag, limit, min_vol, seen):
    """Jeden tag: paginacja po eventach (cap offsetu), rynki z source_tags."""
    out = []
    offset = 0
    while offset < ACTIVE_EVENT_OFFSET_LIMIT and len(out) < limit:
        evs = _gamma_events({
            "closed": "false", "tag_slug": tag, "limit": 100, "offset": offset,
            "order": "volume", "ascending": "false",
        })
        if not evs:
            break
        batch_added = 0
        for ev in evs:
            for m in ev.get("markets", []):
                if m.get("closed") or m.get("archived"):
                    continue
                slug = m.get("slug")
                if not slug or slug in seen:
                    continue
                seen.add(slug)
                if float(m.get("volume") or 0.0) < min_vol:
                    continue
                toks = _j(m.get("clobTokenIds")) or []
                outs = _j(m.get("outcomes")) or []
                if not toks or len(outs) != len(toks) or len(toks) < 2:
                    continue
                if "No" in outs:
                    ni = outs.index("No")
                    m["yes_token"] = str(toks[1 - ni])
                    m["no_token"] = str(toks[ni])
                    m["no_idx"] = ni
                    m["pair_mode"] = False
                elif len(toks) == 2:
                    # rynek 2-wynikowy bez tokenu "No" (nazwy druzyn, Over/Under):
                    # kupno drugiego wyniku = ekonomiczny odpowiednik kupna NO na longshocie
                    m["pair_mode"] = True
                    m["outcome_tokens"] = [[outs[0], str(toks[0])], [outs[1], str(toks[1])]]
                    m["yes_token"] = str(toks[0])
                    m["no_token"] = str(toks[1])
                    m["no_idx"] = 1
                else:
                    continue
                m["source_tags"] = [tag]
                m["_event"] = ev.get("slug") or ev.get("title")
                m["_event_id"] = ev.get("id")
                out.append(m)
                batch_added += 1
                if len(out) >= limit:
                    break
            if len(out) >= limit:
                break
        if offset % 1000 == 0:
            print(f"[active {tag}] offset={offset} rynki={len(out)}")
        if batch_added == 0:
            break
        offset += 100
    return out


def fetch_active_markets(tags, limit=ACTIVE_MARKET_LIMIT_PER_TAG, min_vol=0.0):
    """Aktywne rynki z wielu tagï¿½w (ThreadPool), dedupe po slug, union source_tags."""
    tags = expand_tags(tags)
    seen = set()
    results = {}
    with ThreadPoolExecutor(6) as pool:
        futs = {pool.submit(_fetch_active_one, t, limit, min_vol, seen): t for t in tags}
        for fut, t in futs.items():
            results[t] = fut.result()
    by_slug = {}
    for t in tags:
        for m in results.get(t, []):
            slug = m.get("slug")
            ex = by_slug.get(slug)
            if ex is None:
                by_slug[slug] = m
            else:
                ex["source_tags"] = sorted(set(ex.get("source_tags") or []) |
                                           set(m.get("source_tags") or []))
    return list(by_slug.values())


# ===========================================================================
# TIMING I POLITYKA WEJï¿½ï¿½ (jedna definicja kaï¿½dej funkcji ï¿½ bez martwego kodu)
# ===========================================================================
def _is_live_game(m, lw=LIVE_WINDOW_H):
    """Mecz trwa: gameStartTime w (teraz - lw h, teraz)."""
    gs = _ts(m.get("gameStartTime"))
    if gs is None:
        return False
    h = (time.time() - gs) / 3600.0
    return 0.0 <= h <= lw


def _is_pre_game(m, window_h=PRE_GAME_WINDOW_H):
    """Mecz zaczyna siï¿½ w ciï¿½gu najbliï¿½szych window_h godzin (pre-market)."""
    gs = _ts(m.get("gameStartTime"))
    if gs is None:
        return False
    h = (gs - time.time()) / 3600.0
    return 0.0 < h <= window_h


def _entry_timing(m, live_window=LIVE_WINDOW_H):
    """'live' | 'pre' | None ï¿½ na podstawie gameStartTime."""
    if _is_live_game(m, live_window):
        return "live"
    if _is_pre_game(m):
        return "pre"
    return None


def _duration_h(tags):
    """Typowy czas trwania meczu (h) na podstawie tagow sportowych."""
    durs = [SPORT_DURATION_H[t] for t in (tags or []) if t in SPORT_DURATION_H]
    return max(durs) if durs else DEFAULT_DURATION_H


def _expected_end_ts(gs, tags):
    """Oszacowany koniec meczu (unix ts) = start + typowy czas trwania."""
    if gs is None:
        return None
    return gs + _duration_h(tags) * 3600.0


def _local_midnight_ts(ref_ts=None):
    """Najblizsza lokalna polnoc po ref_ts (domyslnie: po teraz)."""
    ref = time.time() if ref_ts is None else ref_ts
    dt = datetime.fromtimestamp(ref).astimezone()
    nxt = dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return nxt.timestamp()


def _same_day_ok(m, ref_ts=None, gs=None):
    """True gdy mecz konczy sie (+bufor) przed lokalna polnoca -> rozstrzygniecie tego samego dnia."""
    if not SAME_DAY_ONLY:
        return True
    if gs is None:
        gs = _ts(m.get("gameStartTime") or m.get("game_start"))
    end = _expected_end_ts(gs, m.get("source_tags"))
    if end is None:
        return False
    ref = time.time() if ref_ts is None else ref_ts
    resolve_ts = end + SAME_DAY_GRACE_H * 3600.0
    if resolve_ts - ref > MAX_HOURS_TO_RESOLVE * 3600.0:
        return False
    if SAME_CALENDAR_DAY and resolve_ts > _local_midnight_ts(ref):
        return False
    return True


def _timing_ok_strict(gs, t, timing_filter):
    """Ta sama polityka czasu co live: pre = 0..PRE_GAME_WINDOW_H przed startem, live = 0..LIVE_WINDOW_H po."""
    if gs is None:
        return False
    if timing_filter == "pre":
        return 0 < gs - t <= PRE_GAME_WINDOW_H * 3600.0
    if timing_filter == "live":
        return 0 <= t - gs <= LIVE_WINDOW_H * 3600.0
    return False          # "post" = po oknie live -> live nie wchodzi, wiec backtest tez nie


def _gamma_outcome_price(slug, idx):
    """Cena wskazujaca z Gamma (outcomePrices[idx]) - fallback przy pustym order booku."""
    try:
        data = requests.get(f"{GAMMA_HOST}/markets", params={"slug": slug}, timeout=15).json()
        m = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else None)
        if not m:
            return None
        prices = _j(m.get("outcomePrices")) or []
        if idx is None or idx >= len(prices):
            return None
        return float(prices[idx])
    except Exception:
        return None


def _position_mark(pos):
    """
    Rozsadna wycena 1 share:
      * bid > 0 i ask < 1  -> srodek spreadu (mid)
      * tylko bid          -> bid
      * pusty book (0 / 1) -> cena z Gamma, a gdy jej brak -> cena wejscia
    Bez tego pusty book dawal falszywe -100% (bid=0) albo +100% (ask=1).
    """
    bid = get_bid(pos["no_token"])
    ask = get_ask(pos["no_token"])
    if bid > 0 and 0 < ask < 1.0:
        return (bid + ask) / 2.0
    if bid > 0:
        return bid
    gamma = _gamma_outcome_price(pos["slug"], pos.get("no_idx"))
    if gamma is not None and 0 < gamma < 1:
        return gamma
    return pos["entry_no"]


def _mark_positions(positions):
    """PnL niezrealizowany (mark-to-market) po wycenie z _position_mark."""
    unreal = 0.0
    for pos in positions.values():
        unreal += pos["shares"] * _position_mark(pos) - pos["usd"]
    return unreal




def _market_group(m):
    """Klasyfikacja rynku: moneyline | totals | spread | other (wariant PATCH_GROUP_V2)."""
    mt = (m.get("sportsMarketType") or "").lower()
    q = ((m.get("_event") or "") + " " + (m.get("question") or "")).lower()
    s = q + " " + mt
    if "total" in mt or "spread" in mt or "handicap" in mt:
        return "totals" if "total" in mt else "spread"
    if any(x in s for x in ("contract", "next team", "$", "million", "salary")):
        return "other"
    if "spread" in s or "handicap" in s or re.search(r"(?<!\w)[+-]\s?\d+(\.5)?\b", s):
        return "spread"
    if re.search(r"\b(?:over|under)\b[^\n]{0,30}\d", s) or re.search(r"\bo/u\b", s) or "total" in s:
        return "totals"
    if re.search(r"\bwill\b.{0,80}\bwin\b", q) or "moneyline" in mt or "winner" in mt:
        return "moneyline"
    return "other"


def _market_sports(m):
    """Tagi sportowe rynku (source_tags ï¿½ dozwolone politykï¿½), bez BLOCKED."""
    src = m.get("source_tags") or []
    sports = {t for t in src if t in PRE_MARKET_POLICY or t in SOCCER_TAGS}
    return {t for t in sports if t not in BLOCKED_SPORT_TAGS}


def _market_allowed_by_policy(m):
    """Polityka wejï¿½ï¿½: wolumen >= MIN_ACTIVE_VOL, sport znany, timing zgodny z politykï¿½."""
    if float(m.get("volume") or 0.0) < MIN_ACTIVE_VOL:
        return False
    sports = _market_sports(m)
    if not sports:
        return False
    group = _market_group(m)
    timing = _entry_timing(m)
    if timing == "live":
        return any(s in SOCCER_TAGS for s in sports) and group in LIVE_SOCCER_MARKETS
    if timing == "pre":
        return any(group in PRE_MARKET_POLICY.get(s, set()) for s in sports)
    return False


# ===========================================================================
# STAN / ZAPIS
# ===========================================================================
def _load(path, default):
    """Wczytuje JSON. Rozroznia: brak pliku / plik uszkodzony / za duzy na pamiec."""
    try:
        return json.load(open(path))
    except FileNotFoundError:
        return default
    except MemoryError:
        try:
            mb = os.path.getsize(path) / 1e6
        except OSError:
            mb = -1
        print(f"[load] {path}: plik {mb:.0f} MB - brak pamieci. Przebuduj cache mniejszym zakresem "
              f"(--days 7 --max-markets 4000).")
        return default
    except Exception as e:
        try:
            mb = os.path.getsize(path) / 1e6
        except OSError:
            mb = -1
        print(f"[load] {path}: nie mozna wczytac ({e!r}), rozmiar {mb:.1f} MB")
        return default


def _save(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def _balance_usd(positions):
    return sum(p["usd"] for p in positions.values())


def _settle_positions(positions, trades, dry, out_dir="."):
    """Rozstrzyga pozycje: sprawdza outcome na Gamma; wygrana = shares*1.0 - koszt."""
    still = {}
    for key, p in list(positions.items()):
        try:
            r = requests.get(f"{GAMMA_HOST}/markets", params={"slug": p["slug"]}, timeout=15)
            data = r.json()
            m = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else None)
        except Exception:
            still[key] = p
            continue
        if not m or not m.get("closed"):
            still[key] = p
            continue
        if m.get("resolved") is False:
            still[key] = p
            continue
        outs = _j(m.get("outcomes")) or []
        winner = (m.get("outcomePrices") or [None, None])
        winner = _j(winner) if isinstance(winner, str) else winner
        if not outs or not winner:
            still[key] = p
            continue
        if "No" in outs:
            no_idx = outs.index("No")
        else:
            no_idx = p.get("no_idx")
        if no_idx is None or no_idx >= len(winner):
            still[key] = p
            continue
        try:
            no_price = float(winner[no_idx])
        except (TypeError, ValueError):
            still[key] = p
            continue
        if no_price >= 0.99:
            pnl, result = p["shares"] * 1.0 - p["usd"], "win"
        elif no_price <= 0.01:
            pnl, result = -p["usd"], "loss"
        else:
            # 0.5/0.5 = rynek anulowany (refund). Czekamy na finalny outcome do endDate+24h.
            ed = _ts(m.get("endDate"))
            if ed is None or time.time() < ed + 86400.0:
                still[key] = p
                continue
            pnl, result = 0.0, "void"
        trades.append({
            "ts": int(time.time()), "key": key, "slug": p["slug"], "event": p["event"],
            "entry_no": p["entry_no"], "shares": p["shares"], "cost": p["usd"],
            "pnl_usd": pnl, "result": result, "settled": True, "dry": dry,
        })
        del positions[key]
    _save(TRADES_FILE_DRY if dry else TRADES_FILE_LIVE, trades)
    _save(POSITIONS_FILE_DRY if dry else POSITIONS_FILE_LIVE, positions)
    return still


# ===========================================================================
# HANDLARZ: DRY vs LIVE (oficjalny py-clob-client)
# ===========================================================================
class DryBroker:
    """Symulacja: zapisuje pozycjï¿½ po cenie ask (bez prawdziwego zlecenia)."""

    def __init__(self, dry=True):
        self.dry = dry

    def buy_no(self, token_id, usd, limit_price, tick, fee_rate):
        ask = get_ask(token_id)
        if ask <= 0:
            return {"ok": False, "err": "brak ask"}
        if ask > limit_price:
            return {"ok": False, "err": f"ask {ask:.4f} > limit {limit_price:.4f}"}
        shares = usd / max(ask, 1e-6)
        cost = usd + taker_fee(shares, ask, fee_rate) + ASSUMED_SPREAD / 2.0 * shares
        return {"ok": True, "price": ask, "shares": shares, "cost": cost,
                "dry": self.dry, "raw": {"simulated": True}}


class LiveBroker:
    """Prawdziwe zlecenia przez py-clob-client (FAK, limit cena = ask + SPREAD/2)."""

    def __init__(self):
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import OrderType
        from py_clob_client.order_builder.constants import BUY
        self.OrderType = OrderType
        self.BUY = BUY
        key = os.environ.get("POLY_PRIVATE_KEY")
        if not key:
            raise SystemExit("POLY_PRIVATE_KEY brak w env")
        funder = os.environ.get("POLYMARKET_DEPOSIT_WALLET") or os.environ.get("POLY_FUNDER")
        sig = int(os.environ.get("POLY_SIGNATURE_TYPE", "1"))
        self.client = ClobClient(
            CLOB_HOST, key=key, chain_id=137,
            signature_type=sig, funder=funder,
        )
        self.client.set_api_creds(self.client.create_or_derive_api_creds())

    def buy_no(self, token_id, usd, limit_price, tick, fee_rate):
        """Kupno NO: MarketOrderArgs(amount=USD, price=limit, FAK).
        SDK sam rozwiï¿½zuje tick_size/neg_risk/fee (zweryfikowane w ï¿½rï¿½dï¿½ach)."""
        from py_clob_client.clob_types import MarketOrderArgs
        limit = min(limit_price, 1.0 - tick)
        limit = math.floor(limit / tick) * tick
        mo = MarketOrderArgs(
            token_id=token_id, amount=usd, side=self.BUY,
            price=round(limit, 4), order_type=self.OrderType.FAK,
        )
        signed = self.client.create_market_order(mo)
        resp = self.client.post_order(signed, self.OrderType.FAK)
        # FAK: peï¿½ne lub czï¿½ï¿½ciowe wypeï¿½nienie; odczyt realnego fillu
        making = float(resp.get("makingAmount") or 0.0)   # USDC wydane
        taking = float(resp.get("takingAmount") or 0.0)   # sztuki NO kupione
        if resp.get("success") is False or (making <= 0 and taking <= 0):
            return {"ok": False, "err": str(resp.get("errorMsg") or resp)}
        if making <= 0 or taking <= 0:
            return {"ok": False, "err": "brak fillu (FAK)"}
        return {"ok": True, "price": making / taking, "shares": taking, "cost": making,
                "dry": False, "raw": resp}


def _entry_prices(m):
    """
    (yes_price, no_token, no_ask, no_idx) dla rynku.
    Yes/No: YES = token longshotu, NO = token przeciwny.
    pair_mode (2 nazwane wyniki): longshot = strona z nizsza cena, NO = druga strona.
    Zwraca None, gdy brak danych z CLOB.
    """
    if m.get("pair_mode"):
        a = get_ask(m["outcome_tokens"][0][1])
        b = get_ask(m["outcome_tokens"][1][1])
        if a <= 0 or b <= 0:
            return None
        if a <= b:
            return a, m["outcome_tokens"][1][1], b, 1
        return b, m["outcome_tokens"][0][1], a, 0
    yes_price = get_ask(m["yes_token"])
    no_token = m["no_token"]
    no_ask = get_ask(no_token)
    if yes_price <= 0 or no_ask <= 0:
        return None
    return yes_price, no_token, no_ask, m.get("no_idx")

def _open_position(m, positions, trades, broker, dry, tags):
    """Wejï¿½cie: kup NO gdy YES w pasmie i EV >= MIN_EDGE. Zwraca True jeï¿½eli otwarto."""
    slug = m.get("slug")
    if slug in positions:
        return False
    group = _market_group(m)
    timing = _entry_timing(m)
    if timing is None:
        return False
    if not _market_allowed_by_policy(m):
        return False
    if not _same_day_ok(m):
        return False
    if len(positions) >= MAX_POSITIONS:
        return False
    pr = _entry_prices(m)
    if not pr:
        return False
    yes_price, no_token, no_ask, no_idx = pr
    if not (LONG_LO <= yes_price <= LONG_HI):
        return False
    if no_ask <= 0:
        return False
    if abs(no_ask - (1.0 - yes_price)) > 0.06:
        return False
    fee_rate = fee_for_tag(",".join(m.get("source_tags") or ["sports"]))
    ev_usd, ev_frac = ev_buy_no(yes_price, fee_rate, ASSUMED_SPREAD)
    if ev_frac < MIN_EDGE:
        return False
    if timing == "pre":
        gs = _ts(m.get("gameStartTime"))
        if gs is None or gs - time.time() > MAX_HOLD_DAYS * 86400:
            return False
    limit_price = min(0.99, no_ask + ASSUMED_SPREAD / 2.0)
    tick = get_tick_size(no_token)
    # Stawka twardo 1 USD — zlecenia market FAK przechodzą po 1 USD (live potwierdzone).
    usd = SIZE_USD
    res = broker.buy_no(no_token, usd, limit_price, tick, fee_rate)
    if not res.get("ok"):
        if not dry:
            print(f"[LIVE-ERR] {slug}: {res.get('err')}")
        return False
    positions[slug] = {
        "slug": slug, "event": m.get("_event") or "", "question": m.get("question") or "",
        "no_idx": no_idx, "pair_mode": m.get("pair_mode", False),
        "no_token": no_token, "yes_token": m["yes_token"], "entry_no": res["price"],
        "shares": res["shares"], "usd": res["cost"], "timing": timing,
        "group": group, "tags": m.get("source_tags") or [], "ts_open": int(time.time()),
    }
    print(f"[{'DRY' if dry else 'LIVE'}] KUPNO NO {res['price']:.4f} x{res['shares']:.2f} "
          f"(${res['cost']:.2f}) | EV {ev_frac * 100:+.1f}% | {timing} | {group} | {slug}")
    return True


# ===========================================================================
# BACKTEST (na bt_cache2.json)
# ===========================================================================
def _time_group(m, start_ts=None):
    """'pre' | 'live' | 'post' ï¿½ na podstawie gameStartTime i okna LIVE_WINDOW_H."""
    gs = _ts(m.get("game_start") or m.get("gameStartTime"))
    if gs is None:
        return None
    start = start_ts if start_ts is not None else time.time()
    if start < gs:
        return "pre"
    if start <= gs + LIVE_WINDOW_H * 3600:
        return "live"
    return "post"


def _sim_yes_threshold(m, no_lo, fee_rate, spread, notional, timing_filter):
    """
    Kup NO przy pierwszym punkcie, gdzie NO >= no_lo (i zgodnie z timing_filter).
    Wyjï¿½cie: hold do rozstrzygniï¿½cia. Zwraca dict albo None.
    """
    gs = _ts(m.get("game_start"))
    final_yes = m.get("final_yes")
    if final_yes is None or 0.01 < final_yes < 0.99:
        return None       # rynek anulowany/niepewny: live robi zwrot, nie liczymy jako przegrana
    for t, p in m["history"]:
        no = 1.0 - p
        if no < no_lo:
            continue
        if no > 1.0 - LONG_LO:
            continue      # YES < LONG_LO -> poza pasmem live (0.15-0.50), nie handlujemy
        if not _timing_ok_strict(gs, t, timing_filter):
            continue
        if not _same_day_ok(m, ref_ts=t, gs=gs):
            continue
        cost = no + taker_fee(1.0, no, fee_rate) + spread / 2.0
        if cost <= 0 or cost >= 1:
            return None
        payout = 1.0 if final_yes < 0.5 else 0.0
        return {"entry_no": no, "entry_t": t, "cost": cost, "payout": payout,
                "pnl_pct": (payout - cost) / cost * 100.0,
                "pnl_usd": (payout - cost) * (notional / cost)}
    return None


def _bt_policy_ok(m, timing):
    """Ta sama polityka co live: dozwolone grupy rynku per liga, live tylko dla soccer."""
    sports = {t for t in (m.get("source_tags") or [])
              if t in PRE_MARKET_POLICY or t in SOCCER_TAGS}
    sports = {t for t in sports if t not in BLOCKED_SPORT_TAGS}
    if not sports:
        return False
    group = m.get("group") or "other"
    if timing == "live":
        return any(t in SOCCER_TAGS for t in sports) and group in LIVE_SOCCER_MARKETS
    if timing == "pre":
        return any(group in PRE_MARKET_POLICY.get(t, set()) for t in sports)
    return False


def _backtest_run(markets, no_lo, timing_filter, notional=SIZE_USD):
    trades = []
    for m in markets:
        if BT_USE_POLICY and not _bt_policy_ok(m, timing_filter):
            continue
        fee_rate = fee_for_tag(",".join(m.get("source_tags") or ["sports"]))
        tr = _sim_yes_threshold(m, no_lo, fee_rate, ASSUMED_SPREAD, notional, timing_filter)
        if tr:
            tr["slug"] = m.get("slug")
            trades.append(tr)
    if not trades:
        return {"n": 0, "wr": 0.0, "ev": 0.0, "pnl": 0.0}
    wr = sum(1 for t in trades if t["payout"] > 0.5) / len(trades) * 100.0
    ev = statistics.mean(t["pnl_pct"] for t in trades)
    pnl = sum(t["pnl_usd"] for t in trades)
    return {"n": len(trades), "wr": wr, "ev": ev, "pnl": pnl}

def _norm_market(m):
    """Uzupelnia tokeny/no_idx/pair_mode (Yes/No albo 2 nazwane wyniki). Zwraca True gdy OK."""
    toks = _j(m.get("clobTokenIds")) or []
    outs = _j(m.get("outcomes")) or []
    if not toks or len(outs) != len(toks) or len(toks) < 2:
        return False
    if "No" in outs:
        ni = outs.index("No")
        m["yes_idx"], m["no_idx"], m["pair_mode"] = 1 - ni, ni, False
    elif len(toks) == 2:
        m["yes_idx"], m["no_idx"], m["pair_mode"] = 0, 1, True
    else:
        return False
    m["yes_token"] = str(toks[m["yes_idx"]])
    m["no_token"] = str(toks[m["no_idx"]])
    return True


def build_bt_cache(tags, days=30, min_vol=MIN_ACTIVE_VOL, max_markets=400, out=BT_CACHE):
    """Buduje bt_cache2.json: rozstrzygniete mecze z ostatnich N dni + historia cen YES."""
    tags = expand_tags(tags)
    cutoff = time.time() - days * 86400
    seen, items = set(), []
    void_n = 0
    per_tag = max(50, max_markets // max(1, len(tags)))   # zeby kazdy tag cos wniosl
    for tag in tags:
        tag_n = 0
        if len(items) >= max_markets:
            break
        for page in range(FETCH_HISTORY_PAGES):
            evs = _gamma_events({"closed": "true", "tag_slug": tag, "limit": 100,
                                 "offset": page * 100, "order": "volume", "ascending": "false"})
            if not evs:
                break
            for ev in evs:
                for m in ev.get("markets", []):
                    slug = m.get("slug")
                    if not slug or slug in seen or not m.get("closed"):
                        continue
                    seen.add(slug)
                    end_ts = _ts(m.get("endDate")) or _ts(m.get("closedTime"))
                    gs = _ts(m.get("gameStartTime"))
                    if end_ts is None or end_ts < cutoff or gs is None:
                        continue
                    if float(m.get("volume") or 0.0) < min_vol:
                        continue
                    if not _norm_market(m):
                        continue
                    prices = _j(m.get("outcomePrices")) or []
                    try:
                        final_yes = float(prices[m["yes_idx"]])
                    except (IndexError, TypeError, ValueError):
                        continue
                    if 0.01 < final_yes < 0.99:
                        void_n += 1
                        continue          # anulowany (0.5/0.5) - live robi zwrot
                    items.append({"slug": slug, "event": ev.get("slug"), "game_start": gs,
                                  "final_yes": final_yes, "source_tags": [tag], "group": _market_group(m),
                                  "pair_mode": m["pair_mode"], "volume": float(m.get("volume") or 0.0),
                                  "yes_token": m["yes_token"]})
                    tag_n += 1
                    if len(items) >= max_markets or tag_n >= per_tag:
                        break
                if len(items) >= max_markets or tag_n >= per_tag:
                    break
            if len(items) >= max_markets or tag_n >= per_tag or len(evs) < 100:
                break
        print(f"[{tag}] +{tag_n} rynkow (razem {len(items)})")

    done = {"n": 0}
    lock = threading.Lock()
    target = len(items)

    def _hist(it):
        """Historia przycieta do okna, ktore strategia moze wykorzystac: [start-3h, start+7h]."""
        gs = it.get("game_start")
        hist = get_price_history(it.pop("yes_token"), fidelity=FETCH_HISTORY_FIDELITY)
        if gs and hist:
            lo = gs - 3 * 3600.0
            hi = gs + (LIVE_WINDOW_H + 1) * 3600.0
            hist = [(t, pr) for t, pr in hist if lo <= t <= hi]
        it["history"] = hist
        with lock:
            done["n"] += 1
            if done["n"] % 100 == 0 or done["n"] == target:
                print(f"  historia cen: {done['n']}/{target}")
        return it

    with ThreadPoolExecutor(10) as pool:
        items = list(pool.map(_hist, items))
    items = [it for it in items if it["history"]]
    _save(out, items)
    if void_n:
        print(f"pominieto {void_n} rynkow anulowanych (0.5/0.5)")
    print(f"zapisano {len(items)} rynkow do {out} (ostatnie {days} dni)")
    return items



def run_backtest():
    """Backtest FADE LONGSHOT: progi NO 0.50-0.85, timing pre/live/post."""
    print("== BACKTEST FADE LONGSHOT (hold do rozstrzygniecia) ==")
    cache = _load(BT_CACHE, None)
    if not cache:
        print(f"brak lub nieczytelny {BT_CACHE} - uruchom: python bot_v2_dry_v3.py "
              f"--fetch-history --days 7 --max-markets 4000")
        return
    total = len(cache)
    cache = [m for m in cache if float(m.get("volume") or 0.0) >= BT_MIN_VOL]
    print(f"rynkow w cache: {total} | po filtrze plynnosci (vol >= {BT_MIN_VOL:.0f}): {len(cache)}"
          f" | spread wejscia: {ASSUMED_SPREAD:.3f}")
    if BT_USE_POLICY:
        n_pre = sum(1 for m in cache if _bt_policy_ok(m, "pre"))
        n_live = sum(1 for m in cache if _bt_policy_ok(m, "live"))
        print(f"rynkow zgodnych z polityka: pre={n_pre} live={n_live} (z {len(cache)})")
    if not cache:
        print("brak rynkow po filtrze - zmniejsz BT_MIN_VOL albo pobierz wiecej danych")
        return
    best = None
    for timing in ("pre", "live"):   # "post" pominiety: polityka nie wpuszcza wejsc po meczu
        for no_lo in (0.50, 0.60, 0.70, 0.75, 0.80, 0.85):
            r = _backtest_run(cache, no_lo, timing)
            print(f"timing={timing:4s} NO>={no_lo:.2f}  n={r['n']:4d} "
                  f"wr={r['wr']:6.2f}%  EV={r['ev']:+7.2f}%  PnL={r['pnl']:+9.2f} USD")
            if r["n"] >= 20 and (best is None or r["ev"] > best[2]):
                best = (timing, no_lo, r["ev"], r["n"], r["wr"], r["pnl"])
    print()
    if BT_BY_TAG and best:
        print(f"PER LIGA (wariant timing={best[0]} NO>={best[1]:.2f}):")
        for tag in sorted({t for m in cache for t in (m.get("source_tags") or [])}):
            sub = [m for m in cache if tag in (m.get("source_tags") or [])]
            r = _backtest_run(sub, best[1], best[0])
            print(f"  {tag:12s} n={r['n']:4d} wr={r['wr']:6.2f}% "
                  f"EV={r['ev']:+7.2f}% PnL={r['pnl']:+8.2f} USD")
        print()
    if best:
        print(f"NAJLEPSZY (n>=20): timing={best[0]} NO>={best[1]:.2f} "
              f"EV={best[2]:+.2f}% n={best[3]} wr={best[4]:.2f}% PnL={best[5]:+.2f} USD")
    else:
        print("zaden wariant nie ma n>=20 - probka za mala, pobierz wiecej rynkow")

# ===========================================================================
# SKAN (bez handlu)
# ===========================================================================
def _reject_reason(m):
    """Powod odrzucenia rynku (pusty string = rynek przechodzi wszystkie filtry)."""
    timing = _entry_timing(m)
    if timing is None:
        gs = _ts(m.get("gameStartTime"))
        if gs is None:
            return "brak gameStartTime (futures/sezon, nie mecz)"
        h = (gs - time.time()) / 3600.0
        return f"poza oknem czasu (start za {h:.1f} h)" if h > 0 else f"mecz juz trwal/skonczony ({-h:.1f} h temu)"
    sports = _market_sports(m)
    if not sports:
        return "kategoria zablokowana (BLOCKED_SPORT_TAGS / brak w polityce)"
    group = _market_group(m)
    if timing == "live":
        if not (any(x in SOCCER_TAGS for x in sports) and group in LIVE_SOCCER_MARKETS):
            return f"live: grupa {group} nie jest handlowana na zywo"
    elif not any(group in PRE_MARKET_POLICY.get(x, set()) for x in sports):
        return f"polityka pre: grupa {group} wylaczona dla {','.join(sorted(sports))}"
    if float(m.get("volume") or 0.0) < MIN_ACTIVE_VOL:
        return "wolumen < MIN_ACTIVE_VOL"
    if not _same_day_ok(m):
        return "nie rozstrzygnie sie dość szybko (same-day)"
    pr = _entry_prices(m)
    if not pr:
        return "brak cen w CLOB"
    yes_price, no_token, no_ask, no_idx = pr
    if not (LONG_LO <= yes_price <= LONG_HI):
        return f"YES={yes_price:.2f} poza pasmem {LONG_LO}-{LONG_HI}"
    if abs(no_ask - (1.0 - yes_price)) > 0.06:
        return f"rozjazd YES/NO ({yes_price:.2f}/{no_ask:.2f})"
    ev = ev_buy_no(yes_price, fee_for_tag(",".join(m.get("source_tags") or ["sports"])),
                   ASSUMED_SPREAD)[1]
    if ev < MIN_EDGE:
        return f"EV {ev * 100:+.1f}% < MIN_EDGE"
    return ""


def run_explain(tags, examples=2):
    """Zlicza powody odrzucenia rynkow - do diagnozy 'dlaczego nic nie kupuje'."""
    print("== EXPLAIN == (powody odrzucen, bez handlu)")
    markets = fetch_active_markets(tags, limit=ACTIVE_MARKET_LIMIT_PER_TAG, min_vol=MIN_ACTIVE_VOL)
    print(f"pobrano {len(markets)} rynkow | tagi={tags}")
    buckets, passed = {}, []
    for m in markets:
        r = _reject_reason(m)
        if not r:
            passed.append(m)
            continue
        key = re.sub(r"\d+([.,]\d+)?", "N", r)
        buckets.setdefault(key, []).append((m.get("slug") or "?", r))
    print(f"PRZECHODZI WSZYSTKIE FILTRY: {len(passed)}")
    for m in passed[:10]:
        pr = _entry_prices(m)
        print(f"  OK  {m.get('slug')[:58]:58s} YES={pr[0]:.2f} NO={pr[2]:.2f} "
              f"{_market_group(m)}/{_entry_timing(m)} vol={float(m.get('volume') or 0):.0f}")
    print("ODRZUCONE (powod -> liczba):")
    for key in sorted(buckets, key=lambda k: -len(buckets[k])):
        print(f"  {len(buckets[key]):4d}  {key}")
        for slug, r in buckets[key][:examples]:
            print(f"          np. {slug[:58]:58s} -> {r}")


def run_scan(tags):
    """Pokazuje TYLKO rynki, ktore bot realnie kupilby teraz (te same filtry co _open_position)."""
    print("== SKAN ==")
    markets = fetch_active_markets(tags, limit=ACTIVE_MARKET_LIMIT_PER_TAG, min_vol=MIN_ACTIVE_VOL)
    print(f"pobrano {len(markets)} rynkow")
    shown = 0
    for m in markets:
        if _reject_reason(m):
            continue
        pr = _entry_prices(m)
        yes_price = pr[0]
        fee_rate = fee_for_tag(",".join(m.get("source_tags") or ["sports"]))
        ev_frac = ev_buy_no(yes_price, fee_rate, ASSUMED_SPREAD)[1]
        print(f"[OK] {_entry_timing(m):4s} {_market_group(m):9s} YES={yes_price:.3f} "
              f"NO={pr[2]:.3f} EV={ev_frac * 100:+6.1f}% | {m.get('slug')}")
        shown += 1
        if shown >= 25:
            break
    if not shown:
        print("brak rynkow spelniajacych wszystkie filtry w tej chwili")
        print("-> powod: python bot_v2_dry_v3.py --explain --tags ...")
        print("-> test okna czasu: python bot_v2_dry_v3.py --pre-hours 24 --scan --tags ...")

# ===========================================================================
# Pï¿½TLA (dry / live)
# ===========================================================================
def run_loop(tags, dry=True):
    broker = DryBroker(dry=dry) if dry else LiveBroker()
    pf = POSITIONS_FILE_DRY if dry else POSITIONS_FILE_LIVE
    tf = TRADES_FILE_DRY if dry else TRADES_FILE_LIVE
    positions = _load(pf, {})
    trades = _load(tf, [])
    markets_cache = {"ts": 0.0, "data": []}
    print(f"== Pï¿½TLA {'DRY' if dry else 'LIVE'} == tagi={tags} "
          f"pozycje={len(positions)} transakcje={len(trades)}")
    while True:
        try:
            positions = _settle_positions(positions, trades, dry)
            now = time.time()
            if now - markets_cache["ts"] > MARKETS_CACHE_TTL or not markets_cache["data"]:
                markets_cache["data"] = fetch_active_markets(
                    tags, limit=ACTIVE_MARKET_LIMIT_PER_TAG, min_vol=MIN_ACTIVE_VOL)
                markets_cache["ts"] = now
            markets = markets_cache["data"]
            opened = 0
            for m in markets:
                if not _market_allowed_by_policy(m):
                    continue
                if _open_position(m, positions, trades, broker, dry, tags):
                    opened += 1
                if opened >= 3:
                    break
            _save(pf, positions)
            _save(tf, trades)
            pnl = sum(t["pnl_usd"] for t in trades)
            unreal = _mark_positions(positions)
            print(f"[{datetime.now(timezone.utc):%H:%M}] pozycje={len(positions)} "
                  f"zamkniete={len(trades)} PnL_zreal={pnl:+.2f} PnL_otwarte={unreal:+.2f} "
                  f"RAZEM={pnl + unreal:+.2f} USD otwarto={opened}")
        except KeyboardInterrupt:
            print("stop")
            break
        except Exception as e:
            print(f"[loop-err] {e!r}")
        try:
            time.sleep(LOOP_SLEEP)
        except KeyboardInterrupt:
            print("stop")
            break


def run_once(tags, dry=True):
    """Jeden przebieg: rozlicz, pobierz rynki, otworz pozycje, pokaz PnL (bez petli)."""
    broker = DryBroker(dry=dry) if dry else LiveBroker()
    pf = POSITIONS_FILE_DRY if dry else POSITIONS_FILE_LIVE
    tf = TRADES_FILE_DRY if dry else TRADES_FILE_LIVE
    positions = _load(pf, {})
    trades = _load(tf, [])
    positions = _settle_positions(positions, trades, dry)
    print(f"== JEDEN PRZEBIEG {'DRY' if dry else 'LIVE'} == tagi={tags} "
          f"pozycje={len(positions)} zamkniete={len(trades)}")
    markets = fetch_active_markets(tags, limit=ACTIVE_MARKET_LIMIT_PER_TAG, min_vol=MIN_ACTIVE_VOL)
    print(f"pobrano {len(markets)} aktywnych rynkow")
    opened = 0
    for m in markets:
        if _open_position(m, positions, trades, broker, dry, tags):
            opened += 1
        if opened >= 3:
            break
    _save(pf, positions)
    _save(tf, trades)
    pnl = sum(t["pnl_usd"] for t in trades)
    unreal = _mark_positions(positions)
    print(f"otwarto={opened} | PnL_zreal={pnl:+.2f} PnL_otwarte={unreal:+.2f} RAZEM={pnl + unreal:+.2f} USD")


def run_report(dry=True):
    """Raport: otwarte pozycje z wycena mark-to-market + PnL zrealizowany."""
    pf = POSITIONS_FILE_DRY if dry else POSITIONS_FILE_LIVE
    tf = TRADES_FILE_DRY if dry else TRADES_FILE_LIVE
    positions = _load(pf, {})
    trades = _load(tf, [])
    print(f"== RAPORT {'DRY' if dry else 'LIVE'} ==")
    unreal = 0.0
    for key, pos in positions.items():
        bid = get_bid(pos["no_token"])
        ask = get_ask(pos["no_token"])
        mark = _position_mark(pos)
        u = pos["shares"] * mark - pos["usd"]
        unreal += u
        print(f"  OTWARTA {pos['slug'][:46]:46s} NO={pos['entry_no']:.3f} bid={bid:.3f} ask={ask:.3f} "
              f"mark={mark:.3f} shares={pos['shares']:.2f} koszt=${pos['usd']:.2f} PnL={u:+.2f}")
    if not positions:
        print("  (brak otwartych pozycji)")
    pnl = sum(t["pnl_usd"] for t in trades)
    wins = sum(1 for t in trades if t.get("result") == "win")
    print(f"  zamkniete={len(trades)} (win={wins}) PnL_zreal={pnl:+.2f} "
          f"PnL_otwarte={unreal:+.2f} RAZEM={pnl + unreal:+.2f} USD")
    return positions, trades



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--explain", action="store_true", help="pokaz powody odrzucania rynkow")
    ap.add_argument("--pre-hours", type=float, default=None,
                    help="nadpisz PRE_GAME_WINDOW_H na ten przebieg (np. 24 do testu)")
    ap.add_argument("--by-tag", action="store_true", help="backtest: rozbicie wyniku per liga")
    ap.add_argument("--no-policy", action="store_true",
                    help="backtest bez filtra polityki (grupy/ligi) - do porownan")
    ap.add_argument("--bt-min-vol", type=float, default=None,
                    help="backtest: min. wolumen rynku (domyslnie 5000; 1000 = wiecej rynkow)")
    ap.add_argument("--assumed-spread", type=float, default=None,
                    help="nadpisz ASSUMED_SPREAD w backtescie (test wrazliwosci, np. 0.04)")
    ap.add_argument("--max-hours", type=float, default=None,
                    help="nadpisz MAX_HOURS_TO_RESOLVE na ten przebieg (test same-day)")
    ap.add_argument("--once", action="store_true", help="jeden przebieg: otworz pozycje i pokaz PnL")
    ap.add_argument("--report", action="store_true", help="raport otwartych pozycji + PnL (mark-to-market)")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--tags", default=",".join(TRADE_TAGS))
    ap.add_argument("--fetch-history", action="store_true", help="zbuduj bt_cache2.json z ostatnich N dni")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--max-markets", type=int, default=2000)
    args = ap.parse_args()
    tags = expand_tags(args.tags)
    if args.pre_hours:
        global PRE_GAME_WINDOW_H
        PRE_GAME_WINDOW_H = float(args.pre_hours)
        _is_pre_game.__defaults__ = (PRE_GAME_WINDOW_H,)
        print(f"[test] okno pre-game = {PRE_GAME_WINDOW_H} h")
    if args.no_policy:
        global BT_USE_POLICY
        BT_USE_POLICY = False
        print("[test] backtest BEZ filtra polityki")
    if args.bt_min_vol is not None:
        global BT_MIN_VOL
        BT_MIN_VOL = float(args.bt_min_vol)
    if args.by_tag:
        global BT_BY_TAG
        BT_BY_TAG = True
    if args.assumed_spread:
        global ASSUMED_SPREAD
        ASSUMED_SPREAD = float(args.assumed_spread)
        print(f"[test] ASSUMED_SPREAD = {ASSUMED_SPREAD}")
    if args.max_hours:
        global MAX_HOURS_TO_RESOLVE
        MAX_HOURS_TO_RESOLVE = float(args.max_hours)
        print(f"[test] MAX_HOURS_TO_RESOLVE = {MAX_HOURS_TO_RESOLVE} h")
    if args.fetch_history:
        build_bt_cache(tags, days=args.days, max_markets=args.max_markets)
    elif args.backtest:
        run_backtest()
    elif args.scan:
        run_scan(tags)
    elif args.explain:
        run_explain(tags)
    elif args.once:
        run_once(tags, dry=not args.live)
    elif args.report:
        run_report(dry=not args.live)
    elif args.dry:
        run_loop(tags, dry=True)
    elif args.live:
        run_loop(tags, dry=False)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
