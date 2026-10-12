# Przeglad wszystkich strategii (gist 3d765b0e…) + co ma realny sens

## 0. Inwentarz: co uzytkownik ma
| paczka | co to jest | status |
|---|---|---|
| `pm-rust` (uruchomiony na live) | Rust, FINANCE-3 (tag 120: A40_40 drop -40%/TP +40%, C30_30 -30/+30, SL -90%) | LIVE, po moich poprawkach v4 (ask<=0.25, hold 12h) |
| `strategia1..6 + strategia_unified .rs` | 6 wariantow "LONG" (drop 15% -> TP/SL 8/8, 12/12, 15/15, 30/12, 15/6, 20/25) + SCALP (kup 0.50-0.85, TP +6c, SL -3c, **SCALP_MAX_POSITIONS=0 = wylaczony**) | paper, ten sam pomysl co FIN, tylko inne TP/SL |
| `termux-7-strategies-paper` (dryrun.py) | 7 presetow s1-s7: drop 12-20% z 20 obserwacji, TP 10-30%, SL 6-25%, "odbicie" 1-2.5%, okna 5m/15m | paper-only, 50$ wirtualne, fee 2%/strona |
| `S8_full_code_(1).txt` | osobny bot S8: DROP 20%, REBOUND_TICKS 3, MIN_UP_TICKS 2, MIN_ENTRY_PRICE 0.45, MAX_SPREAD 0.07 | paper |
| `sports_live/bot_v2.py` | "FADE LONGSHOT + hold do rozstrzygniecia" (kup NO gdy YES w 0.15-0.50), model opłat + bramka EV, backtest wbudowany, `--dry/--scan/--live` | paper z dashboardem |
| `s7-paper-compare` | SPORT_REVERSE (spadek YES -> kup YES) + crypto A/B, mirror-test | paper |

## 1. Weryfikacja ich "dowodu" na sport (strategy_validation.json: fade 0.15-0.50 -> +24%/trade, t=5.5)
Replikacja na 197 rynkach sportowych (tag 1, rozwiazane w ciagu 25 dni, YES/NO, vol>200),
wejscie przy PIERWSZYM wejsciu ceny YES w pasmo, hold do rozstrzygniecia, fee 0.05, spread 2c:

| filtr plynnosci | n | YES wygral | srednia cena | EV kupna NO | t |
|---|---|---|---|---|---|
| vol >= 200 (wszystkie) | 197 | **18,8%** | 0,400 | **+25,4%** | **5,57** |
| vol >= 2 000 | 90 | 24,4% | 0,346 | +10,6% | 1,50 |
| vol >= 10 000 | 40 | **35,0%** | 0,337 | **-6,9%** | -0,61 |
| vol >= 50 000 | 16 | **50,0%** | 0,325 | **-36,7%** | -2,30 |

**Wniosek: to NIE jest edge, ktory da sie zrealizowac.** "Przewaga" jest monotonicznie coraz
mniejsza wraz z plynnoscia i w plynnych rynkach znika/odwraca sie (YES po 0.33 wygrywa 50%).
Czyli backtest nagradza rynki, w ktorych wydrukowana cena (mid/last) nie jest cena, po ktorej
mozna kupic NO - klasyczny artefakt cienkich rynkow. Ich walidacja (n=194, +24%) = moja kolumna
"vol>=200". Wniosek praktyczny: bramka EV w `bot_v2.py` musi dzialac na REALNEJ ksiedze
(i tak dziala w trybie live), ale `strategy_validation.json` daje falszywa pewnosc siebie.

## 2. Weryfikacja rodziny "kup po spadku" na krypto (presety s1-s7, S5-S9, warianty .rs)
30 dni swiec BTC 1-min (43200) + CLOB:
- 5-min okna: baseline P(up)=50,5%; po spadku w oknie rozliczenie "Up" tylko **4-16%** (nie 50%).
- 1h okna: te same 0-11%.
- Geometria +30..40% TP / -90% SL wymaga **69-75% winrate** (78% po opłatach). Zmierzone 10-16%.
- Fee crypto = 0.07 (nie 2% jak w ich modelach): przy p=0.3 to ~4.9% wartosci pozycji na strone.
=> Zadna konfiguracja TP/SL z paczek s1-s7 tego nie ratuje: problem jest w sygnale (kupujemy
strona, ktora jest pod woda wzgledem open okna) i w kosztach. 2%/strona w ich dryrun.py to zanizenie.

## 3. Co naprawic (konkretnie)
1. **Modele kosztow we wszystkich paczkach**: 2%/strona -> `fee = shares*rate*p*(1-p)` +
   realny spread (wejscie ask / wyjscie bid). Bez tego kazdy paper run klamie o +2-4 p.p./transakcje.
2. **SCALP (kup 0.50-0.85, TP +6c, SL -3c)**: jako taker jest samobojczy - `MAX_SPREAD=0.07`
   przy TP 6c oznacza koszt wiekszy niz cel. Zmiana: **zlecenia maker (post-only)** w rynkach
   o spreadzie <= 0.01-0.02, wyjscie limitem; maker placi 0 i dostaje rebate 15-25% (+ program
   liquidity rewards). To jedyne strukturalnie dodatnie zrodlo przychodu na tej platformie.
3. **Sport**: zostawic FADE (ich dane: momentum -6,3%/trade, t=-16 -> wywalone slusznie), ale
   (a) liczyc EV z realnej ksiazki, (b) dodac minimalny wolumen rynku (np. >10k) i maks. spread,
   (c) wziac pasmo 0.15-0.50 tylko tam, gdzie jest realna dwustronna ksiazka, (d) mierzyc forward.
4. **Krypto 5m/15m/1h (s1-s7, S5-S9)**: przeniesc na inne uniwersum - nie ma tam edge, a fee 0.07
   dobija. Jesli chca zostac przy "kup po spadku", to tylko na rynkach, gdzie kwotowania realnie
   wracaja: cienkie Finance (to juz chodzi) albo in-play sport.
5. **Portfel**: 20 pozycji x 1$ przy saldzie ~14-20$ = 100% ekspozycji; dodac limit ekspozycji
   (jest w pm-rust: LIVE_MAX_EXPOSURE) i kill-switch (jest: KILL_SWITCH_DROP_PCT=0.30).

## 4. Rekomendacja kategorii
1. **Finance/Recurring (tanie rynki, dlugi hold)** - jedyna konfiguracja z dodatnim EV w symulacji
   (12-24h: +17..27%/poz brutto) - URUCHOMIONA na live (v4). Do oceny po 1-2 dniach na `dry_trades.csv`.
2. **Sports in-play** - kierunkowo sensowna (przegrywajacy faworyt/underdog przereagowuje), ale
   "dowod" +24% jest artefaktem cienkich rynkow; sensowne tylko z realna ksiazka + feedem na zywo.
3. **Market making + liquidity rewards** (crypto up/down, weather, recurring) - jedyne zrodlo
   przychodu niezalezne od kierunku; wymaga zlecen maker i zarzadzania zapasem.
4. **Crypto 5m/15m/1h rebound** - zmierzone ~0; nie skalowac.

## 5. Skrypty badawcze (w tym repo)
- `notes/pm-rust-kategorie-i-edge.md` - dane kategorii/tagow + fee + testy.
- `notes/edge-test-btc.js` - test "kup Up po spadku" na 30 dniach BTC 1m.
- `notes/replikacja-ask-bid-fee.js` - sweep horyzontu z realnymi kosztami (ask/bid/fee).
- replikacja sportu: patrz logi w tej sesji (sports_fade3/5.js) - wyniki w tabeli wyzej.
