# Odpalenie dry-runów w Termuxie (krok po kroku)

Silnik jest **bez zależności** (tylko biblioteka standardowa Pythona) — żadnego `pip install`,
żadnych kluczy API. Potrzebny tylko git i python.

## 0. Szybka odpowiedź: 'czy oba dry-runy działają?'
```bash
pgrep -af 'dryrun'                       # powinny być 2 linie (albo 1 przy start_both)
tail -3 logs/dryrun1.log logs/dryrun2.log  # linie 'cykl ... err 0'
python3 dryrun1_master.py --report | head -6
python3 dryrun2_master.py --report | head -6
```
Czas w logach jest w **UTC** (telefon zwykle pokazuje UTC+1/UTC+2).

## 1. Jednorazowa instalacja
```bash
pkg update -y && pkg install -y git python
termux-wake-lock          # żeby Android nie usypiał procesów w tle
```

## 2. Klon repozytorium
```bash
git clone https://github.com/Gumos12345/poly-flash.git
cd poly-flash/bots
```
(jeśli masz już klona: `cd poly-flash && git pull && cd bots`)

## 3. Test silnika (2 sekundy, bez sieci)
```bash
python3 -m unittest -q tests_engine
# oczekiwane: Ran 21 tests ... OK
```

## 4. Start OBU dry-runów (w tle, bankroll 50 $, stawka 1.25 $)

**Wariant A (zalecany na telefonie) - oba w JEDNYM procesie** (wspólne pobieranie danych,
~2x szybciej i o połowę mniej zapytań - na LTE/telefonie to duża różnica):
```bash
chmod +x *.sh
./start_both.sh
tail -f logs/both.log
```

**Wariant B - dwa osobne procesy** (dokładnie jak w sandboxie; więcej zapytań, wolniejsze cykle):
```bash
./start_all.sh
tail -f logs/dryrun1.log
tail -f logs/dryrun2.log
```

## 5. Podgląd na żywo
```bash
tail -f logs/dryrun1.log      # Ctrl+C zamyka tylko podgląd, bot dalej działa
tail -f logs/dryrun2.log
```
W linii `cykl` widzisz: kapitał i liczbę transakcji trzech czołowych wariantów, status cen/zmienności,
liczbę zapytań i błędów.

## 6. Raport (piękna tabela HTML ze wszystkimi statystykami)
```bash
python3 report_rich.py        # -> RAPORT.html  +  reports/RAPORT.csv
./finalize.sh                 # -> reports/dryrun1_report.md/.csv, dryrun2_..., results_summary.md
termux-open RAPORT.html       # otwarcie w przeglądarce (wymaga: pkg install termux-api)
```
Sam HTML jest samodzielny (CSS+JS w środku) — możesz go też skopiować do pamięci telefonu i otworzyć
w Chrome. Klikasz nagłówek kolumny = sortowanie.


## 6a. Tabelka na żywo w terminalu (bez przeglądarki)
```bash
python3 tabelka.py                # jeden rzut tabeli (oba przebiegi)
python3 tabelka.py --watch        # odświeżanie co 20 s (Ctrl+C = koniec podglądu, bot działa dalej)
python3 tabelka.py -w -i 10       # co 10 s
python3 tabelka.py --set 2        # tylko przebieg 42-wariantowy
python3 tabelka.py --top 40       # wszystkie warianty
python3 tabelka.py --sort wr      # sortowanie: pnl | wr | n | dd
python3 tabelka.py -w --trades    # + ostatnie 8 zamkniętych transakcji
```
Kolumny: `n` liczba transakcji, `WR%` skuteczność, `PnL$` zysk, `W/L` wygrane/przegrane,
`ret%` zwrot z bankrolla 50 $, `DD%` maks. obsunięcie, `5m$/15m$` PnL per interwał,
`px` średnia cena wejścia, `edge` średnia przewaga przy wejściu, `otw` otwarte pozycje.
Tabelka **tylko czyta** `state/*.json`, więc można ją odpalać równolegle z botem.


## 6b. Backtest na danych historycznych (1 dzień / tydzień)
Ten sam kod co dry-run, ale na cenach z przeszłości (CLOB `prices-history` + rozliczenia z Gammy).
```bash
python3 backtest.py --days 1                        # doba, BTC/ETH/SOL, 5m+15m (~2-3 min)
python3 backtest.py --days 7 --assets BTC,ETH       # tydzień, 2 monety (~15-30 min na LTE)
python3 backtest.py --hours 6 --assets BTC --tfs 5m
python3 backtest.py --days 1 --slip 0.02            # gorsze wypełnienia (2c poślizgu)
python3 backtest.py --days 1 --limit 50             # szybki test na 50 oknach
```
Wynik: **BACKTEST.html** (ta sama tabela co RAPORT.html) + `reports/BACKTEST.csv`.
Pobrane okna są cache'owane w `backtest_cache/`, więc kolejne uruchomienia i przerwane przebiegi
dokańczają się bez ponownego pytania API.


## 6c. LIVE: S2_TP70 na wszystkie 5m/15m (bankroll 50$, stawka 1.25$, drabinka +1%/+1%)
```bash
pip install py-clob-client-v2            # to samo SDK, ktorego uzywa Twoj najr_live_UP_HOLD.py
export PM_PRIVATE_KEY="0x..."             # klucz prywatny portfela
export PM_FUNDER="0x..."                  # adres portfela/proxy z USDC (jak w UI Polymarket)
export PM_SIG_TYPE=3                      # 1 = email/Magic, 2 = proxy, 3 = gnosis (domyslnie w bocie)

python3 live_s2.py --check                # 1) logowanie + saldo + rynki, ZERO zlecen
python3 live_s2.py --paper                # 2) 24-48 h na zywych ksiazkach, bez pieniedzy
I_UNDERSTAND_RISK=1 python3 live_s2.py --live --yes --bank 50 --stake 1.25 --max-order 1.25 --max-open 3
```
Podglad: `python3 tabelka.py --set 3 -w`  •  stop: `Ctrl+C` albo `pkill -f live_s2.py`
Bezpieczniki: max_order 1.25$, max_open 3, dzienny stop 10% kapitalu, jedna pozycja na rynek,
BRAK ponowien po niejednoznacznej odpowiedzi. Wygrane z rozliczen odbierasz w UI (Claim).


## 6d. DWA boty naraz (S2_TP70 + BIN) - jak pilnowac ekspozycji
```bash
# bot A (S2_TP70): 5 pozycji, dzienny stop -50%%, drabinka +1%%/+1%%
python3 live_s2.py --live --yes --bank 50 --stake 1.25 --max-order 1.25 --max-open 5 --daily-stop 0.5

# bot B (Twoj najr_live jako BIN, id 17): 3 pozycje, twardy prog kapitalu 25$ (-50%%)
NAJR_LIVE=BIN NAJR_STEP=0.01 NAJR_STEP_BANK=0.01 \
  python3 najr_live_UP_HOLD.py --live --yes --bankroll 50 --stake 1.25 --max-order 1.25 \
  --stop 25 --max-poz 3 --max-lacznie 3 --max-open 3.75 \
  --bin-tp 0.70 --fair-min 0.45 --edge-5m 0.04 --edge-15m 0.04 --bin-max-px-5m 0.90

# wspolny licznik ekspozycji obu botow (drugi terminal)
python3 exposure.py -w -i 15 --max-cost 10
```
Maks. ekspozycja: 5 x 1.25 + 3 x 1.25 = **10 $** (20%% bankrolla). Stopy dzialaja NIEZALEZNIE.

## 7. Stop / wznowienie
```bash
./stop_all.sh                 # zatrzymuje oba procesy (także tryb start_both) — stan zapisany
./start_all.sh                # UWAGA: start_all.sh zeruje stan!
# wznowienie BEZ zerowania:
python3 dryrun1_master.py --bank 50 --stake 1.25
python3 dryrun2_master.py --bank 50 --stake 1.25
```

## 8. Przydatne przełączniki
```bash
python3 dryrun1_master.py --list                 # lista 25 wariantów
python3 dryrun2_master.py --list                 # lista 42 wariantów
python3 dryrun1_master.py --report               # tabela z zapisanego stanu (bez sieci)
python3 dryrun1_master.py --reset                # zerowanie statystyk
python3 dryrun1_master.py --minutes 480          # auto-stop po 8 h
python3 dryrun2_master.py --bank 50 --stake 1.25 # własny bankroll/stawka
```

## 9. Co ile pyta API (zużycie danych)
Jeden przebieg: ~28 zapytań na cykl (7 monet × 5m/15m × 2 strony książki) przy cyklu ~3–5 s.
Dwa przebiegi równolegle ≈ 15 zapytań/s. Transfer jest mały (JSON-y po kilka kB), ale to nadal
dane mobilne — na Wi-Fi bez znaczenia.

## 10. Gdzie co leży
```
state/dryrun1.json, state/dryrun2.json     # stan (bankroll, pozycje, historia) — przeżywa restart
reports/dryrun1_trades.jsonl               # każda zamknięta transakcja (audyt)
reports/RAPORT.csv                         # 52 kolumny statystyk dla 67 wariantów
RAPORT.html                                # pełny raport z tabelami i sortowaniem
logs/dryrun1.log, logs/snapshots.txt       # logi + migawki co 5 min
```
