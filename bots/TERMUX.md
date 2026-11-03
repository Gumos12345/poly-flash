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
