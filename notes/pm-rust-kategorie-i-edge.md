# Analiza: gdzie przeniesc bota + czy strategia "kup Up po spadku" ma sens
Dane zebrane 2026-10-12 (sandbox). Zrodla: Gamma API (`gamma-api.polymarket.com`),
CLOB API, docs.polymarket.com/trading/fees, Binance daily klines (1m, 30 dni: 2026-09-12..2026-10-11).

## 1. Tagi/kategorie: wolumen i spread (top-100 rynkow per tag, volume24hr)
| tag_id | kategoria | suma vol24 (top100) | mediana spreadu | taker fee rate |
|---|---|---|---|---|
| 1 | Sports | $10.3M | 0.010 | 0.05 |
| 100639 | Games | $8.3M | 0.010 | 0.05 |
| 2 | Politics | $8.2M | 0.003 | 0.04 |
| 64 | Esports | $6.3M | 0.010 | 0.05 |
| 101757 | Recurring | $2.8M | 0.002 | 0.05 |
| 100350 | Soccer | $2.2M | 0.010 | 0.05 |
| 21 | Crypto | $2.0M | 0.010 | 0.07 |
| 1312 | Crypto Prices | $1.9M | 0.006 | 0.07 |
| 864 | Tennis | $1.3M | 0.010 | 0.05 |
| 84 | Weather | $0.7M | 0.001 | 0.05 |
| **120** | **Finance (obecny tag bota)** | — | — | 0.04 |

Tag 120 = "Finance" to tematyka IPO / stopy Fed / rate cuts (sprawdzone eventy: `kraken-ipo-in-2025`,
`how-many-fed-rate-cuts-in-2026`, `openai-ipo-by`). To rynki **dlugoterminowe i rzadkie** — nie da sie
na nich "napierdalac pozycjami" ani stosowac logiki spadku z 5-minutowego okna.

Proba 500 najwiekszych eventow: Sports 186 eventow / 7607 rynkow, Games 120/5445, Esports 20/392,
Soccer 77/2252, Tennis 26/390, Crypto 39/432. W chwili snapshotu `live=true` bylo 8 eventow
(in-play), kazdy z 12-17 rynkami (np. CS2: 15 rynkow, ATP: 16).

## 2. Oplaty (docs.polymarket.com/trading/fees)
`fee = C x feeRate x p x (1-p)` (C = liczba share'ow, p = cena). Tylko taker; maker 0 (+ rebate 15-25%).
Rate: Crypto 0.07, Sports/Economics/Culture/Weather/Other 0.05, Finance/Politics/Tech/Mentions 0.04, Geopolitics 0.
W praktyce: dla 100 share'ow @ $0.20 fee = $1.12 => **5.6% wartosci pozycji**; @ $0.50 => $1.75 => 3.5%.
Im tanszy share, tym wiekszy procentowy koszt (przy $0.10 to 6.3%). To zabija skalpowanie na 5m crypto.

## 3. Test "kup Up po spadku" (BTC, 30 dni, 43200 swiec 1m)
Baseline bez sygnalu: P(okno 5m konczy sie wyzej niz open) = 50.5% (n=8640); 1h = 51.0% (n=720).
Srednia |zmiana| w oknie: 5m = 0.075%, 1h = 0.224%.

| prog. spadku | wejscie w minucie | sygnaly | P(rozliczenie Up) |
|---|---|---|---|
| 0.05% | 1 | 1300 | 15.8% |
| 0.05% | 2 | 1645 | 9.2% |
| 0.05% | 3 | 1829 | 3.8% |
| 0.10% | 1 | 422 | 10.9% |
| 0.20% | 1 | 75 | 4.0% |
| 0.20% | 2 | 125 | 1.6% |
| 1h, 0.30% | 30 | 52 | 11.5% |
| 1h, 0.30% | 45 | 64 | 1.6% |

Wniosek mechaniczny (nie "brak szczescia"): jesli cena jest ponizej open okna, to okno rozlicza sie
"Up" tylko w 4-16% przypadkow — czyli share "Up" po spadku jest wart ~0.04-0.16 i mniej wiecej tyle
kosztuje na rynku. Kupowanie go i trzymanie do rozliczenia = EV ~0 minus spread i fee.

A geometria wyjsc bota (+30..40% TP / -90% SL) wymaga winrate **69.2%** (+40/-90) lub **75.0%** (+30/-90),
a po doliczeniu fee przy p~0.20 juz **~78%**. Zmierzone 10-16% => EV ok. -0.7 do -0.9 na kazde 1$ stawki
w wariancie "trzymam do rozliczenia" i mocno ujemne w wariancie TP/SL.

Test powtarzalny: `notes/edge-test-btc.js` (pobiera klines z data.binance.vision i liczy tabele).

## 4. Gdzie realnie mozna postawic ten bot (kolejnosc wg sensownosci)
1. **Sports / Games / Esports in-play** (tagi 1, 100639, 64, 100350, 864) — najwiecej rynkow i wolumenu,
   krotkie zycie rynku, ceny przereagowuja na pojedyncze zdarzenia (gol, czerwona kartka) => tylko tu
   logika "spadek -> odbicie" ma sens ekonomiczny. Wymaga feedu na zywo (wynik/statystyki).
2. **Weather** (tag 84) — mediana spreadu 0.001 (najlepsza na platformie), deterministyczne rozliczenie
   (NWS/NOAA), duzo bucketow dziennych, mala konkurencja. Ale potrzebny nowy modul strategii
   (odczyt temperatury vs bucket), nie "spadek -> Up".
3. **Market making + liquidity rewards** (maker rebate 15-25%, rewardsMinSize/rewardsMaxSpread) —
   jedyny strukturalnie dodatni EV sposob; to inny bot (kwotowanie obu stron, zarzadzanie zapasem).
4. **Crypto 5m/1h up/down** — najwiecej rynkow dziennie, ale zmierzony edge ~0 przy fee 0.07 + spread 1c.
5. **Finance/Politics/Recurring** — za rzadkie/za dlugie, nie do "napierdalania".
6. Geopolitics — fee 0, ale illiquid i dlugi horyzont.

## 5. Adresy do przeslania plikow (dla uzytkownika)
- termbin (najprosciej, bez logowania): `cat ~/pm-rust/src/main.rs | nc termbin.com 9999` -> wypisze URL
- 0x0.st: `curl -F 'file=@~/pm-rust/src/main.rs' https://0x0.st` -> URL
- paste.rs: `curl --data-binary @~/pm-rust/src/main.rs https://paste.rs` -> URL
- gist: https://gist.github.com/ -> wklej -> "Create secret gist" -> link
- wlasne repo: https://github.com/Gumos12345/poly-flash/upload/main (PUBLICZNE!) albo nowe prywatne:
  https://github.com/new -> nazwa `pm-rust`, Private -> upload plikow -> link (mam dostep do repo uzytkownika)
- UWAGA: nie wysylac `~/.poly_env` ani klucza prywatnego na zadne publiczne paste/gist/repo.


## 6. Replikacja backtestu z ekranow uzytkownika (2026-10-12)
Uzytkownik dostal (od innego narzedzia) tabelke: okno 6h, -40/+40 -> win 75,8% / ROI +21,3%,
-30/+30 -> win 75,4% / ROI +14,2%, wejsc 3,4-5,8/h. Sprawdzone wlasnym backtestem z realnych danych.

Metoda (`notes/replikacja-backtestu-finance.js`):
- Gamma: wszystkie rynki tag_id=120 (Finance), limit 100: 1000 zamknietych + 500 otwartych = 1500, z tego 1442 z historia,
- CLOB `prices-history?interval=max&fidelity=1` = ostatnie 30 dni, ~4300 punktow (~10-min probkowanie),
- sygnal: cena spadla o X% w ciagu 6h; wejscie w cenie z historii; wyjscie: TP +X%, SL -90%, time-exit 2h,
- brak spreadu, brak oplat, "win" = PnL > 0.

Wyniki:
| konfiguracja | sygnaly | win | ROI/pozycja (brutto) | TP/SL/time-exit |
|---|---|---|---|---|
| 6h, -40/+40 | 16096 | 48,3% | +9,53% | 4646 / 2 / 11448 |
| 6h, -30/+30 | 33880 | 49,4% | +7,40% | 10291 / 5 / 23584 |

Przy probkowaniu 1h (fidelity=60) win spada do ~36% a ROI do +1,7-1,9% -> wynik jest bardzo
wrazliwy na rozdzielczosc danych. Wniosek: tabelka 73-76% winrate / +12-21% ROI NIE replikuje sie.

Kluczowe zastrzezenia do tych +9,5%:
1. Fee: Finance 0,04 => `fee=C*0,04*p*(1-p)` => ok. 2-4% wartosci pozycji na strone (przy p~0,2:
   3,2% kupno + ~2,9% sprzedaz) => netto ok. -2% do +2%.
2. Spread: MAX_SPREAD=0.05 to przy share za 0,20-0,50 koszt 2-5c = 10-25% ceny; 0.05 "przepuszcza"
   koszt wiekszy niz TP.
3. SL -90% praktycznie nigdy nie dziala (2 wystapienia na 16096) => pozycja zyje do time-exit 2h.
4. Historia CLOB w illiquid rynkach to czesto ostatni trade/quote, nie ksiazka => te ceny nie sa
   wykonywalne (brak plynnosci na tych poziomach). To najprawdopodobniejsza przyczyna zawyzenia.
5. Tylko 30 dni historii (API) i brak danych o tym, czy backtest uwzglednil filtry bota.


## 7. Przeglad prawdziwego kodu (gist `finance_6h_start_z_historia_v3`, main.rs 3990 linii)
Kod zdekodowany do `pm-rust/src/main.rs`, skrypt do `pm-rust/finance_6h_start_z_historia_v3-1.sh`.

**NAJWAZNIEJSZE: live bot nie gra tego, co bylo backtestowane.**
- `manage_exits` (linia ~2009): dla `kind != "crypto"` (a Finance wchodzi z `kind="finance"`) time-exit =
  `opened_at + SPORTS_TIME_EXIT_SEC`, a `SPORTS_TIME_EXIT_SEC = 7200` => **twarde wyjscie po 2h**.
- Ten sam backtest (1442 rynki tag 120, 30 dni, dane CLOB ~10 min), z time-exitem 2h vs bez:
  | konfiguracja | sygnaly | win | ROI/pozycja (brutto) |
  |---|---|---|---|
  | 6h -40/+40, time-exit 2h | 16096 | 48,3% | +9,53% |
  | 6h -40/+40, BEZ time-exitu (hold do TP/SL) | 16100 | **84,4%** | **+26,70%** |
  | 6h -30/+30, time-exit 2h | 33880 | 49,4% | +7,40% |
  | 6h -30/+30, BEZ time-exitu | 33890 | **84,8%** | **+19,57%** |
  => tabelka 73-76% / +12-21% z backtestu uzytkownika odpowiada wariantowi BEZ time-exitu.
  Wariant z 2h (czyli to, co chodzi na live) ma ok. polowe win-rate i ~1/3 ROI.

**Pozostale znaleziska:**
1. Min. rozmiar zlecenia: wszystkie rynki tag 120 maja `orderMinSize=5` (share'ow). Przy stawce 1$ i
   ask > ~0.20 zlecenie BUY (5 share'ow) nie ma szans -> odrzucenie "minimum size". W kodzie BRAK
   sprawdzania `orderMinSize`; jest tylko `price in [0.15, 0.90]`. Fix: `stake = max(stake, ask*5)` albo
   filtr `stake/ask >= 5`.
2. Model oplat w paperze: `PAPER_FEE_PCT = 0.02` i tylko od strony sprzedazy (jedna strona).
   Realnie Finance = 0.04 na strone wg `fee = C*rate*p*(1-p)` -> przy p=0.2 ok. 3,2% (kupno) + 2,9% (sprzedaz)
   = ~6% wartosci pozycji. Papier zaniza koszty o ~3 p.p. na transakcje => `dry_stats.txt` jest optymistyczne.
3. TP/SL liczone na BID, wejscie po ASK (`manage_exits` uzywa `get_bid`). To dobrze, ale przy
   `MAX_SPREAD_CENTS=0.05` TP +40% wymaga ruchu mid o ~40% + 5c. Ustawienie 0.05 lamie definicje TP.
   Wrocic do 0.03 (albo 0.02).
4. Skrypt ustawia `LIVE_MAX_EXPOSURE=${LIVE_MAX_EXPOSURE:-100000}` => wylacza bezpiecznik z kodu
   (`live_max_exposure()` domyslnie 25). Przy bankrollu ~20$ to i tak bez znaczenia, ale zostawic 25.
5. Banner startowy wypisuje wszystkie strategie (S5..S9, SPT, CAT 6 kategorii), choc wlaczona jest
   tylko Finance (tag 120) - mylace przy czytaniu logow.
6. Dobre rzeczy w kodzie: guard "brak SL = brak wejscia" (sl<1), weryfikacja wypelnienia BUY
   (`success`/status), retry z korekta ilosci przy SELL, reconcile + phantom/dust, bid<=ask guard.

Uwaga: `cargo`/`rustc` nie ma w tym sandboxie, wiec nie moge zbudowac poprawionej binarki -
latki musza byc dostarczone jako diff/zmiany w zrodle (uzytkownik buduje u siebie).
