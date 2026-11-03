#!/usr/bin/env python3
"""
NAJR LIVE (wariant ANTI_UP_TP80, id 31; start: python najr_live.py --live) - pochodna NAJR DRY (2 warianty stawki: UP = stawka tylko rosnie (nie spada nawet gdy bankroll spada), UD = stawka rosnie I maleje z bankrollem; krok domyslnie +2% stawki / +2% bankrolla (NAJR_STEP), wyjscia TP80 i HOLD (NAJR_EXIT); bankroll 20$ stawka 1$, max 7 otwartych na wariant. LIVE: stawka rosnie rownomiernie z bankrollem, bez resetu i bez spadku. Pochodna: KAPSKO LIVE (F_TP80, schemat X2) - PATCH z kapsko.py: odblokowany --live, tylko wariant 64, stawka X2 z realnego bankrolla.
Zmienne: PM_PRIVATE_KEY, PM_FUNDER, PM_SIG_TYPE. Start: python kapsko_live.py --live --bankroll 12

--- oryginał ---
KAPSKO (TYLKO DRY-RUN) - odwrócony Jasiuplacek, TWAP60 WYŁĄCZONY (sygnał tylko z Binance),
z rosnącą stawką (compounding schodkowy) i dwoma trybami wejścia po take-profit. Okna 5m + 15m.
Ten sam sygnał co BIN (model, progi), ale kupuje PRZECIWNĄ stronę. Każdy wariant ma własny portfel $11 i stawkę startową $1.
49 wariantów równolegle (7 schematów stawki x TP40/50/60/70/80/90/HOLD, $11 i start $1.10) (nazwa = SCHEMAT_WYJŚCIE_TRYB):
  Schemat stawki (po każdym kroku wzrostu ZREALIZOWANEGO bankrolla stawka rośnie o procent, mnożnikowo):
    A = stawka +1%  co każde +3%  bankrolla      B = +5% co +10%      C = +10% co +20%
    (bankroll = $11 + zrealizowany PnL; stawka nie spada poniżej $1; liczone od bankrolla startowego $11)
  Wyjście:  TP60 / TP90 = sprzedaż gdy bid >= 60c / 90c (wejście tylko do TP-3c);   HOLD = do rozliczenia rynku
  Tryb (tylko TP):  RE = po TP może wejść PONOWNIE w ten sam rynek (ta sama strona, po 10 s, limit --max-reentry)
                    1X = tylko JEDNO wejście na rynek, po TP czeka do następnego okna (nowego interwału)
  A_TP60_RE A_TP60_1X A_TP90_RE A_TP90_1X A_HOLD   (to samo dla B i C)  = 15 wariantów, id 31-45
Prawdziwych zleceń ta wersja NIE wysyła.

  python kupsko.py                         # 49 wariantów, dry-run, BEZ TWAP
  python kupsko.py -s 17,31,32     # + oryginalny BIN do porównania
  python kupsko.py --max-reentry 3 # limit ponownych wejść na rynek w trybie RE (0 = bez limitu)
  python kupsko.py --stats         # pełny raport (bez sieci) + zapis tabeli CSV i wyjście
  python kupsko.py --reset         # statystyki od zera, salda wracają do $11
W trakcie pracy klawisze 1-9 przełączają strony: 1 panel, 2 wyniki, 3 ryzyko/serie/TP, 4 wejścia/koszty/MFE/MAE,
5 rozbicia (cena, strona, interwał, czas do końca), 6 aktywa, 7 segmenty, 8 stawka/re-wejścia, 9 ranking 15 wariantów;
n = następna strona, g = następna grupa wariantów (strony 2-8 pokazują 3 warianty: schematy A/B/C jednej konfiguracji).

--- oryginalny opis (JASIUPLACEK v8) ---
JASIUPLACEK (v8, dawniej CYCKI LIVE / Jaśkodwa) - bot pod krypto Up/Down 5m i 15m na Polymarket.
Gra WYŁĄCZNIE okna 5m i 15m (BTC ETH SOL XRP DOGE BNB HYPE). Poniżej historia wersji bazowego bota:
CYCKI LIVE - wielostrategiowy bot pod rynki krypto Up/Down na Polymarket
(BTC / ETH / SOL / XRP / DOGE / BNB / HYPE; BIN: krótkie rynki tylko po potwierdzeniu feedu rozliczeniowego)
oraz rynki finance/pogoda. Nie zakłada zysku; domyślnie pracuje w DRY-RUN.

POPRAWKI (v8 = jasiuplacek):
               * tylko 5m i 15m (strike / finance / pogoda / 1h / 4h / 1d wycięte z pętli = szybszy cykl, mniej zapytań)
               * ponad 2 nogi na rynek: obie strony (Up+Down) + DOKŁADANIE nóg (--max-legs, domyślnie 4):
                 nowa noga tej samej strony tylko gdy jest tańsza o --leg-step od poprzedniej (albo model wyraźnie
                 silniejszy), przy zachowanej przewadze, z limitem kosztu na rynek i rezerwą wolnych stawek
               * szybciej: orderbooki pobierane RÓWNOLEGLE (też do TP i znacznika -50%), rynki następnego okna
                 pobierane z wyprzedzeniem (wejścia od pierwszej sekundy), pomijanie zbędnych zapytań o orderbook
               * mało wolnych slotów w budżecie => wyższy próg przewagi (ostatnie miejsca tylko na lepsze sygnały)
               * tabela 5m vs 15m ze wszystkimi statystykami (na żywo + --report + plik jasiuplacek_report.txt)
               * domyślnie DRY-RUN (wcześniej --live było domyślnie włączone); dry: budżet 10$ jeśli nie podano --budget
POPRAWKI (v3): rynki krypto 5m/15m/4h są szukane przez /events?slug= (Gamma /markets?slug= zwraca im []),
finance bierze ceny z Yahoo Finance (Pyth Hermes od 31.07.2026 wymaga klucza API), Binance ma zapasowy host.
POPRAWKI (v7): * stawka 1.25$, bez limitu ekspozycji, statystyki od zera przy pierwszym starcie v7 (stary stan -> .v6.bak,
                 otwarte pozycje zostają pilnowane)
               * BIN/SNIPER grają teraz 1d Up/Down (zamknięcie świecy 1m Binance o 12:00 ET vs poprzedni dzień) oraz strike
                 "powyżej X" (dzienne: świeca 1m 12:00 ET, godzinowe: świeca 1h) - reguły zweryfikowane
               * 8 krypto: BTC ETH SOL XRP DOGE BNB HYPE ZEC; strike wykrywany automatycznie dla każdej monety
               * zmienność dopasowana do horyzontu (1m + 1h), ogon Studenta dla długich rynków, wyższy próg przewagi daleko od końca
               * finance: więcej tickerów (Brent, miedź, platyna, NFLX, AMD, AVGO, INTC, BABA, CRCL, Russell), horyzont 72 h
               * pogoda: więcej miast, horyzont 72 h
POPRAWKI (v6): * pogoda: P(Yes) z ensemble ECMWF metodą "kernel dressing" (każdy członek + rozmyty błąd zależny od
                 horyzontu) zamiast zliczania członków - koniec z fałszywymi ~1% na sąsiednich przedziałach;
                 środek rozkładu korygowany prognozą deterministyczną; Denver = stacja Buckley SFB (jak w regułach
                 rynku); rok z daty rynku (przełom grudzień/styczeń); dzienne maksima w cache (szybciej, mniej zapytań)
               * finance: ogon Studenta (5 st. swobody) zamiast rozkładu normalnego; zmienność = mieszanka całego dnia
                 i ostatnich 60 barów (liczona na sekundę, bez dziur); wiek ceny Yahoo zwiększa niepewność;
                 cena otwarcia Up/Down musi pochodzić z baru blisko startu rynku
               * BIN finance/pogoda: fair mieszany z ceną rynkową (--fin-mkt-w / --wx-mkt-w; 0 = czysty model)
POPRAWKI (v5): Binance pozostaje sygnałem wyprzedzającym, ale 5m/15m/4h wymagają świeżego
               Chainlink TWAP60 z publicznego RTDS; brak feedu lub brak ceny otwarcia = BRAK WEJŚCIA.
               Wyniki 5m/15m/4h są rozliczane wyłącznie po oficjalnym wyniku Gamma (nie po świecy Binance).
               Opłaty takera są liczone konserwatywnie wg wzoru feeRate * p * (1-p).
POPRAWKI (v4): * limit ekspozycji ZDJĘTY (--max-open domyślnie 0 = bez limitu; podanie wartości > 0 nadal go włącza)
               * bot importuje WSZYSTKIE otwarte pozycje z konta (Data API) - także te nie założone przez niego
                 (zlecenia ręczne, stare uruchomienia, skasowany stan): liczą się w "otw.", w ekspozycji i blokują
                 ponowne wejście w ten sam rynek; --no-import wyłącza
               * Yahoo: ponowienia + zapasowy curl + eskalowana pauza po 429 (zamiast stałych 90 s dla wszystkiego)
               * brak rynków 5m/15m/1h/4h (np. luka Polymarketu przy zmianie czasu w USA): --check pokazuje, kiedy
                 rynki wracają; bot nie zalewa Gamma zapytaniami (wykładniczy odstęp), sam wraca do gry
               * pogoda: P(Yes) z 51 członków ECMWF IFS ensemble; brak danych = brak zakładu;
                 próg BIN 15c + dodatkowy margines po shrink i opłacie
               * import pozycji: Data API bez progu 0.1 udziału; synchronizacja przywraca pozycje widoczne na koncie

TRYB DOMYŚLNY: DRY-RUN (te same ceny i orderbooki, zlecenia tylko symulowane).
Prawdziwe pieniądze dopiero z flagą --live.
Do RTDS wymagany jest pakiet: pip install websocket-client

Zasady bezpieczeństwa:
  * stała stawka 1.25$ na zakład (bez Kelly, bez mnożników), twardy limit --max-order
  * MAKS. JEDNA otwarta pozycja na (strategia, rynek) - blokada zakładana PRZED wysłaniem zlecenia
  * po rozliczeniu pozycji blokada znika i strategia może wejść ponownie
  * zlecenia FOK z limitem ceny: albo wypełni się cała stawka po cenie <= max strategii, albo nic
  * niejednoznaczny wynik zlecenia (timeout, 5xx) = pozycja "SPRAWDŹ" i blokada, ZERO ponowień
  * limit łącznej ekspozycji --max-open (domyślnie WYŁĄCZONY: 0 = bez limitu)

Zmienne środowiskowe (tylko --live):
  PM_PRIVATE_KEY   klucz prywatny portfela
  PM_FUNDER        adres portfela/proxy z którego płacisz (konta z Polymarket UI)
  PM_SIG_TYPE      typ podpisu (0 EOA, 1 POLY_PROXY, 2 GNOSIS_SAFE; domyślnie 3)

Użycie:
  python jasiuplacek.py --dry --budget 10 --stake 1   # dry-run: 10$ budżetu, 1$ na zakład (to samo co samo "python jasiuplacek.py")
  python jasiuplacek.py --report          # pełna tabela 5m vs 15m ze stanu (bot może działać w innym oknie)
  python jasiuplacek.py --check            # test: czy rynki 15m/1h/4h/1d są znajdowane (bez zleceń)
  python jasiuplacek.py --check --live     # j.w. + test logowania i salda
  python jasiuplacek.py                    # dry-run: domyślnie tylko SNIPER (3) + BIN (17)
  python jasiuplacek.py --live             # PRAWDZIWE zlecenia, SNIPER + BIN
  python jasiuplacek.py --all              # wszystkie strategie
  python jasiuplacek.py -s 17 --live       # wybrane strategie
  python jasiuplacek.py --radar            # dodatkowo tabela radaru rynków
  python jasiuplacek.py --bin-tp 0.85      # BIN: take-profit przy bid >= 85c (0 = wyłączony)
  python jasiuplacek.py --bin-max-rem 3600 # BIN: wejścia tylko w ostatniej godzinie okna
  python jasiuplacek.py --pos              # dodatkowo tabela wszystkich otwartych pozycji (bot + konto)
  python jasiuplacek.py --no-strike        # wyłącz rynki BTC „powyżej X”
  python jasiuplacek.py --strike-event bitcoin-above-on-november-3   # wskaż wydarzenie ręcznie (slug lub link)
  python jasiuplacek.py --edge-strike 0.15 --strike-cap 2 --strike-hours 24   # strike: przewaga BIN, limit pozycji na wydarzenie, jak daleko w przód
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import threading
from collections import deque
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests
from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ----------------------------- KONFIGURACJA ---------------------------------
CFG = {
    "stake": 1.0,           # stała kwota zakładu ($)
    "max_order": 1000000.0,        # twardy limit pojedynczego zlecenia ($) - zabezpieczenie
    "max_open": 0.0,         # limit łącznej ekspozycji w otwartych pozycjach ($); 0 = BEZ LIMITU
    "min_price": 0.03,       # nie kupuj taniej niż
    "shrink": 0.90,          # ściągnięcie p do 0.5 (grube ogony rozkładu)
    "loop_sleep": 1.0,       # sekundy między cyklami
    "fail_cooldown": 8,      # s przerwy na (strategia, rynek) po nieudanym FOK (było 20: częstsze próby)
    "bin_edge_5m": 0.05,     # BIN: minimalna przewaga na rynkach 5m (5c)
    "bin_edge_15m": 0.05,    # BIN: minimalna przewaga na rynkach 15m (5c)
    "bin_fair_min": 0.40,    # BIN: minimalne prawdopodobieństwo strony wg modelu (40%)
    "counter": True,         # kontra: pozycja <= -counter_at => przeciwna strona na drugim interwale (5m<->15m), potem na tym samym
    "counter_at": 0.10,      # od jakiej straty (ułamek kosztu, wg ceny mid) pozycja wywołuje kontrę
    "counter_min_rem": 30,   # kontra tylko gdy do końca okna docelowego zostało >= tyle sekund
    "btc_rule": "inverse",   # inverse: po wejściu BTC strona X, alty w tym oknie NIE mogą strony X; follow: odwrotnie; off: wyłączone
    "loss_block": 0.50,      # pozycja na oknie <= -50% blokuje inne wejścia w tę stronę w tym oknie, do czasu aż wyjdzie na plus (0 = off)
    "bin_max_rem": 0,        # BIN: wejścia tylko gdy do końca <= tyle sekund (0 = bez limitu) - dla 1h/4h/1d
    "bin_rem_5m": 0,       # BIN na 5m: wchodzi tylko w ostatnich 2 minutach
    "bin_rem_15m": 0,      # BIN na 15m: wchodzi tylko w ostatnich 5 minutach
    "fin": True,             # finance (akcje, indeksy, złoto, srebro, WTI, gaz) przez Yahoo Finance
    "wx": False,              # pogoda (najwyższa temperatura dnia) przez Open-Meteo
    "bin_edge_fin": 0.10,    # BIN: minimalna przewaga na finance (11c)
    "bin_edge_wx": 0.08,     # BIN: minimalna przewaga na pogodzie (12c; fair z ensemble, po zmieszaniu z rynkiem)
    "wx_mkt_w": 0.10,        # BIN pogoda: waga ceny rynkowej w fair (0 = czysty model)
    "fin_mkt_w": 0.0,       # BIN finance: j.w.
    "wx_det_w": 0.4,         # pogoda: jaka część różnicy (prognoza deterministyczna - średnia ensemble) przesuwa rozkład
    "wx_det_cap": 2.0,       # pogoda: maks. przesunięcie środka w °C (dla °F razy 1.8)
    "import": True,          # importuj otwarte pozycje z konta (Data API) - tylko --live
    "pos_sync": 60,          # co ile sekund odświeżać pozycje z konta
    "fin_scan": 72 * 3600,   # finance: rynki kończące się w ciągu tylu sekund
    "wx_scan": 72 * 3600,    # pogoda: j.w.

    "strike": True,          # rynki BTC "powyżej X" (Yes/No) włączone
    "bin_edge_strike": 0.15, # BIN: minimalna przewaga na rynkach strike (11c)
    "strike_horizon": 1800,  # strike: "blisko końca" = ostatnie tyle sekund (SNIPER gra tylko w ostatnich 10% tego,
                             # BIN gra cały czas: blisko końca co 3 s, dalej rzadziej)
    "strike_scan": 24 * 3600, # strike: bierz rynki kończące się w ciągu tylu sekund (BIN gra je od razu)
    "strike_far_every": 20,  # strike daleko od końca: BIN sprawdza dany rynek co tyle sekund
    "strike_far_budget": 6,   # strike daleko od końca: maks. tyle rynków na jeden cykl (limit zapytań)
    "strike_stop": 3,        # strike: stop wejść tyle sekund przed endDate rynku
    "strike_cap": 2,         # strike: maks. otwartych pozycji (strategia, wydarzenie) - strike'y są skorelowane
    "strike_zmin": 0.25,     # strike: pomijaj strike'i prawie "w pieniądzu" (BIN i tak wymaga fair >= 60%)
    "strike_zmax": 4.0,      # strike: pomijaj strike'i skrajnie daleko (ask ~ 99c, brak szansy na wejście)
    "strike_events": [],     # ręcznie wskazane sluggi wydarzeń (--strike-event)
    "bin_max_px_5m": 0.95,   # BIN na 5m: maks. cena ask wejścia (na pozostałych 0.95)
    "bin_max_px_4h": 0.95,   # BIN na 4h: maks. cena ask wejścia
    "bin_min_odds": 2.0,      # BIN: MIN. kurs dziesiętny wejścia (1.8 = cena max 55.5c); 1.0 = bez limitu od góry ceny
    "bin_max_odds": 33.0,     # BIN: maks. kurs dziesiętny (1/cena); 4.0 = nie kupuje taniej niż 25c
    "twap_cut_5m": 60,       # 5m: stop wejść tyle sekund przed końcem
    "twap_cut_15m": 60,      # 15m: stop wejść tyle sekund przed końcem (reszta okien TWAP: 60)
    "bin_edge_1d": 0.10,     # BIN: minimalna przewaga na 1d Up/Down
    "long_mkt_w": 0.0,      # BIN 1d/strike dalej niż godzina od końca: waga ceny rynkowej w fair
    "far_rem": 6 * 3600,     # 1d/strike dalej niż tyle sekund od końca: wymagana większa przewaga
    "far_add": 0.0,         # ... o tyle więcej
    "pair_max": 0.96,        # druga noga tylko gdy suma cen obu nóg (za udział) <= tyle (SNIPER i inne: bez zmian)
    "bin_pair_max": 9.0,     # TYLKO BIN: limit sumy cen obu nóg (9.0 = bez limitu; stare zachowanie 0.96)
    "bin_pair_match": False, # TYLKO BIN: False = druga noga zwykła stała stawka; True = tyle samo udziałów co pierwsza
    "auto_pair": True,       # BIN: gdy jedna noga otwarta, a druga strona ma kurs >= auto_pair_odds -> kup drugą automatycznie (bez sygnału)
    "auto_pair_odds": 2.0,   # min. kurs drugiej nogi w auto-parze (2.0 = cena ask <= 50c)
    "auto_min_profit": 0.02, # auto-para tylko gdy pewny zysk (po opłatach) >= tyle $ niezależnie od wyniku rynku
    "short_only": True,      # nowe wejścia TYLKO na rynkach 5m/15m (--all-markets wyłącza ten filtr)
    "bin_second_gap": 2,     # TYLKO BIN: s między sprawdzeniami sygnału drugiej nogi (inne strategie: 10)
    "both_sides": True,      # strategia może wejść w OBIE strony tego samego rynku (każda strona max raz, każda musi spełnić swój próg)
    "state_file": "kapsko_state.json",
    "anti_max_px": 0.90,     # ANTI: nie kupuj odwrotnej strony drożej niż (ask)
    # --- v8 (jasiuplacek) ---
    "eval_gap": 2,           # s między ocenami sygnału na (strategia, rynek)
    "max_legs": 4,           # maks. nóg BIN na jeden rynek (okno): obie strony + dokładanie (2 = jak dawniej, tylko Up+Down)
    "leg_gap": 15,           # dokładanie: min. sekund od poprzedniej nogi tej samej strony
    "leg_step": 0.03,        # dokładanie: nowa noga tańsza o tyle od poprzedniej tej strony...
    "leg_dp": 0.06,          # ...albo p modelu wyższe o tyle (wtedy cena może być wyższa, ale edge nadal musi się zgadzać)
    "leg_min_rem": 75,       # dokładanie tylko gdy do końca okna zostało >= tyle sekund
    "leg_cap_frac": 0.45,    # maks. koszt otwartych nóg na jednym rynku jako ułamek budżetu (min. 3 stawki)
    "leg_reserve": 2,        # dokładanie tylko gdy po zakupie zostają >= tyle wolnych stawek (miejsce na pierwsze nogi innych rynków)
    "slot_low": 3,           # mało wolnych slotów (saldo < tyle stawek) => wyższy próg przewagi...
    "slot_extra": 0.0,      # ...o tyle
    "book_ttl": 2.0,         # s ważności cache orderbooka
    "workers": 8,            # równoległe pobieranie orderbooków / rynków
    "prewarm_s": 20,         # na tyle sekund przed końcem okna pobieram rynki następnego
    "report_file": "najr_up_ud_report.txt",
    "csv_file": "najr_up_ud_tabela.csv",
    "reentry_max": 3,        # tryb RE: maks. ponownych wejść w ten sam rynek po TP (0 = bez limitu)
}
DRY_STATE = "najr_up_ud_state.json"
LIVE_STATE = "najr_live_state.json"
LIVE_ID = 31          # ANTI_UP_TP80 (przy NAJR_EXIT=TP80: 31 = UP, 32 = UD)
LIVE_CFG = {"bankroll": 0.0, "base": 1.0, "div": 1.0, "stop": 0.0, "max_stake": 1000.0, "max_pos": 7, "max_pos_fin": 7, "max_total": 7, "fin_on": False,
            "step_bank": 0.02, "step_stake": 0.02, "min_stake": 1.0}
WINDOWS = {"5m": {"period": 300}, "15m": {"period": 900}, "1h": {"period": 3600}, "4h": {"period": 14400}, "1d": {"period": 86400}}
ASSETS = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT", "XRP": "XRPUSDT", "DOGE": "DOGEUSDT", "BNB": "BNBUSDT",
          "HYPE": "HYPEUSDT", "ZEC": "ZECUSDT"}
NAMES = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "xrp", "DOGE": "dogecoin", "BNB": "bnb",
         "HYPE": "hyperliquid", "ZEC": "zcash"}
# coiny z rynkami tylko na części interwałów (dla pozostałych bot nawet nie pyta Polymarketu o sluga)
ONLY_TF = {"ZEC": ("1d",)}
STRIKE_PREFIX = tuple(n + "-" for n in NAMES.values()) + tuple(a.lower() + "-" for a in ASSETS)


def tf_ok(asset, tf):
    return tf in ONLY_TF.get(asset, WINDOWS)
MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]
ANTI_MARGIN = 0.03                            # wariant TP nie wchodzi, gdy ask > TP - 3c
# schemat: litera -> (krok bankrolla, krok stawki). Stawka = start * (1+krok_stawki)^floor(wzrost zrealizowanego bankrolla / krok_bankrolla)
NAJR_STEP = float(os.environ.get("NAJR_STEP", "0.02"))     # o ile % rosnie stawka na kazde +2% bankrolla (0.02 / 0.04 / 0.05)
NAJR_EXIT = [x.strip() for x in os.environ.get("NAJR_EXIT", "TP80,HOLD").upper().split(",") if x.strip()]    # TP40 TP50 TP60 TP70 TP80 TP90 HOLD (po przecinku)
LIVE_CFG["step_stake"] = NAJR_STEP
NAJR_STEP_BANK = float(os.environ.get("NAJR_STEP_BANK", "0.02"))   # krok bankrolla w schemacie stawki (0.01 = +1%)
STAKE_SCHEMES = {"UP": (NAJR_STEP_BANK, NAJR_STEP), "UD": (NAJR_STEP_BANK, NAJR_STEP)}   # UP: tylko w gore (zapamietuje szczyt), UD: w gore i w dol
SCHEME_LABEL = {k: f"+{round(v[1] * 100)}%/{round(v[0] * 100)}%" for k, v in STAKE_SCHEMES.items()}   # stawka / bankroll
# drabinka stawki (tylko DRY, --ladder): stawka rośnie I maleje z bankrollem + reset przy podwojeniu (12->24->48->96...)
#   poziom bazowy: 12$ -> start_stake (1.2$); potem baza = ref/div (24$->2$, 48$->4$, 96$->8$...)
#   w obrębie poziomu: stawka = baza * (1+step_stake)^k, k = floor(ln(bankroll/ref)/ln(1+step_bank)) (k może być ujemne)
LADDER = {"on": False, "start_stake": 1.0, "div": 20.0, "step_bank": 0.02, "step_stake": 0.02,
          "min_stake": 1.0, "max_stake": 1000.0, "reset_mult": 2.0,
          "down": False}      # down=False: stawka tylko rosnie w obrebie poziomu (po resecie baza 2$, 4$...), nie spada ponizej bazy; True = rosnie I maleje
VARIANTS, GROUPS = [], []
_vid = 31
for _ex, _tp in [x for x in (("TP40", 0.40), ("TP50", 0.50), ("TP60", 0.60), ("TP70", 0.70), ("TP80", 0.80), ("TP90", 0.90), ("HOLD", None)) if x[0] in NAJR_EXIT]:
    _ids = []
    for _sch in STAKE_SCHEMES:
        VARIANTS.append({"id": _vid, "name": f"ANTI_{_sch}_{_ex}", "scheme": _sch, "exit": _ex, "tp": _tp, "reentry": False})
        _ids.append(_vid)
        _vid += 1
    _title = (f"{_ex} jedno wejście na rynek") if _tp else "HOLD do rozliczenia"
    for _k in range(0, len(_ids), 3):                      # po 3 warianty na stronę (wąski ekran telefonu)
        GROUPS.append((f"{_title} [{'/'.join(x for x in list(STAKE_SCHEMES)[_k:_k + 3])}]", _ids[_k:_k + 3]))
ANTI_TP = {v["id"]: v["tp"] for v in VARIANTS if v["tp"]}      # id -> próg take-profit (cena bid)
ANTI_IDS = tuple(v["id"] for v in VARIANTS)
ONCE_IDS = {v["id"] for v in VARIANTS if not v["reentry"]}     # 1 pozycja na rynek NA ZAWSZE (także po TP / rozliczeniu)
REENTRY_IDS = {v["id"] for v in VARIANTS if v["reentry"]}      # po TP wolno wejść ponownie w ten sam rynek
STAKE_OF = {v["id"]: STAKE_SCHEMES[v["scheme"]] for v in VARIANTS}
VAR_BY_ID = {v["id"]: v for v in VARIANTS}
# LIVE gra JEDEN wariant wskazany nazwa (domyslnie ANTI_UP_HOLD = UP_HOLD z dry-runa). Zmiana: NAJR_LIVE=ANTI_UD_HOLD (stawka rosnie I maleje).
LIVE_VARIANT = os.environ.get("NAJR_LIVE", "ANTI_UP_HOLD").strip()
LIVE_ID = next((v["id"] for v in VARIANTS if v["name"] == LIVE_VARIANT), None)
DEFAULT_IDS = ANTI_IDS
ACTIVE_TFS = ("5m", "15m")   # jasiuplacek gra TYLKO te dwa interwały
LOCK = ("pending", "open", "check")   # statusy blokujące ponowne wejście (strategia, rynek)

GAMMA = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
BINANCE = "https://api.binance.com"
COINBASE = "https://api.coinbase.com/v2/prices/{}-USD/spot"
BINANCE_ALT = "https://data-api.binance.vision"      # ten sam publiczny API, zapasowy host (bez blokad regionalnych)
BN_HOSTS = [BINANCE, BINANCE_ALT]
YAHOO = ["https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"]
OPENMETEO = "https://api.open-meteo.com/v1/forecast"
OPENMETEO_ENSEMBLE = "https://ensemble-api.open-meteo.com/v1/ensemble"

# finance: q = fraza do wyszukiwarki Polymarketu, rx = jak rozpoznać rynek po treści pytania,
# y = symbol w Yahoo Finance (cena, zmienność, cena otwarcia)
def _stock(t, name):
    return dict(q=name, rx=r"\b(?:%s|%s)\b" % (name.lower(), t.lower()), y=t)


FIN = {
    "GOLD": dict(q="Gold", rx=r"\bgold\b", y="GC=F"),
    "SILVER": dict(q="Silver", rx=r"\bsilver\b", y="SI=F"),
    "BRENT": dict(q="Brent Crude Oil", rx=r"\bbrent\b", y="BZ=F"),
    "COPPER": dict(q="Copper", rx=r"\bcopper\b", y="HG=F"),
    "PLAT": dict(q="Platinum", rx=r"\bplatinum\b", y="PL=F"),
    "RUT": dict(q="Russell 2000", rx=r"russell|\brut\b", y="^RUT"),
    "WTI": dict(q="WTI Crude Oil", rx=r"\bwti\b|crude", y="CL=F"),
    "NATGAS": dict(q="Natural Gas", rx=r"natural gas|nat\.? ?gas", y="NG=F"),
    "SPX": dict(q="S&P 500", rx=r"s&p|\bspx\b|sp500", y="^GSPC"),
    "NDX": dict(q="Nasdaq 100", rx=r"nasdaq|\bndx\b|\bqqq\b", y="^NDX"),
    "DOW": dict(q="Dow Jones", rx=r"\bdow\b|\bdji\b", y="^DJI"),
    "TSLA": _stock("TSLA", "Tesla"), "COIN": _stock("COIN", "Coinbase"), "PLTR": _stock("PLTR", "Palantir"),
    "NVDA": _stock("NVDA", "Nvidia"), "AAPL": _stock("AAPL", "Apple"), "MSFT": _stock("MSFT", "Microsoft"),
    "AMZN": _stock("AMZN", "Amazon"), "GOOGL": _stock("GOOGL", "Google"), "META": _stock("META", "Meta"),
    "HOOD": _stock("HOOD", "Robinhood"), "MSTR": _stock("MSTR", "MicroStrategy"),
    "NFLX": _stock("NFLX", "Netflix"), "AMD": _stock("AMD", "AMD"), "AVGO": _stock("AVGO", "Broadcom"),
    "INTC": _stock("INTC", "Intel"), "BABA": _stock("BABA", "Alibaba"), "CRCL": _stock("CRCL", "Circle"),
}

# pogoda: miasto -> (lat, lon)
WX_CITIES = {
    "nyc": (40.78, -73.87), "new york city": (40.78, -73.87), "new york": (40.78, -73.87),
    "chicago": (41.98, -87.90), "miami": (25.79, -80.29), "los angeles": (33.94, -118.41),
    "dallas": (32.85, -96.85), "houston": (29.65, -95.28), "atlanta": (33.64, -84.43),
    "seattle": (47.45, -122.31), "denver": (39.70, -104.75), "san francisco": (37.62, -122.38),
    "austin": (30.19, -97.67), "boston": (42.36, -71.01), "washington": (38.85, -77.04),
    "phoenix": (33.43, -112.01), "philadelphia": (39.87, -75.24), "las vegas": (36.08, -115.15),
    "london": (51.50, 0.05), "paris": (48.97, 2.44), "madrid": (40.47, -3.56), "milan": (45.63, 8.72),
    "munich": (48.35, 11.79), "warsaw": (52.17, 20.97), "amsterdam": (52.31, 4.76), "moscow": (55.97, 37.41),
    "istanbul": (41.26, 28.74), "ankara": (40.12, 32.99), "tel aviv": (32.01, 34.89),
    "tokyo": (35.55, 139.78), "seoul": (37.46, 126.44), "beijing": (40.08, 116.58),
    "shanghai": (31.14, 121.80), "hong kong": (22.31, 113.91), "singapore": (1.36, 103.99),
    "taipei": (25.08, 121.23), "wellington": (-41.33, 174.81), "sydney": (-33.94, 151.17),
    "toronto": (43.68, -79.63), "mexico city": (19.44, -99.07), "sao paulo": (-23.43, -46.47),
    "buenos aires": (-34.82, -58.54), "lucknow": (26.76, 80.88), "jakarta": (-6.13, 106.66),
    "shenzhen": (22.64, 113.81), "chengdu": (30.58, 103.95), "wuhan": (30.78, 114.21),
    "chongqing": (29.72, 106.64), "panama city": (9.07, -79.38),
    "dubai": (25.25, 55.36), "doha": (25.27, 51.61), "riyadh": (24.96, 46.70), "mumbai": (19.09, 72.87),
    "delhi": (28.56, 77.10), "new delhi": (28.56, 77.10), "karachi": (24.91, 67.16), "bangkok": (13.69, 100.75),
    "kuala lumpur": (2.75, 101.71), "manila": (14.51, 121.02), "cairo": (30.12, 31.41),
    "johannesburg": (-26.14, 28.25), "cape town": (-33.97, 18.60), "lagos": (6.58, 3.32),
    "berlin": (52.36, 13.50), "rome": (41.80, 12.24), "vienna": (48.11, 16.57), "lisbon": (38.77, -9.13),
    "dublin": (53.42, -6.27), "zurich": (47.46, 8.55), "brussels": (50.90, 4.48), "prague": (50.10, 14.26),
    "athens": (37.94, 23.95), "copenhagen": (55.62, 12.65), "oslo": (60.19, 11.10), "stockholm": (59.65, 17.92),
    "helsinki": (60.32, 24.96), "kyiv": (50.34, 30.89), "bogota": (4.70, -74.15), "lima": (-12.02, -77.11),
    "santiago": (-33.39, -70.79), "rio de janeiro": (-22.81, -43.25), "montreal": (45.47, -73.74),
    "vancouver": (49.19, -123.18), "minneapolis": (44.88, -93.22), "detroit": (42.21, -83.35),
    "orlando": (28.43, -81.31), "san diego": (32.73, -117.19), "osaka": (34.43, 135.24),
}

# dodatkowe miasta (współrzędne głównych lotnisk) - rynek z miastem spoza listy jest pomijany, więc im więcej tym lepiej
_WX_EXTRA = {
    "guangzhou": (23.39, 113.30), "hangzhou": (30.23, 120.43), "nanjing": (31.74, 118.86), "qingdao": (36.27, 120.37),
    "tianjin": (39.12, 117.35), "xian": (34.44, 108.75), "xi'an": (34.44, 108.75), "kolkata": (22.65, 88.45),
    "bengaluru": (13.20, 77.71), "bangalore": (13.20, 77.71), "hyderabad": (17.24, 78.43), "chennai": (12.99, 80.17),
    "dhaka": (23.84, 90.40), "hanoi": (21.22, 105.81), "ho chi minh city": (10.82, 106.65), "lahore": (31.52, 74.40),
    "islamabad": (33.55, 72.83), "tehran": (35.69, 51.31), "baghdad": (33.26, 44.23), "jeddah": (21.68, 39.16),
    "kuwait city": (29.23, 47.97), "muscat": (23.59, 58.28), "abu dhabi": (24.43, 54.65), "amman": (31.72, 35.99),
    "beirut": (33.82, 35.49), "colombo": (7.18, 79.88), "kathmandu": (27.70, 85.36), "yangon": (16.91, 96.13),
    "phnom penh": (11.55, 104.84), "nairobi": (-1.32, 36.93), "accra": (5.61, -0.17), "casablanca": (33.37, -7.59),
    "algiers": (36.69, 3.22), "tunis": (36.85, 10.23), "addis ababa": (8.98, 38.80), "budapest": (47.44, 19.26),
    "bucharest": (44.57, 26.08), "sofia": (42.70, 23.41), "belgrade": (44.82, 20.31), "krakow": (50.08, 19.78),
    "barcelona": (41.30, 2.08), "lyon": (45.73, 5.08), "hamburg": (53.63, 9.99), "frankfurt": (50.03, 8.57),
    "manchester": (53.35, -2.27), "edinburgh": (55.95, -3.37), "reykjavik": (63.99, -22.62), "tallinn": (59.41, 24.83),
    "riga": (56.92, 23.97), "vilnius": (54.63, 25.28), "minsk": (53.88, 28.03), "st petersburg": (59.80, 30.26),
    "almaty": (43.35, 77.04), "tashkent": (41.26, 69.28), "baku": (40.47, 50.05), "tbilisi": (41.67, 44.95),
    "yerevan": (40.15, 44.40), "geneva": (46.24, 6.11), "naples": (40.88, 14.29), "venice": (45.50, 12.35),
    "seville": (37.42, -5.89), "valencia": (39.49, -0.48), "porto": (41.24, -8.68), "gothenburg": (57.66, 12.28),
    "bergen": (60.29, 5.22), "perth": (-31.94, 115.97), "melbourne": (-37.67, 144.84), "brisbane": (-27.38, 153.12),
    "auckland": (-37.01, 174.79), "honolulu": (21.32, -157.92), "anchorage": (61.17, -150.00),
    "kansas city": (39.30, -94.71), "st louis": (38.75, -90.37), "nashville": (36.12, -86.68),
    "new orleans": (29.99, -90.26), "tampa": (27.98, -82.53), "charlotte": (35.21, -80.94),
    "salt lake city": (40.79, -111.98), "portland": (45.59, -122.60), "sacramento": (38.70, -121.59),
    "baltimore": (39.18, -76.67), "pittsburgh": (40.49, -80.23), "cleveland": (41.41, -81.85),
    "cincinnati": (39.05, -84.66), "indianapolis": (39.72, -86.29), "columbus": (39.99, -82.89),
    "milwaukee": (42.95, -87.90), "albuquerque": (35.04, -106.61), "oklahoma city": (35.39, -97.60),
    "san antonio": (29.53, -98.47), "guadalajara": (20.52, -103.31), "monterrey": (25.78, -100.11),
    "havana": (22.99, -82.41), "caracas": (10.60, -66.99), "quito": (-0.14, -78.49), "montevideo": (-34.84, -56.03),
    "brasilia": (-15.87, -47.92), "medellin": (6.16, -75.42), "calgary": (51.11, -114.02), "ottawa": (45.32, -75.67),
    "edmonton": (53.31, -113.58), "winnipeg": (49.91, -97.24), "fukuoka": (33.59, 130.45), "nagoya": (34.86, 136.81),
    "sapporo": (42.78, 141.69), "busan": (35.18, 128.94), "washington dc": (38.85, -77.04), "washington, dc": (38.85, -77.04),
    "são paulo": (-23.43, -46.47),
}
for _k, _v in _WX_EXTRA.items():
    WX_CITIES.setdefault(_k, _v)

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json"})
console = Console()


# ------------------------------- NARZĘDZIA ----------------------------------
def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def t5_cdf(x):
    """Dystrybuanta rozkładu Studenta (5 st. swobody, skala 1) - postać zamknięta. Grubsze ogony niż normalny:
    ten sam z-score daje mniejszą pewność (z=2: 95% zamiast 97.7%; z=3: 98.5% zamiast 99.9%)."""
    th = math.atan(x / math.sqrt(5.0))
    s, c = math.sin(th), math.cos(th)
    return 0.5 + (th + s * c * (1.0 + 2.0 / 3.0 * c * c)) / math.pi


def bin_max_px(tf):
    return CFG["bin_max_px_5m"] if tf == "5m" else CFG["bin_max_px_4h"] if tf == "4h" else 0.95


def bin_cap(tf):
    """Maks. cena wejścia BIN: mniejsza z limitu ceny i 1 / minimalny kurs."""
    return min(bin_max_px(tf), 1.0 / max(1.0, CFG["bin_min_odds"]))


def twap_cut(tf):
    return CFG["twap_cut_15m"] if tf == "15m" else CFG["twap_cut_5m"] if tf == "5m" else 60


def cdf_for(tf, rem=0):
    """Rozkład ceny do prawdopodobieństwa: finance i długie rynki (1d, strike > 30 min) dostają ogon Studenta,
    krótkie krypto zostaje przy normalnym."""
    if tf in ("fin", "1d") or (tf == "strike" and rem > 1800):
        return t5_cdf
    return norm_cdf


# pogoda: odchylenie (°C) dokładane do każdego członka ensemble (ensemble IFS jest za wąski względem stacji)
WX_SIGMA_C = {1: 1.1, 2: 1.4, 3: 1.7}


def wx_sigma(days_ahead, unit, hour_now=None):
    """Rozmycie członka ensemble w jednostce rynku. Dziś: maleje wraz z upływem dnia (maksimum prawie znane)."""
    d = max(0, int(days_ahead))
    if d == 0:
        frac = 1.0 if hour_now is None else min(1.0, max(0.0, (17.0 - hour_now) / 10.0))
        s = 0.6 + 0.3 * frac
    else:
        s = WX_SIGMA_C[min(d, max(WX_SIGMA_C))]
    return s * (1.8 if unit == "F" else 1.0)


def wx_bucket_prob(maxes, sigma, lo, hi):
    """P(zaokrąglone maksimum dnia trafia w [lo, hi]) = średnia po członkach z P(lo-0.5 <= X < hi+0.5),
    X ~ N(maksimum członka, sigma^2). Przedziały otwarte (-inf / +inf) obsłużone."""
    sigma = max(float(sigma), 1e-6)
    a = lo - 0.5 if lo != -math.inf else None
    b = hi + 0.5 if hi != math.inf else None
    tot = 0.0
    for x in maxes:
        pa = norm_cdf((a - x) / sigma) if a is not None else 0.0
        pb = norm_cdf((b - x) / sigma) if b is not None else 1.0
        tot += pb - pa
    return tot / len(maxes)


def fin_vol(pairs):
    """Zmienność na sekundę z barów 1m [(czas, close)]: zrealizowana wariancja = suma r^2 / suma dt, mieszanka
    całego dnia i ostatnich 60 barów (sam krótki odcinek bywa przypadkowo spokojny). Przerwy > 5 min pomijane.
    None gdy za mało danych."""
    rs = []
    for i in range(1, len(pairs)):
        dt = pairs[i][0] - pairs[i - 1][0]
        a, b = pairs[i - 1][1], pairs[i][1]
        if 0 < dt <= 300 and a > 0 and b > 0:
            rs.append((math.log(b / a), dt))
    if len(rs) < 30:
        return None

    def var(x):
        return sum(r * r for r, _ in x) / sum(d for _, d in x)

    v = 0.5 * var(rs[-60:]) + 0.5 * var(rs)
    return math.sqrt(max(v, (2e-4) ** 2 / 60.0))


def jl(x):
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return []
    return x or []


def fee_rate_for(tf):
    """Konserwatywne stawki takera wg kategorii Polymarket (mogą się zmieniać per rynek)."""
    if tf in WINDOWS or tf == "strike":
        return 0.07       # crypto
    if tf == "fin":
        return 0.04       # finance
    if tf == "wx":
        return 0.05       # weather
    return 0.05           # other/general


def fee_per_share(price, tf=None):
    """Szacowana opłata USDC na udział: feeRate * p * (1-p)."""
    p = min(0.999999, max(0.000001, float(price)))
    return 0.25 * (p * (1.0 - p)) ** 2   # jak w starym bocie


def get_json(url, **kw):
    r = S.get(url, timeout=6, **kw)
    r.raise_for_status()
    return r.json()


_bn = {"i": 0}


def bn_get(path, **kw):
    """Binance z automatycznym przełączeniem na zapasowy host (data-api.binance.vision)."""
    hosts = [BN_HOSTS[_bn["i"]], BN_HOSTS[1 - _bn["i"]]]
    last = None
    for k, base in enumerate(hosts):
        try:
            d = get_json(base + path, **kw)
            if k == 1:
                _bn["i"] = 1 - _bn["i"]
            return d
        except Exception as e:
            last = e
    raise last


# Polymarket crypto 5m/15m/4h rozlicza przez Chainlink TWAP60 (stan reguł zweryfikowany 2026-11).
# Binance nadal jest sygnałem szybszym: różnica Binance-Chainlink koryguje bieżącą wartość TWAP.
ORACLE_TFS = {"5m", "15m", "4h"}   # wymóg Chainlink TWAP60 włączony
ORACLE_SYMBOLS = {"BTC": "btc/usd", "ETH": "eth/usd", "SOL": "sol/usd", "XRP": "xrp/usd",
                  "DOGE": "doge/usd", "BNB": "bnb/usd", "HYPE": "hype/usd"}   # brak feedu w RTDS = brak wejścia (fail-closed)
ORACLE_ASSETS = {v: k for k, v in ORACLE_SYMBOLS.items()}


class OracleRTDS:
    """Bezkluczowy RTDS Polymarket: Chainlink spot + Chainlink TWAP60.

    Cena jest używana wyłącznie wtedy, gdy feed jest świeży, rynek opisuje Chainlink/TWAP,
    a bot ma zachowaną próbkę TWAP z sekundy otwarcia. Brak danych nigdy nie przełącza
    strategii po cichu z powrotem na Binance.
    """
    URL = "wss://ws-live-data.polymarket.com"

    def __init__(self):
        self.lock = threading.Lock()
        self.data = {a: {"chainlink": deque(maxlen=20000), "twap60": deque(maxlen=20000)}
                     for a in ORACLE_SYMBOLS}
        self.connected = False
        self.last_msg = 0.0
        self.error = ""
        self.ws = None
        self.thread = threading.Thread(target=self._worker, name="polymarket-rtds", daemon=True)
        self.thread.start()

    def _on_open(self, ws):
        for symbol in ORACLE_SYMBOLS.values():     # osobna subskrypcja na symbol: nieobsługiwany nie psuje reszty
            filt = json.dumps({"symbol": symbol}, separators=(",", ":"))
            subs = [{"topic": "crypto_prices_chainlink", "type": "update", "filters": filt},
                    {"topic": "crypto_prices_twap_sixty", "type": "update", "filters": filt}]
            ws.send(json.dumps({"action": "subscribe", "subscriptions": subs}, separators=(",", ":")))
        self.connected = True
        self.error = ""

    def _on_message(self, ws, raw):
        try:
            msg = json.loads(raw)
            topic = str(msg.get("topic") or "")
            payload = msg.get("payload") or {}
            stream = "twap60" if topic == "crypto_prices_twap_sixty" else                      "chainlink" if topic == "crypto_prices_chainlink" else None
            if not stream:
                return
            symbol = str(payload.get("symbol") or "").lower()
            asset = ORACLE_ASSETS.get(symbol)
            if not asset:
                return
            # RTDS payloads use observed_at (ms); some gateways expose timestamp.
            ts = float(payload.get("observed_at") or payload.get("timestamp") or
                       msg.get("timestamp") or payload.get("published_at") or 0)
            if ts > 1e12:
                ts /= 1000.0
            if ts <= 0:
                return
            value = payload.get("value")
            if value is None:
                raw_e18 = payload.get("full_accuracy_value")
                if raw_e18 is None:
                    return
                value = float(raw_e18) / 1e18
            value = float(value)
            if not math.isfinite(value) or value <= 0:
                return
            received = time.time()
            with self.lock:
                q = self.data[asset][stream]
                if not q or ts >= q[-1][0]:
                    q.append((ts, value, received))
                self.last_msg = received
        except Exception:
            return

    def _on_error(self, ws, err):
        self.error = f"{type(err).__name__}: {str(err)[:60]}"

    def _on_close(self, ws, code, reason):
        self.connected = False

    def _worker(self):
        try:
            import websocket
        except Exception as e:
            self.error = "brak websocket-client (pip install websocket-client)"
            return
        while True:
            try:
                self.ws = websocket.WebSocketApp(
                    self.URL, on_open=self._on_open, on_message=self._on_message,
                    on_error=self._on_error, on_close=self._on_close)
                self.ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception as e:
                self.error = f"{type(e).__name__}: {str(e)[:60]}"
            self.connected = False
            time.sleep(3)

    def latest(self, asset, stream, now=None, max_age=5):
        now = time.time() if now is None else now
        with self.lock:
            q = list(self.data.get(asset, {}).get(stream, ()))
        for row in reversed(q):
            if now - row[0] <= max_age and now - row[2] <= max_age:
                return row
        return None

    def at_or_before(self, asset, stream, ts, max_gap=2):
        with self.lock:
            q = list(self.data.get(asset, {}).get(stream, ()))
        for row in reversed(q):
            if row[0] <= ts and ts - row[0] <= max_gap:
                return row
        return None

    def status(self):
        if self.last_msg and time.time() - self.last_msg <= 8:
            return "OK"
        return "BRAK" if self.error else "OCZEKIWANIE"


YAHOO_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36")


def _yahoo_curl(url, params):
    """Zapasowa ścieżka: systemowy curl (inny odcisk TLS niż requests - Yahoo bywa łaskawszy). Podnosi wyjątek."""
    if not shutil.which("curl"):
        raise RuntimeError("brak curl")
    full = url + "?" + "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    out = subprocess.run(["curl", "-s", "-m", "8", "-A", YAHOO_UA, "-H", "Accept: application/json", full],
                         capture_output=True, text=True, timeout=12)
    try:
        return json.loads(out.stdout)["chart"]["result"][0]
    except Exception:
        raise RuntimeError(f"curl: {(out.stdout or out.stderr)[:40]!r}")


def yahoo(sym, **params):
    """Wykres Yahoo Finance dla symbolu -> słownik 'result' (meta + timestamp + indicators).
    Kolejno: oba hosty przez requests, potem curl. Przy porażce podnosi PIERWSZY błąd HTTP (żeby było widać 429)."""
    first = None
    path = f"/v8/finance/chart/{quote(sym, safe='')}"
    for host in YAHOO:
        try:
            r = S.get(host + path, params=params, timeout=8, headers={"User-Agent": YAHOO_UA})
            r.raise_for_status()
            return r.json()["chart"]["result"][0]
        except Exception as e:
            first = first or e
    try:
        return _yahoo_curl(YAHOO[0] + path, params)
    except Exception:
        pass
    raise first


def yahoo_series(res):
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    return ts, q.get("open") or [], q.get("close") or []


def other(side):
    return "Down" if side == "Up" else "Up"


def norm_side(outcome):
    """Wynik z Polymarketu -> strona bota: Yes=Up, No=Down, inne (Up/Down/nazwy) bez zmian."""
    o = str(outcome or "").strip()
    return "Up" if o.lower() in ("up", "yes") else "Down" if o.lower() in ("down", "no") else o


def trade_side(t):
    return t.get("outcome") or side_label(t["tf"], t["side"])


def infer_tf(slug):
    s = slug.lower()
    m = re.search(r"-updown-(5m|15m|1h|4h|1d)-", s)
    if m:
        return m.group(1)
    if "highest-temperature" in s:
        return "wx"
    if "-above-" in s:
        return "strike" if s.startswith(STRIKE_PREFIX) else "fin"
    if "up-or-down" in s:
        return "1h" if re.search(r"-\d{1,2}(am|pm)-et$", s) else "1d"
    return "ext"


def infer_asset(slug, tf):
    s = slug.lower()
    if tf == "wx":
        m = re.search(r"highest-temperature-in-(.+?)-on-", s)
        return m.group(1).replace("-", " ").title() if m else "EXT"
    for a, n in NAMES.items():
        if s.startswith(n + "-") or s.startswith(a.lower() + "-"):
            return a
    return "EXT"


def fetch_positions(addr):
    """Wszystkie pozycje konta z Data API (publiczne, bez logowania). Podnosi wyjątek przy błędzie."""
    out = []
    for off in range(0, 2000, 500):
        data = get_json(DATA_API + "/positions",
                        params={"user": addr, "sizeThreshold": 0, "limit": 500, "offset": off})
        if not isinstance(data, list):
            raise ValueError(f"nieoczekiwana odpowiedź: {str(data)[:60]}")
        out += data
        if len(data) < 500:
            break
    return out


def parse_ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def et_offset(ts):
    """Sekundy do DODANIA do UTC, żeby dostać czas Nowego Jorku (reguła DST USA)."""
    y = time.gmtime(ts).tm_year

    def nth_sunday(month, n):
        d = datetime(y, month, 1, tzinfo=timezone.utc)
        return d + timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))

    start = nth_sunday(3, 2).replace(hour=7).timestamp()    # 2:00 EST
    end = nth_sunday(11, 1).replace(hour=6).timestamp()     # 2:00 EDT
    return -4 * 3600 if start <= ts < end else -5 * 3600


def slug_candidates(asset, tf, now):
    """Możliwe slugi aktualnego okna. Właściwy wybiera się po endDate z Gamma (patrz Bot.window)."""
    per = WINDOWS[tf]["period"]
    a, name = asset.lower(), NAMES[asset]
    off = et_offset(now)
    out = []
    if tf in ("5m", "15m"):
        out.append(f"{a}-updown-{tf}-{int(now // per * per)}")
    elif tf == "1h":
        out.append(f"{a}-updown-1h-{int(now // per * per)}")
        et = datetime.fromtimestamp(now + off, tz=timezone.utc)
        out.append(f"{name}-up-or-down-{MONTHS[et.month - 1]}-{et.day}-{et.year}-"
                   f"{et.hour % 12 or 12}{'am' if et.hour < 12 else 'pm'}-et")
    elif tf == "4h":
        for o in (0, 3600):   # okna wyrównane do północy ET: przesunięcie zależy od DST
            out.append(f"{a}-updown-4h-{int((now - o) // per * per + o)}")
    elif tf == "1d":
        for dd in (0, 1):
            et = datetime.fromtimestamp(now + off + dd * 86400, tz=timezone.utc)
            out.append(f"{name}-up-or-down-on-{MONTHS[et.month - 1]}-{et.day}-{et.year}")
        out.append(f"{a}-updown-1d-{int(now // per * per)}")
    return out


# ----------------------- RYNKI "BTC POWYŻEJ X" (STRIKE) ----------------------
ALIAS = {"up": ("yes",), "down": ("no",)}   # rynki strike: Up = "powyżej" = Yes, Down = No
STRIKE_RE = re.compile(r"above\s*\$?\s*(\d[\d,]*(?:\.\d+)?)\s*(k\b)?", re.I)


def side_matches(outcome, side):
    o, sd = str(outcome).lower(), side.lower()
    return o.startswith(sd) or o in ALIAS.get(sd, ())


def mkt_label(t):
    """Krótka etykieta rynku do logów i tabel (dla strike: BTC>80k)."""
    if t.get("label"):
        return t["label"]
    if t.get("tf") == "strike":
        k = t.get("strike") or 0
        a = t.get("asset") or "BTC"
        return f"{a}>{k / 1000:g}k" if k >= 1000 else f"{a}>{k:g}"
    return "%s %s" % (t["asset"], t["tf"])


def side_label(tf, side):
    return ("Yes" if side == "Up" else "No") if tf in ("strike", "wx") else side


def clean_event_arg(x):
    """Link albo slug wydarzenia z Polymarketu -> sam slug."""
    x = x.strip().split("?")[0].rstrip("/")
    if "/event/" in x:
        x = x.split("/event/", 1)[1].split("/")[0]
    return x


STRIKE_NAMES = dict(NAMES)
STRIKE_ASSETS = {"BTC": ("bitcoin", "btc"), "ETH": ("ethereum", "eth"), "SOL": ("solana", "sol"), "XRP": ("xrp",),
                 "DOGE": ("dogecoin", "doge"), "BNB": ("bnb",), "HYPE": ("hyperliquid", "hype"), "ZEC": ("zcash", "zec")}


def strike_event_slugs(now):
    """Możliwe sluggi wydarzeń '<coin> above ...' (godzinowe: 4 najbliższe pełne godziny, dzienne: dziś i jutro ET)."""
    out = []
    base = int(now // 3600 * 3600)
    off = et_offset(now)
    for name in STRIKE_NAMES.values():
        for k in (1, 2, 3, 4):
            T = base + 3600 * k
            et = datetime.fromtimestamp(T + et_offset(T), tz=timezone.utc)
            h = f"{et.hour % 12 or 12}{'am' if et.hour < 12 else 'pm'}"
            mo = MONTHS[et.month - 1]
            out.append(f"{name}-above-on-{mo}-{et.day}-{h}-et")
            out.append(f"{name}-above-on-{mo}-{et.day}-{et.year}-{h}-et")
        for dd in (0, 1):
            et = datetime.fromtimestamp(now + off + dd * 86400, tz=timezone.utc)
            mo = MONTHS[et.month - 1]
            out.append(f"{name}-above-on-{mo}-{et.day}")
            out.append(f"{name}-above-on-{mo}-{et.day}-{et.year}")
    return out


def strike_hourly(m):
    """Strike godzinowy ('... on April 26, 11PM ET?') rozlicza zamknięcie świecy 1h kończącej się o T (rem = do T);
    dzienny rozlicza świeca 1m o 12:00 ET (zamyka się minutę po endDate)."""
    txt = f"{m.get('question') or ''} {m.get('slug') or ''}".lower().replace("-", " ")
    return bool(re.search(r"\b\d{1,2}\s?(?:am|pm)\s+et\b", txt))


def strike_info(m):
    """Rynek '<coin> above X' (Yes/No) -> (coin, strike, endDate jako timestamp) albo None."""
    q = str(m.get("question") or "")
    slug = str(m.get("slug") or "")
    txt = f"{q} {slug}".lower()
    if "above" not in txt:
        return None
    asset = None
    for a_, names in STRIKE_ASSETS.items():
        if re.search(r"\b(?:%s)\b" % "|".join(names), txt):
            asset = a_
            break
    if not asset:
        return None
    if any(w in txt for w in ("up or down", "updown", "up-or-down", "reach", "dip", "below", "between")):
        return None
    if m.get("closed") or m.get("acceptingOrders") is False:
        return None
    if sorted(str(o).lower() for o in jl(m.get("outcomes"))) != ["no", "yes"] or len(jl(m.get("clobTokenIds"))) != 2:
        return None
    val = None
    mt = STRIKE_RE.search(q)
    if mt:
        val = float(mt.group(1).replace(",", "")) * (1000 if mt.group(2) else 1)
    else:
        ms = re.search(r"above-(\d+)", slug)
        if ms:
            val = float(ms.group(1))
    end = parse_ts(m.get("endDate"))
    if not val or not end or not (0 < val <= 10_000_000):
        return None
    return asset, val, end


# ----------------------- FINANCE (Pyth) i POGODA: rozpoznawanie rynków -------
def fin_classify(m, ev, now):
    """Rynek finance z wyszukiwarki -> dict albo None. Obsługa: 'close above X' (Yes/No) i dzienne Up/Down."""
    if m.get("closed") or m.get("acceptingOrders") is False:
        return None
    q = str(m.get("question") or "")
    slug = str(m.get("slug") or "")
    txt = f"{q} {slug} {(ev or {}).get('title', '')}".lower().replace("-", " ")
    if any(w in txt for w in ("bitcoin", "ethereum", "solana", "xrp", "dogecoin", "hyperliquid", "zcash", "bnb", "between", "bracket", "range", "highest temperature")):
        return None
    label = next((lb for lb, sp in FIN.items() if re.search(sp["rx"], txt)), None)
    if not label:
        return None
    end = parse_ts(m.get("endDate"))
    if not end or not (now + 20 < end <= now + CFG["fin_scan"]):
        return None
    outs = sorted(str(o).lower() for o in jl(m.get("outcomes")))
    if len(jl(m.get("clobTokenIds"))) != 2:
        return None
    try:
        px = [float(x) for x in jl(m.get("outcomePrices"))]
    except Exception:
        px = []
    if outs == ["no", "yes"]:
        mt = re.search(r"above\s*\$?\s*(\d[\d,]*(?:\.\d+)?)", q, re.I)
        if not mt or "close" not in txt:
            return None
        return {"slug": slug, "label": label, "kind": "above", "strike": float(mt.group(1).replace(",", "")),
                "end": end, "start": None, "px": px}
    if outs == ["down", "up"]:
        st = parse_ts(m.get("eventStartTime") or (ev or {}).get("startTime"))
        if not st or st >= end:
            return None
        return {"slug": slug, "label": label, "kind": "updown", "strike": None, "end": end, "start": st, "px": px}
    return None


def parse_wx(m, now):
    """Rynek 'Highest temperature in <miasto> ...' (jeden przedział, Yes/No) -> dict albo None."""
    q = str(m.get("question") or "").replace("º", "°").replace("˚", "°")
    if "highest temperature" not in q.lower():
        return None
    if m.get("closed") or m.get("acceptingOrders") is False:
        return None
    if sorted(str(o).lower() for o in jl(m.get("outcomes"))) != ["no", "yes"] or len(jl(m.get("clobTokenIds"))) != 2:
        return None
    mc = re.search(r"highest temperature in (.+?)\s+(?:be|on|reach|exceed)\b", q, re.I)
    city = mc.group(1).strip().lower() if mc else None
    if not city or city not in WX_CITIES:
        return None
    end = parse_ts(m.get("endDate"))
    if not end or not (now + 30 < end <= now + CFG["wx_scan"]):
        return None
    md = re.search(r"\bon\s+([A-Za-z]+)\s+(\d{1,2})", q)
    if not md or md.group(1).lower() not in MONTHS:
        return None
    mon, day = MONTHS.index(md.group(1).lower()) + 1, int(md.group(2))
    y0, best_y = datetime.fromtimestamp(now, tz=timezone.utc).year, None
    for yy in (y0 - 1, y0, y0 + 1):      # rok, przy którym data leży najbliżej endDate (przełom grudzień/styczeń)
        try:
            dist = abs(datetime(yy, mon, day, 12, tzinfo=timezone.utc).timestamp() - end)
        except ValueError:
            continue
        if best_y is None or dist < best_y[0]:
            best_y = (dist, yy)
    if best_y is None:
        return None
    date = f"{best_y[1]}-{mon:02d}-{day:02d}"
    num = r"(-?\d+(?:\.\d+)?)"
    lo = hi = unit = None
    r1 = re.search(r"between\s+" + num + r"\s*(?:°\s*[FC])?\s*(?:-|–|and|to)\s*" + num + r"\s*°?\s*([FC])\b", q, re.I)
    r2 = re.search(num + r"\s*°\s*([FC])\s+or\s+(?:below|lower|less)", q, re.I)
    r3 = re.search(num + r"\s*°\s*([FC])\s+or\s+(?:higher|above|more|greater)", q, re.I)
    r4 = re.search(r"\bbe\s+" + num + r"\s*°\s*([FC])", q, re.I)
    if r1:
        lo, hi, unit, lab = float(r1.group(1)), float(r1.group(2)), r1.group(3).upper(), f"{r1.group(1)}-{r1.group(2)}"
    elif r2:
        lo, hi, unit, lab = -math.inf, float(r2.group(1)), r2.group(2).upper(), f"<={r2.group(1)}"
    elif r3:
        lo, hi, unit, lab = float(r3.group(1)), math.inf, r3.group(2).upper(), f">={r3.group(1)}"
    elif r4:
        lo = hi = float(r4.group(1))
        unit, lab = r4.group(2).upper(), r4.group(1)
    else:
        return None
    try:
        px = [float(x) for x in jl(m.get("outcomePrices"))]
    except Exception:
        px = []
    outs = [str(o).lower() for o in jl(m.get("outcomes"))]
    yes_px = px[outs.index("yes")] if len(px) == 2 and "yes" in outs else None
    return {"slug": str(m.get("slug") or ""), "city": city, "unit": unit, "lo": lo, "hi": hi, "date": date,
            "end": end, "yes_px": yes_px, "label": f"{city.title()[:9]} {lab}{unit}"}


# ------------------------------ STRATEGIE -----------------------------------
class Sig:
    """Sygnał wejścia zwracany przez strategię. (kelly/stake_mult ignorowane w wersji live)"""
    def __init__(self, side, max_price, min_edge=None, stake_mult=1.0, kelly=False):
        self.side, self.max_price, self.min_edge = side, max_price, min_edge
        self.stake_mult, self.kelly = stake_mult, kelly


STRATS = []


def strat(sid, name, desc, zone):
    """zone = (górna granica, dolna granica) pozostałego czasu jako ułamek okna."""
    def deco(fn):
        STRATS.append({"id": sid, "name": name, "desc": desc, "zone": zone, "fn": fn})
        return fn
    return deco


@strat(1, "LATE_EDGE", "Model vs ask: edge >= 5c, pewność >= 62%", (0.40, 0.03))
def s_late_edge(c):
    side, p = c.best()
    if p >= 0.62:
        return Sig(side, 0.93, min_edge=0.05)


@strat(2, "LATE_LITE", "Luźniejsza wersja: edge >= 2c, pewność >= 70%", (0.25, 0.03))
def s_late_lite(c):
    side, p = c.best()
    if p >= 0.70:
        return Sig(side, 0.95, min_edge=0.02)


@strat(3, "SNIPER", "Ostatnie sekundy, model >= 93%, kupuje niemal pewniaki", (0.10, 0.0))
def s_sniper(c):
    side, p = c.best()
    if p >= (0.90 if c.tf == "wx" else 0.93):   # pogoda: fair max 0.97, po shrink ~0.92
        return Sig(side, 0.97, min_edge=0.01)


@strat(4, "KELLY", "Jak LATE_EDGE z edge >= 4c (w live stawka stała, bez mnożnika Kelly)", (0.40, 0.03))
def s_kelly(c):
    side, p = c.best()
    if p >= 0.62:
        return Sig(side, 0.93, min_edge=0.04, kelly=True)


@strat(10, "ANTI_CHEAP", "ODWROTNOŚĆ CHEAP_VAL: gdy tania strona wygląda na okazję, kupujemy DROGĄ", (0.35, 0.06))
def s_cheap_inv(c):
    best = None
    for side in ("Up", "Down"):
        a = c.ask(side)
        if a and a <= 0.35:
            gap = c.p_of(side) - a
            if gap >= 0.12 and (best is None or gap > best[0]):
                best = (gap, side)
    if best:
        # oryginał kupował tanią stronę - my kupujemy przeciwną (faworyta)
        return Sig(other(best[1]), 0.90)


@strat(13, "BOOK_IMB", "Nierównowaga orderbooka (top 5 poziomów), zgodna z modelem", (0.50, 0.10))
def s_book_imb(c):
    imb = c.imbalance()
    if imb is None:
        return None
    side = "Up" if imb >= 0.68 else "Down" if imb <= 0.32 else None
    if side and c.p_of(side) >= 0.5:
        return Sig(side, 0.80)


@strat(14, "ANTI_LEAD", "ODWROTNOŚĆ BTC_LEAD: gdy alt 'ma dogonić' BTC, gramy przeciw", (0.60, 0.10))
def s_btc_lead_inv(c):
    if c.asset == "BTC":
        return None
    b = c.peers.get("BTC")
    zb = b.zmove(30) if b else None
    za = c.zmove(30)
    if zb is None or za is None or abs(zb) < 1.5:
        return None
    sgn = 1 if zb > 0 else -1
    if za * sgn < 0.5 * abs(zb):
        # oryginał kupował stronę zgodną z BTC - my kupujemy PRZECIWNĄ
        return Sig("Down" if sgn > 0 else "Up", 0.80)


@strat(15, "QUORUM", "Głosowanie: model, momentum, orderbook, faworyt - min. 3 z 4", (0.40, 0.08))
def s_quorum(c):
    votes = {"Up": 0, "Down": 0}
    side, p = c.best()
    if p >= 0.60:
        votes[side] += 1
    z = c.zmove(30)
    if z is not None and abs(z) >= 0.8:
        votes["Up" if z > 0 else "Down"] += 1
    imb = c.imbalance()
    if imb is not None and (imb >= 0.6 or imb <= 0.4):
        votes["Up" if imb >= 0.6 else "Down"] += 1
    au, ad = c.ask("Up"), c.ask("Down")
    if au and ad and abs(au - ad) >= 0.10:
        votes["Up" if au > ad else "Down"] += 1
    for sd, n in votes.items():
        if n >= 3:
            return Sig(sd, 0.88)


# BIN przeniesiona z Snajper.py: fair z ruchu Binance, wejście przy dużej przewadze po haircucie
BIN_HAIRCUT, BIN_MIN_EDGE = 0.03, 0.10


@strat(17, "BIN", "Binance lead + fair value; krótkie krypto tylko na potwierdzonym Chainlink TWAP60; 1d i strike po świecach Binance", (1.0, 0.0))
def s_bin(c):
    # Końcowy TWAP60 jest już częściowo zbudowany z przeszłych sekund; nie używamy tu modelu spot.
    if c.tf in ORACLE_TFS and c.rem <= twap_cut(c.tf):
        return None
    mx = (CFG["bin_rem_5m"] if c.tf == "5m" else CFG["bin_rem_15m"] if c.tf == "15m" else CFG["bin_max_rem"])
    if c.rem < 8 or (mx and c.rem > mx):
        return None
    fixed = getattr(c, "fair", None)       # pogoda: gotowe prawdopodobieństwo "Yes" z prognozy
    fair_up = fixed if fixed is not None else c.cdf(c.d / (c.sigma * math.sqrt(c.rem)))
    long_ = c.tf in ("1d", "strike") and c.rem > 3600
    w_mkt = (CFG["wx_mkt_w"] if c.tf == "wx" else CFG["fin_mkt_w"] if c.tf == "fin"
             else CFG["long_mkt_w"] if long_ else 0.0)
    need = (CFG["bin_edge_5m"] if c.tf == "5m"
            else CFG["bin_edge_15m"] if c.tf == "15m"
            else CFG["bin_edge_strike"] if c.tf == "strike"
            else CFG["bin_edge_1d"] if c.tf == "1d"
            else CFG["bin_edge_fin"] if c.tf == "fin"
            else CFG["bin_edge_wx"] if c.tf == "wx" else BIN_MIN_EDGE)
    if c.tf in ("1d", "strike") and c.rem > CFG["far_rem"]:
        need += CFG["far_add"]              # daleko od końca model jest mniej pewny
    if c.tf in ("5m", "15m") and CFG["slot_extra"] > 0:
        bal_ = c.bot.balance_now()
        if bal_ is not None and bal_ < CFG["slot_low"] * c.bot.stake:
            need += CFG["slot_extra"]       # mało wolnych slotów: ostatnie miejsca tylko na lepsze sygnały
    best = None
    for side, fair in (("Up", fair_up), ("Down", 1 - fair_up)):
        if fair < CFG["bin_fair_min"]:
            continue                    # bez zbędnego zapytania o orderbook (decyzja ta sama)
        a = c.ask(side)
        if not a or fair < CFG["bin_fair_min"] or a > bin_cap(c.tf) or a < 1.0 / CFG["bin_max_odds"]:
            continue
        if w_mkt > 0:                   # model bywa zbyt pewny siebie: mieszam z ceną rynkową (mid / ask)
            mk = c.mid(side)
            if mk is not None:
                fair = (1 - w_mkt) * fair + w_mkt * mk
        edge = fair - BIN_HAIRCUT - a
        if (c.tf in ("fin", "wx") or long_) and edge > 0.45:
            continue                    # za piękne, by było prawdziwe = zły feed/parsowanie - pomijam
        if edge >= need and (best is None or edge > best[0]):
            best = (edge, side, a)
    if best:
        return Sig(best[1], min(0.97, best[2] + 0.01, bin_cap(c.tf)), min_edge=0.07 + (need - BIN_MIN_EDGE))


def s_anti_bin(c):
    sg = s_bin(c)                       # ten sam sygnał, te same progi i ten sam model co BIN
    if sg is None:
        return None
    side = other(sg.side)               # BIN chciał sg.side - bierzemy drugą stronę
    a = c.ask(side)
    if not a or a > CFG["anti_max_px"]:
        return None
    return Sig(side, min(0.97, a + 0.01))   # bez min_edge: edge w statystykach wyjdzie ujemny (tak ma być)


def _anti_variant(v):
    sid, tp, reentry = v["id"], v["tp"], v["reentry"]
    if tp is None:
        desc = f"ANTI_BIN, stawka {SCHEME_LABEL[v['scheme']]}, bez TP: trzyma do rozliczenia"
    else:
        desc = (f"ANTI_BIN, stawka {SCHEME_LABEL[v['scheme']]}, TP przy bid >= {round(tp * 100)}c (wejście do "
                f"{round((tp - ANTI_MARGIN) * 100)}c), " + ("po TP wolno wejść ponownie w ten rynek" if reentry
                                                           else "jedno wejście na rynek"))

    @strat(sid, v["name"], desc, (1.0, 0.0))
    def _fn(c):
        sg = s_anti_bin(c)
        if sg is None:
            return None
        if tp is not None:
            a = c.ask(sg.side)
            if a is None or a > tp - ANTI_MARGIN + 1e-9:
                return None             # za blisko progu TP: spread + opłaty dałyby stratę
        if reentry:
            prev = getattr(c.bot, "slug_trades", {}).get((sid, c.slug))
            if prev:                    # były już wejścia w ten rynek (otwarta pozycja blokuje osobno)
                if CFG["reentry_max"] > 0 and len(prev) >= 1 + CFG["reentry_max"]:
                    return None
                if prev[-1]["side"] != sg.side:
                    return None         # re-wejście tylko w TĘ SAMĄ pozycję (stronę) co poprzednio
        return sg
    return _fn


for _v in VARIANTS:
    _anti_variant(_v)


# ------------------------------ KONTEKST RYNKU -------------------------------
class Ctx:
    def __init__(self, bot, asset, tf, per, ts, rem, spot, op, sigma, slug, end):
        self.bot, self.asset, self.tf, self.per, self.ts, self.end = bot, asset, tf, per, ts, end
        self.rem, self.elapsed = rem, per - rem
        self.slug = slug
        self.spot, self.open, self.sigma = spot, op, sigma
        self.d = math.log(spot / op)
        z = self.d / (sigma * math.sqrt(max(rem, 1)))
        self.cdf = cdf_for(tf, rem)
        self.p_up = 0.5 + (self.cdf(z) - 0.5) * CFG["shrink"]
        self.peers = {}
        self.event = ""     # strike: grupa rynków z tym samym końcem (limit wejść na wydarzenie)
        self.label, self.fair = "", None

    def p_of(self, side):
        return self.p_up if side == "Up" else 1 - self.p_up

    def best(self):
        return ("Up", self.p_up) if self.p_up >= 0.5 else ("Down", 1 - self.p_up)

    def zmove(self, secs):
        p0 = self.bot.price_ago(self.asset, secs)
        if not p0:
            return None
        return math.log(self.spot / p0) / (self.sigma * math.sqrt(secs))

    def zopen(self):
        return self.d / (self.sigma * math.sqrt(max(self.elapsed, 1)))

    def book(self, side):
        return self.bot.get_book(self, side)

    def ask(self, side):
        b = self.book(side)
        return b["asks"][0][0] if b and b["asks"] else None

    def mid(self, side):
        """Cena rynkowa strony: środek spreadu, gdy spread <= 15c; przy szerokim spreadzie / braku bidów sam ask."""
        b = self.book(side)
        if not b or not b["asks"]:
            return None
        a = b["asks"][0][0]
        if b["bids"] and a - b["bids"][0][0] <= 0.15:
            return (a + b["bids"][0][0]) / 2
        return a

    def imbalance(self):
        b = self.book("Up")
        if not b:
            return None
        bid = sum(s for _, s in b["bids"][:5])
        ask = sum(s for _, s in b["asks"][:5])
        return bid / (bid + ask) if bid + ask > 0 else None


# -------------------------------- BROKER ------------------------------------
class Broker:
    """Warstwa zleceń. Cała zależność od SDK Polymarket jest TUTAJ (łatwo podmienić na nowe SDK)."""

    def __init__(self, live):
        self.live = live
        self.client = None
        self.sdk = None
        self._bal = (0.0, None)
        if live:
            self._connect()

    def _connect(self):
        try:
            import py_clob_client_v2 as sdk
        except ImportError:
            sys.exit("Brak SDK. Zainstaluj: pip install py-clob-client-v2")
        pk = os.environ.get("PM_PRIVATE_KEY")
        if not pk:
            sys.exit("Ustaw zmienną środowiskową PM_PRIVATE_KEY.")
        kw = {"host": CLOB, "chain_id": 137, "key": pk}
        funder = os.environ.get("PM_FUNDER")
        if funder:
            kw["funder"] = funder
            kw["signature_type"] = int(os.environ.get("PM_SIG_TYPE", "3"))
        tmp = sdk.ClobClient(**kw)
        creds = None
        # najpierw POBIERZ istniejący klucz API (bez błędu 400 "Could not create api key"), dopiero potem utwórz
        derive = getattr(tmp, "derive_api_key", None) or getattr(tmp, "derive_api_creds", None)
        if derive:
            try:
                creds = derive()
                if not getattr(creds, "api_key", None) and not (isinstance(creds, dict) and creds.get("apiKey")):
                    creds = None
            except Exception:
                creds = None
        if creds is None:
            mk = getattr(tmp, "create_or_derive_api_key", None) or getattr(tmp, "create_or_derive_api_creds")
            creds = mk()
        self.client = sdk.ClobClient(**kw, creds=creds)
        self.sdk = sdk

    def address(self):
        """Adres portfela, na którym leżą pozycje (PM_FUNDER albo adres wyliczony z klucza)."""
        f = os.environ.get("PM_FUNDER")
        if f:
            return f.strip()
        try:
            return self.client.get_address()
        except Exception:
            pass
        try:
            from eth_account import Account
            return Account.from_key(os.environ["PM_PRIVATE_KEY"]).address
        except Exception:
            return None

    def balance(self):
        """Saldo kolaterału w $ (None gdy nieznane). Odświeżane co 60 s."""
        if not self.live:
            return None
        if time.time() - self._bal[0] < 60:
            return self._bal[1]
        val = None
        try:
            r = self.client.get_balance_allowance(
                self.sdk.BalanceAllowanceParams(asset_type=self.sdk.AssetType.COLLATERAL))
            val = float(r["balance"]) / 1e6
        except Exception:
            pass
        self._bal = (time.time(), val)
        return val

    def refresh_balance(self):
        self._bal = (0.0, self._bal[1])

    def buy(self, tok, usd, worst, m, sim):
        """Zlecenie FOK na `usd` dolarów, limit ceny `worst`.
        Zwraca {"status": "filled"|"rejected"|"unknown", ...}. Nigdy nie ponawia."""
        avg, shares, spent = sim
        if not self.live:
            return {"status": "filled", "spent": spent, "shares": shares, "id": "DRY", "est": True}
        sdk = self.sdk
        try:
            try:
                args = sdk.MarketOrderArgs(token_id=tok, amount=usd, side=sdk.Side.BUY,
                                           price=worst, order_type=sdk.OrderType.FOK)
            except TypeError:   # wersja SDK bez pola price - chroni nas wtedy sprawdzenie orderbooka
                args = sdk.MarketOrderArgs(token_id=tok, amount=usd, side=sdk.Side.BUY,
                                           order_type=sdk.OrderType.FOK)
            tick = m.get("orderPriceMinTickSize")
            opts = sdk.PartialCreateOrderOptions(tick_size=f"{float(tick):g}") if tick else None
            resp = self.client.create_and_post_market_order(
                order_args=args, options=opts, order_type=sdk.OrderType.FOK)
            if not isinstance(resp, dict):
                resp = dict(getattr(resp, "__dict__", {}) or {})
            status = str(resp.get("status", "")).lower()
            if resp.get("success") and status in ("matched", "filled"):
                mk, tk = float(resp.get("makingAmount") or 0), float(resp.get("takingAmount") or 0)
                est = not (mk > 0 and tk > 0)
                return {"status": "filled", "spent": spent if est else mk, "shares": shares if est else tk,
                        "id": resp.get("orderID", ""), "est": est}
            err = str(resp.get("errorMsg") or "")
            if resp.get("success") is False or err:
                return {"status": "rejected", "msg": err or status or "odrzucone"}
            return {"status": "unknown", "msg": f"status={status}", "id": resp.get("orderID", "")}
        except Exception as e:
            code = getattr(e, "status_code", None)
            msg = str(getattr(e, "error_msg", "") or e)[:80]
            if isinstance(code, int) and 400 <= code < 500:
                return {"status": "rejected", "msg": msg}
            return {"status": "unknown", "msg": f"{type(e).__name__}: {msg}"}

    def sell(self, tok, shares, minpx, m, sim_proceeds):
        """Sprzedaż `shares` udziałów FOK, nie taniej niż `minpx`. Nigdy nie ponawia."""
        if not self.live:
            return {"status": "filled", "proceeds": sim_proceeds, "id": "DRY"}
        sdk = self.sdk
        try:
            try:
                args = sdk.MarketOrderArgs(token_id=tok, amount=shares, side=sdk.Side.SELL,
                                           price=minpx, order_type=sdk.OrderType.FOK)
            except TypeError:
                args = sdk.MarketOrderArgs(token_id=tok, amount=shares, side=sdk.Side.SELL,
                                           order_type=sdk.OrderType.FOK)
            tick = m.get("orderPriceMinTickSize")
            opts = sdk.PartialCreateOrderOptions(tick_size=f"{float(tick):g}") if tick else None
            resp = self.client.create_and_post_market_order(
                order_args=args, options=opts, order_type=sdk.OrderType.FOK)
            if not isinstance(resp, dict):
                resp = dict(getattr(resp, "__dict__", {}) or {})
            status = str(resp.get("status", "")).lower()
            if resp.get("success") and status in ("matched", "filled"):
                got = float(resp.get("takingAmount") or 0)     # SELL: dostajemy USDC
                return {"status": "filled", "proceeds": got if got > 0 else sim_proceeds,
                        "id": resp.get("orderID", "")}
            err = str(resp.get("errorMsg") or "")
            if resp.get("success") is False or err:
                return {"status": "rejected", "msg": err or status or "odrzucone"}
            return {"status": "unknown", "msg": f"status={status}"}
        except Exception as e:
            code = getattr(e, "status_code", None)
            msg = str(getattr(e, "error_msg", "") or e)[:80]
            if isinstance(code, int) and 400 <= code < 500:
                return {"status": "rejected", "msg": msg}
            return {"status": "unknown", "msg": f"{type(e).__name__}: {msg}"}


# ----------------------- STATYSTYKI: NARZĘDZIA (ANTI) ------------------------
class _NullOracle:
    """Atrapa RTDS do trybu --stats (raport bez sieci)."""
    def status(self): return "-"
    def latest(self, *a, **k): return None
    def at_or_before(self, *a, **k): return None


def wilson(w, n, z=1.96):
    """95% przedział ufności Wilsona dla odsetka wygranych (w %)."""
    if n <= 0:
        return None, None
    p = w / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h) * 100, min(1.0, c + h) * 100


def fsecs(s):
    if s is None:
        return "-"
    s = int(round(s))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{s % 3600 // 60:02d}m"


def short_name(name):
    return name.replace("ANTI_", "")


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def N(v, f="{:.2f}", suf="", style=""):
    return Text("-", style="dim") if v is None else Text(f.format(v) + suf, style=style)


def SG(v, f="{:+.2f}", suf=""):
    return Text("-", style="dim") if v is None else Text(f.format(v) + suf, style="green" if v > 0 else "red" if v < 0 else "white")


# --------------------------------- BOT --------------------------------------
class Bot:
    def __init__(self, active_ids, stake, focus, broker, max_open):
        self.active = [s for s in STRATS if s["id"] in active_ids]
        self.active_ids = {s["id"] for s in self.active}
        self.stake, self.focus, self.broker, self.max_open = stake, focus, broker, max_open
        self.state = {"trades": [], "start": time.time()}
        if os.path.exists(CFG["state_file"]):
            try:
                with open(CFG["state_file"]) as f:
                    self.state = json.load(f)
            except Exception:
                pass
        if self.state.get("ver") != 7:          # v7: statystyki od zera (kopia starego stanu, otwarte pozycje zostają)
            try:
                if os.path.exists(CFG["state_file"]):
                    shutil.copy(CFG["state_file"], CFG["state_file"] + ".v6.bak")
            except Exception:
                pass
            keep = [t for t in self.state.get("trades", []) if t.get("status") in LOCK]
            self.state = {"trades": keep, "start": time.time(), "since": time.time(), "ver": 7}
        # statystyki liczą się od zapisanego momentu startu (przeżywają restart; --reset zeruje)
        self.since = self.state.get("since") or self.state.get("start") or time.time()
        self.state["since"] = self.since
        self.state.setdefault("start", self.since)
        for t in self.state["trades"]:        # zlecenie przerwane w trakcie -> do ręcznego sprawdzenia
            if t["status"] == "pending":
                t["status"] = "check"
        self.spot, self.open_px, self.sigma_c = {}, {}, {}
        self.market_c, self.book_c = {}, {}
        self.win_c, self.win_miss = {}, {}
        self.hist = {a: deque(maxlen=700) for a in ASSETS}
        self.last_eval, self.last_res_try = {}, {}
        self.cool, self.halt_until, self.fail_streak, self.last_warn = {}, 0.0, 0, {}
        self.radar, self.ask_seen = {}, {}
        self.show_radar = False
        self.sigma_hc, self.strike_scan_mk = {}, []
        self.ev_c, self.strike_cache = {}, []        # strike: cache wydarzeń i lista aktywnych rynków
        self.strike_next = self.strike_scan_next = 0.0
        self.far_t = {}                              # strike: kiedy ostatnio sprawdzono rynek daleko od końca
        self.side_locked = set()
        self.rule_diag = {"btc": 0, "loss": 0}
        self.t_start = time.time()
        self.sim_budget = None        # DRY: symulowany budżet w $
        self.cur_ctx = {}             # (asset, tf) -> Ctx z bieżącego cyklu
        self.n_counter = 0
        self.tw_diag = self.tw_last = {"ok": 0, "reguly": 0, "feed": 0, "otwarcie": 0}
        self.tp = {}          # id strategii -> próg take-profit (cena bid)
        self.api = {"binance": "?", "polymarket": "?"}
        self.oracle = OracleRTDS()
        self.fin_feeds, self.fin_px, self.fin_hist, self.fin_sig, self.fin_op = {}, {}, {}, {}, {}
        self.fin_cache, self.fin_next = [], 0.0
        self.wx_cache, self.wx_next, self.wx_fc_c = [], 0.0, {}
        self.wx_unknown = set()
        self.wx_ens_c, self.wx_dm_c = {}, {}
        self.log = []
        self.bn_bad, self.gamma_err = set(), None      # coiny bez pary na Binance, ostatni błąd Gamma
        self.fin_try, self.fin_block, self.fin_err, self.fin_op_try = {}, 0.0, {}, {}
        self.fin_429 = 0                               # kolejne 429 z Yahoo (eskalacja pauzy)
        self.pos_next, self.pos_info, self.pos_claim, self.pos_ok = 0.0, "-", 0, None   # import pozycji z konta
        self.show_pos = False
        self.full_view = False
        self.rep_next = 0.0
        self.pool = ThreadPoolExecutor(max_workers=CFG["workers"])
        self.page, self.dirty, self._tty = 1, False, None
        self.group = 0                 # aktualnie oglądana grupa wariantów (klawisz g)
        self.slug_trades = {}          # (id wariantu, slug) -> wejścia w bieżące / niedawne rynki

    # ---------- zapis / log ----------
    def save(self):
        try:
            with open(CFG["state_file"], "w") as f:
                json.dump(self.state, f)
        except Exception:
            pass

    def note(self, msg):
        self.log.append(f"{time.strftime('%H:%M:%S')} {msg}")
        self.log = self.log[-6:]

    def warn_once(self, key, msg, every=60):
        if time.time() - self.last_warn.get(key, 0) > every:
            self.last_warn[key] = time.time()
            self.note(msg)

    # ---------- ceny ----------
    def fetch_spot(self):
        got = {}
        good = [a for a in ASSETS if a not in self.bn_bad]
        try:
            syms = json.dumps([ASSETS[a] for a in good], separators=(",", ":"))
            data = bn_get("/api/v3/ticker/price", params={"symbols": syms})
            m = {d["symbol"]: float(d["price"]) for d in data}
            got = {a: m[ASSETS[a]] for a in good if ASSETS[a] in m}
        except Exception:
            for a in good:        # paczka padła (np. symbolu nie ma na Binance) - sprawdzam pojedynczo
                try:
                    got[a] = float(bn_get("/api/v3/ticker/price", params={"symbol": ASSETS[a]})["price"])
                except requests.HTTPError as e:
                    if e.response is not None and e.response.status_code == 400:
                        self.bn_bad.add(a)          # takiej pary nie ma - więcej nie pytam
                except Exception:
                    break
        self.spot.update(got)
        good = [a for a in good if a not in self.bn_bad]
        miss = [a for a in good if a not in got]
        self.api["binance"] = "OK" if good and not miss else "Coinbase"
        for a in miss:
            try:
                d = get_json(COINBASE.format(a))
                self.spot[a] = float(d["data"]["amount"])
            except Exception:
                pass

    def price_ago(self, asset, secs):
        h = self.hist[asset]
        tgt = time.time() - secs
        if not h or h[0][0] > tgt:
            return None
        for t, p in reversed(h):
            if t <= tgt:
                return p
        return None

    def kline(self, asset, start_ms=None, limit=1, interval="1m"):
        p = {"symbol": ASSETS[asset], "interval": interval, "limit": limit}
        if start_ms:
            p["startTime"] = start_ms
        return bn_get("/api/v3/klines", params=p)

    def open_price(self, asset, ts):
        k = (asset, ts)
        if k in self.open_px:
            return self.open_px[k]
        try:
            kl = self.kline(asset, ts * 1000, 1)
            if kl and int(kl[0][0]) == ts * 1000:
                self.open_px[k] = float(kl[0][1])
                if len(self.open_px) > 100:
                    self.open_px.pop(next(iter(self.open_px)))
                return self.open_px[k]
        except Exception:
            pass
        return None

    def sigma(self, asset):
        c = self.sigma_c.get(asset)
        if c and time.time() - c[0] < 60:
            return c[1]
        try:
            kl = self.kline(asset, None, 61)
            cl = [float(x[4]) for x in kl]
            rets = [math.log(cl[i] / cl[i - 1]) for i in range(1, len(cl))]
            m = sum(rets) / len(rets)
            sd = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
            sig = max(sd, 2e-5) / math.sqrt(60)  # na sekundę
            self.sigma_c[asset] = (time.time(), sig)
            return sig
        except Exception:
            return c[1] if c else None

    def sigma_for(self, asset, rem):
        """Zmienność na sekundę dopasowana do horyzontu: do godziny z barów 1m, dłużej mieszanka z barami 1h."""
        s1 = self.sigma(asset)
        if not s1 or rem <= 3600:
            return s1
        now = time.time()
        c = self.sigma_hc.get(asset)
        if not c or now - c[0] > 600:
            try:
                kl = self.kline(asset, None, 72, interval="1h")
                cl = [float(x[4]) for x in kl]
                rs = [math.log(cl[i] / cl[i - 1]) for i in range(1, len(cl))]
                sh = math.sqrt(sum(r * r for r in rs) / len(rs)) / 60.0      # na sekundę (sqrt(3600) = 60)
                c = self.sigma_hc[asset] = (now, sh)
            except Exception:
                c = (now, c[1]) if c else None
                if c:
                    self.sigma_hc[asset] = c
        if not c:
            return s1
        w = min(1.0, (rem - 3600) / 7200.0)
        return max((1 - w) * s1 + w * c[1], 0.7 * s1)

    def open_1d(self, asset, ts):
        """Cena odniesienia 1d Up/Down: zamknięcie świecy 1m Binance o 12:00 ET poprzedniego dnia."""
        k = (asset, int(ts), "1d")
        if k in self.open_px:
            return self.open_px[k]
        try:
            kl = self.kline(asset, int(ts) * 1000, 1)
            if kl and int(kl[0][0]) == int(ts) * 1000:
                self.open_px[k] = float(kl[0][4])
                return self.open_px[k]
        except Exception:
            pass
        return None

    # ---------- Polymarket ----------
    def gamma_market(self, slug):
        """Rynek po slugu -> (dict albo None, opis błędu albo None).
        Rynki updown (5m/15m/4h...) Polymarket wystawia jako WYDARZENIE: /markets?slug= zwraca im [],
        dlatego dla nich pytam najpierw /events?slug= i biorę zagnieżdżony rynek."""
        order = ("events", "markets") if "updown" in slug else ("markets", "events")
        err = None
        for kind in order:
            data = None
            for _ in (0, 1):                          # jedna powtórka przy błędzie sieci
                try:
                    data = get_json(GAMMA + "/" + kind, params={"slug": slug})
                    break
                except Exception as e:
                    err = f"{kind}: {type(e).__name__} {str(e)[:70]}"
            if not data or not isinstance(data, list):
                continue
            if kind == "markets":
                return data[0], None
            ev = data[0]
            mk = ev.get("markets") or []
            if not mk:
                continue
            m = dict(next((x for x in mk if x.get("slug") == slug), mk[0]))
            m.setdefault("slug", slug)
            if not m.get("endDate") and ev.get("endDate"):
                m["endDate"] = ev["endDate"]
            if not m.get("description") and ev.get("description"):
                m["description"] = ev["description"]
            if not m.get("eventStartTime") and (ev.get("startTime") or ev.get("eventStartTime")):
                m["eventStartTime"] = ev.get("startTime") or ev.get("eventStartTime")
            return m, None
        return None, err

    def market(self, slug):
        c = self.market_c.get(slug)
        if c and (c["m"] or time.time() - c["t"] < 10):
            return c["m"]
        m, err = self.gamma_market(slug)
        if err and not m:
            self.api["polymarket"] = "BŁĄD"
            self.gamma_err = err
        else:
            self.api["polymarket"] = "OK"
        self.market_c[slug] = {"m": m, "t": time.time()}
        if len(self.market_c) > 400:
            self.market_c.pop(next(iter(self.market_c)))
        return m

    def window(self, asset, tf, now):
        """Aktywne okno (slug + koniec) dla danego krypto i interwału albo None."""
        key = (asset, tf)
        w = self.win_c.get(key)
        if w and now < w["end"]:
            return w
        per = WINDOWS[tf]["period"]
        idx = int(now // per)
        miss = self.win_miss.get(key)               # (kiedy, ile pudeł z rzędu, numer okna)
        if miss and now - miss[0] < (6 if miss[2] != idx else min(45, 6 * 1.7 ** miss[1])):
            return None                              # brak rynku: odstęp rośnie (6,10,17,29,45 s), nowe okno = od nowa
        for slug in slug_candidates(asset, tf, now):
            m = self.market(slug)
            if not m or m.get("closed"):
                continue
            if tf in ("5m", "15m"):
                # slug = {coin}-updown-{tf}-{start}: okno to [start, start+per) - ufam slugowi, nie polu endDate
                try:
                    st = int(slug.rsplit("-", 1)[1])
                except ValueError:
                    continue
                if not (st <= now < st + per):
                    continue
                w = {"slug": slug, "end": float(st + per), "ts": st, "m": m}
                self.win_c[key] = w
                return w
            end = parse_ts(m.get("endDate"))
            # to musi być okno, które TRWA teraz (start <= teraz < koniec, długość = per)
            if end and now < end <= now + per + 120 and end - per <= now + 5:
                w = {"slug": slug, "end": end, "ts": int(round(end - per)), "m": m}
                self.win_c[key] = w
                return w
        self.win_miss[key] = (now, (miss[1] + 1) if (miss and miss[2] == idx) else 1, idx)
        return None

    @staticmethod
    def market_confirms_twap(m):
        """Fail-closed: wymagamy reguły Chainlink TWAP z lookbackiem dokładnie 60 s."""
        if not m:
            return False
        # Gamma may expose market config at top level, in eventMetadata, or raw.cryptoMarketConfig.
        raw = m.get("raw") or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = {}
        meta = m.get("eventMetadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        cfg = (m.get("cryptoMarketConfig") or
               (raw.get("cryptoMarketConfig") if isinstance(raw, dict) else None) or
               (meta.get("cryptoMarketConfig") if isinstance(meta, dict) else None) or meta)
        if isinstance(cfg, dict):
            lookback = cfg.get("twapLookbackSeconds") or cfg.get("twap_lookback_seconds")
            enabled = cfg.get("twapEnabled", cfg.get("twap_enabled"))
            if enabled is True and str(lookback) == "60":
                return True
        txt = " ".join(str(m.get(k) or "") for k in ("description", "question", "rules", "resolutionSource")).lower()
        has_60s = any(term in txt for term in ("60-second", "60 second", "60 seconds", "60s", "sixty-second", "sixty second"))
        return "chainlink" in txt and ("twap" in txt or "time-weighted average" in txt) and has_60s

    @staticmethod
    def token_for(m, side):
        outs = [str(o).lower() for o in jl(m.get("outcomes"))]
        toks = jl(m.get("clobTokenIds"))
        for i, o in enumerate(outs):
            if side_matches(o, side) and i < len(toks):
                return toks[i]
        return None

    def get_book(self, c, side):
        m = self.market(c.slug)
        if not m:
            return None
        tok = self.token_for(m, side)
        if not tok:
            return None
        cached = self.book_c.get(tok)
        if cached and time.time() - cached[0] < CFG["book_ttl"]:
            return cached[1]
        try:
            b = get_json(CLOB + "/book", params={"token_id": tok})
            asks = sorted((float(x["price"]), float(x["size"])) for x in b.get("asks", []))
            bids = sorted(((float(x["price"]), float(x["size"])) for x in b.get("bids", [])), reverse=True)
        except Exception:
            return None
        book = {"asks": asks, "bids": bids}
        self.book_c[tok] = (time.time(), book)
        if len(self.book_c) > 200:
            self.book_c.pop(next(iter(self.book_c)))
        if asks:
            seen = self.ask_seen.setdefault((c.asset, c.tf), {})
            if seen.get("slug") != c.slug:
                seen.clear()
                seen["slug"] = c.slug
            seen[side] = asks[0][0]
        return book

    def book_tok(self, tok):
        cached = self.book_c.get(tok)
        if cached and time.time() - cached[0] < CFG["book_ttl"]:
            return cached[1]
        try:
            b = get_json(CLOB + "/book", params={"token_id": tok})
            asks = sorted((float(x["price"]), float(x["size"])) for x in b.get("asks", []))
            bids = sorted(((float(x["price"]), float(x["size"])) for x in b.get("bids", [])), reverse=True)
        except Exception:
            return None
        book = {"asks": asks, "bids": bids}
        self.book_c[tok] = (time.time(), book)
        return book

    @staticmethod
    def fill(asks, budget):
        """Symulacja zakupu za `budget`$ po kolejnych poziomach asków -> (avg, shares, spent, worst)."""
        spent = shares = worst = 0.0
        for price, size in asks:
            take = min(size, (budget - spent) / price)
            if take <= 0:
                break
            shares += take
            spent += take * price
            worst = price
            if budget - spent < 0.01:
                break
        return (spent / shares, shares, spent, worst) if shares else (None, 0, 0, 0)

    # ---------- ekspozycja ----------
    def exposure(self, sid=None):
        return sum(t["cost"] for t in self.state["trades"] if t["status"] in LOCK and (sid is None or t["strat"] == sid))

    def wallet(self, sid):
        """DRY: osobny portfel wariantu = budżet + zrealizowany wynik - koszt otwartych (od początku statystyk)."""
        tr = [t for t in self.state["trades"] if t["strat"] == sid and t.get("t_open", 0) >= self.since]
        pnl = sum(t.get("pnl", 0.0) for t in tr if t["status"] in ("won", "lost"))
        cost = sum(t.get("cost", 0.0) for t in tr if t["status"] in LOCK)
        return self.sim_budget + pnl - cost

    def realized(self, sid):
        """Zrealizowany PnL wariantu (tylko zamknięte pozycje) od początku statystyk."""
        return sum(t.get("pnl", 0.0) for t in self.state["trades"]
                   if t["strat"] == sid and t.get("t_open", 0) >= self.since and t["status"] in ("won", "lost"))

    def stake_level(self, sid):
        """Ile kroków wzrostu stawki wykonano: floor(wzrost zrealizowanego bankrolla / próg schematu)."""
        if LADDER["on"] or self.broker.live:
            return getattr(self, "lvl_c", {}).get(sid, 0)       # drabinka: poziom k (może być ujemny)
        sch = STAKE_OF.get(sid)
        if not sch or not self.sim_budget:
            return 0
        g = self.realized(sid) / self.sim_budget
        return int(g / sch[0] + 1e-9) if g > 0 else 0

    def live_equity(self):
        """Kapitał wg księgi bota: bankroll startowy + zrealizowany PnL pozycji live (nie zależy od momentu odbioru wygranych)."""
        pnl = sum(t.get("pnl", 0.0) for t in self.state["trades"]
                  if t.get("strat") == LIVE_ID and t.get("live") and t.get("status") in ("won", "lost"))
        return LIVE_CFG["bankroll"] + pnl

    def stake_for(self, sid):
        """LIVE: X2. ref podwaja się przy 2x (24$, 48$, 96$...), stawka = ref/12, spada z kapitałem, min 1$, stop poniżej progu."""
        if self.broker.live and sid == LIVE_ID:
            return self.live_ladder_stake(sid)
        """Stawka wariantu: start * (1 + krok_stawki) ^ poziom; nigdy poniżej stawki startowej."""
        if LADDER["on"] and not self.broker.live:
            return self.ladder_stake(sid)
        sch = STAKE_OF.get(sid)
        if not sch:
            return self.stake
        return round(self.stake * (1.0 + sch[1]) ** self.stake_level(sid), 2)

    def live_ladder_stake(self, sid):
        """LIVE: TA SAMA drabinka co w dry (ladder_stake), ale kapital = bankroll startowy + zrealizowany PnL live.
        Poziom ref podwaja sie przy 2x kapitalu; baza = start (np. 1$), po resecie ref / (bankroll_start / start) - proporcja jak w dry.
        stawka = baza * (1+krok_stawki)^k, k = floor(ln(kapital/ref)/ln(1+krok_bankrolla)).
        UP: k tylko w gore (pamieta szczyt na danym poziomie). UD: k rosnie I maleje. Nie schodzi ponizej min_stake."""
        L = LADDER
        bank0 = float(LIVE_CFG["bankroll"])
        eq = self.live_equity()
        ref = float(self.state.get("live_lref") or bank0)
        while eq >= ref * L["reset_mult"]:
            ref *= L["reset_mult"]
            self.note(f"RESET drabiny LIVE: kapital {eq:.2f}$ -> poziom {ref:g}$, baza {ref * LIVE_CFG['base'] / bank0:.2f}$")
        self.state["live_lref"] = ref
        if eq < LIVE_CFG["stop"] or eq < LIVE_CFG["min_stake"]:
            return 0.0
        base = LIVE_CFG["base"] if ref <= bank0 * 1.0001 else ref * LIVE_CFG["base"] / bank0
        step_bank, step_stake = STAKE_OF.get(sid) or (L["step_bank"], L["step_stake"])
        k = int(math.floor(math.log(max(eq, 1e-9) / ref) / math.log(1.0 + step_bank) + 1e-9))
        if (VAR_BY_ID.get(sid) or {}).get("scheme") == "UD":
            k = max(k, -80)
        else:
            km = self.state.get("live_lkmax")
            kmax = int(km[1]) if isinstance(km, list) and len(km) == 2 and abs(float(km[0]) - ref) < 1e-9 else 0
            k = max(k, kmax, 0)
            self.state["live_lkmax"] = [ref, k]
        if not hasattr(self, "lvl_c"):
            self.lvl_c = {}
        self.lvl_c[sid] = k
        st = base * (1.0 + step_stake) ** k
        return round(min(max(st, LIVE_CFG["min_stake"]), LIVE_CFG["max_stake"], CFG["max_order"]), 2)

    def ladder_stake(self, sid):
        """DRY, --ladder: kapitał = budżet + zrealizowany PnL wariantu. Poziom ref podwaja się przy 2x (reset: 12->24->48->96...).
        Stawka = baza * (1+krok_stawki)^k, k = floor(ln(kapitał/ref)/ln(1+krok_bankrolla)) - rośnie i maleje; min/max wg LADDER."""
        L = LADDER
        bank0 = float(self.sim_budget or 12.0)
        eq = bank0 + self.realized(sid)
        key = f"ladder_ref_{sid}"
        ref = float(self.state.get(key) or bank0)
        while eq >= ref * L["reset_mult"]:
            ref *= L["reset_mult"]
            self.note(f"RESET drabiny: kapitał {eq:.2f}$ -> poziom {ref:g}$, baza {ref / L['div']:.2f}$")
        self.state[key] = ref
        if eq < L["min_stake"]:
            return 0.0
        base = L["start_stake"] if ref <= bank0 * 1.0001 else ref / L["div"]
        step_bank, step_stake = STAKE_OF.get(sid) or (L["step_bank"], L["step_stake"])     # krok wg schematu wariantu (D/F/G)
        k = int(math.floor(math.log(max(eq, 1e-9) / ref) / math.log(1.0 + step_bank) + 1e-9))
        mode = (VAR_BY_ID.get(sid) or {}).get("scheme")
        if mode == "UD":
            k = max(k, -80)                           # rosnie I maleje (stawka nie spada ponizej min_stake)
        else:                                         # UP: stawka tylko rosnie - pamieta najwyzszy poziom k na tym poziomie bazy
            km = self.state.get(f"ladder_kmax_{sid}")
            kmax = int(km[1]) if isinstance(km, list) and len(km) == 2 and abs(float(km[0]) - ref) < 1e-9 else 0
            k = max(k, kmax, 0)
            self.state[f"ladder_kmax_{sid}"] = [ref, k]
        if not hasattr(self, "lvl_c"):
            self.lvl_c = {}
        self.lvl_c[sid] = k
        st = base * (1.0 + step_stake) ** k
        return round(min(max(st, L["min_stake"]), L["max_stake"], CFG["max_order"]), 2)

    def groups(self):
        gs = [(t_, [i for i in ids if i in self.active_ids]) for t_, ids in GROUPS]
        gs = [g for g in gs if g[1]]
        rest = [x["id"] for x in self.active if x["id"] not in ANTI_IDS]
        if rest:
            gs.append(("pozostałe strategie", rest))
        return gs or [("wszystkie", [x["id"] for x in self.active])]

    def view_sids(self):
        gs = self.groups()
        return gs[self.group % len(gs)][1]

    def group_line(self):
        gs = self.groups()
        k = self.group % len(gs)
        return Text(f"Grupa {k + 1}/{len(gs)}: {gs[k][0]}   [g] = następna", style="bold yellow")

    def balance_now(self, sid=None):
        if self.broker.live:
            return self.broker.balance()
        if self.sim_budget is None:
            return None
        if sid is not None:
            return self.wallet(sid)
        return sum(self.wallet(s["id"]) for s in self.active)

    def counter_pass(self, now):
        """Pozycja BIN <= -counter_at: kontra przeciwną stroną najpierw na DRUGIM interwale (5m<->15m) tej samej krypto,
        potem na tym samym. Kurs min. bin_min_odds, reguły okna (BTC / -50%) obowiązują. Każda nowa noga może wywołać kolejną."""
        if not CFG["counter"]:
            return
        s17 = next((x for x in self.active if x["id"] == 17), None)
        if not s17:
            return
        for L in list(self.state["trades"]):
            if (L.get("strat") != 17 or L.get("status") != "open" or L.get("tf") not in ("5m", "15m")
                    or L.get("cnt_done") or now < L.get("cnt_next", 0)):
                continue
            pp = L.get("pnl_pct")
            if pp is None or pp > -CFG["counter_at"] or L["end_ts"] - now < 15:
                continue
            L["cnt_next"] = now + 4
            a, tf, cside = L["asset"], L["tf"], other(L["side"])
            for ctf in (("15m", "5m") if tf == "5m" else ("5m", "15m")):
                c = self.cur_ctx.get((a, ctf))
                if c is None or c.rem < CFG["counter_min_rem"]:
                    continue
                if c.tf in ORACLE_TFS and c.rem <= twap_cut(c.tf):
                    continue
                if (17, c.slug, cside) in self.side_locked:
                    continue
                if self.execute(s17, Sig(cside, 1.0 / CFG["bin_min_odds"]), c, now, counter=True):
                    self.side_locked.add((17, c.slug, cside))
                    L["cnt_done"] = True
                    self.n_counter += 1
                    break

    # ---------- v8: równoległe pobieranie + dokładanie nóg ----------
    def _fetch_book_raw(self, tok):
        b = get_json(CLOB + "/book", params={"token_id": tok})
        asks = sorted((float(x["price"]), float(x["size"])) for x in b.get("asks", []))
        bids = sorted(((float(x["price"]), float(x["size"])) for x in b.get("bids", [])), reverse=True)
        return {"asks": asks, "bids": bids}

    def prefetch_books(self, now):
        """Równolegle pobiera orderbooki: rynków 5m/15m, które mają szansę na wejście (fair strony >= fair_min),
        oraz otwartych pozycji (TP i znacznik -50%). Potem get_book/book_tok trafiają w cache."""
        jobs = {}
        for c in self.cur_ctx.values():
            if c.tf not in ACTIVE_TFS or c.rem < 8:
                continue
            if c.tf in ORACLE_TFS and c.rem <= twap_cut(c.tf):
                continue
            try:
                fair_up = c.cdf(c.d / (c.sigma * math.sqrt(c.rem)))
            except Exception:
                continue
            m = (self.market_c.get(c.slug) or {}).get("m")
            if not m:
                continue
            for side, fair in (("Up", fair_up), ("Down", 1 - fair_up)):
                if fair < CFG["bin_fair_min"] and not any(i_ in ANTI_IDS for i_ in self.active_ids):
                    continue
                tok = self.token_for(m, side)
                if tok:
                    jobs[tok] = (c, side)
        for t in self.state["trades"]:
            if t.get("status") != "open" or t.get("tf") not in ACTIVE_TFS or now >= t.get("end_ts", 0) - 1:
                continue
            m = (self.market_c.get(t["slug"]) or {}).get("m")
            tok = self.token_for(m, t["side"]) if m else None
            if tok and tok not in jobs:
                jobs[tok] = None
        ttl = CFG["book_ttl"]
        todo = [tok for tok in jobs if not (self.book_c.get(tok) and time.time() - self.book_c[tok][0] < ttl)]
        if not todo:
            return

        def one(tok):
            try:
                return tok, self._fetch_book_raw(tok)
            except Exception:
                return tok, None

        for tok, book in self.pool.map(one, todo):
            if book is None:
                continue
            self.book_c[tok] = (time.time(), book)
            meta = jobs.get(tok)
            if meta and book["asks"]:
                c, side = meta
                seen = self.ask_seen.setdefault((c.asset, c.tf), {})
                if seen.get("slug") != c.slug:
                    seen.clear()
                    seen["slug"] = c.slug
                seen[side] = book["asks"][0][0]
        while len(self.book_c) > 300:
            self.book_c.pop(next(iter(self.book_c)))

    def prewarm(self, now):
        """Tuż przed końcem okna pobiera równolegle rynki NASTĘPNEGO okna 5m/15m, żeby wejścia ruszyły od pierwszej
        sekundy. Wyniki ujemne (rynek jeszcze nie istnieje) nie są zapamiętywane."""
        slugs = []
        for tf in ACTIVE_TFS:
            per = WINDOWS[tf]["period"]
            if per - (now % per) > CFG["prewarm_s"]:
                continue
            nxt = int(now // per * per + per)
            for a in ASSETS:
                if not tf_ok(a, tf) or a in self.bn_bad:
                    continue
                slug = f"{a.lower()}-updown-{tf}-{nxt}"
                cached = self.market_c.get(slug)
                if cached and cached["m"]:
                    continue
                slugs.append(slug)
        if not slugs:
            return

        def one(slug):
            try:
                m, _err = self.gamma_market(slug)
                return slug, m
            except Exception:
                return slug, None

        for slug, m in self.pool.map(one, slugs):
            if m:
                self.market_c[slug] = {"m": m, "t": time.time()}
        while len(self.market_c) > 400:
            self.market_c.pop(next(iter(self.market_c)))

    def leg_pass(self, now):
        """Dokładanie nóg BIN (3., 4., ...) na rynkach 5m/15m. Warunki: strona ma już otwartą nogę, sygnał BIN nadal
        wskazuje tę stronę z pełną przewagą, nowa noga jest TAŃSZA o leg_step od poprzedniej (albo p modelu wyższe o
        leg_dp), minął leg_gap, do końca >= leg_min_rem, łączna liczba nóg < max_legs, koszt otwartych nóg na rynku
        w limicie, a po zakupie zostaje rezerwa wolnych stawek. Rynek z auto-parą (zabezpieczoną) jest pomijany."""
        if CFG["max_legs"] <= 2:
            return
        s17 = next((x for x in self.active if x["id"] == 17), None)
        if not s17:
            return
        budget = self.sim_budget if self.sim_budget else (self.max_open if self.max_open > 0 else None)
        cap = max(3 * self.stake, CFG["leg_cap_frac"] * budget) if budget else 3 * self.stake
        for c in list(self.cur_ctx.values()):
            if c.tf not in ACTIVE_TFS or c.rem < CFG["leg_min_rem"]:
                continue
            if c.tf in ORACLE_TFS and c.rem <= twap_cut(c.tf):
                continue
            mine = [t for t in self.state["trades"]
                    if t.get("strat") == 17 and t.get("slug") == c.slug
                    and t.get("status") in ("pending", "open", "check", "won", "lost")]
            if not mine or len(mine) >= CFG["max_legs"] or any(t.get("paired") for t in mine):
                continue
            if any(t.get("status") in ("pending", "check") for t in mine):
                continue
            key = ("leg", c.slug)
            if now - self.last_eval.get(key, 0) < CFG["eval_gap"] + 1:
                continue
            self.last_eval[key] = now
            open_cost = sum(t["cost"] for t in mine if t.get("status") == "open")
            if open_cost + self.stake > cap + 1e-9:
                continue
            bal = self.balance_now()
            if bal is not None and bal - self.stake < CFG["leg_reserve"] * self.stake:
                continue
            try:
                sg = s17["fn"](c)
            except Exception:
                continue
            if sg is None:
                continue
            same = [t for t in mine if t.get("side") == sg.side and t.get("status") == "open"]
            if not same:
                continue                    # pierwsza noga tej strony = zwykła ścieżka (scan)
            last = max(same, key=lambda t: t.get("t_open", 0))
            if now - last.get("t_open", 0) < CFG["leg_gap"]:
                continue
            a = c.ask(sg.side)
            if not a:
                continue
            cheaper = a <= last["entry"] - CFG["leg_step"]
            stronger = c.p_of(sg.side) >= (last.get("p") or 0.0) + CFG["leg_dp"]
            if not (cheaper or stronger):
                continue
            self.execute(s17, sg, c, now, extra=True)

    # ---------- reguły okna: BTC odwrotnie + blokada -50% ----------
    def rule_block(self, c, side):
        """'btc' / 'loss' gdy wejście w tę stronę jest zabronione w tym trwającym oknie, inaczej None."""
        if c.tf not in ("5m", "15m"):
            return None
        mode = CFG["btc_rule"]
        for t in self.state["trades"]:
            if t.get("strat") in ANTI_IDS or t.get("tf") != c.tf or t.get("end_ts") != c.end:
                continue
            if mode != "off" and c.asset != "BTC" and t.get("asset") == "BTC":
                banned = t["side"] if mode == "inverse" else other(t["side"])
                if side == banned:
                    return "btc"              # BTC już grał w tym oknie (także zamknięty / po TP)
            if CFG["loss_block"] > 0 and t.get("bad") and t.get("status") == "open" and t.get("side") == side:
                return "loss"                 # inna pozycja w tę stronę jest <= -50% i jeszcze nie na plusie
        return None

    def update_bad(self, now):
        """Oznacza pozycje <= -loss_block (wg ceny mid); zdejmuje znacznik dopiero, gdy pozycja jest na plusie."""
        lim = CFG["loss_block"] if CFG["loss_block"] > 0 else 9.0     # 9.0 = blokada -50% wyłączona, pnl_pct nadal liczone
        for t in self.state["trades"]:
            if t.get("status") != "open" or t.get("tf") not in ("5m", "15m") or not t.get("shares"):
                continue
            if now >= t.get("end_ts", 0) - 2 or now < t.get("bad_next", 0):
                continue
            t["bad_next"] = now + 3
            try:
                m = self.market(t["slug"])
                tok = self.token_for(m, t["side"]) if m else None
                book = self.book_tok(tok) if tok else None
            except Exception:
                continue
            if not book or not book["bids"]:
                continue
            bb_ = book["bids"][0][0]
            t["hi_bid"] = max(t.get("hi_bid", 0.0), bb_)
            t["lo_bid"] = min(t.get("lo_bid", 1.0), bb_)
            px = (book["bids"][0][0] + book["asks"][0][0]) / 2 if book["asks"] else book["bids"][0][0]
            cost = t.get("cost") or 0
            if cost <= 0:
                continue
            pnl = (px * t["shares"] - cost) / cost
            t["pnl_pct"] = pnl
            if pnl <= -lim:
                t["bad"] = True
            elif pnl > 0:
                t["bad"] = False

    # ---------- wykonanie sygnału ----------
    def execute(self, s, sg, c, now, auto=False, counter=False, extra=False):
        """True = wejście zrobione albo zablokowane do rozliczenia (nie próbuj ponownie)."""
        key = (s["id"], c.slug)
        if self.cool.get(key, 0) > now:
            return False
        if s["id"] == 17:
            why = self.rule_block(c, sg.side)
            if why:
                self.rule_diag[why] += 1
                return False
        is_bin = s["id"] == 17                           # zmiany dwóch nóg tylko dla BIN; SNIPER po staremu
        pmatch = CFG["bin_pair_match"] if is_bin else True
        pmax = CFG["bin_pair_max"] if is_bin else CFG["pair_max"]
        if auto:                                         # auto-para: równe udziały, pewny zysk liczony niżej
            pmatch, pmax = True, 9.0
        book = self.get_book(c, sg.side)
        if not book or not book["asks"]:
            return False
        limit = min(sg.max_price, 0.99)
        asks = [x for x in book["asks"] if x[0] <= limit]
        stake = self.stake_for(s["id"])
        if stake <= 0:
            self.warn_once("livestop", f"kapitał {self.live_equity():.2f}$ za niski na stawkę - brak nowych wejść")
            return False
        if stake > CFG["max_order"]:
            return False
        if s["id"] in ANTI_IDS:        # limit otwartych pozycji NA WARIANT (tez w dry-run)
            is_fin = c.tf == "fin"
            mine_open = [x for x in self.state["trades"] if x.get("strat") == s["id"] and x.get("status") in LOCK]
            n_cat = sum(1 for x in mine_open if (x.get("tf") == "fin") == is_fin)
            lim = LIVE_CFG["max_pos_fin"] if is_fin else LIVE_CFG["max_pos"]
            if n_cat >= lim:
                self.warn_once("maxpos_fin" if is_fin else "maxpos",
                               f"limit otwartych {'FINANSE' if is_fin else 'KRYPTO'}: {lim} - czekam na zamknięcie")
                return False
            if LIVE_CFG["max_total"] and len(mine_open) >= LIVE_CFG["max_total"]:
                self.warn_once("maxtotal", f"limit łączny otwartych: {LIVE_CFG['max_total']} - czekam na zamknięcie")
                return False
        first = None
        if CFG["both_sides"] and not extra and s["id"] not in ANTI_IDS:
            first = next((x for x in self.state["trades"] if x["strat"] == s["id"] and x["slug"] == c.slug
                          and x["side"] == other(sg.side) and x["status"] in LOCK), None)
            if first is not None and pmatch:            # druga noga: tyle samo udziałów co pierwsza (zabezpieczona para)
                if first["status"] != "open" or not first.get("shares") or not asks:
                    return False
                stake = max(self.stake, first["shares"] * asks[0][0])
                if stake > CFG["max_order"]:
                    return False
        avg, shares, spent, worst = self.fill(asks, stake)     # stała stawka, zero mnożników (druga noga: wyrównanie udziałów)
        if not avg or spent < stake - 0.02:                    # FOK: cała kwota albo nic
            return False
        if auto:                                               # pewny zysk po opłatach niezależnie od wyniku rynku
            if first is None:
                return False
            net = (min(first["shares"], shares) - first["cost"] - spent
                   - shares * fee_per_share(avg, c.tf))
            if net < CFG["auto_min_profit"]:
                return False
        if first is not None and first["entry"] + avg > pmax:
            return False      # suma cen obu nóg za wysoka: para dałaby pewną stratę
        if avg < CFG["min_price"]:
            return False
        tp_ = self.tp.get(s["id"])
        if tp_ and avg >= tp_ - 0.01 and any(x["strat"] == s["id"] and x["slug"] == c.slug and x.get("exit") == "TP"
                                             for x in self.state["trades"]):
            return False      # ponowne wejście po TP tylko poniżej progu TP (inaczej TP od razu sprzedałoby ze stratą)
        p = c.p_of(sg.side)
        edge = p - avg - fee_per_share(avg, c.tf)
        if sg.min_edge is not None and edge < sg.min_edge:
            return False
        if self.max_open > 0 and self.exposure(s["id"]) + stake > self.max_open:
            self.warn_once("maxopen", f"limit ekspozycji ${self.max_open:.0f} - pomijam wejścia")
            return False
        bal = self.balance_now(s["id"])
        if bal is not None and bal < stake + 0.05:
            self.warn_once(f"bal{s['id']}", f"{s['name']}: saldo ${bal:.2f} za niskie - pomijam wejścia")
            return False
        m = self.market(c.slug)
        tok = self.token_for(m, sg.side) if m else None
        if not tok:
            return False
        worst_px = min(0.99, math.ceil(worst * 100 - 1e-9) / 100)   # limit ceny FOK (tick 0.01)
        n_leg = 1 + sum(1 for x in self.state["trades"]
                        if x["strat"] == s["id"] and x["slug"] == c.slug
                        and x["status"] in ("pending", "open", "check", "won", "lost"))
        rec = {
            "id": f"{s['id']}:{c.slug}:{sg.side}" + (f"#{n_leg}" if extra else ""), "leg": n_leg,
            "strat": s["id"], "slug": c.slug,
            "asset": c.asset, "tf": c.tf, "side": sg.side, "entry": avg, "shares": shares,
            "cost": stake, "p": p, "edge": edge, "t_open": now, "end_ts": c.end,
            "open_px": c.open, "status": "pending", "pnl": 0.0, "est": False,
            "live": self.broker.live, "order_id": "",
            "event": c.event, "strike": c.open if c.tf in ("strike", "fin") else None,
            "label": c.label, "rem_in": c.rem, "fee_in": 0.0,
            "anti": s["id"] in ANTI_IDS, "mdl_up": c.p_up, "stake": stake, "lvl": self.stake_level(s["id"]),
            "bank_in": round(self.realized(s["id"]) + (self.sim_budget or 0.0), 4),
            "spr_in": (book["asks"][0][0] - book["bids"][0][0]) if book["bids"] else None,
        }
        if counter:
            rec["counter"] = True
        if extra:
            rec["extra"] = True
        if auto:
            rec["paired"] = True                        # para zabezpieczona: bez TP, trzymamy do rozliczenia
        # BLOKADA PRZED WYSŁANIEM: pozycja istnieje w stanie i na dysku zanim zlecenie wyjdzie
        self.state["trades"].append(rec)
        self.save()
        res = self.broker.buy(tok, stake, worst_px, m, (avg, shares, spent))
        tag = "LIVE" if self.broker.live else "DRY"
        if res["status"] == "filled":
            sp, sh = res["spent"], res["shares"]
            fee = sh * fee_per_share(sp / sh, c.tf)
            rec.update(status="open", entry=sp / sh, shares=sh, cost=sp + fee,
                       edge=p - sp / sh - fee_per_share(sp / sh, c.tf), order_id=res.get("id", ""), fee_in=fee,
                       fill_est=bool(res.get("est")) and self.broker.live)
            self.fail_streak = 0
            if auto and first is not None:
                first["paired"] = True
            self.broker.refresh_balance()
            self.note(f"{tag} {s['name']} {'KONTRA' if counter else 'NOGA%d' % n_leg if extra else 'KUPNO'} {mkt_label(rec)} {side_label(c.tf, sg.side)} @ {sp / sh * 100:.1f}c (${sp:.2f})")
        elif res["status"] == "rejected":
            self.state["trades"].remove(rec)
            self.cool[key] = now + CFG["fail_cooldown"]
            msg = res.get("msg", "")
            if not any(k in msg.lower() for k in ("fok", "fully", "filled", "liquidity")):
                self.fail_streak += 1
                if self.fail_streak >= 5:
                    self.halt_until = now + 120
                    self.fail_streak = 0
                    self.note("5 odrzuceń z rzędu - pauza 120 s")
            self.note(f"{tag} {s['name']} {mkt_label(rec)} odrzucone: {msg[:50]}")
            self.save()
            return False
        else:   # niejednoznaczne: NIE ponawiamy, blokada do rozliczenia
            rec.update(status="check", order_id=res.get("id", ""))
            self.note(f"{tag} {s['name']} {mkt_label(rec)} NIEPEWNE ({res.get('msg', '')[:40]}) - SPRAWDŹ RĘCZNIE")
        self.save()
        return True

    # ---------- import pozycji z konta ----------
    def sync_positions(self, now):
        """Pobiera otwarte pozycje portfela z Data API i dopisuje te, których bot nie zna (strategia 0 = IMPORT).
        Pozycje bota nie są duplikowane; 'SPRAWDŹ' potwierdzone przez konto -> 'otwarta'. Pozycje 'do odebrania'
        (rynek rozstrzygnięty) są tylko liczone. IMPORT nigdy nie jest sprzedawany przez bota (zero take-profit)."""
        addr = self.broker.address()
        if not addr:
            self.pos_ok, self.pos_info = False, "brak adresu portfela (ustaw PM_FUNDER)"
            return
        data = fetch_positions(addr)
        trades = self.state["trades"]
        mine = [t for t in trades if t["strat"] != 0]
        imp = {t["tok"]: t for t in trades if t["strat"] == 0 and t.get("tok")}
        seen, claim, added, changed = set(), 0, 0, False
        for p in data:
            try:
                size = float(p.get("size") or 0)
                tok, slug = str(p.get("asset") or ""), str(p.get("slug") or "")
                if size <= 1e-8 or not tok or not slug:
                    continue
                side = norm_side(p.get("outcome"))
                avg = float(p.get("avgPrice") or 0)
                cost = float(p.get("initialValue") or 0) or size * avg
                cur = float(p.get("curPrice") or 0)
            except (TypeError, ValueError):
                continue
            seen.add(tok)
            if p.get("redeemable"):
                claim += 1
            if tok in imp:
                # Tylko pozycja nierozliczona jest aktywną pozycją; redeemable liczy się osobno jako claim.
                if not p.get("redeemable"):
                    imp[tok].update(status="open", shares=size, cost=cost,
                                    entry=avg or imp[tok]["entry"], cur=cur, miss=0)
                continue
            if p.get("redeemable"):
                mt = next((t for t in mine if t["slug"] == slug and t["side"] == side and t.get("status") == "check"), None)
                if mt:                                # niepewne zlecenie, a konto pokazuje rozliczoną pozycję -> była kupiona, settle() ją rozliczy
                    mt.update(status="open", shares=size, cost=cost, entry=avg or mt["entry"], tok=tok, cur=cur, miss=0)
                    self.note(f"SPRAWDŹ rozwiązane z konta: {mkt_label(mt)} {trade_side(mt)}")
                    changed = True
                continue                              # rozstrzygnięte, nieznane botowi - nic do pilnowania
            match = next((t for t in mine if t["slug"] == slug and t["side"] == side), None)
            if match:                                 # konto potwierdza tylko rekord nadal otwarty/niepewny
                old_status = match.get("status")
                if old_status in LOCK:
                    match.update(status="open", shares=size, cost=cost,
                                 entry=avg or match["entry"], tok=tok, cur=cur, miss=0)
                    if old_status != "open":
                        self.note(f"konto potwierdza/przywraca pozycję: {mkt_label(match)} {trade_side(match)}")
                        changed = True
                continue
            m = self.market(slug)
            end = parse_ts((m or {}).get("endDate")) or parse_ts(p.get("endDate")) or now + 3600
            tf = infer_tf(slug)
            asset = infer_asset(slug, tf)
            label = ""
            if tf == "strike":
                mk_ = re.search(r"above-(\d+(?:pt\d+)?)", slug)
                label = f"{asset}>{mk_.group(1).replace('pt', '.')}" if mk_ else ""
            elif tf in ("fin", "wx", "ext") or asset == "EXT":
                label = str(p.get("title") or slug)[:16]
            rec = {
                "id": f"0:{slug}:{side}", "strat": 0, "slug": slug, "asset": asset, "tf": tf, "side": side,
                "outcome": str(p.get("outcome") or ""), "tok": tok, "entry": avg, "shares": size, "cost": cost,
                "p": 0.0, "edge": 0.0, "t_open": now, "end_ts": end, "open_px": None, "status": "open",
                "pnl": 0.0, "est": False, "live": True, "order_id": "", "event": "", "strike": None,
                "label": label, "cur": cur, "title": str(p.get("title") or ""),
            }
            trades.append(rec)
            added += 1
            changed = True
        for t in list(trades):                        # pozycja zniknęła z konta (sprzedana/odebrana) - 3 pudła z rzędu
            if t["strat"] == 0 and t["status"] == "open" and t.get("tok") and t["tok"] not in seen:
                t["miss"] = t.get("miss", 0) + 1
                if t["miss"] >= 3:
                    trades.remove(t)
                    changed = True
        seen_ss = {(str(p.get("slug") or ""), norm_side(p.get("outcome"))) for p in data}
        for t in list(trades):                        # "check" bez śladu na koncie długo po końcu rynku = zlecenie nie weszło (albo już odebrane) -> zdejmij blokadę
            if (t["strat"] != 0 and t.get("status") == "check" and now > t["end_ts"] + 240
                    and (t["slug"], t["side"]) not in seen_ss):
                trades.remove(t)
                self.note(f"SPRAWDŹ zdjęte (brak pozycji na koncie): {mkt_label(t)} {trade_side(t)}")
                changed = True
        n_imp = sum(1 for t in trades if t["strat"] == 0 and t["status"] == "open")
        self.pos_claim, self.pos_ok = claim, True
        self.pos_info = f"{n_imp} z konta" + (f", {claim} do odebrania" if claim else "")
        if added:
            self.note(f"import z konta: +{added} poz. (razem otwartych: {sum(1 for t in trades if t['status'] in LOCK)})")
        if changed:
            self.save()

    # ---------- take-profit ----------
    def exits(self, now):
        """Sprzedaż pozycji strategii z self.tp, gdy kupujący płacą >= próg (cała pozycja FOK)."""
        for t in self.state["trades"]:
            tp = self.tp.get(t["strat"])
            if (not tp or t["status"] != "open" or t.get("tp_off") or t.get("paired") or now < t.get("tp_next", 0)
                    or now >= t["end_ts"] - (63 if t.get("tf") == "strike" else 3)):
                continue
            t["tp_next"] = now + 3
            m = self.market(t["slug"])
            tok = self.token_for(m, t["side"]) if m else None
            book = self.book_tok(tok) if tok else None
            if not book:
                continue
            shares = math.floor(t["shares"] * 100) / 100
            minpx = math.ceil(tp * 100 - 1e-9) / 100
            got = need = 0.0
            for price, size in book["bids"]:          # bidy malejąco
                if price < minpx:
                    break
                take = min(size, shares - need)
                got += take * price
                need += take
                if need >= shares - 1e-9:
                    break
            if shares <= 0 or need < shares - 1e-9:   # za mała głębokość przy cenie >= próg
                continue
            res = self.broker.sell(tok, shares, minpx, m, got)
            name = next((s["name"] for s in STRATS if s["id"] == t["strat"]), "?")
            tag = "LIVE" if self.broker.live else "DRY"
            if res["status"] == "filled":
                exit_fee = shares * fee_per_share(res["proceeds"] / shares, t.get("tf")) if shares else 0.0
                t["pnl"] = res["proceeds"] - exit_fee - t["cost"]
                t["status"] = "won" if t["pnl"] > 0 else "lost"     # blokada zdjęta
                t["exit"], t["t_close"], t["est"] = "TP", now, False
                t["exit_px"], t["fee_out"] = (res["proceeds"] / shares if shares else 0.0), exit_fee
                t["hi_bid"] = max(t.get("hi_bid", 0.0), book["bids"][0][0])
                self.cool[(t["strat"], t["slug"])] = now + 10   # po take-profit można wejść ponownie w ten sam rynek (po 10 s)
                self.broker.refresh_balance()
                self.note(f"{tag} {name} TP {mkt_label(t)} {side_label(t['tf'], t['side'])} {t['pnl']:+.2f}$")
            elif res["status"] == "rejected":
                t["tp_fail"] = t.get("tp_fail", 0) + 1
                t["tp_next"] = now + 10
                if t["tp_fail"] >= 5:
                    t["tp_off"] = True
                    self.note(f"{name} {mkt_label(t)}: TP nie działa ({res.get('msg', '')[:30]}) - trzymam do końca")
            else:
                t["status"] = "check"
                self.note(f"{tag} {name} {mkt_label(t)} SPRZEDAŻ NIEPEWNA - SPRAWDŹ RĘCZNIE")
            self.save()

    # ---------- rozliczanie ----------
    def settle(self):
        now = time.time()
        for t in self.state["trades"]:
            if t["status"] != "open" or now < t["end_ts"] + 4:
                continue
            winner, est = None, False
            if now - self.last_res_try.get(t["slug"], 0) > 8:
                self.last_res_try[t["slug"]] = now
                try:
                    m, _err = self.gamma_market(t["slug"])
                    if m and (m.get("closed") or m.get("acceptingOrders") is False):
                        prices = [float(x) for x in jl(m.get("outcomePrices"))]
                        outs = [str(o).lower() for o in jl(m.get("outcomes"))]
                        if prices and max(prices) >= 0.99:
                            winner = outs[prices.index(max(prices))]
                except Exception:
                    pass
            if winner is None and now > t["end_ts"] + 90 and t.get("tf") == "1h":
                try:  # 1h rozlicza się świecą Binance 1h; 5m/15m/4h czekają na oficjalny wynik Gamma
                    hour_start = int(t["end_ts"] - 3600)
                    kl = self.kline(t["asset"], hour_start * 1000, 1, interval="1h")
                    if not kl or int(kl[0][0]) != hour_start * 1000:
                        continue
                    cl = float(kl[0][4])
                    winner = "up" if cl >= t["open_px"] else "down"
                    est = True
                except Exception:
                    continue
            if winner is None:
                continue
            won = side_matches(winner, t["side"])
            t["status"] = "won" if won else "lost"      # blokada (strategia, rynek) zdjęta
            t["t_close"] = now
            t["est"] = est
            t["pnl"] = (t["shares"] if won else 0.0) - t["cost"]
            name = "IMPORT" if t["strat"] == 0 else next((s["name"] for s in STRATS if s["id"] == t["strat"]), "?")
            self.note(f"{name} {mkt_label(t)} {trade_side(t)} -> {'WIN' if won else 'LOSS'} {t['pnl']:+.2f}$")
            self.save()

    # ---------- główny cykl ----------
    def step(self):
        self.fetch_spot()
        now = time.time()
        self.tw_diag = {"ok": 0, "reguly": 0, "feed": 0, "otwarcie": 0}
        for a, p in self.spot.items():
            self.hist[a].append((now, p))
        if self.broker.live and CFG["import"] and now >= self.pos_next:
            try:
                self.sync_positions(now)
                self.pos_next = now + CFG["pos_sync"]
            except Exception as e:
                self.pos_ok = False
                self.pos_info = f"błąd {type(e).__name__}"
                self.pos_next = now + 30
                self.warn_once("pos", f"import pozycji: {type(e).__name__} {str(e)[:50]}")
        self.side_locked = {(t["strat"], t["slug"], t["side"]) for t in self.state["trades"] if t["status"] in LOCK}
        locked = set()
        for sid_, slug_, side_ in self.side_locked:     # pełna blokada rynku: bez both_sides po 1. wejściu, z both_sides gdy są obie strony
            if not CFG["both_sides"] or sid_ in ANTI_IDS or (sid_, slug_, other(side_)) in self.side_locked:
                locked.add((sid_, slug_))
        # wejścia wariantów w niedawne rynki (okna trwają max 15 min): tryb 1X/HOLD = blokada rynku NA ZAWSZE (także po TP),
        # tryb RE = blokuje tylko otwarta pozycja (side_locked), po TP wolno wejść ponownie (limit i strona w strategii)
        self.slug_trades = {}
        for t in self.state["trades"][-4000:]:           # tylko ostatnie wpisy: okna trwają max 15 min
            if t.get("t_open", 0) < now - 3600:
                continue
            if t["strat"] in ANTI_IDS:
                self.slug_trades.setdefault((t["strat"], t["slug"]), []).append(t)
                if t["strat"] in ONCE_IDS:
                    locked.add((t["strat"], t["slug"]))
        for t in self.state["trades"]:               # pozycje z konta (nie nasze): żadna strategia nie wchodzi drugi raz
            if t["strat"] == 0 and t["status"] in LOCK:
                locked.update((s["id"], t["slug"]) for s in self.active)
        if len(self.last_eval) > 3000:
            self.last_eval.clear()
        self.cur_ctx = {}
        self.update_bad(now)
        trading = now >= self.halt_until
        try:
            self.prewarm(now)
        except Exception as e:
            self.warn_once("prewarm", f"prewarm: {type(e).__name__}")
        scan_q = []
        for tf in ACTIVE_TFS:
            per = WINDOWS[tf]["period"]
            peers = {}
            for a in ASSETS:
                if not tf_ok(a, tf) or a in self.bn_bad:
                    continue
                win = self.window(a, tf, now)
                if not win:
                    self.radar[(a, tf)] = {"rem": 0, "c": None, "slug": "-"}
                    continue
                rem = win["end"] - now
                sig = self.sigma(a)
                spot = self.spot.get(a)
                if tf in ORACLE_TFS:
                    # 5m/15m/4h: oficjalny próg = Chainlink TWAP60, Binance służy jako leading indicator.
                    op_row = self.oracle.at_or_before(a, "twap60", win["ts"], max_gap=2)
                    tw_now = self.oracle.latest(a, "twap60", now, max_age=5)
                    cl_now = self.oracle.latest(a, "chainlink", now, max_age=5)
                    market_ok = self.market_confirms_twap(win.get("m"))
                    if not market_ok:
                        self.tw_diag["reguly"] += 1        # opis rynku nie potwierdza Chainlink TWAP 60 s
                    elif not (tw_now and cl_now):
                        self.tw_diag["feed"] += 1          # brak świeżego feedu TWAP60 / Chainlink
                    elif not op_row:
                        self.tw_diag["otwarcie"] += 1      # brak próbki TWAP z sekundy otwarcia okna
                    else:
                        self.tw_diag["ok"] += 1
                    if op_row and tw_now and cl_now and spot and sig and market_ok and cl_now[1] > 0:
                        # Im bliżej końca, tym mniejszy udział świeżej ceny Binance w końcowym TWAP60.
                        lead_weight = min(1.0, max(0.0, rem / 60.0))
                        adjusted = tw_now[1] + (spot - cl_now[1]) * lead_weight
                        op = op_row[1]
                        c = Ctx(self, a, tf, per, win["ts"], rem, adjusted, op, sig, win["slug"], win["end"])
                        c.binance_spot, c.oracle_spot, c.oracle_twap = spot, cl_now[1], tw_now[1]
                    else:
                        c = None  # brak ceny oracle, ceny otwarcia albo reguł TWAP = bez wejścia
                elif tf != "1d":
                    op = self.open_price(a, win["ts"])
                    c = (Ctx(self, a, tf, per, win["ts"], rem, spot, op, sig, win["slug"], win["end"])
                         if (spot and op and sig) else None)
                else:
                    # 1d Up/Down: Binance 1m, zamknięcie o 12:00 ET dziś vs wczoraj; świeca zamyka się minutę po endDate
                    rem_d = rem + 60
                    d0 = datetime.fromtimestamp(win["end"] + et_offset(win["end"]), tz=timezone.utc) - timedelta(days=1)
                    loc = datetime(d0.year, d0.month, d0.day, 12, tzinfo=timezone.utc).timestamp()
                    ts0 = int(loc - et_offset(loc + 5 * 3600))
                    op = self.open_1d(a, ts0)
                    sg = self.sigma_for(a, rem_d)
                    c = (Ctx(self, a, tf, per, ts0, rem_d, spot, op, sg, win["slug"], win["end"] + 60)
                         if (spot and op and sg) else None)
                if c:
                    peers[a] = c
                self.radar[(a, tf)] = {"rem": rem, "c": c, "slug": win["slug"]}
            for c in peers.values():
                c.peers = peers
                self.cur_ctx[(c.asset, c.tf)] = c
            scan_q.append((per, list(peers.values())))
        try:
            self.prefetch_books(now)
        except Exception as e:
            self.warn_once("prefetch", f"prefetch: {type(e).__name__}")
        if trading:
            cand = []
            for per_, cs_ in scan_q:
                for c in cs_:
                    self.scan(c, per_, now, locked, cand)
            # sloty budżetu idą na najlepsze sygnały (BTC pierwszy: reguła okna 'BTC odwrotnie' zakłada, że BTC wchodzi przed altami)
            cand.sort(key=lambda x: (0 if x[3].asset == "BTC" else 1, -x[0]))
            for _edge, s_, sg_, c_, key_ in cand:
                if (s_["id"], c_.slug, sg_.side) in self.side_locked:
                    continue
                if self.execute(s_, sg_, c_, now):
                    self.side_locked.add((s_["id"], c_.slug, sg_.side))
                    if not CFG["both_sides"] or s_["id"] in ANTI_IDS or (s_["id"], c_.slug, other(sg_.side)) in self.side_locked:
                        locked.add(key_)
            try:
                self.counter_pass(now)
            except Exception as e:
                self.warn_once("counter", f"kontra błąd: {type(e).__name__} {str(e)[:40]}")
            try:
                self.leg_pass(now)
            except Exception as e:
                self.warn_once("legs", f"nogi błąd: {type(e).__name__} {str(e)[:40]}")
        if CFG["strike"]:
            try:
                self.step_strike(now, locked, trading)
            except Exception as e:
                self.warn_once("strike", f"strike błąd: {type(e).__name__}")
        for flag, fn, nm in ((CFG["fin"], self.step_fin, "fin"), (CFG["wx"], self.step_wx, "wx")):
            if flag:
                try:
                    fn(now, locked, trading)
                except Exception as e:
                    self.warn_once(nm, f"{nm} błąd: {type(e).__name__}")
        self.exits(now)
        self.settle()
        self.tw_last = dict(self.tw_diag)

    def scan(self, c, per, now, locked, cand=None):
        """Uruchamia aktywne strategie na jednym rynku (max. jedno wejście na (strategia, rynek)).
        cand != None: sygnały są tylko zbierane (przewaga = p - ask), a wejścia robi step() od najlepszego."""
        if CFG["short_only"] and c.tf not in ("5m", "15m") and not (LIVE_CFG["fin_on"] and c.tf == "fin"):
            return                             # tylko krypto 5m/15m; reszta rynków (1h/4h/1d/strike/fin/wx) wyłączona
        for s in self.active:
            key = (s["id"], c.slug)
            hi, lo = s["zone"]
            top = hi * per
            if c.tf in ("strike", "fin", "wx") and s["id"] == 17:
                top = float("inf")             # BIN na strike/finance/pogodzie: w każdej minucie życia rynku
            if c.tf == "wx" and s["id"] not in (3, 17):
                continue                       # pogoda: BIN + SNIPER
            if key in locked or not (max(lo * per, 6) <= c.rem <= top):
                continue
            if c.tf in ORACLE_TFS and c.rem <= twap_cut(c.tf):
                continue
            gap = 20 if (c.tf == "1d" and c.rem > 3600) else CFG["eval_gap"]        # daleko od końca 1d: rzadziej (limit zapytań)
            if (s["id"], c.slug, "Up") in self.side_locked or (s["id"], c.slug, "Down") in self.side_locked:
                gap = max(gap, CFG["bin_second_gap"] if s["id"] == 17 else 10)  # jedna strona już otwarta: druga tylko przy zmianie sygnału, rzadziej pytam o orderbook
            if now - self.last_eval.get(key, 0) < gap:
                continue
            if c.event and self.event_open(s["id"], c.event) >= CFG["strike_cap"]:
                continue
            self.last_eval[key] = now
            if s["id"] == 17 and self.rule_block(c, "Up") and self.rule_block(c, "Down"):
                continue                                 # obie strony zabronione regułami: nie pytam o orderbook
            if s["id"] == 17 and CFG["auto_pair"]:       # druga noga automatycznie, gdy jej kurs >= auto_pair_odds
                for sd_ in ("Up", "Down"):
                    if (17, c.slug, sd_) in self.side_locked and (17, c.slug, other(sd_)) not in self.side_locked:
                        if self.execute(s, Sig(other(sd_), 1.0 / CFG["auto_pair_odds"]), c, now, auto=True):
                            self.side_locked.add((17, c.slug, other(sd_)))
                            locked.add(key)
                        break
                if key in locked:
                    continue
            try:
                res = s["fn"](c)
            except Exception:
                continue
            if res is None:
                continue
            for sg in (res if isinstance(res, list) else [res]):
                if (s["id"], c.slug, sg.side) in self.side_locked:
                    continue                   # ta strona tego rynku już otwarta
                if cand is not None:
                    a_ = c.ask(sg.side)
                    cand.append(((c.p_of(sg.side) - a_) if a_ else 0.0, s, sg, c, key))
                    break
                if self.execute(s, sg, c, now):
                    self.side_locked.add((s["id"], c.slug, sg.side))
                    if not CFG["both_sides"] or s["id"] in ANTI_IDS or (s["id"], c.slug, other(sg.side)) in self.side_locked:
                        locked.add(key)
                    break                      # max. JEDNO wejście na cykl; druga strona dopiero, gdy sama spełni warunki

    def event_open(self, sid, event):
        return sum(1 for t in self.state["trades"]
                   if t["strat"] == sid and t.get("event") == event and t["status"] in LOCK)

    # ---------- rynki "BTC powyżej X" ----------
    def strike_scan(self, now):
        """Awaryjne wyszukiwanie po dacie końca (gdy sluggi wydarzeń nie pasują)."""
        def iso(ts):
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        out = []
        for off in range(0, 3000, 500):
            data = get_json(GAMMA + "/markets", params={
                "active": "true", "closed": "false", "limit": 500, "offset": off,
                "end_date_min": iso(now), "end_date_max": iso(now + CFG["strike_scan"])})
            if not isinstance(data, list):
                break
            out += [m for m in data if strike_info(m)]
            if len(data) < 500:
                break
        return out

    def strike_list(self, now):
        """Aktywne rynki 'BTC above X' kończące się w ciągu strike_scan sekund (odświeżane co 15 s)."""
        if now < self.strike_next:
            return self.strike_cache
        found = {}

        def add(ms):
            for m in ms or []:
                try:
                    info = strike_info(m)
                except Exception:
                    continue
                if not info:
                    continue
                asset, strike, end = info
                slug = m.get("slug")
                if not slug or not (now - 5 < end <= now + CFG["strike_scan"]):
                    continue
                found[slug] = {"slug": slug, "asset": asset, "strike": strike, "end": end, "event": f"{asset}{int(end)}",
                               "hourly": strike_hourly(m)}
                if not (self.market_c.get(slug) or {}).get("m"):
                    self.market_c[slug] = {"m": m, "t": now}

        for slug in strike_event_slugs(now) + CFG["strike_events"]:
            ev = self.ev_c.get(slug)
            if not ev or now >= ev["until"]:
                try:
                    data = get_json(GAMMA + "/events", params={"slug": slug})
                    ms = (data[0].get("markets") if data else None) or []
                    ev = self.ev_c[slug] = {"mk": ms, "until": now + (600 if ms else 90)}
                except Exception:
                    if ev:
                        ev["until"] = now + 20
                    else:
                        ev = self.ev_c[slug] = {"mk": [], "until": now + 30}
            add(ev["mk"])
        if len(self.ev_c) > 120:
            self.ev_c.pop(next(iter(self.ev_c)))
        if now >= self.strike_scan_next:          # skan po dacie końca co 4 min: łapie strike każdej monety (też bez znanego sluga)
            self.strike_scan_next = now + (240 if found else 60)
            try:
                self.strike_scan_mk = self.strike_scan(now)
            except Exception:
                pass
        add(self.strike_scan_mk)
        self.strike_cache = sorted(found.values(), key=lambda w: (w["end"], w["strike"]))
        self.strike_next = now + 15
        return self.strike_cache

    def step_strike(self, now, locked, trading):
        """Strike (krypto 'powyżej X'): P(cena > X o czasie T) z tego samego modelu co okna Up/Down.
        Rozstrzyga zamknięcie świecy 1m (Binance) o T, więc czas do końca liczymy do T+60. Wejścia kończą się tuż przed T.
        BIN gra cały czas życia rynku, SNIPER tylko tuż przed końcem."""
        if not trading:
            return
        per = CFG["strike_horizon"]
        open_bin = {}
        for t in self.state["trades"]:
            if t["strat"] == 17 and t.get("event") and t["status"] in LOCK:
                open_bin[t["event"]] = open_bin.get(t["event"], 0) + 1
        far = []
        for w in self.strike_list(now):
            asset = w.get("asset", "BTC")
            tail = 0 if w.get("hourly") else 60          # godzinowe: świeca 1h kończy się o T; dzienne: świeca 1m o T zamyka się po minucie
            rem = w["end"] + tail - now
            spot, sig = self.spot.get(asset), self.sigma_for(asset, rem)
            if not spot or not sig:
                continue
            if now >= w["end"] - CFG["strike_stop"]:
                continue
            z = math.log(spot / w["strike"]) / (sig * math.sqrt(rem))
            if not (CFG["strike_zmin"] <= abs(z) <= CFG["strike_zmax"]):
                continue
            c = Ctx(self, asset, "strike", per, int(w["end"]), rem, spot, w["strike"], sig, w["slug"], w["end"] + tail)
            c.event = w["event"]
            if rem <= per:
                self.scan(c, per, now, locked)          # blisko końca: SNIPER + BIN co 3 s
            elif (17, c.slug) not in locked and open_bin.get(c.event, 0) < CFG["strike_cap"]:
                far.append(c)
        far.sort(key=lambda c: self.far_t.get(c.slug, 0))
        for c in far[:CFG["strike_far_budget"]]:
            if now - self.far_t.get(c.slug, 0) < CFG["strike_far_every"]:
                break
            self.far_t[c.slug] = now
            self.scan(c, per, now, locked)
        if len(self.far_t) > 800:
            self.far_t.pop(next(iter(self.far_t)))

    # ---------- FINANCE (Pyth) ----------
    def fin_feed(self, lb):
        y = FIN.get(lb, {}).get("y")
        return (y, y) if y else None

    def fin_prices(self, need, now):
        """need = {etykieta: ttl w s}. Odświeża ceny i zmienność z Yahoo (maks. 4 zapytania na cykl)."""
        if now < self.fin_block:
            return
        todo = [lb for lb, ttl in need.items() if lb in FIN and now - self.fin_try.get(lb, 0) >= ttl]
        todo.sort(key=lambda lb: self.fin_try.get(lb, 0))
        for lb in todo[:4]:
            self.fin_try[lb] = now
            try:
                res = yahoo(FIN[lb]["y"], interval="1m", range="1d")
                ts, _op, cl = yahoo_series(res)
                pairs = [(float(t_), float(c_)) for t_, c_ in zip(ts, cl) if c_]
                if not pairs:
                    raise ValueError("brak swiec")
                px_t, px = pairs[-1]
                meta = res.get("meta") or {}
                mp, mt = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
                if mp and mt and float(mt) >= px_t:
                    px, px_t = float(mp), float(mt)
                if px > 0:
                    self.fin_px[lb] = (px, px_t, now)
                sg_ = fin_vol(pairs)
                if sg_:
                    self.fin_sig[lb] = (now, sg_)
                self.fin_err.pop(lb, None)
                self.fin_429 = 0
            except Exception as e:
                code = getattr(getattr(e, "response", None), "status_code", None)
                self.fin_err[lb] = f"{type(e).__name__} {code or ''} {str(e)[:40]}".strip()
                if code == 429:
                    self.fin_429 += 1
                    pause = min(300, 30 * 2 ** min(self.fin_429 - 1, 4))     # 30, 60, 120, 240, 300 s
                    self.fin_block = now + pause
                    self.warn_once("finpx", f"finance: Yahoo limit zapytań (429) - pauza {pause} s")
                    break
                self.warn_once("finpx", f"finance: błąd Yahoo ({lb}: {type(e).__name__} {code or ''})".replace("  ", " "))

    def fin_sigma(self, lb, now):
        c = self.fin_sig.get(lb)
        return c[1] if c and now - c[0] < 300 else None

    def fin_open(self, lb, start):
        """Cena otwarcia (Yahoo) w chwili startu rynku Up/Down."""
        k = (lb, int(start))
        if k in self.fin_op:
            return self.fin_op[k]
        if time.time() - self.fin_op_try.get(k, 0) < 60:
            return None
        self.fin_op_try[k] = time.time()
        try:
            res = yahoo(FIN[lb]["y"], interval="1m", period1=int(start) - 120, period2=int(start) + 900,
                        includePrePost="true")
            ts, op, _cl = yahoo_series(res)
            for t_, o_ in zip(ts, op):
                if t_ >= int(start) - 1 and o_:
                    if t_ - int(start) > 900:
                        break                    # pierwszy bar dopiero długo po starcie: cena otwarcia niewiarygodna
                    self.fin_op[k] = float(o_)
                    return self.fin_op[k]
        except Exception:
            pass
        return None

    def fin_list(self, now):
        if now < self.fin_next:
            return self.fin_cache
        found = {}
        for lb, spec in FIN.items():
            try:
                data = get_json(GAMMA + "/public-search",
                                params={"q": spec["q"], "limit_per_type": 30, "events_status": "active"})
            except Exception:
                continue
            for ev in data.get("events") or []:
                for m in ev.get("markets") or []:
                    w = fin_classify(m, ev, now)
                    if w and w["slug"]:
                        found[w["slug"]] = w
                        if not (self.market_c.get(w["slug"]) or {}).get("m"):
                            self.market_c[w["slug"]] = {"m": m, "t": now}
        self.fin_cache = sorted(found.values(), key=lambda w: (w["end"], w["label"]))
        self.fin_next = now + 120
        return self.fin_cache

    def step_fin(self, now, locked, trading):
        ws = self.fin_list(now)
        if not ws or not trading:
            return
        per = CFG["strike_horizon"]
        need = {}
        for w in ws:
            if now >= w["end"] - CFG["strike_stop"]:
                continue
            ttl = 5 if w["end"] - now <= per else 20        # blisko końca odświeżam częściej
            need[w["label"]] = min(need.get(w["label"], 99), ttl)
        self.fin_prices(need, now)
        for w in ws:
            lb = w["label"]
            px = self.fin_px.get(lb)
            if not px or now - px[2] > 60 or now - px[1] > 150:     # tylko świeża cena (rynek otwarty)
                continue
            if now >= w["end"] - CFG["strike_stop"] or ((17, w["slug"]) in locked and (3, w["slug"]) in locked):
                continue
            rem = w["end"] - now
            if rem > per and now - self.far_t.get(w["slug"], 0) < CFG["strike_far_every"]:
                continue
            ref = w["strike"] if w["kind"] == "above" else self.fin_open(lb, w["start"])
            sig = self.fin_sigma(lb, now)
            if not ref or not sig:
                continue
            sig = sig * math.sqrt((rem + max(0.0, now - px[1])) / rem)   # wiek ceny Yahoo = dodatkowa wariancja
            z = math.log(px[0] / ref) / (sig * math.sqrt(rem))
            if not (CFG["strike_zmin"] <= abs(z) <= CFG["strike_zmax"]):
                continue
            if rem > per:
                self.far_t[w["slug"]] = now
            c = Ctx(self, lb, "fin", per, int(w["end"]), rem, px[0], ref, sig, w["slug"], w["end"])
            c.event = f"FIN{lb}{int(w['end'])}"
            c.label = lb + (f">{ref:g}" if w["kind"] == "above" else " U/D")
            self.scan(c, per, now, locked)

    # ---------- POGODA (Open-Meteo) ----------
    def wx_fc(self, city, unit, now):
        k = (city, unit)
        c = self.wx_fc_c.get(k)
        if c and now - c[0] < 900:
            return c[1]
        fc = None
        try:
            lat, lon = WX_CITIES[city]
            d = get_json(OPENMETEO, params={
                "latitude": lat, "longitude": lon, "hourly": "temperature_2m", "timezone": "auto",
                "forecast_days": 4, "past_days": 1,
                "temperature_unit": "fahrenheit" if unit == "F" else "celsius"})
            days = {}
            for tm, tv in zip(d["hourly"]["time"], d["hourly"]["temperature_2m"]):
                if tv is None:
                    continue
                dt = datetime.strptime(tm, "%Y-%m-%dT%H:%M")
                days.setdefault(tm[:10], []).append((dt.hour + dt.minute / 60, float(tv)))
            fc = {"off": int(d.get("utc_offset_seconds", 0)), "days": days}
        except Exception:
            pass
        self.wx_fc_c[k] = (now if fc else now - 840, fc)
        return fc

    def wx_ensemble_fc(self, city, unit, now):
        """ECMWF IFS ensemble: hourly temperature members, cached 15 min.
        Fails closed (None) if a valid ensemble with enough members is unavailable.
        """
        key = (city, unit)
        cached = self.wx_ens_c.get(key)
        if cached and now - cached[0] < (1800 if cached[1] else 60):     # model liczy się co 6 h - 30 min wystarcza
            return cached[1]
        fc = None
        try:
            lat, lon = WX_CITIES[city]
            data = get_json(OPENMETEO_ENSEMBLE, params={
                "latitude": lat,
                "longitude": lon,
                "hourly": "temperature_2m",
                "models": "ecmwf_ifs025_ensemble",
                "timezone": "auto",
                "forecast_days": 4,
                "temperature_unit": "fahrenheit" if unit == "F" else "celsius",
                "cell_selection": "land",
            })
            hourly = data.get("hourly") or {}
            times = hourly.get("time") or []
            members = []
            for name, values in hourly.items():
                lname = str(name).lower()
                if name == "time" or "temperature_2m" not in lname or "member" not in lname:
                    continue
                if not isinstance(values, list) or len(values) != len(times):
                    continue
                arr = []
                for value in values:
                    try:
                        arr.append(float(value) if value is not None else None)
                    except (TypeError, ValueError):
                        arr.append(None)
                members.append(arr)
            # 20 is a fail-closed minimum; ECMWF IFS ensemble normally supplies 51 members.
            if times and len(members) >= 20:
                dh = [(str(x)[:10], int(str(x)[11:13]) + int(str(x)[14:16]) / 60.0) for x in times]
                fc = {"times": times, "dh": dh, "members": members, "t": now,
                      "off": int(data.get("utc_offset_seconds", 0))}
        except Exception:
            fc = None
        self.wx_ens_c[key] = (now, fc)
        return fc

    def wx_day_maxes(self, w, now, ens):
        """Dzienne maksima (w jednostce rynku) każdego członka ensemble dla daty rynku + rozmycie sigma.
        Dla dnia dzisiejszego: minione godziny zastępuje maksimum z dotychczasowego przebiegu (Open-Meteo).
        Dla dni przyszłych: środek rozkładu lekko przesunięty ku prognozie deterministycznej (wyższa rozdzielczość,
        lepiej łapie lokalne odchylenia stacji od komórki siatki). Wynik w cache."""
        target = w["date"]
        local_now = datetime.fromtimestamp(now + ens["off"], tz=timezone.utc).replace(tzinfo=None)
        today = local_now.strftime("%Y-%m-%d")
        hour_now = local_now.hour + local_now.minute / 60
        if target < today:
            return None
        is_today = target == today
        base = self.wx_fc(w["city"], w["unit"], now)
        key = (w["city"], w["unit"], target, ens.get("t"), int(now // 300) if is_today else 0,
               int((self.wx_fc_c.get((w["city"], w["unit"])) or (0,))[0]))
        hit = self.wx_dm_c.get(key)
        if hit is not None:
            return hit or None
        out = None
        lower = None
        if is_today:
            day = (base or {}).get("days", {}).get(target) or []
            observed = [tv for hh, tv in day if hh <= hour_now]
            lower = max(observed) if observed else None
        if not (is_today and lower is None):
            maxes = []
            for member in ens["members"]:
                vals = [tv for (dd, hh), tv in zip(ens["dh"], member)
                        if tv is not None and dd == target and not (is_today and hh <= hour_now)]
                if vals:
                    mx = max(vals) if lower is None else max(max(vals), lower)
                elif lower is not None:
                    mx = lower
                else:
                    continue
                maxes.append(mx)
            if len(maxes) >= 20:
                shift = 0.0
                if not is_today and CFG["wx_det_w"] > 0 and base:
                    dv = [tv for _hh, tv in (base.get("days", {}).get(target) or [])]
                    if len(dv) >= 20:               # pełny dzień prognozy deterministycznej
                        cap = CFG["wx_det_cap"] * (1.8 if w["unit"] == "F" else 1.0)
                        diff = max(dv) - sum(maxes) / len(maxes)
                        shift = max(-cap, min(cap, CFG["wx_det_w"] * diff))
                        maxes = [x + shift for x in maxes]
                days_ahead = (datetime.strptime(target, "%Y-%m-%d") - datetime.strptime(today, "%Y-%m-%d")).days
                out = {"maxes": maxes, "shift": shift, "mean": sum(maxes) / len(maxes),
                       "sigma": wx_sigma(days_ahead, w["unit"], hour_now if is_today else None)}
        if len(self.wx_dm_c) > 400:
            self.wx_dm_c.clear()
        self.wx_dm_c[key] = out or False
        return out

    def wx_prob(self, w, now):
        """P(Yes) = średnia po członkach ECMWF IFS ensemble z rozmytym (kernel dressing) maksimum dnia: surowe
        zliczanie 51 członków daje fałszywe 0%/1% na sąsiednich przedziałach (ensemble jest za wąski względem stacji).
        Brak ensemble albo brak danych = brak zakładu (bez zapasowego rozkładu normalnego)."""
        ens = self.wx_ensemble_fc(w["city"], w["unit"], now)
        if not ens:
            return None
        try:
            dm = self.wx_day_maxes(w, now, ens)
            if not dm:
                return None
            p = wx_bucket_prob(dm["maxes"], dm["sigma"], w["lo"], w["hi"])
            return min(0.97, max(0.03, p))
        except Exception:
            return None

    def wx_list(self, now):
        if now < self.wx_next:
            return self.wx_cache
        found = {}
        for page in (1, 2, 3, 4, 5, 6, 7, 8):
            try:
                data = get_json(GAMMA + "/public-search", params={
                    "q": "highest temperature", "limit_per_type": 50, "page": page, "events_status": "active"})
            except Exception:
                break
            evs = data.get("events") or []
            for ev in evs:
                for m in ev.get("markets") or []:
                    w = parse_wx(m, now)
                    if w and w["slug"]:
                        found[w["slug"]] = w
                        if not (self.market_c.get(w["slug"]) or {}).get("m"):
                            self.market_c[w["slug"]] = {"m": m, "t": now}
                    else:
                        qq = str(m.get("question") or "")
                        mu = re.search(r"highest temperature in (.+?)\s+(?:be|on|reach|exceed)\b", qq, re.I)
                        if mu and not m.get("closed") and mu.group(1).strip().lower() not in WX_CITIES:
                            self.wx_unknown.add(mu.group(1).strip().lower())
            if not evs:
                break
        if self.wx_unknown:
            self.warn_once("wxunk", "pogoda: brak miasta na liście: " + ", ".join(sorted(self.wx_unknown))[:90], every=600)
        self.wx_cache = sorted(found.values(), key=lambda w: (w["end"], w["city"], w["lo"]))
        self.wx_next = now + 120
        return self.wx_cache

    def step_wx(self, now, locked, trading):
        ws = self.wx_list(now)
        if not ws or not trading:
            return
        need, per, done = CFG["bin_edge_wx"], CFG["strike_horizon"], 0
        for w in ws:
            if now >= w["end"] - 30 or (17, w["slug"]) in locked or now - self.far_t.get(w["slug"], 0) < 20:
                continue
            fair = self.wx_prob(w, now)
            if fair is None:
                continue
            yp = w.get("yes_px")
            if yp is not None and w["end"] - now > per * 0.1 and not (fair - BIN_HAIRCUT - yp >= need - 0.06 or (1 - fair) - BIN_HAIRCUT - (1 - yp) >= need - 0.06):
                continue                 # wstępny filtr po cenach z wyszukiwarki (bez zapytania o orderbook)
            if done >= 8:
                break
            done += 1
            self.far_t[w["slug"]] = now
            rem = w["end"] - now
            c = Ctx(self, w["city"].title(), "wx", per, int(w["end"]), rem, 1.0, 1.0, 1e-3, w["slug"], w["end"])
            c.fair = fair
            c.p_up = 0.5 + (fair - 0.5) * CFG["shrink"]
            c.event = f"WX{w['city']}{w['date']}"
            c.label = w["label"]
            self.scan(c, per, now, locked)

    # ---------- statystyki ----------
    def in_scope(self, t):
        """Czy transakcja liczy się do statystyk (IMPORT: otwarte zawsze, zamknięte od momentu startu statystyk)."""
        if t["strat"] == 0:
            return t["status"] in LOCK or t.get("t_close", t["t_open"]) >= self.since
        return t["strat"] in self.active_ids and t["t_open"] >= self.since

    def stats(self, sid=None, asset=None, tf=None):
        tr = [t for t in self.state["trades"]
              if self.in_scope(t)
              and (sid is None or t["strat"] == sid)
              and (asset is None or t["asset"] == asset)
              and (tf is None or t["tf"] == tf)]
        closed = sorted((t for t in tr if t["status"] in ("won", "lost")),
                        key=lambda t: t.get("t_close", t["end_ts"]))
        wins = [t for t in closed if t["status"] == "won"]
        losses = [t for t in closed if t["status"] == "lost"]
        opn = [t for t in tr if t["status"] in ("pending", "open")]
        placed = [t for t in tr if t["status"] in ("open", "won", "lost") and t["strat"] != 0]   # edge/cena: tylko bot
        staked = sum(t["cost"] for t in closed)
        pnl = sum(t["pnl"] for t in closed)
        cum = peak = dd = 0.0
        streak = max_ls = 0
        for t in closed:
            cum += t["pnl"]
            peak = max(peak, cum)
            dd = max(dd, peak - cum)
            if t["status"] == "won":
                streak = streak + 1 if streak > 0 else 1
            else:
                streak = streak - 1 if streak < 0 else -1
                max_ls = max(max_ls, -streak)
        gw = sum(t["pnl"] for t in wins)
        gl = -sum(t["pnl"] for t in losses)
        return {
            "n": len(closed), "open": len(opn), "wins": len(wins), "losses": len(losses),
            "check": sum(1 for t in tr if t["status"] == "check"),
            "wr": (len(wins) / len(closed) * 100) if closed else None,
            "pnl": pnl, "staked": staked,
            "roi": (pnl / staked * 100) if staked else None,
            "dd": dd, "max_ls": max_ls, "streak": streak,
            "pf": (gw / gl) if gl > 0 else None,
            "avg_win": (gw / len(wins)) if wins else None,
            "avg_loss": (-gl / len(losses)) if losses else None,
            "exp": (pnl / len(closed)) if closed else None,
            "avg_entry": (sum(t["entry"] for t in placed) / len(placed) * 100) if placed else None,
            "avg_edge": (sum(t["edge"] for t in placed) / len(placed) * 100) if placed else None,
            "best": max((t["pnl"] for t in closed), default=None),
            "worst": min((t["pnl"] for t in closed), default=None),
            "exposure": sum(t["cost"] for t in tr if t["status"] in LOCK),
        }

    # ---------- widok ----------
    @staticmethod
    def money(v, dec=2):
        if v is None:
            return Text("-", style="dim")
        return Text(f"{v:+.{dec}f}", style="green" if v > 0 else "red" if v < 0 else "white")

    @staticmethod
    def pct(v):
        if v is None:
            return Text("-", style="dim")
        return Text(f"{v:.1f}%", style="green" if v >= 55 else "yellow" if v >= 45 else "red")

    @staticmethod
    def roi_t(v):
        if v is None:
            return Text("-", style="dim")
        return Text(f"{v:+.1f}%", style="green" if v > 0 else "red" if v < 0 else "white")

    @staticmethod
    def fnum(v, fmt="{:.2f}", suf=""):
        return "-" if v is None else fmt.format(v) + suf

    def render_main(self):
        now_ = time.time()
        up = int(now_ - self.state["start"])
        bal = self.balance_now()
        fs = {s["id"]: self.vstats(s["id"]) for s in self.active}
        n_tot = sum(f["n"] for f in fs.values())
        pnl_tot = sum(f["pnl"] for f in fs.values())
        n_open = sum(f["open"] for f in fs.values())
        n_chk = sum(f["check"] for f in fs.values())
        expo = sum(self.exposure(s["id"]) for s in self.active)
        head = Table.grid(padding=(0, 1))
        head.add_column(); head.add_column(justify="right"); head.add_column(); head.add_column(justify="right")
        head.add_row("PnL Σ $", self.money(pnl_tot if n_tot else None), "Saldo Σ", Text("-" if bal is None else f"${bal:,.2f}", style="bold"))
        head.add_row("Otwarte", Text(str(n_open), style="cyan"), "Zamknięte", Text(str(n_tot)))
        head.add_row("W grze $", Text(f"{expo:.2f}"), "Budżet/wariant", Text(f"${self.sim_budget or 0:.0f}"))
        if n_chk:
            head.add_row(Text("SPRAWDŹ", style="bold yellow"), Text(str(n_chk), style="bold yellow"), "", "")
        head.add_row("Binance", Text(self.api["binance"], style="green" if self.api["binance"] == "OK" else "yellow"),
                     "Polymarket", Text(self.api["polymarket"], style="green" if self.api["polymarket"] == "OK" else "red"))
        ost = self.oracle.status()
        head.add_row("TWAP60", Text("WYŁĄCZONY", style="bold black on yellow"),
                     "Sygnał", Text("tylko Binance", style="cyan"))
        head.add_row("Czas pracy", Text(f"{up//3600}h{up%3600//60:02d}m", style="dim"), "Tryb",
                     Text("DRY-RUN", style="bold black on yellow"))
        p1 = Panel(head, title=f"[bold]KAPSKO[/bold] | {len(self.active)} wariantów | 5m+15m | start ${self.stake:.2f}",
                   border_style="cyan")
        tv = Table(title="Warianty", box=box.SIMPLE_HEAVY, expand=True, pad_edge=False)
        for cn, j_ in [("Wariant", "left"), ("Zak", "right"), ("Ot", "right"), ("Win%", "right"),
                       ("PnL $", "right"), ("Saldo", "right"), ("Staw", "right")]:
            tv.add_column(cn, justify=j_, no_wrap=True)
        for s_ in self.active:
            f = fs[s_["id"]]
            tv.add_row(short_name(s_["name"]), str(f["n"]), str(f["open"]), self.pct(f["wr"]),
                       self.money(f["pnl"] if f["n"] else None),
                       "-" if f["eq_now"] is None else f"{f['eq_now']:.2f}", f"{f['stake_now']:.2f}")
        parts = [self.nav(), p1, tv]
        if self.show_radar:
            r = Table(title="Radar (na żywo)", box=box.SIMPLE, expand=True)
            for cn, j in [("Rynek", "left"), ("Zostało", "right"), ("Model", "right"), ("Ask U/D", "right"), ("Poz.", "right")]:
                r.add_column(cn, justify=j, no_wrap=True)
            for (a, tf), x in self.radar.items():
                c, rem = x["c"], x["rem"]
                seen = self.ask_seen.get((a, tf), {})
                asks = "-"
                if seen.get("slug") == x["slug"]:
                    u, d = seen.get("Up"), seen.get("Down")
                    asks = (f"{u*100:.0f}/" if u else "-/") + (f"{d*100:.0f}" if d else "-")
                npos = sum(1 for tr in self.state["trades"] if tr["slug"] == x["slug"] and tr["status"] in LOCK)
                side, p = c.best() if c else (None, None)
                rem_s = f"{int(rem)//60}:{int(rem)%60:02d}"
                r.add_row(f"{a} {tf}", rem_s if x["slug"] != "-" else "brak",
                          f"{side} {p*100:.0f}%" if c else "-", asks, str(npos) if npos else "-")
            parts.append(r)
        names = {s["id"]: s["name"] for s in STRATS}
        o = Table(title="Ostatnie transakcje", box=box.SIMPLE, expand=True)
        for cn, j in [("Czas", "left"), ("Wariant", "left"), ("Rynek", "left"), ("Str.", "left"),
                      ("Cena", "right"), ("Wynik", "left"), ("PnL $", "right")]:
            o.add_column(cn, justify=j, no_wrap=True)
        recent = sorted((x for x in self.state["trades"]
                         if x["strat"] != 0 and x["strat"] in self.active_ids and x["t_open"] >= self.since),
                        key=lambda z: z["t_open"], reverse=True)[:6]
        for tr in recent:
            st = {"pending": Text("wysyłam", style="yellow"), "open": Text("otwarta", style="cyan"),
                  "check": Text("SPRAWDŹ", style="bold yellow"),
                  "won": Text("WIN" + (" TP" if tr.get("exit") else ""), style="green"),
                  "lost": Text("LOSS" + (" TP" if tr.get("exit") else ""), style="red")}[tr["status"]]
            o.add_row(time.strftime("%H:%M:%S", time.localtime(tr["t_open"])), short_name(names.get(tr["strat"], "?")),
                      mkt_label(tr), trade_side(tr), f"{tr['entry']*100:.0f}c", st,
                      self.money(tr["pnl"]) if tr["status"] in ("won", "lost") else Text("-", style="dim"))
        parts.append(o)
        parts.append(Text("\n".join(self.log) or "-", style="dim"))
        parts.append(Text("Klawisze 1-9 = strony, n = następna, g = grupa wariantów. Pełny raport: python kupsko.py --stats. Ctrl+C = stop i zapis.",
                          style="dim italic"))
        return Group(*parts)

    # ---------- rozszerzone statystyki wariantu ----------
    def fstats(self, sid):
        from statistics import median, stdev
        now = time.time()
        tr = [t for t in self.state["trades"] if t["strat"] == sid and t["t_open"] >= self.since]
        closed = sorted((t for t in tr if t["status"] in ("won", "lost")), key=lambda t: t.get("t_close", t["end_ts"]))
        wins = [t for t in closed if t["status"] == "won"]
        losses = [t for t in closed if t["status"] == "lost"]
        placed = [t for t in tr if t["status"] in ("open", "won", "lost")]
        n, bud = len(closed), (self.sim_budget or 0.0)
        pnls = [t["pnl"] for t in closed]
        gw, gl = sum(t["pnl"] for t in wins), -sum(t["pnl"] for t in losses)
        r = {"n": n, "wins": len(wins), "losses": len(losses), "gw": gw, "gl": gl,
             "open": sum(1 for t in tr if t["status"] in ("pending", "open")),
             "check": sum(1 for t in tr if t["status"] == "check")}
        r["wr"] = len(wins) / n * 100 if n else None
        r["wr_lo"], r["wr_hi"] = wilson(len(wins), n)
        r["pnl"] = sum(pnls)
        r["staked"] = sum(t["cost"] for t in closed)
        r["roi"] = r["pnl"] / r["staked"] * 100 if r["staked"] else None
        r["ret"] = r["pnl"] / bud * 100 if bud else None
        r["exp"] = r["pnl"] / n if n else None
        pc = [t["pnl"] / t["cost"] for t in closed if t.get("cost")]
        r["exp_pct"] = _mean(pc) * 100 if pc else None
        r["avg_win"] = gw / len(wins) if wins else None
        r["avg_loss"] = -gl / len(losses) if losses else None
        r["payoff"] = r["avg_win"] / -r["avg_loss"] if wins and losses and gl > 0 else None
        r["pf"] = gw / gl if gl > 0 else None
        r["be_wr"] = r["wr_edge"] = r["kelly"] = None
        if wins and losses and gw + gl > 0:
            W, L = gw / len(wins), gl / len(losses)
            r["be_wr"] = L / (W + L) * 100                      # próg opłacalności: tyle % wygranych daje PnL = 0
            r["wr_edge"] = r["wr"] - r["be_wr"]
        if r["payoff"] and r["wr"] is not None:
            wf = r["wr"] / 100
            r["kelly"] = (wf - (1 - wf) / r["payoff"]) * 100
        r["med"] = median(pnls) if pnls else None
        r["sd"] = r["tstat"] = r["sharpe"] = None
        if n >= 2:
            r["sd"] = stdev(pnls)
            if r["sd"] > 0:
                m = r["pnl"] / n
                r["tstat"], r["sharpe"] = m / (r["sd"] / math.sqrt(n)), m / r["sd"]
        r["best"], r["worst"] = (max(pnls), min(pnls)) if pnls else (None, None)
        # krzywa kapitału, obsunięcie, serie
        cum = peak = dd = lo = hi = 0.0
        cur = mws = mls = 0
        for t in closed:
            cum += t["pnl"]
            peak, lo, hi = max(peak, cum), min(lo, cum), max(hi, cum)
            dd = max(dd, peak - cum)
            if t["status"] == "won":
                cur = cur + 1 if cur > 0 else 1
                mws = max(mws, cur)
            else:
                cur = cur - 1 if cur < 0 else -1
                mls = max(mls, -cur)
        r.update(dd=dd if n else None, dd_pct=(dd / bud * 100 if bud and n else None),
                 rec=(r["pnl"] / dd if dd > 0 else None), mws=mws if n else None, mls=mls if n else None, cur=cur,
                 eq_now=(self.wallet(sid) if self.sim_budget else None),
                 eq_min=(bud + lo if bud and n else None), eq_max=(bud + hi if bud and n else None))
        l10 = closed[-10:]
        r["l10_pnl"] = sum(t["pnl"] for t in l10) if l10 else None
        r["l10_w"] = sum(1 for t in l10 if t["status"] == "won")
        r["l10_l"] = len(l10) - r["l10_w"]
        # take-profit vs rozliczenie
        tp = [t for t in closed if t.get("exit") == "TP"]
        rs = [t for t in closed if t.get("exit") != "TP"]
        r["tp_n"], r["tp_pct"] = len(tp), (len(tp) / n * 100 if n else None)
        r["tp_w"] = sum(1 for t in tp if t["pnl"] > 0)
        r["tp_l"] = len(tp) - r["tp_w"]
        r["rs_w"] = sum(1 for t in rs if t["status"] == "won")
        r["rs_l"] = len(rs) - r["rs_w"]
        x = _mean(t["exit_px"] for t in tp if t.get("exit_px"))
        r["tp_px"] = x * 100 if x is not None else None
        r["tp_secs"] = _mean(t["t_close"] - t["t_open"] for t in tp if t.get("t_close"))
        r["tp_avg"], r["rs_avg"] = _mean(t["pnl"] for t in tp), _mean(t["pnl"] for t in rs)
        # wejścia
        ent = sorted(t["entry"] for t in placed)
        r["e_avg"] = _mean(ent) * 100 if ent else None
        r["e_med"] = median(ent) * 100 if ent else None
        r["e_min"], r["e_max"] = (ent[0] * 100, ent[-1] * 100) if ent else (None, None)
        r["p_avg"] = _mean(t["p"] for t in placed) * 100 if placed else None
        r["edge_avg"] = _mean(t["edge"] for t in placed) * 100 if placed else None
        r["sh_avg"] = _mean(t["shares"] for t in placed)
        r["cost_avg"] = _mean(t["cost"] for t in placed)
        r["mkts"] = len({t["slug"] for t in tr}) if tr else None
        r["up_pct"] = sum(1 for t in placed if t["side"] == "Up") / len(placed) * 100 if placed else None
        # opłaty
        fi, fo = sum(t.get("fee_in", 0.0) for t in placed), sum(t.get("fee_out", 0.0) for t in closed)
        r["fees"] = (fi + fo) if placed else None
        r["fee_tr"] = (fi + fo) / n if n else None
        r["fee_gw"] = (fi + fo) / gw * 100 if gw > 0 else None
        # czas
        r["hold"] = _mean(t["t_close"] - t["t_open"] for t in closed if t.get("t_close"))
        r["rem_in"] = _mean(t["rem_in"] for t in placed if t.get("rem_in") is not None)
        hrs = max((now - self.since) / 3600, 1e-9)
        r["hrs"], r["per_h"], r["pnl_h"] = hrs, n / hrs, r["pnl"] / hrs
        # ekstrema ceny bid w czasie trzymania
        his = [t["hi_bid"] for t in placed if t.get("hi_bid")]
        los = [t["lo_bid"] for t in placed if t.get("hi_bid") and t.get("lo_bid") is not None]
        r["hi_avg"] = _mean(his) * 100 if his else None
        r["lo_avg"] = _mean(los) * 100 if los else None
        for lv in (70, 80, 90):
            r[f"t{lv}"] = sum(1 for h in his if h >= lv / 100 - 1e-9) / len(his) * 100 if his else None
        # --- dodatkowe metryki ---
        mfe = [(t["hi_bid"] - t["entry"]) * 100 for t in placed if t.get("hi_bid")]
        mae = [(t["entry"] - t["lo_bid"]) * 100 for t in placed if t.get("hi_bid") and t.get("lo_bid") is not None]
        r["mfe"], r["mae"] = _mean(mfe), _mean(mae)
        r["mfe5"] = sum(1 for x in mfe if x >= 5) / len(mfe) * 100 if mfe else None
        r["mae10"] = sum(1 for x in mae if x >= 10) / len(mae) * 100 if mae else None
        dn = [p for p in pnls if p < 0]
        dsd = math.sqrt(sum(p * p for p in dn) / n) if n and dn else 0.0
        r["sortino"] = (r["pnl"] / n) / dsd if dsd > 0 else None
        rs_set = [t for t in closed if t.get("exit") != "TP"]
        r["bin_wr"] = sum(1 for t in rs_set if t["status"] == "lost") / len(rs_set) * 100 if rs_set else None
        r["mkt_cal"] = (r["wr"] - r["e_avg"]) if (r["wr"] is not None and r["e_avg"] is not None) else None
        r["mdl_cal"] = (r["wr"] - r["p_avg"]) if (r["wr"] is not None and r["p_avg"] is not None) else None
        x_ = _mean(t["spr_in"] for t in placed if t.get("spr_in") is not None)
        r["spr"] = x_ * 100 if x_ is not None else None
        pcts = [t for t in tr if t["status"] == "open" and t.get("pnl_pct") is not None and t.get("cost")]
        r["unreal"] = sum(t["pnl_pct"] * t["cost"] for t in pcts) if pcts else None
        r["pnl_tot"] = r["pnl"] + (r["unreal"] or 0.0)
        ev = []
        for t in placed:
            s0 = t["t_open"]
            e0 = now if t["status"] == "open" else t.get("t_close", t["end_ts"])
            ev.append((s0, 1, t["cost"]))
            ev.append((max(e0, s0), -1, -t["cost"]))
        ev.sort(key=lambda x: (x[0], x[1]))
        cur_n = pk_n = 0
        cc = pk_c = 0.0
        for _, d_, cst in ev:
            cur_n += d_
            cc += cst
            pk_n, pk_c = max(pk_n, cur_n), max(pk_c, cc)
        r["peak_n"], r["peak_cost"] = (pk_n, pk_c) if placed else (None, None)
        return r

    def vstats(self, sid):
        """fstats + statystyki stawki rosnącej i ponownych wejść (re-wejść po TP)."""
        r = self.fstats(sid)
        bud = self.sim_budget or 0.0
        tr = self.scoped(sid)
        placed = [t for t in tr if t["status"] in ("open", "won", "lost")]
        closed = sorted((t for t in tr if t["status"] in ("won", "lost")), key=lambda t: t.get("t_close", t["end_ts"]))
        sch = STAKE_OF.get(sid)
        r["stake_now"], r["lvl"] = self.stake_for(sid), self.stake_level(sid)
        stk = [t.get("stake", t["cost"]) for t in placed]
        r["stake_avg"], r["stake_max"] = _mean(stk), (max(stk) if stk else None)
        lv = [t.get("lvl", 0) for t in placed]
        r["lvl_max"] = max(lv) if lv else None
        real = sum(t["pnl"] for t in closed)
        r["bank"] = bud + real if bud else None
        r["bank_g"] = real / bud * 100 if bud else None
        r["to_next"] = ((r["lvl"] + 1) * sch[0] * bud - real) if (sch and bud) else None
        r["stake_pct"] = r["stake_now"] / r["bank"] * 100 if r["bank"] else None
        eq = peak = bud
        ddp = 0.0
        for t in closed:
            eq += t["pnl"]
            peak = max(peak, eq)
            ddp = max(ddp, (peak - eq) / peak * 100 if peak > 0 else 0.0)
        r["eq_peak"], r["dd_eq"] = (peak if closed else None), (ddp if closed else None)
        r["turn"] = sum(t["cost"] for t in placed) if placed else None
        r["turn_x"] = (r["turn"] / bud) if (placed and bud) else None
        by = {}
        for t in placed:
            by.setdefault(t["slug"], []).append(t)
        r["entries"] = len(placed) or None
        r["mk_played"] = len(by) or None
        r["ent_per_mkt"] = (len(placed) / len(by)) if by else None
        r["mk_re"] = sum(1 for v in by.values() if len(v) > 1) if by else None
        re_ = [t for t in placed if (t.get("leg") or 1) > 1]
        fi = [t for t in placed if (t.get("leg") or 1) <= 1]
        cl = lambda L: [t for t in L if t["status"] in ("won", "lost")]
        r["re_n"], r["re_closed"] = len(re_), len(cl(re_))
        r["re_pnl"] = sum(t["pnl"] for t in cl(re_)) if cl(re_) else None
        r["first_pnl"] = sum(t["pnl"] for t in cl(fi)) if cl(fi) else None
        r["re_wr"] = (sum(1 for t in cl(re_) if t["status"] == "won") / len(cl(re_)) * 100) if cl(re_) else None
        gaps = []
        for v in by.values():
            v.sort(key=lambda t: t["t_open"])
            for a_, b_ in zip(v, v[1:]):
                if a_.get("t_close"):
                    gaps.append(b_["t_open"] - a_["t_close"])
        r["re_gap"] = _mean(gaps)
        r["lvl_pnl"] = (r["pnl"] / r["lvl_max"]) if r["lvl_max"] else None
        return r

    def _all_v(self):
        """vstats wszystkich aktywnych wariantów (cache 1.5 s, żeby odświeżanie ekranu nie liczyło wszystkiego od nowa)."""
        c = getattr(self, "_vcache", None)
        if c and time.time() - c[0] < 1.5:
            return c[1]
        fa = {x["id"]: self.vstats(x["id"]) for x in self.active}
        self._vcache = (time.time(), fa)
        return fa

    def rank_tables(self, kind="map", window=0):
        """kind: 'map' = mapy schemat x wyjście + zbiorówki; 'a' = ranking wynik/ryzyko/pozycja/stawka;
        'b' = ranking TP/jakość/kapitał. window>0 = tylko okno wierszy (klawisz g)."""
        names = {x["id"]: x["name"] for x in STRATS}
        fa = self._all_v()
        allids = [x["id"] for x in self.active]
        order = sorted(allids, key=lambda i: -(fa[i]["eq_now"] if fa[i]["eq_now"] is not None else 0.0))
        pos0 = {sid: k for k, sid in enumerate(order, 1)}

        def mk(title, cols):
            t = Table(title=title, box=box.SIMPLE, expand=True, pad_edge=False, show_edge=False)
            for cn, j_ in cols:
                t.add_column(cn, justify=j_, no_wrap=True)
            return t
        bud = self.sim_budget or 0.0
        played = [i for i in allids if fa[i]["n"]]
        if kind == "map":
            exits = [e for e in dict.fromkeys(v["exit"] for v in VARIANTS) if any(VAR_BY_ID[i]["exit"] == e for i in allids)]
            schemes = [k for k in STAKE_SCHEMES if any(VAR_BY_ID[i]["scheme"] == k for i in allids)]
            cell = {(VAR_BY_ID[i]["scheme"], VAR_BY_ID[i]["exit"]): i for i in allids}
            ex_lab = lambda e: e.replace("TP", "") if e.startswith("TP") else "H"

            def matrix(title, fn, base, hi_good=True, fmt="{:.1f}"):
                vals = [fn(fa[i]) for i in played if fn(fa[i]) is not None]
                best = (max if hi_good else min)(vals) if vals else None
                t = mk(title, [("", "left")] + [(ex_lab(e), "right") for e in exits])
                for k in schemes:
                    row = [Text(f"{k} {SCHEME_LABEL[k]}", style="bold")]
                    for e in exits:
                        i = cell.get((k, e))
                        v = fn(fa[i]) if (i is not None and fa[i]["n"]) else None
                        if v is None:
                            row.append(Text("-", style="dim"))
                            continue
                        good = (v > base) if hi_good else (v < base)
                        bad = (v < base) if hi_good else (v > base)
                        st = "bold black on green" if v == best else "green" if good else "red" if bad else "white"
                        row.append(Text(fmt.format(v), style=st))
                    t.add_row(*row)
                return t
            out = []
            if played:
                top = max(played, key=lambda i: fa[i]["eq_now"] if fa[i]["eq_now"] is not None else -1e9)
                low = min(played, key=lambda i: fa[i]["eq_now"] if fa[i]["eq_now"] is not None else 1e9)
                tot_pnl = sum(fa[i]["pnl"] for i in played)
                tot_n = sum(fa[i]["n"] for i in played)
                tot_w = sum(fa[i]["wins"] for i in played)
                out.append(Text(f"Najlepszy {short_name(names[top])} saldo {fa[top]['eq_now']:.2f}  |  najgorszy {short_name(names[low])} {fa[low]['eq_now']:.2f}", style="bold yellow"))
                out.append(Text(f"Σ pozycji {tot_n}  win {tot_w / tot_n * 100:.1f}%  Σ PnL {tot_pnl:+.2f}$  |  grają {len(played)}/{len(allids)}", style="yellow"))
            else:
                out.append(Text("Brak zamkniętych pozycji - mapy wypełnią się po pierwszych rozliczeniach.", style="dim"))
            out.append(Text("Kolumny: wyjście (40..90 = TP przy bid >= tylu c, H = HOLD). Wiersze: schemat stawki +stawka%/bankroll%.", style="dim italic"))
            out.append(matrix("Mapa: SALDO $ (start %.0f)" % bud, lambda f: f["eq_now"], bud, True, "{:.2f}"))
            out.append(matrix("Mapa: WIN %", lambda f: f["wr"], 50.0, True, "{:.0f}"))
            out.append(matrix("Mapa: MAX DD % kapitału", lambda f: f["dd_eq"], 10.0, False, "{:.0f}"))
            out.append(matrix("Mapa: $ / pozycję", lambda f: f["exp"], 0.0, True, "{:+.2f}"))
            out.append(matrix("Mapa: najdł. seria L", lambda f: f["mls"], 3, False, "{:.0f}"))
            out.append(matrix("Mapa: stawka teraz $", lambda f: f["stake_now"], self.stake, True, "{:.2f}"))

            def agg(title, first, groups_, keyf, label_other, other_of):
                t = mk(title, [(first, "left"), ("Poz", "right"), ("Win%", "right"), ("PnL Σ", "right"), ("$/poz", "right"), ("Śr.DD%", "right"), (label_other, "right")])
                for g_ in groups_:
                    ids = [i for i in played if keyf(VAR_BY_ID[i]) == g_]
                    if not ids:
                        t.add_row(str(g_), "0", "-", "-", "-", "-", "-")
                        continue
                    n_ = sum(fa[i]["n"] for i in ids)
                    w_ = sum(fa[i]["wins"] for i in ids)
                    pn = sum(fa[i]["pnl"] for i in ids)
                    dds = [fa[i]["dd_eq"] for i in ids if fa[i]["dd_eq"] is not None]
                    bst = max(ids, key=lambda i: fa[i]["eq_now"] if fa[i]["eq_now"] is not None else -1e9)
                    t.add_row(str(g_), str(n_), f"{w_ / n_ * 100:.0f}" if n_ else "-", self.money(pn), SG(pn / n_ if n_ else None, "{:+.3f}"),
                              f"{sum(dds) / len(dds):.0f}" if dds else "-", other_of(VAR_BY_ID[bst]))
                return t
            out.append(agg("Zbiorczo wg WYJŚCIA", "Wyj.", exits, lambda v: v["exit"], "Best st.", lambda v: v["scheme"]))
            out.append(agg("Zbiorczo wg SCHEMATU stawki", "Schem.", schemes, lambda v: v["scheme"], "Best wyj.", lambda v: v["exit"]))
            return out

        if window and len(order) > window:
            m = (len(order) + window - 1) // window
            k = self.group % m
            order = order[k * window:(k + 1) * window]
            hdr = Text(f"Miejsca {k * window + 1}-{k * window + len(order)} z {len(allids)}   [g] = następne okno", style="bold yellow")
        else:
            hdr = Text(f"Wszystkie warianty: {len(order)}", style="bold yellow")
        if kind == "a":
            t1 = mk("1) Wynik (wg salda)", [("#", "right"), ("Wariant", "left"), ("Staw.", "right"), ("Poz.", "right"), ("Otw", "right"), ("PnL", "right"), ("Saldo", "right")])
            t2 = mk("2) Ryzyko", [("Wariant", "left"), ("MaxDD$", "right"), ("DD%", "right"), ("SerL", "right"), ("SerW", "right"), ("PF", "right"), ("Seria", "right")])
            t3 = mk("3) Na pozycję", [("Wariant", "left"), ("$/poz", "right"), ("Win%", "right"), ("ŚrW$", "right"), ("ŚrL$", "right"), ("ROI%", "right"), ("Med$", "right")])
            t4 = mk("4) Stawka / wzrost", [("Wariant", "left"), ("Staw.", "right"), ("Lvl", "right"), ("MaxSt", "right"), ("ŚrSt", "right"), ("Wzr.bk%", "right"), ("Do nast.$", "right")])
            for sid in order:
                f = fa[sid]
                nm = short_name(names[sid])
                cur = f["cur"]
                t1.add_row(str(pos0[sid]), nm, f"{f['stake_now']:.2f}", str(f["entries"] or 0), str(f["open"]), self.money(f["pnl"] if f["n"] else None),
                           "-" if f["eq_now"] is None else f"{f['eq_now']:.2f}")
                t2.add_row(nm, N(f["dd"]), N(f["dd_pct"], "{:.1f}", "%"), N(f["mls"], "{:d}"), N(f["mws"], "{:d}"), N(f["pf"]),
                           Text(f"{'W' if cur > 0 else 'L'}{abs(cur)}" if cur else "-"))
                t3.add_row(nm, SG(f["exp"], "{:+.3f}"), self.pct(f["wr"]), SG(f["avg_win"]), SG(f["avg_loss"]),
                           SG(f["roi"], "{:+.1f}", ""), SG(f["med"]))
                t4.add_row(nm, f"{f['stake_now']:.2f}", N(f["lvl"], "{:d}"), N(f["stake_max"], "{:.2f}"), N(f["stake_avg"], "{:.3f}"),
                           SG(f["bank_g"] if f["n"] else None, "{:+.1f}", ""), SG(f["to_next"]))
            return [hdr, t1, t2, t3, t4]
        # kind == "b"
        t5 = mk("5) Wyjścia TP", [("Wariant", "left"), ("TP n", "right"), ("TP%", "right"), ("TP W/L", "right"), ("ŚrTP$", "right"), ("ŚrRozl$", "right"), ("Czas TP", "right")])
        t6 = mk("6) Jakość", [("Wariant", "left"), ("Sharpe", "right"), ("Sortino", "right"), ("t-stat", "right"), ("Kelly%", "right"), ("Recov", "right"), ("BE W%", "right")])
        t7 = mk("7) Kapitał", [("Wariant", "left"), ("Min$", "right"), ("Max$", "right"), ("Zwrot%", "right"), ("Obrót x", "right"), ("Max poz", "right"), ("Zaang$", "right")])
        for sid in order:
            f = fa[sid]
            nm = short_name(names[sid])
            t5.add_row(nm, N(f["tp_n"], "{:d}"), N(f["tp_pct"], "{:.0f}", ""), Text(f"{f['tp_w']}/{f['tp_l']}" if f["tp_n"] else "-"),
                       SG(f["tp_avg"]), SG(f["rs_avg"]), Text(fsecs(f["tp_secs"]), style="" if f["tp_secs"] is not None else "dim"))
            t6.add_row(nm, SG(f["sharpe"]), SG(f["sortino"]), SG(f["tstat"]), SG(f["kelly"], "{:+.0f}", ""), N(f["rec"]), N(f["be_wr"], "{:.0f}", ""))
            t7.add_row(nm, N(f["eq_min"]), N(f["eq_max"]), SG(f["ret"] if f["n"] else None, "{:+.1f}", ""), N(f["turn_x"], "{:.1f}", ""),
                       N(f["peak_n"], "{:d}"), N(f["peak_cost"]))
        return [hdr, t5, t6, t7]

    def scoped(self, sid):
        return [t for t in self.state["trades"] if t["strat"] == sid and t["t_open"] >= self.since]

    def stat_rows(self, page):
        P = self.pct
        if page == 2:
            return [
                ("Zamknięte", lambda r: N(r["n"], "{:d}")),
                ("Otwarte", lambda r: N(r["open"], "{:d}", style="cyan")),
                ("W / L", lambda r: Text(f"{r['wins']}/{r['losses']}")),
                ("Win%", lambda r: P(r["wr"])),
                ("Win% przedz.95%", lambda r: Text("-" if r["wr_lo"] is None else f"{r['wr_lo']:.0f}-{r['wr_hi']:.0f}", style="dim")),
                ("Próg BE Win%", lambda r: N(r["be_wr"], "{:.1f}", "%")),
                ("Win% minus BE", lambda r: SG(r["wr_edge"], "{:+.1f}", "pp")),
                ("PnL $", lambda r: SG(r["pnl"] if r["n"] else None)),
                ("ROI (obrót)", lambda r: SG(r["roi"], "{:+.1f}", "%")),
                ("Zwrot / budżet", lambda r: SG(r["ret"] if r["n"] else None, "{:+.1f}", "%")),
                ("$ / zakład", lambda r: SG(r["exp"], "{:+.3f}")),
                ("% / zakład", lambda r: SG(r["exp_pct"], "{:+.1f}", "%")),
                ("Śr. wygrana $", lambda r: SG(r["avg_win"])),
                ("Śr. strata $", lambda r: SG(r["avg_loss"])),
                ("Payoff W/L", lambda r: N(r["payoff"])),
                ("Profit factor", lambda r: N(r["pf"])),
                ("Mediana $", lambda r: SG(r["med"])),
                ("Odch. std $", lambda r: N(r["sd"])),
                ("t-stat", lambda r: SG(r["tstat"])),
                ("Sharpe/zakład", lambda r: SG(r["sharpe"])),
                ("Kelly %", lambda r: SG(r["kelly"], "{:+.0f}", "%")),
                ("PnL otwarte (mid) $", lambda r: SG(r["unreal"])),
                ("PnL razem $", lambda r: SG(r["pnl_tot"] if (r["n"] or r["unreal"] is not None) else None)),
                ("Sortino/zakład", lambda r: SG(r["sortino"])),
                ("BIN win% (rozl.)", lambda r: N(r["bin_wr"], "{:.1f}", "%")),
                ("Realny - cena (pp)", lambda r: SG(r["mkt_cal"], "{:+.1f}", "pp")),
                ("Realny - model (pp)", lambda r: SG(r["mdl_cal"], "{:+.1f}", "pp")),
            ]
        if page == 8:
            return [
                ("Stawka teraz $", lambda r: N(r["stake_now"], "{:.2f}")),
                ("Poziom stawki", lambda r: N(r["lvl"], "{:d}")),
                ("Max poziom", lambda r: N(r["lvl_max"], "{:d}")),
                ("Do nast. progu $", lambda r: SG(r["to_next"])),
                ("Śr. stawka $", lambda r: N(r["stake_avg"], "{:.3f}")),
                ("Max stawka $", lambda r: N(r["stake_max"], "{:.2f}")),
                ("Stawka % kapit.", lambda r: N(r["stake_pct"], "{:.1f}", "%")),
                ("Bankroll real. $", lambda r: N(r["bank"])),
                ("Wzrost bankrolla", lambda r: SG(r["bank_g"] if r["n"] else None, "{:+.1f}", "%")),
                ("Szczyt kapitału $", lambda r: N(r["eq_peak"])),
                ("Max DD % kapit.", lambda r: N(r["dd_eq"], "{:.1f}", "%")),
                ("Obrót $", lambda r: N(r["turn"])),
                ("Obrót / bankroll", lambda r: N(r["turn_x"], "{:.1f}", "x")),
                ("Wejść razem", lambda r: N(r["entries"], "{:d}")),
                ("Rynków zagranych", lambda r: N(r["mk_played"], "{:d}")),
                ("Wejść / rynek", lambda r: N(r["ent_per_mkt"])),
                ("Rynków z re-wej.", lambda r: N(r["mk_re"], "{:d}")),
                ("Re-wejść razem", lambda r: N(r["re_n"], "{:d}")),
                ("Re-wejść zamkn.", lambda r: N(r["re_closed"], "{:d}")),
                ("PnL 1. wejść $", lambda r: SG(r["first_pnl"])),
                ("PnL re-wejść $", lambda r: SG(r["re_pnl"])),
                ("Win% re-wejść", lambda r: N(r["re_wr"], "{:.0f}", "%")),
                ("Śr. przerwa TP>re", lambda r: Text(fsecs(r["re_gap"]), style="" if r["re_gap"] is not None else "dim")),
                ("PnL na poziom $", lambda r: SG(r["lvl_pnl"])),
            ]
        if page == 3:
            return [
                ("Najlepszy $", lambda r: SG(r["best"])),
                ("Najgorszy $", lambda r: SG(r["worst"])),
                ("Brutto zysk $", lambda r: SG(r["gw"] if r["wins"] else None)),
                ("Brutto strata $", lambda r: SG(-r["gl"] if r["losses"] else None)),
                ("Max DD $", lambda r: N(r["dd"])),
                ("Max DD % budż.", lambda r: N(r["dd_pct"], "{:.1f}", "%")),
                ("Recovery factor", lambda r: N(r["rec"])),
                ("Saldo $", lambda r: N(r["eq_now"])),
                ("Saldo min $", lambda r: N(r["eq_min"])),
                ("Saldo max $", lambda r: N(r["eq_max"])),
                ("Najdł. seria W", lambda r: N(r["mws"], "{:d}")),
                ("Najdł. seria L", lambda r: N(r["mls"], "{:d}")),
                ("Seria teraz", lambda r: Text(f"{'W' if r['cur'] > 0 else 'L'}{abs(r['cur'])}" if r["cur"] else "-")),
                ("Ost.10 PnL $", lambda r: SG(r["l10_pnl"])),
                ("Ost.10 W/L", lambda r: Text(f"{r['l10_w']}/{r['l10_l']}" if r["n"] else "-")),
                ("Wyjść TP", lambda r: N(r["tp_n"], "{:d}")),
                ("TP % zakładów", lambda r: N(r["tp_pct"], "{:.0f}", "%")),
                ("TP zysk/strata", lambda r: Text(f"{r['tp_w']}/{r['tp_l']}" if r["tp_n"] else "-")),
                ("Rozlicz. W/L", lambda r: Text(f"{r['rs_w']}/{r['rs_l']}" if r["n"] - r["tp_n"] else "-")),
                ("Śr. cena TP c", lambda r: N(r["tp_px"], "{:.1f}")),
                ("Śr. czas do TP", lambda r: Text(fsecs(r["tp_secs"]), style="" if r["tp_secs"] is not None else "dim")),
                ("Śr. PnL TP $", lambda r: SG(r["tp_avg"])),
                ("Śr. PnL rozl. $", lambda r: SG(r["rs_avg"])),
                ("Szczyt jednocz. poz.", lambda r: N(r["peak_n"], "{:d}")),
                ("Szczyt zaangaż. $", lambda r: N(r["peak_cost"])),
            ]
        return [   # page 4
            ("Śr. cena wej. c", lambda r: N(r["e_avg"], "{:.1f}")),
            ("Mediana wej. c", lambda r: N(r["e_med"], "{:.1f}")),
            ("Min wej. c", lambda r: N(r["e_min"], "{:.1f}")),
            ("Max wej. c", lambda r: N(r["e_max"], "{:.1f}")),
            ("Model p% (nasza)", lambda r: N(r["p_avg"], "{:.1f}", "%")),
            ("Edge wg BIN c", lambda r: SG(r["edge_avg"], "{:+.1f}")),
            ("Śr. udziały", lambda r: N(r["sh_avg"])),
            ("Śr. koszt $", lambda r: N(r["cost_avg"], "{:.3f}")),
            ("Rynków unikat.", lambda r: N(r["mkts"], "{:d}")),
            ("Wejść w Up %", lambda r: N(r["up_pct"], "{:.0f}", "%")),
            ("Opłaty razem $", lambda r: N(r["fees"], "{:.3f}")),
            ("Opłaty / zakład $", lambda r: N(r["fee_tr"], "{:.3f}")),
            ("Opłaty % brutto", lambda r: N(r["fee_gw"], "{:.0f}", "%")),
            ("Śr. trzymanie", lambda r: Text(fsecs(r["hold"]), style="" if r["hold"] is not None else "dim")),
            ("Do końca (wej.)", lambda r: Text(fsecs(r["rem_in"]), style="" if r["rem_in"] is not None else "dim")),
            ("Zakładów / godz.", lambda r: N(r["per_h"], "{:.1f}")),
            ("PnL / godz. $", lambda r: SG(r["pnl_h"] if r["n"] else None)),
            ("Czas pomiaru", lambda r: Text(fsecs(r["hrs"] * 3600))),
            ("Śr. max bid c", lambda r: N(r["hi_avg"], "{:.1f}")),
            ("Śr. min bid c", lambda r: N(r["lo_avg"], "{:.1f}")),
            ("Bid >= 70c %", lambda r: N(r["t70"], "{:.0f}", "%")),
            ("Bid >= 80c %", lambda r: N(r["t80"], "{:.0f}", "%")),
            ("Bid >= 90c %", lambda r: N(r["t90"], "{:.0f}", "%")),
            ("Śr. spread wej. c", lambda r: N(r["spr"], "{:.1f}")),
            ("MFE śr. c (max bid-wej.)", lambda r: SG(r["mfe"], "{:+.1f}")),
            ("MAE śr. c (wej.-min bid)", lambda r: N(r["mae"], "{:.1f}")),
            ("MFE >= 5c %", lambda r: N(r["mfe5"], "{:.0f}", "%")),
            ("MAE >= 10c %", lambda r: N(r["mae10"], "{:.0f}", "%")),
        ]

    def cell_nwp(self, trs):
        cl = [t for t in trs if t["status"] in ("won", "lost")]
        if not cl:
            return Text("-", style="dim")
        w, pnl = sum(1 for t in cl if t["status"] == "won"), sum(t["pnl"] for t in cl)
        return Text(f"{len(cl)} {w / len(cl) * 100:.0f} {pnl:+.1f}", style="green" if pnl > 0 else "red" if pnl < 0 else "white")

    def breakdown(self, title, first, buckets, sids):
        t = Table(title=title, box=box.SIMPLE, expand=True, pad_edge=False, show_edge=False)
        t.add_column(first, justify="left", no_wrap=True)
        names = {s["id"]: s["name"] for s in STRATS}
        trs = {sid: self.scoped(sid) for sid in sids}
        for sid in sids:
            t.add_column(short_name(names[sid]), justify="right", no_wrap=True)
        for label, pred in buckets:
            t.add_row(label, *[self.cell_nwp([x for x in trs[sid] if pred(x)]) for sid in sids])
        return t

    def stat_tables(self, page):
        sids = self.view_sids()
        names = {s["id"]: s["name"] for s in STRATS}
        if page == 9:
            return self.rank_tables("map")
        if page == 10:
            return self.rank_tables("a", window=6)
        if page == 11:
            return self.rank_tables("b", window=6)
        if page in (2, 3, 4, 8):
            fs = {sid: self.vstats(sid) for sid in sids}
            title = {2: "Wyniki", 3: "Ryzyko / serie / TP", 4: "Wejścia / koszty / czas / bid", 8: "Stawka / re-wejścia"}[page]
            t = Table(title=title, box=box.SIMPLE, expand=True, pad_edge=False, show_edge=False)
            t.add_column("", justify="left", no_wrap=True)
            for sid in sids:
                t.add_column(short_name(names[sid]), justify="right", no_wrap=True, style="bold")
            for label, fn in self.stat_rows(page):
                t.add_row(label, *[fn(fs[sid]) for sid in sids])
            return [t]
        if page == 5:
            E = lambda lo, hi: (lambda t: lo <= t["entry"] < hi)
            R = lambda lo, hi: (lambda t: t.get("rem_in") is not None and lo <= t["rem_in"] < hi)
            return [
                self.breakdown("Cena wejścia (n W% $)", "cena", [("<50c", E(0, .50)), ("50-60c", E(.50, .60)), ("60-70c", E(.60, .70)),
                               ("70-80c", E(.70, .80)), ("80c+", E(.80, 2))], sids),
                self.breakdown("Strona (n W% $)", "strona", [("Up", lambda t: t["side"] == "Up"),
                               ("Down", lambda t: t["side"] == "Down")], sids),
                self.breakdown("Interwał (n W% $)", "okno", [(tf, (lambda tf: lambda t: t["tf"] == tf)(tf)) for tf in WINDOWS
                               if tf in ("5m", "15m") or any(x["tf"] == tf for sid in sids for x in self.scoped(sid))], sids),
                self.breakdown("Do końca przy wejściu (n W% $)", "zostało", [("<30s", R(0, 30)), ("30-60s", R(30, 60)),
                               ("1-2m", R(60, 120)), ("2-5m", R(120, 300)), ("5m+", R(300, 10 ** 9))], sids),
            ]
        if page == 7:
            Pm = lambda lo, hi: (lambda t: lo <= (t.get("p") or 0.0) < hi)
            Hh = lambda lo, hi: (lambda t: lo <= time.localtime(t["t_open"]).tm_hour < hi)
            Sp = lambda lo, hi: (lambda t: t.get("spr_in") is not None and lo <= t["spr_in"] < hi)
            return [
                self.breakdown("Model p naszej strony (n W% $)", "p", [("<10%", Pm(0, .10)), ("10-20%", Pm(.10, .20)),
                               ("20-30%", Pm(.20, .30)), ("30-40%", Pm(.30, .40)), ("40%+", Pm(.40, 2))], sids),
                self.breakdown("Godzina wejścia (n W% $)", "godz.", [("0-6", Hh(0, 6)), ("6-12", Hh(6, 12)),
                               ("12-18", Hh(12, 18)), ("18-24", Hh(18, 24))], sids),
                self.breakdown("Spread przy wejściu (n W% $)", "spread", [("<2c", Sp(0, .02)), ("2-4c", Sp(.02, .04)),
                               ("4-8c", Sp(.04, .08)), ("8c+", Sp(.08, 2))], sids),
                self.breakdown("Wyjście (n W% $)", "wyjście", [("TP", lambda t: t.get("exit") == "TP"),
                               ("rozliczenie", lambda t: t.get("exit") != "TP")], sids),
            ]
        used = [a for a in ASSETS if any(x["asset"] == a for sid in sids for x in self.scoped(sid))]
        return [self.breakdown("Aktywa (n W% $)", "aktywo",
                               [(a, (lambda a: lambda t: t["asset"] == a)(a)) for a in used] or [("brak danych", lambda t: False)], sids)]

    def stat_notes(self, page):
        notes = {2: "BE = próg opłacalności: |śr.strata|/(śr.wygrana+|śr.strata|). |t|>2 = istotne. Kelly<0 = brak przewagi. n<30 = wnioski niepewne.",
                 4: "Bid>=X%: do wyjścia/rozliczenia. Edge wg BIN < 0 = model BIN jest przeciw nam (tak ma być).",
                 5: "Komórka: n zamkniętych / win% / PnL $.",
                 7: "Komórka: n zamkniętych / win% / PnL $. p = model BIN dla NASZEJ (odwrotnej) strony.",
                 8: "Stawka = start x (1+krok)^poziom; poziom = floor(wzrost zrealizowanego bankrolla / próg). A +1%/1%, B +2%/1%, C +3%/1%, D +2%/2%, E +3%/2%, F +4%/2%, G +5%/2% (stawka/bankroll). Re-wejście = kolejne wejście w ten sam rynek po TP (tryb RE).",
                 9: "Zielone tło = najlepsza komórka mapy. Mapa pokazuje, który schemat stawki i które wyjście wygrywa; zbiorówki liczą wszystkie warianty danego wyjścia / schematu.",
                 10: "Staw. = stawka teraz. Poz. = wszystkie wejścia. SerL/SerW = najdłuższe serie strat/wygranych, Seria = aktualna. $/poz = średni zysk na zamkniętą pozycję. Lvl = poziom wzrostu stawki.",
                 11: "TP% = udział wyjść przez take-profit. Czas TP = śr. czas do TP. BE W% = próg opłacalności win%. Recov = PnL / max DD. Obrót x = obrót / budżet."}
        return [Text(notes[page], style="dim italic")] if page in notes else []

    def nav(self):
        t = Text()
        for k, nm in ((1, "Pan"), (2, "Wyn"), (3, "Ryz"), (4, "Wej"), (5, "Roz"), (6, "Akt"), (7, "Seg"), (8, "Staw"), (9, "Mapa"), (10, "[0]Rank"), (11, "[k]Kap")):
            t.append(nm if k >= 10 else f"[{k}]{nm}", style="bold black on cyan" if k == self.page else "dim")
            t.append(" ")
        return t

    def render(self):
        if self.page == 1:
            return self.render_main()
        top = [self.nav()] + ([self.group_line()] if self.page in (2, 3, 4, 5, 6, 7, 8) else [])
        return Group(*top, *self.stat_tables(self.page), *self.stat_notes(self.page))

    # ---------- klawisze 1-6 (zmiana strony); bez terminala po prostu nie działają ----------
    def start_keys(self):
        try:
            import termios, tty
            fd = sys.stdin.fileno()
            if not os.isatty(fd):
                return
            self._tty = (fd, termios.tcgetattr(fd))
            tty.setcbreak(fd)
        except Exception:
            self._tty = None
            return

        def worker():
            while True:
                try:
                    b = os.read(fd, 16)
                except Exception:
                    return
                if not b:
                    return
                for ch in b.decode("utf-8", "ignore"):
                    if ch in "123456789":
                        self.page, self.dirty = int(ch), True
                    elif ch == "0":
                        self.page, self.dirty = 10, True
                    elif ch in "kK":
                        self.page, self.dirty = 11, True
                    elif ch in "nN":
                        self.page, self.dirty = self.page % 11 + 1, True
                    elif ch in "gG":
                        self.group, self.dirty = self.group + 1, True
        threading.Thread(target=worker, name="keys", daemon=True).start()

    def stop_keys(self):
        if self._tty:
            try:
                import termios
                termios.tcsetattr(self._tty[0], termios.TCSADRAIN, self._tty[1])
            except Exception:
                pass
            self._tty = None

    def print_stats(self, con=None, full=True):
        con = con or console
        con.print(Text(f"KAPSKO - raport {time.strftime('%Y-%m-%d %H:%M:%S')} | statystyki od "
                       f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(self.since))} | budżet ${self.sim_budget or 0:.0f}/wariant",
                       style="bold cyan"))
        keep = self.group
        try:
            if full:
                gs = self.groups()
                for p in (2, 3, 4, 5, 6, 7, 8):
                    for k, (ttl, _ids) in enumerate(gs):
                        self.group = k
                        con.print(Text(f"== strona {p} | grupa {k + 1}/{len(gs)}: {ttl} ==", style="bold yellow"))
                        for tb in self.stat_tables(p):
                            con.print(tb)
                        for nt in self.stat_notes(p):
                            con.print(nt)
            for pg in (9, 10, 11):
                con.print(Text(f"== strona {pg} ==", style="bold yellow"))
                for tb in (self.rank_tables({9: "map", 10: "a", 11: "b"}[pg], 0)):
                    con.print(tb)
                for nt in self.stat_notes(pg):
                    con.print(nt)
        finally:
            self.group = keep

    def run(self):
        self.start_keys()
        try:
            with Live(self.render(), console=console, refresh_per_second=2, screen=False) as live:
                while True:
                    try:
                        self.step()
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        self.note(f"błąd: {type(e).__name__}")
                    self.dirty = False
                    live.update(self.render())
                    if time.time() >= self.rep_next:
                        self.rep_next = time.time() + 30
                        try:
                            write_report_file(self)
                        except Exception:
                            pass
                    t_end = time.time() + CFG["loop_sleep"]
                    while time.time() < t_end:              # krótkie drzemki: zmiana strony widać od razu
                        if self.dirty:
                            self.dirty = False
                            live.update(self.render())
                        time.sleep(0.1)
        finally:
            self.stop_keys()


# ------------------------------ RAPORT 5m / 15m ------------------------------
def _c_txt(v, fmt="{}", style="white"):
    return ("-", "dim") if v is None else (fmt.format(v), style)


def _c_money(v, dec=2):
    if v is None:
        return ("-", "dim")
    return (f"{v:+.{dec}f}", "green" if v > 0 else "red" if v < 0 else "white")


def _c_pct(v, dec=1):
    if v is None:
        return ("-", "dim")
    return (f"{v:.{dec}f}%", "green" if v >= 55 else "yellow" if v >= 45 else "red")


def _c_roi(v):
    if v is None:
        return ("-", "dim")
    return (f"{v:+.1f}%", "green" if v > 0 else "red" if v < 0 else "white")


def _c_nw(d):
    """liczba / win%"""
    if not d["n"]:
        return ("0", "dim")
    return (f"{d['n']} / {d['wr']:.0f}%", "green" if d["wr"] >= 55 else "yellow" if d["wr"] >= 45 else "red")


def _c_np(d):
    """liczba / PnL"""
    if not d["n"]:
        return ("0", "dim")
    return (f"{d['n']} / {d['pnl']:+.2f}", "green" if d["pnl"] > 0 else "red" if d["pnl"] < 0 else "white")


def _sub(lst):
    w = sum(1 for t in lst if t["status"] == "won")
    return {"n": len(lst), "wr": (w / len(lst) * 100) if lst else None, "pnl": sum(t["pnl"] for t in lst)}


def tf_metrics(tr, now, t0):
    """Wszystkie statystyki dla listy transakcji bota (jeden interwał albo razem). t0 = początek liczenia (do 'poz./godz.')."""
    closed = sorted((t for t in tr if t["status"] in ("won", "lost")), key=lambda t: t.get("t_close", t["end_ts"]))
    wins = [t for t in closed if t["status"] == "won"]
    losses = [t for t in closed if t["status"] == "lost"]
    opn = [t for t in tr if t["status"] in ("pending", "open")]
    placed = [t for t in tr if t["status"] in ("open", "won", "lost")]
    m = {"n": len(closed), "open": len(opn), "placed": len(placed), "wins": len(wins), "losses": len(losses),
         "check": sum(1 for t in tr if t["status"] == "check")}
    m["pnl"] = sum(t["pnl"] for t in closed)
    m["staked"] = sum(t["cost"] for t in closed)
    m["roi"] = (m["pnl"] / m["staked"] * 100) if m["staked"] else None
    m["wr"] = (len(wins) / len(closed) * 100) if closed else None
    gw = sum(t["pnl"] for t in wins)
    gl = -sum(t["pnl"] for t in losses)
    m["pf"] = (gw / gl) if gl > 0 else None
    m["avg_win"] = (gw / len(wins)) if wins else None
    m["avg_loss"] = (-gl / len(losses)) if losses else None
    m["payoff"] = (m["avg_win"] / -m["avg_loss"]) if (m["avg_win"] is not None and m["avg_loss"]) else None
    m["exp"] = (m["pnl"] / len(closed)) if closed else None
    m["best"] = max((t["pnl"] for t in closed), default=None)
    m["worst"] = min((t["pnl"] for t in closed), default=None)
    cum = peak = dd = 0.0
    streak = max_ls = max_ws = 0
    for t in closed:
        cum += t["pnl"]
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
        if t["status"] == "won":
            streak = streak + 1 if streak > 0 else 1
            max_ws = max(max_ws, streak)
        else:
            streak = streak - 1 if streak < 0 else -1
            max_ls = max(max_ls, -streak)
    m["dd"], m["max_ls"], m["max_ws"], m["streak"] = dd, max_ls, max_ws, streak
    pcts = [t for t in opn if t.get("pnl_pct") is not None and t.get("cost")]
    m["unreal"] = sum(t["pnl_pct"] * t["cost"] for t in pcts) if pcts else None
    m["pnl_total"] = m["pnl"] + (m["unreal"] or 0.0)
    m["exposure"] = sum(t["cost"] for t in tr if t["status"] in LOCK)
    # jednoczesne pozycje (najwięcej naraz) i zaangażowanie
    ev = []
    for t in placed:
        s0 = t["t_open"]
        e0 = now if t["status"] == "open" else t.get("t_close", t["end_ts"])
        ev.append((s0, 1, t["cost"]))
        ev.append((max(e0, s0), -1, -t["cost"]))
    ev.sort(key=lambda x: (x[0], x[1]))
    cur = pk = 0
    ccost = pcost = 0.0
    for _, d, cst in ev:
        cur += d
        ccost += cst
        pk = max(pk, cur)
        pcost = max(pcost, ccost)
    m["peak_n"], m["peak_cost"] = pk, pcost
    hrs = max((now - t0) / 3600.0, 1 / 60.0)
    m["per_hr"] = len(placed) / hrs
    cnt = {}
    for t in placed:
        cnt[t["slug"]] = cnt.get(t["slug"], 0) + 1
    m["markets"] = len(cnt)
    m["legs_avg"] = (len(placed) / len(cnt)) if cnt else None
    m["multi"] = sum(1 for v in cnt.values() if v >= 3)
    m["max_legs"] = max(cnt.values(), default=0)
    m["avg_entry"] = (sum(t["entry"] for t in placed) / len(placed) * 100) if placed else None
    m["avg_edge"] = (sum(t["edge"] for t in placed) / len(placed) * 100) if placed else None
    m["avg_shares"] = (sum(t.get("shares") or 0 for t in placed) / len(placed)) if placed else None
    m["avg_cost"] = (sum(t["cost"] for t in placed) / len(placed)) if placed else None
    m["fees"] = sum(max(0.0, t["cost"] - t["entry"] * t["shares"]) for t in placed if t.get("shares"))
    ps = [t["p"] * 100 for t in closed if t.get("p") is not None]
    m["avg_p"] = (sum(ps) / len(ps)) if ps else None
    m["calib"] = (m["wr"] - m["avg_p"]) if (ps and m["wr"] is not None) else None
    holds = [t.get("t_close", t["end_ts"]) - t["t_open"] for t in closed]
    holds = [h for h in holds if h >= 0]
    m["hold"] = (sum(holds) / len(holds)) if holds else None
    m["up"], m["down"] = _sub([t for t in closed if t["side"] == "Up"]), _sub([t for t in closed if t["side"] == "Down"])
    m["tp"] = _sub([t for t in closed if t.get("exit") == "TP"])
    m["held"] = _sub([t for t in closed if t.get("exit") != "TP"])
    m["k_counter"] = _sub([t for t in closed if t.get("counter")])
    m["k_extra"] = _sub([t for t in closed if t.get("extra") and not t.get("counter")])
    m["k_pair"] = _sub([t for t in closed if t.get("paired") and not t.get("counter") and not t.get("extra")])
    m["k_plain"] = _sub([t for t in closed if not (t.get("counter") or t.get("extra") or t.get("paired"))])
    return m


def build_metrics(trades, since, active_ids, now, t0):
    """Statystyki per interwał + razem. Zwraca ({'5m':..., '15m':..., 'ALL':...}, lista transakcji w zakresie)."""
    sc = [t for t in trades if t.get("strat") != 0 and (active_ids is None or t.get("strat") in active_ids)
          and t.get("t_open", 0) >= since and t.get("tf") in ACTIVE_TFS]
    M = {tf: tf_metrics([t for t in sc if t["tf"] == tf], now, t0) for tf in ACTIVE_TFS}
    M["ALL"] = tf_metrics(sc, now, t0)
    return M, sc


def _fmt_hold(v):
    if v is None:
        return ("-", "dim")
    return (f"{int(v) // 60}m{int(v) % 60:02d}s", "white")


def report_rows(M):
    """Wiersze tabeli: (sekcja, etykieta, [komórka 5m, komórka 15m, komórka RAZEM], core). Komórka = (tekst, styl)."""
    keys = ("5m", "15m", "ALL")
    R = []

    def row(sec, label, fn, core=False):
        R.append((sec, label, [fn(M[k]) for k in keys], core))

    S = "POZYCJE"
    row(S, "Otwarte teraz", lambda m: _c_txt(m["open"]), True)
    row(S, "Zamknięte", lambda m: _c_txt(m["n"]), True)
    row(S, "Złożone razem", lambda m: _c_txt(m["placed"]))
    row(S, "Pozycji / godz.", lambda m: _c_txt(m["per_hr"], "{:.1f}"), True)
    row(S, "Szczyt jednocz. poz.", lambda m: _c_txt(m["peak_n"]), True)
    row(S, "Szczyt zaangaż. $", lambda m: _c_txt(m["peak_cost"], "{:.2f}"))
    row(S, "W grze teraz $", lambda m: _c_txt(m["exposure"], "{:.2f}"))
    row(S, "Rynki zagrane", lambda m: _c_txt(m["markets"]))
    row(S, "Śr. nóg / rynek", lambda m: _c_txt(m["legs_avg"], "{:.2f}"))
    row(S, "Rynki z 3+ nogami", lambda m: _c_txt(m["multi"]))
    row(S, "Maks. nóg na rynku", lambda m: _c_txt(m["max_legs"]))
    S = "WYNIK"
    row(S, "PnL zamknięte $", lambda m: _c_money(m["pnl"]), True)
    row(S, "PnL otwarte $ (mid)", lambda m: _c_money(m["unreal"]), True)
    row(S, "PnL razem $", lambda m: _c_money(m["pnl_total"]), True)
    row(S, "Zainwestowane $", lambda m: _c_txt(m["staked"], "{:.2f}"))
    row(S, "ROI", lambda m: _c_roi(m["roi"]), True)
    row(S, "Wygrane / przegrane", lambda m: _c_txt(f"{m['wins']}/{m['losses']}"), True)
    row(S, "Win %", lambda m: _c_pct(m["wr"]), True)
    row(S, "Śr. wygrana $", lambda m: _c_money(m["avg_win"]), True)
    row(S, "Śr. strata $", lambda m: _c_money(m["avg_loss"]), True)
    row(S, "Payoff (wygr./strata)", lambda m: _c_txt(m["payoff"], "{:.2f}"))
    row(S, "Profit factor", lambda m: _c_txt(m["pf"], "{:.2f}"), True)
    row(S, "$ / zakład", lambda m: _c_money(m["exp"], 3), True)
    row(S, "Najlepsza", lambda m: _c_money(m["best"]))
    row(S, "Najgorsza", lambda m: _c_money(m["worst"]))
    row(S, "Max DD $", lambda m: (f"-{m['dd']:.2f}", "red") if m["dd"] else ("0.00", "white"), True)
    row(S, "Najdł. seria L", lambda m: _c_txt(m["max_ls"]))
    row(S, "Najdł. seria W", lambda m: _c_txt(m["max_ws"]))
    row(S, "Seria teraz", lambda m: (("W" if m["streak"] > 0 else "L") + str(abs(m["streak"])), "white") if m["streak"] else ("-", "dim"))
    S = "WEJŚCIA"
    row(S, "Śr. cena wejścia", lambda m: _c_txt(m["avg_entry"], "{:.1f}c"), True)
    row(S, "Śr. edge", lambda m: _c_txt(m["avg_edge"], "{:.1f}c"), True)
    row(S, "Śr. p modelu", lambda m: _c_txt(m["avg_p"], "{:.1f}%"))
    row(S, "Realny win %", lambda m: _c_pct(m["wr"]))
    row(S, "Realny − model (pp)", lambda m: _c_money(m["calib"], 1), True)
    row(S, "Śr. udziałów", lambda m: _c_txt(m["avg_shares"], "{:.2f}"))
    row(S, "Śr. koszt $", lambda m: _c_txt(m["avg_cost"], "{:.3f}"))
    row(S, "Opłaty wejścia $", lambda m: _c_txt(m["fees"], "{:.2f}"))
    row(S, "Śr. czas trzymania", lambda m: _fmt_hold(m["hold"]))
    S = "STRONY"
    row(S, "Up: ile / win%", lambda m: _c_nw(m["up"]))
    row(S, "Up: PnL $", lambda m: _c_money(m["up"]["pnl"] if m["up"]["n"] else None))
    row(S, "Down: ile / win%", lambda m: _c_nw(m["down"]))
    row(S, "Down: PnL $", lambda m: _c_money(m["down"]["pnl"] if m["down"]["n"] else None))
    S = "WYJŚCIA"
    row(S, "TP: ile / win%", lambda m: _c_nw(m["tp"]), True)
    row(S, "TP: PnL $", lambda m: _c_money(m["tp"]["pnl"] if m["tp"]["n"] else None))
    row(S, "Do końca: ile / win%", lambda m: _c_nw(m["held"]), True)
    row(S, "Do końca: PnL $", lambda m: _c_money(m["held"]["pnl"] if m["held"]["n"] else None))
    S = "TYPY WEJŚĆ"
    row(S, "Zwykłe: ile / PnL", lambda m: _c_np(m["k_plain"]))
    row(S, "Dokładane nogi: ile/PnL", lambda m: _c_np(m["k_extra"]))
    row(S, "Pary auto: ile / PnL", lambda m: _c_np(m["k_pair"]))
    row(S, "Kontry: ile / PnL", lambda m: _c_np(m["k_counter"]))
    return R


def asset_rows(sc):
    """Wiersze tabeli aktywów: [aktywo, 5m W/L, 5m $, 15m W/L, 15m $, razem $] (komórki = (tekst, styl))."""
    out = []
    for a in ASSETS:
        if not any(tf_ok(a, tf) for tf in ACTIVE_TFS):
            continue
        row = [a]
        tot = 0.0
        any_closed = False
        for tf in ACTIVE_TFS:
            sub = [t for t in sc if t["asset"] == a and t["tf"] == tf]
            closed = [t for t in sub if t["status"] in ("won", "lost")]
            w = sum(1 for t in closed if t["status"] == "won")
            op = sum(1 for t in sub if t["status"] in ("open", "pending"))
            p = sum(t["pnl"] for t in closed)
            tot += p
            any_closed = any_closed or bool(closed)
            row.append((f"{w}/{len(closed) - w}" + (f"+{op}" if op else ""), "white" if sub else "dim"))
            row.append(_c_money(p) if closed else ("-", "dim"))
        row.append(_c_money(tot) if any_closed else ("-", "dim"))
        out.append(row)
    return out


def format_report(M, arows, head=None):
    """Ta sama tabela jako zwykły tekst (do --report, pliku i wyjścia po Ctrl+C)."""
    L = list(head or [])
    w0, w = 25, 12
    L.append(f"{'':<{w0}}" + "".join(f"{h:>{w}}" for h in ("5m", "15m", "RAZEM")))
    last = None
    for sec, label, cells, _core in report_rows(M):
        if sec != last:
            L.append(f"-- {sec} " + "-" * max(2, w0 + 3 * w - len(sec) - 4))
            last = sec
        L.append(f"{label:<{w0}}" + "".join(f"{c[0]:>{w}}" for c in cells))
    L.append("")
    L.append("-- AKTYWA (zamknięte W/L [+otwarte]) " + "-" * 10)
    L.append(f"{'':<8}" + "".join(f"{h:>10}" for h in ("5m W/L", "5m $", "15m W/L", "15m $", "Razem $")))
    for r in arows:
        L.append(f"{r[0]:<8}" + "".join(f"{c[0]:>10}" for c in r[1:]))
    return "\n".join(L)


CSV_LABELS = {
    "n": "zamkniete", "open": "otwarte", "check": "sprawdz", "wins": "wygrane", "losses": "przegrane", "wr": "win_pct",
    "wr_lo": "win_pct_dol95", "wr_hi": "win_pct_gora95", "pnl": "pnl_usd", "staked": "obrot_zamkn_usd", "roi": "roi_obrot_pct",
    "ret": "zwrot_budzet_pct", "exp": "usd_na_zaklad", "exp_pct": "pct_na_zaklad", "avg_win": "sr_wygrana_usd",
    "avg_loss": "sr_strata_usd", "payoff": "payoff", "pf": "profit_factor", "be_wr": "prog_be_win_pct", "wr_edge": "win_minus_be_pp",
    "kelly": "kelly_pct", "med": "mediana_usd", "sd": "odch_std_usd", "tstat": "t_stat", "sharpe": "sharpe_na_zaklad",
    "sortino": "sortino_na_zaklad", "best": "najlepszy_usd", "worst": "najgorszy_usd", "gw": "brutto_zysk_usd",
    "gl": "brutto_strata_usd", "dd": "max_dd_usd", "dd_pct": "max_dd_pct_budzetu", "rec": "recovery_factor", "mws": "seria_W_max",
    "mls": "seria_L_max", "cur": "seria_teraz", "eq_now": "saldo_usd", "eq_min": "saldo_min_usd", "eq_max": "saldo_max_usd",
    "l10_pnl": "ost10_pnl_usd", "tp_n": "wyjsc_tp", "tp_pct": "tp_pct_zakladow", "tp_w": "tp_zysk", "tp_l": "tp_strata",
    "rs_w": "rozl_wygrane", "rs_l": "rozl_przegrane", "tp_px": "sr_cena_tp_c", "tp_secs": "sr_czas_do_tp_s", "tp_avg": "sr_pnl_tp_usd",
    "rs_avg": "sr_pnl_rozl_usd", "e_avg": "sr_cena_wej_c", "e_med": "med_cena_wej_c", "e_min": "min_cena_wej_c", "e_max": "max_cena_wej_c",
    "p_avg": "model_p_pct", "edge_avg": "edge_wg_bin_c", "sh_avg": "sr_udzialy", "cost_avg": "sr_koszt_usd", "mkts": "rynkow_unikat",
    "up_pct": "wejsc_up_pct", "fees": "oplaty_usd", "fee_tr": "oplaty_na_zaklad_usd", "fee_gw": "oplaty_pct_brutto", "hold": "sr_trzymanie_s",
    "rem_in": "sr_do_konca_wej_s", "hrs": "czas_pomiaru_h", "per_h": "zakladow_na_h", "pnl_h": "pnl_na_h_usd", "hi_avg": "sr_max_bid_c",
    "lo_avg": "sr_min_bid_c", "t70": "bid70_pct", "t80": "bid80_pct", "t90": "bid90_pct", "mfe": "mfe_c", "mae": "mae_c",
    "mfe5": "mfe5c_pct", "mae10": "mae10c_pct", "bin_wr": "bin_win_rozl_pct", "mkt_cal": "realny_minus_cena_pp", "mdl_cal": "realny_minus_model_pp",
    "spr": "sr_spread_wej_c", "unreal": "pnl_otwarte_usd", "pnl_tot": "pnl_razem_usd", "peak_n": "szczyt_poz", "peak_cost": "szczyt_zaang_usd",
    "stake_now": "stawka_teraz_usd", "lvl": "poziom_stawki", "stake_avg": "sr_stawka_usd", "stake_max": "max_stawka_usd",
    "lvl_max": "max_poziom", "bank": "bankroll_real_usd", "bank_g": "wzrost_bankrolla_pct", "to_next": "do_nast_progu_usd",
    "stake_pct": "stawka_pct_kapitalu", "eq_peak": "szczyt_kapitalu_usd", "dd_eq": "max_dd_pct_kapitalu", "turn": "obrot_usd",
    "turn_x": "obrot_x_bankroll", "entries": "wejsc_razem", "mk_played": "rynkow_zagranych", "ent_per_mkt": "wejsc_na_rynek",
    "mk_re": "rynkow_z_rewejsciem", "re_n": "rewejsc", "re_closed": "rewejsc_zamkn", "re_pnl": "pnl_rewejsc_usd",
    "first_pnl": "pnl_pierwszych_wejsc_usd", "re_wr": "win_pct_rewejsc", "re_gap": "sr_przerwa_tp_rewejscie_s", "lvl_pnl": "pnl_na_poziom_usd",
}


def write_csv(bot):
    """Pełna tabela: jeden wiersz = jeden wariant, kolumny = wszystkie statystyki (do arkusza / porównań)."""
    import csv
    rows = []
    for s_ in bot.active:
        v = VAR_BY_ID.get(s_["id"])
        row = {"wariant": short_name(s_["name"]), "id": s_["id"],
               "schemat_stawki": SCHEME_LABEL.get(v["scheme"], "") if v else "",
               "wyjscie": v["exit"] if v else "", "tryb": ("RE" if v["reentry"] else "1X" if v["tp"] else "HOLD") if v else ""}
        for k, val in bot.vstats(s_["id"]).items():
            if val is None or isinstance(val, (int, float)):
                row[CSV_LABELS.get(k, k)] = "" if val is None else (round(val, 6) if isinstance(val, float) else val)
        rows.append(row)
    cols = []
    for row in rows:
        for k in row:
            if k not in cols:
                cols.append(k)
    with open(CFG["csv_file"], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return CFG["csv_file"]


def write_report_file(bot):
    """Zapisuje pełny raport (wszystkie strony statystyk) do pliku; zwraca tekst."""
    import io
    buf = io.StringIO()
    con = Console(file=buf, width=100, color_system=None, force_terminal=False)
    bot.print_stats(con)
    txt = buf.getvalue()
    with open(CFG["report_file"], "w", encoding="utf-8") as f:
        f.write(txt)
    try:
        write_csv(bot)
    except Exception:
        pass
    return txt


def print_report(path):
    """--report: pełna tabela ze zapisanego stanu, bez uruchamiania bota."""
    try:
        with open(path) as f:
            st = json.load(f)
    except Exception as e:
        sys.exit(f"Nie mogę wczytać stanu {path}: {type(e).__name__}. Uruchom najpierw bota (albo podaj --state plik).")
    since = st.get("since") or st.get("start") or 0
    now = time.time()
    M, sc = build_metrics(st.get("trades", []), since, None, now, since)
    head = [f"JASIUPLACEK v8 | raport ze stanu: {path} | start {time.strftime('%Y-%m-%d %H:%M', time.localtime(since))}"
            f" | teraz {time.strftime('%H:%M:%S')}", ""]
    print(format_report(M, asset_rows(sc), head))


# --------------------------------- CLI --------------------------------------
def print_list():
    print("\nDostępne strategie:\n")
    for s in STRATS:
        print(f"  {s['id']:>2}. {s['name']:<11} {s['desc']}")
    print()


def probe_gap(now):
    """Sprawdza (równolegle) które okna BTC 5m/15m/1h istnieją wokół TERAZ -> pokazuje luki po stronie Polymarketu."""
    from concurrent.futures import ThreadPoolExecutor

    def exists(slug):
        try:
            r = requests.get(GAMMA + "/events", params={"slug": slug}, timeout=6, headers=S.headers)
            return bool(r.json()) if r.status_code == 200 else None
        except Exception:
            return None

    def hour_slugs(st):          # godzinówki mają dwa możliwe zapisy sluga (epoka albo nazwa z godziną ET)
        et = datetime.fromtimestamp(st + et_offset(st), tz=timezone.utc)
        return [f"btc-updown-1h-{st}",
                f"bitcoin-up-or-down-{MONTHS[et.month - 1]}-{et.day}-{et.year}-"
                f"{et.hour % 12 or 12}{'am' if et.hour < 12 else 'pm'}-et"]

    def has(tf, st):
        if tf != "1h":
            return exists(f"btc-updown-{tf}-{st}")
        r = [exists(s) for s in hour_slugs(st)]
        return True if any(r) else None if all(x is None for x in r) else False

    def lt(ts):
        return f"{time.strftime('%H:%M', time.gmtime(ts))} UTC = {time.strftime('%H:%M', time.localtime(ts))} u Ciebie"

    print("\n  LUKA? Szukam okien BTC, które naprawdę istnieją na Polymarkecie (z tyłu i z przodu):")
    if et_offset(now - 86400) != et_offset(now + 86400):
        print("  (w USA jest dziś/jutro zmiana czasu - Polymarket liczy te rynki w ET, tu zwykle powstaje luka)")
    future = False
    for tf, back, fwd in (("5m", 36, 48), ("15m", 12, 24), ("1h", 4, 8)):
        per = WINDOWS[tf]["period"]
        base = int(now // per * per)
        starts = [base + k * per for k in range(-back, fwd + 1)]
        with ThreadPoolExecutor(8) as ex:
            res = list(ex.map(lambda st: has(tf, st), starts))
        if all(r is None for r in res):
            print(f"  {tf:<4} nie udało się zapytać Gamma (sieć?)")
            continue
        have = [st for st, r in zip(starts, res) if r]
        if not have:
            print(f"  {tf:<4} w całym zakresie ({back} okien wstecz / {fwd} w przód) nie ma żadnego okna "
                  f"- luka dłuższa niż ten zakres albo Polymarket zmienił slug")
            continue
        cur = base in have
        past = [st for st in have if st <= now]
        nxt = [st for st in have if st > now]
        future = future or bool(nxt)
        if cur:
            print(f"  {tf:<4} bieżące okno ISTNIEJE ({lt(base)})")
        else:
            print(f"  {tf:<4} bieżącego okna NIE MA. Ostatnie istniejące: "
                  + (lt(max(past)) if past else "brak w zakresie")
                  + " | najbliższe następne: " + (lt(min(nxt)) if nxt else "brak w zakresie"))
    if future:
        print("  => okna wracają w przyszłości = LUKA PO STRONIE POLYMARKETU: bot nic nie psuje i wejdzie sam,"
              "\n     gdy tylko rynek się pojawi (finance/pogoda/strike/1d grają w tym czasie normalnie).")


def run_check(bot):
    """Test bez zleceń: czy każdy (krypto, interwał) ma znalezione aktywne okno."""
    now = time.time()
    print(f"\nTest rynków ({time.strftime('%H:%M:%S')}):\n")
    slug0 = slug_candidates("BTC", "5m", now)[0]
    for kind in ("events", "markets"):
        try:
            r = S.get(GAMMA + "/" + kind, params={"slug": slug0}, timeout=8)
            print(f"  Gamma /{kind}: HTTP {r.status_code} {r.text[:50]!r}")
        except Exception as e:
            print(f"  Gamma /{kind} BŁĄD: {type(e).__name__}: {str(e)[:70]}")
    print("  (dla rynków 5m/15m /markets zwraca [] - to normalne, bot używa /events)")
    bot.fetch_spot()
    print(f"  Binance: {bot.api['binance']}, ceny: {len(bot.spot)}/{len(ASSETS)}"
          + (f", brak pary na Binance: {', '.join(sorted(bot.bn_bad))}" if bot.bn_bad else ""))
    print(f"  Chainlink RTDS/TWAP60: {bot.oracle.status()} (5m/15m/4h bez świeżego feedu nie handlują)")
    print(f"  (sekunda w minucie: {int(now) % 60} - tuż po :00/:15/:30/:45 nowy rynek bywa jeszcze nieutworzony)\n")
    first_miss = None
    for tf in WINDOWS:
        for a in ASSETS:
            if not tf_ok(a, tf):
                continue
            w = bot.window(a, tf, now)
            if w:
                rem = int(w["end"] - now)
                print(f"  OK   {a:<5}{tf:<4} {w['slug']}  (koniec za {rem // 3600}h{rem % 3600 // 60:02d}m)")
            else:
                first_miss = first_miss or (a, tf)
                print(f"  BRAK {a:<5}{tf:<4} (żaden slug nie pasuje - bot nie będzie tu grał)")
    if first_miss:
        probe_gap(now)
        sl = slug_candidates(first_miss[0], first_miss[1], now)[0]
        print(f"\n  DIAGNOSTYKA {sl}: ostatni błąd Gamma: {bot.gamma_err or 'brak (puste odpowiedzi)'}")
        try:
            r = S.get(GAMMA + "/events", params={"slug": sl}, timeout=8)
            print(f"  /events HTTP {r.status_code}: {r.text[:300]!r}")
        except Exception as e:
            print(f"  /events BŁĄD: {type(e).__name__}: {str(e)[:80]}")
        print()
    if CFG["strike"]:
        ws = bot.strike_list(now)
        print("  Rynki „powyżej X” (strike, wszystkie krypto):")
        if ws:
            for asset in sorted({w["asset"] for w in ws}):
                for ev_end in sorted({w["end"] for w in ws if w["asset"] == asset}):
                    grp = [w for w in ws if w["end"] == ev_end and w["asset"] == asset]
                    rem = int(ev_end - now)
                    print(f"  OK   {asset} koniec za {rem // 3600}h{rem % 3600 // 60:02d}m: {len(grp)} strike'ów "
                          f"({grp[0]['strike']:,.4g} .. {grp[-1]['strike']:,.4g})  np. {grp[0]['slug']}")
        else:
            print("  BRAK (nie znaleziono) - wklej link do takiego wydarzenia: --strike-event <link>")
        print()
    if CFG["fin"]:
        ws = bot.fin_list(now)
        print("  Finance (Yahoo):")
        labels = sorted({w["label"] for w in ws})
        for lb in labels:                      # pojedynczo, z przerwą - test nie ma sam wywoływać 429
            bot.fin_block = 0.0
            bot.fin_try.pop(lb, None)
            bot.fin_prices({lb: 0.0}, time.time())
            time.sleep(0.4)
        for lb in labels:
            n = sum(1 for w in ws if w["label"] == lb)
            px, sg = bot.fin_px.get(lb), bot.fin_sigma(lb, time.time())
            if px:
                print(f"  OK   {lb:<7} rynków: {n:<3} cena {px[0]:.6g} ({int(time.time() - px[1])}s temu) "
                      f"sigma/min {('%.2e' % (sg * math.sqrt(60))) if sg else '-'}  [{FIN[lb]['y']}]")
            else:
                print(f"  BRAK {lb:<7} rynków: {n:<3} [{FIN[lb]['y']}] {bot.fin_err.get(lb, 'brak danych')}")
        if not ws:
            print("  BRAK rynków finance (poza sesją albo zmienił się format) - bot ich po prostu nie ruszy")
    if CFG["wx"]:
        ws = bot.wx_list(now)
        print(f"  Pogoda (Open-Meteo): rynków {len(ws)}, miast {len({w['city'] for w in ws})}")
        for w in ws[:3]:
            print(f"    {w['label']} {w['date']} P(Yes)={bot.wx_prob(w, now)} cena Yes={w['yes_px']}")
    if bot.broker.live:
        bal = bot.broker.balance()
        print("\n  Logowanie OK." + (f" Saldo: ${bal:.2f}" if bal is not None else " Saldo: nieznane (SDK)."))
        if CFG["import"]:
            addr = bot.broker.address()
            print(f"  Portfel: {addr or 'BRAK ADRESU (ustaw PM_FUNDER)'}")
            if addr:
                try:
                    pos = fetch_positions(addr)
                    opn = [p for p in pos if not p.get("redeemable")]
                    clm = [p for p in pos if p.get("redeemable")]
                    print(f"  Pozycje na koncie: {len(opn)} otwartych, {len(clm)} do odebrania (claim).")
                    for p in opn[:20]:
                        print(f"    {str(p.get('outcome'))[:5]:<5} {float(p.get('avgPrice') or 0) * 100:>3.0f}c "
                              f"${float(p.get('initialValue') or 0):>5.2f}  {str(p.get('title') or p.get('slug'))[:50]}")
                except Exception as e:
                    print(f"  Pozycje na koncie: BŁĄD {type(e).__name__}: {str(e)[:70]}")
    print()


def main():
    ap = argparse.ArgumentParser(description="JASIUPLACEK - bot Polymarket krypto 5m/15m (domyślnie DRY-RUN)")
    ap.add_argument("-s", "--strategies", help="numery strategii po przecinku, np. 1,2,17")
    ap.add_argument("--all", action="store_true", help="uruchom wszystkie strategie")
    ap.add_argument("--list", action="store_true", help="pokaż listę strategii i wyjdź")
    ap.add_argument("--live", action="store_true", default=False, help="PRAWDZIWE zlecenia (bez tego: dry-run)")
    ap.add_argument("--yes", action="store_true", default=False, help="pomiń potwierdzenie przy --live")
    ap.add_argument("--check", action="store_true", help="sprawdź znajdowanie rynków i wyjdź")
    ap.add_argument("--stake", type=float, default=1.0, help="stawka początkowa w $ (domyślnie 1.1; rośnie wg schematu wariantu)")
    ap.add_argument("--max-order", type=float, default=CFG["max_order"], help="twardy limit jednego zlecenia w $")
    ap.add_argument("--max-open", type=float, default=CFG["max_open"],
                    help="limit łącznej ekspozycji w $ (domyślnie 0 = BEZ LIMITU; wartość > 0 włącza limit)")
    ap.add_argument("--no-import", action="store_true", help="nie importuj otwartych pozycji z konta (Data API)")
    ap.add_argument("--pos", action="store_true", help="pokaż tabelę wszystkich otwartych pozycji (bot + konto)")
    ap.add_argument("--focus", type=int, help="numer strategii do tabeli per krypto (domyślnie wszystkie)")
    ap.add_argument("--bin-tp", type=float, default=0.80,
                    help="BIN: sprzedaj gdy cena bid >= tyle (0.90 = 90c), 0 = trzymaj do rozliczenia")
    ap.add_argument("--bin-max-rem", type=int, default=0,
                    help="BIN: wchodź tylko gdy do końca okna <= tyle sekund (0 = bez limitu)")
    ap.add_argument("--edge-5m", type=float, default=CFG["bin_edge_5m"],
                    help="BIN: minimalna przewaga na rynkach 5m (domyślnie 0.17 = 17c)")
    ap.add_argument("--edge-15m", type=float, default=CFG["bin_edge_15m"],
                    help="BIN: minimalna przewaga na rynkach 15m (domyślnie 0.13 = 13c)")
    ap.add_argument("--no-strike", action="store_true", help="wyłącz rynki powyżej X (strike)")
    ap.add_argument("--no-fin", action="store_true", help="wyłącz finance (akcje/indeksy/surowce)")
    ap.add_argument("--no-wx", action="store_true", default=True, help="wyłącz pogodę")
    ap.add_argument("--edge-fin", type=float, default=CFG["bin_edge_fin"], help="BIN: przewaga na finance (domyślnie 0.11)")
    ap.add_argument("--edge-wx", type=float, default=CFG["bin_edge_wx"], help="BIN: przewaga na pogodzie (domyślnie 0.12; ECMWF ensemble)")
    ap.add_argument("--wx-mkt-w", type=float, default=CFG["wx_mkt_w"],
                    help="BIN pogoda: waga ceny rynkowej w fair, 0-0.9 (domyślnie 0.25; 0 = czysty model)")
    ap.add_argument("--fin-mkt-w", type=float, default=CFG["fin_mkt_w"],
                    help="BIN finance: waga ceny rynkowej w fair, 0-0.9 (domyślnie 0.30; 0 = czysty model)")
    ap.add_argument("--rem-5m", type=int, default=CFG["bin_rem_5m"], help="BIN 5m: wejścia tylko w ostatnich tylu sekundach (120)")
    ap.add_argument("--rem-15m", type=int, default=CFG["bin_rem_15m"], help="BIN 15m: wejścia tylko w ostatnich tylu sekundach (300)")
    ap.add_argument("--strike-event", default="",
                    help="slug lub link wydarzenia Bitcoin above (po przecinku) - gdy autowykrywanie go nie znajduje")
    ap.add_argument("--edge-strike", type=float, default=CFG["bin_edge_strike"],
                    help="BIN: minimalna przewaga na rynkach strike (domyślnie 0.11 = 11c)")
    ap.add_argument("--strike-min", type=int, default=CFG["strike_horizon"] // 60,
                    help="strike: blisko końca = ostatnie tyle minut (SNIPER gra tylko tam, BIN gra cały czas; domyślnie 30)")
    ap.add_argument("--strike-hours", type=int, default=CFG["strike_scan"] // 3600,
                    help="strike: bierz rynki kończące się w ciągu tylu godzin (domyślnie 24)")
    ap.add_argument("--strike-cap", type=int, default=CFG["strike_cap"],
                    help="strike: maks. otwartych pozycji na (strategia, wydarzenie) (domyślnie 2)")
    ap.add_argument("--bin-max-px-5m", type=float, default=CFG["bin_max_px_5m"], help="BIN 5m: maks. cena ask wejścia (domyślnie 0.85)")
    ap.add_argument("--bin-max-px-4h", type=float, default=CFG["bin_max_px_4h"], help="BIN 4h: maks. cena ask wejścia (domyślnie 0.85)")
    ap.add_argument("--btc-rule", choices=("inverse", "follow", "off"), default=CFG["btc_rule"],
                    help="inverse: po wejściu BTC w stronę X alty w tym oknie nie grają X (domyślnie); follow: alty nie grają przeciw BTC; off")
    ap.add_argument("--loss-block", type=float, default=CFG["loss_block"],
                    help="pozycja <= -tyle (0.5 = -50%%) blokuje inne wejścia w tę stronę w tym oknie do czasu wyjścia na plus (0 = off)")
    ap.add_argument("--fair-min", type=float, default=CFG["bin_fair_min"], help="BIN: min. prawdopodobieństwo strony wg modelu (domyślnie 0.55)")
    ap.add_argument("--budget", type=float, default=0.0,
                    help="budżet w $: limit ekspozycji; w --dry także symulowane saldo (np. --budget 10)")
    ap.add_argument("--no-counter", action="store_true", help="wyłącz kontrę na drugim interwale")
    ap.add_argument("--counter-at", type=float, default=CFG["counter_at"],
                    help="strata (0.10 = -10%%) wywołująca kontrę (domyślnie 0.10)")
    ap.add_argument("--no-auto-pair", action="store_true", help="wyłącz auto-drugą nogę (BIN)")
    ap.add_argument("--auto-pair-odds", type=float, default=CFG["auto_pair_odds"], help="auto-para: min. kurs drugiej nogi (domyślnie 2.0)")
    ap.add_argument("--auto-min-profit", type=float, default=CFG["auto_min_profit"], help="auto-para: min. pewny zysk w $ (domyślnie 0.02)")
    ap.add_argument("--bin-min-odds", type=float, default=CFG["bin_min_odds"], help="BIN: min. kurs dziesiętny wejścia, 1.8 = cena max 55.5c (domyślnie 1.8)")
    ap.add_argument("--bin-max-odds", type=float, default=CFG["bin_max_odds"], help="BIN: maks. kurs dziesiętny wejścia, 4 = cena min. 25c (domyślnie 4)")
    ap.add_argument("--no-twap", action="store_true", help="5m/15m/4h bez wymogu Chainlink TWAP60 (sygnał tylko z Binance)")
    ap.add_argument("--bin-pair-max", type=float, default=CFG["bin_pair_max"],
                    help="TYLKO BIN: druga noga gdy suma cen obu nóg <= tyle (domyślnie 9 = bez limitu; stare 0.96)")
    ap.add_argument("--bin-pair-match", action="store_true",
                    help="TYLKO BIN: druga noga = tyle samo udziałów co pierwsza (stare zachowanie)")
    ap.add_argument("--bin-second-gap", type=int, default=CFG["bin_second_gap"],
                    help="TYLKO BIN: s między sprawdzeniami drugiej nogi (domyślnie 3)")
    ap.add_argument("--one-side", action="store_true", help="wyłącz granie obu stron tego samego rynku (tylko jedna pozycja na rynek)")
    ap.add_argument("--no-radar", action="store_true", help="ukryj tabelę radaru (domyślnie włączona)")
    ap.add_argument("--twap-cut-5m", type=int, default=CFG["twap_cut_5m"], help="5m: stop wejść tyle sekund przed końcem (domyślnie 30)")
    ap.add_argument("--twap-cut-15m", type=int, default=CFG["twap_cut_15m"], help="15m: stop wejść tyle sekund przed końcem (domyślnie 30)")
    ap.add_argument("--radar", action="store_true", help="pokaż tabelę radaru wszystkich rynków")
    ap.add_argument("--reset", action="store_true",
                    help="wyzeruj statystyki (kopia stanu do .bak); otwarte pozycje zostają, żeby bot dalej je pilnował")
    ap.add_argument("--all-markets", action="store_true", help="nowe wejścia na wszystkich rynkach (domyślnie tylko 5m/15m)")
    ap.add_argument("--with-sniper", action="store_true", help="pozwól uruchomić SNIPER (domyślnie wyłączony)")
    ap.add_argument("--dry", action="store_true",
                    help="TEST: symulowane zlecenia (te same ceny i orderbooki), osobny plik stanu cycuszki_dry_state.json, bez importu z konta")
    ap.add_argument("--state", default=None, help="własny plik stanu/statystyk (domyślnie cycki_live_state.json; w --dry cycuszki_dry_state.json)")
    ap.add_argument("--tabela", action="store_true", help="wypisz pełną tabelę wszystkich wariantów (stawka, DD, serie, $/poz...) ze stanu i wyjdź")
    ap.add_argument("--report", action="store_true", help="wypisz pełną tabelę 5m vs 15m ze stanu i wyjdź (bot może działać w innym oknie)")
    ap.add_argument("--full", action="store_true", help="na żywo pokazuj WSZYSTKIE wiersze tabeli 5m/15m (domyślnie: najważniejsze, gdy ekran niski)")
    ap.add_argument("--max-legs", type=int, default=CFG["max_legs"], help="maks. nóg BIN na rynek (2 = tylko Up+Down; domyślnie 4)")
    ap.add_argument("--leg-step", type=float, default=CFG["leg_step"], help="dokładanie: nowa noga tańsza o tyle od poprzedniej (domyślnie 0.03)")
    ap.add_argument("--leg-gap", type=int, default=CFG["leg_gap"], help="dokładanie: min. sekund między nogami tej samej strony (domyślnie 15)")
    ap.add_argument("--slot-extra", type=float, default=CFG["slot_extra"], help="dodatkowy próg przewagi gdy mało wolnych stawek (domyślnie 0.03; 0 = wyłączone)")
    ap.add_argument("--stats", action="store_true", help="to samo co --report: pełny raport ze stanu i wyjście")
    ap.add_argument("--max-reentry", type=int, default=CFG["reentry_max"],
                    help="tryb RE: maks. ponownych wejść w ten sam rynek po TP (0 = bez limitu; domyślnie 3)")
    ap.add_argument("--anti-max-px", type=float, default=CFG["anti_max_px"], help="ANTI: maks. cena ask odwrotnej strony (domyślnie 0.90)")
    ap.add_argument("--bankroll", type=float, default=0.0, help="LIVE: kapitał startowy $ do schematu X2 (12)")
    ap.add_argument("--stop", type=float, default=0.0, help="LIVE: opcjonalny twardy stop (0 = wyłączony; bot i tak nie wejdzie, gdy kapitał < stawka)")
    ap.add_argument("--max-poz", type=int, default=7, help="maks. jednocześnie otwartych pozycji KRYPTO (5)")
    ap.add_argument("--fin", action="store_true", help="dodatkowo rynki FINANSE (akcje, indeksy, surowce; Yahoo)")
    ap.add_argument("--max-poz-fin", type=int, default=5, help="maks. jednocześnie otwartych pozycji FINANSE (5)")
    ap.add_argument("--max-lacznie", type=int, default=7, help="opcjonalny limit ŁĄCZNY krypto+finanse (0 = brak)")
    ap.add_argument("--max-stake", type=float, default=1000.0, help="LIVE: górny limit stawki $ (8); w --ladder też górny limit stawki")
    ap.add_argument("--ladder", action="store_true",
                    help="DRY: stawka rosnąca I malejąca z bankrollem + reset przy podwojeniu (12->24->48->96: baza 1.2/2/4/8$)")
    ap.add_argument("--ladder-start", type=float, default=1.0, help="--ladder: stawka bazowa na poziomie startowym (1.2)")
    ap.add_argument("--ladder-step-bank", type=float, default=0.02, help="--ladder: krok bankrolla (0.02 = 2%%)")
    ap.add_argument("--ladder-step-stake", type=float, default=0.04, help="--ladder: zmiana stawki na krok (0.04 = 4%%)")
    ap.add_argument("--ladder-min", type=float, default=1.0, help="--ladder: dolny limit stawki $ (1.0)")
    args = ap.parse_args()
    if args.live and LIVE_ID is None:
        sys.exit(f"LIVE: brak wariantu {LIVE_VARIANT} (NAJR_EXIT={','.join(NAJR_EXIT)}). Dla UP_HOLD uzyj NAJR_EXIT zawierajacego HOLD (domyslnie TP80,HOLD).")
    args.ladder = not args.live        # dry: drabina z resetem przy podwojeniu; live: stake_for (UP, reset przy podwojeniu)
    args.no_twap = True                # ta wersja ZAWSZE bez wymogu TWAP60
    args.report = args.report or args.stats or args.tabela
    args.dry = not args.live           # bez --live symulacja
    if args.live:
        LIVE_CFG["bankroll"] = args.bankroll
        LIVE_CFG["stop"] = args.stop
        LIVE_CFG["base"] = args.stake
        LIVE_CFG["max_stake"] = args.max_stake
        LIVE_CFG["max_pos"] = max(1, args.max_poz)
        LIVE_CFG["max_pos_fin"] = max(1, args.max_poz_fin)
        LIVE_CFG["max_total"] = max(0, args.max_lacznie)
        if not args.state:
            args.state = LIVE_STATE
        args.strategies = args.strategies or str(LIVE_ID)
        if args.max_order >= 1000000.0:
            args.max_order = args.max_stake        # twardy limit zlecenia = max stawka
    if args.dry:
        args.live = False
        args.no_import = True
        if not args.state:
            args.state = DRY_STATE
        if args.budget <= 0:
            args.budget = 20.0
    if args.ladder:
        if args.live:
            sys.exit("--ladder działa tylko w dry-run (tryb live ma własny schemat X2).")
        LADDER.update(on=True, start_stake=args.ladder_start, step_bank=max(1e-4, args.ladder_step_bank),
                      step_stake=args.ladder_step_stake, min_stake=args.ladder_min, max_stake=args.max_stake)
        args.stake = args.ladder_start
    if args.state:
        CFG["state_file"] = args.state
    args.max_open = 0.0                # stawka rośnie, a kontrolę wolnych środków robi saldo wariantu (bez sztywnego limitu $11)

    if args.list:
        print_list()
        return
    if args.stake > args.max_order:
        sys.exit(f"Stawka ${args.stake} przekracza --max-order ${args.max_order}. Zmień jedno z nich świadomie.")
    if args.reset and os.path.exists(CFG["state_file"]):
        try:
            with open(CFG["state_file"]) as f:
                old = json.load(f)
            bak = f"{CFG['state_file']}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
            with open(bak, "w") as f:
                json.dump(old, f)
            # statystyki od zera, ale pozycje jeszcze niezamknięte zostają:
            # bez nich bot nie rozliczyłby prawdziwych zakładów i mógłby wejść drugi raz w ten sam rynek
            keep = [t for t in old.get("trades", []) if t.get("status") in LOCK]
            with open(CFG["state_file"], "w") as f:
                json.dump({"trades": keep, "start": time.time(), "since": time.time()}, f)
            print(f"Statystyki wyzerowane. Kopia: {bak}. Zachowano otwarte pozycje: {len(keep)}.")
        except Exception as e:
            sys.exit(f"Reset nieudany ({type(e).__name__}) - nic nie zmieniono, stan zostaje.")

    if args.all:
        ids = [s["id"] for s in STRATS]
    elif args.strategies:
        ids = [int(x) for x in args.strategies.replace(" ", "").split(",") if x.isdigit()]
    else:
        ids = list(DEFAULT_IDS)
    ids = [i for i in ids if i in {s["id"] for s in STRATS}]
    if args.live:
        ids = [LIVE_ID]                                   # LIVE: tylko wariant z NAJR_LIVE (domyslnie ANTI_UP_HOLD)
    CFG["short_only"] = True      # jasiuplacek: zawsze tylko 5m/15m
    if not args.with_sniper:
        ids = [i for i in ids if i != 3] or list(DEFAULT_IDS)      # SNIPER wyłączony; bez niego zostaje BIN
    if not ids:
        print("Nie wybrano żadnej poprawnej strategii.")
        return
    focus = args.focus if args.focus in ids else None

    if args.live and not args.check and not args.yes:
        print(f"\n!!! LIVE: prawdziwe zlecenia, ${args.stake:.2f} na zakład, strategii: {len(ids)}, "
              + (f"limit ekspozycji ${args.max_open:.0f}." if args.max_open > 0 else "BEZ limitu ekspozycji."))
        if input("Wpisz TAK aby uruchomić: ").strip() != "TAK":
            print("Anulowano.")
            return

    if args.report:
        globals()["OracleRTDS"] = _NullOracle                 # raport bez sieci: bez połączenia z RTDS
        for _ in range(5):                                    # plik może być akurat zapisywany przez działającego bota
            try:
                with open(CFG["state_file"]) as f:
                    json.load(f)
                break
            except Exception:
                time.sleep(0.3)
    globals()["OracleRTDS"] = _NullOracle                     # BEZ TWAP: brak połączenia z RTDS/Chainlink
    ORACLE_TFS.clear()
    broker = Broker(args.live)
    bot = Bot(set(ids), args.stake, focus, broker, args.max_open)
    bot.show_radar = not args.no_radar
    CFG["bin_max_odds"] = max(1.05, args.bin_max_odds)
    CFG["bin_min_odds"] = max(1.0, args.bin_min_odds)
    CFG["auto_pair"] = not args.no_auto_pair
    CFG["counter"] = not args.no_counter
    CFG["counter_at"] = max(0.0, args.counter_at)
    CFG["btc_rule"] = args.btc_rule
    CFG["loss_block"] = max(0.0, args.loss_block)
    CFG["bin_fair_min"] = args.fair_min
    CFG["auto_pair_odds"] = max(1.01, args.auto_pair_odds)
    CFG["auto_min_profit"] = args.auto_min_profit
    CFG["bin_max_px_5m"] = min(0.99, max(0.05, args.bin_max_px_5m))
    CFG["bin_max_px_4h"] = min(0.99, max(0.05, args.bin_max_px_4h))
    bot.show_pos = args.pos
    if args.dry and args.budget > 0:
        bot.sim_budget = args.budget
    if args.live:
        # bankroll startowy: --bankroll albo (domyslnie) realne saldo konta przy pierwszym starcie; zapamietany w stanie
        b0 = args.bankroll if args.bankroll > 0 else bot.state.get("live_bank0")
        if not b0:
            b0 = bot.broker.balance()
        if not b0 or b0 < LIVE_CFG["min_stake"]:
            if args.check:
                b0 = LIVE_CFG["min_stake"]
            else:
                sys.exit("Nie znam salda konta (albo < 1$). Podaj bankroll: python najr_live.py --live --bankroll 5")
        b0 = round(float(b0), 2)
        bot.state["live_bank0"] = b0
        LIVE_CFG["bankroll"] = b0
        LIVE_CFG["div"] = b0 / max(0.01, LIVE_CFG["base"])      # reset przy podwojeniu: baza = poziom / div (start 1$ -> 2$ przy 2x, 4$ przy 4x...)
        bot.sim_budget = b0                    # LIVE: księga bota liczy kapitał od bankrolla startowego
        print(f"LIVE: wariant {LIVE_VARIANT} (id {LIVE_ID}), bankroll startowy ${b0:.2f}, stawka start ${LIVE_CFG['base']:.2f} "
              f"({LIVE_CFG['base'] / b0 * 100:.1f}% bankrolla), +{NAJR_STEP * 100:.0f}% stawki / +2% bankrolla, reset przy 2x kapitalu (jak w dry), "
              f"max {LIVE_CFG['max_pos']} otwartych na wariant (lacznie {LIVE_CFG['max_total']})")
        if not args.check:
            bot.save()
    CFG["import"] = not args.no_import
    bot.tp = {k: v for k, v in [(17, args.bin_tp)] + list(ANTI_TP.items()) if v > 0}
    CFG["bin_max_rem"] = args.bin_max_rem
    CFG["bin_edge_5m"] = args.edge_5m
    CFG["bin_edge_15m"] = args.edge_15m
    CFG["reentry_max"] = max(0, args.max_reentry)
    CFG["slot_extra"] = 0.0
    CFG["twap_cut_5m"] = max(8, args.twap_cut_5m)
    CFG["twap_cut_15m"] = max(8, args.twap_cut_15m)
    if args.no_twap:
        ORACLE_TFS.clear()
    CFG["both_sides"] = not args.one_side
    CFG["bin_pair_max"] = args.bin_pair_max
    CFG["bin_pair_match"] = args.bin_pair_match
    CFG["bin_second_gap"] = max(1, args.bin_second_gap)
    CFG["max_legs"] = max(2, args.max_legs)
    CFG["anti_max_px"] = min(0.99, max(0.05, args.anti_max_px))
    CFG["leg_step"] = max(0.0, args.leg_step)
    CFG["leg_gap"] = max(3, args.leg_gap)
    CFG["slot_extra"] = max(0.0, args.slot_extra)
    bot.full_view = args.full
    CFG["strike"] = CFG["wx"] = False
    CFG["fin"] = bool(args.fin)                          # finanse tylko z --fin
    LIVE_CFG["fin_on"] = bool(args.fin)
    LIVE_CFG["max_pos_fin"] = max(1, args.max_poz_fin)
    LIVE_CFG["max_pos"] = max(1, args.max_poz)
    LIVE_CFG["max_total"] = max(0, args.max_lacznie)
    CFG["bin_edge_fin"] = args.edge_fin
    CFG["bin_edge_wx"] = args.edge_wx
    CFG["wx_mkt_w"] = min(0.9, max(0.0, args.wx_mkt_w))
    CFG["fin_mkt_w"] = min(0.9, max(0.0, args.fin_mkt_w))
    CFG["bin_rem_5m"] = max(0, args.rem_5m)
    CFG["bin_rem_15m"] = max(0, args.rem_15m)
    CFG["bin_edge_strike"] = args.edge_strike
    CFG["strike_horizon"] = max(5, args.strike_min) * 60
    CFG["strike_scan"] = max(1, args.strike_hours) * 3600
    CFG["strike_cap"] = max(1, args.strike_cap)
    CFG["strike_events"] = [clean_event_arg(x) for x in args.strike_event.split(",") if x.strip()]
    if args.tabela:
        console.print(Text(f"KAPSKO - tabela {time.strftime('%Y-%m-%d %H:%M:%S')} | budżet ${bot.sim_budget or 0:.0f}/wariant", style="bold cyan"))
        for kd in ("map", "a", "b"):
            for tb in bot.rank_tables(kd, 0):
                console.print(tb)
        return
    if args.report:
        bot.print_stats()
        try:
            print("\nTabela CSV (wszystkie statystyki, wiersz = wariant):", write_csv(bot))
        except Exception as e:
            print("CSV nieudany:", type(e).__name__)
        return
    if args.check:
        run_check(bot)
        return
    try:
        bot.run()
    except KeyboardInterrupt:
        bot.save()
        try:
            write_report_file(bot)
            bot.print_stats(full=False)
        except Exception:
            pass
        print("\nZatrzymano. Stan zapisany w", CFG["state_file"], "| raport:", CFG["report_file"], "| tabela:", CFG["csv_file"])
        sys.exit(0)


if __name__ == "__main__":
    main()
