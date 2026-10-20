# Bot v3 — uruchomienie w Termux (dry run + backtest)

Plik: `bot_v2_dry_v3.py` (poprawiona wersja `bot_v2_dry_fixed.py`).

## 1. Instalacja (raz)

```bash
pkg update -y && pkg install -y python
pip install --upgrade pip
pip install requests
# tylko dla trybu --live (prawdziwe zlecenia):
# pip install py-clob-client
```

## 2. Pobranie bota

> `raw.githubusercontent.com` potrafi podawać **starą wersję z cache** (dlatego `--explain`
> może "nie istnieć"). Pobieraj przez API GitHuba — to zawsze aktualna wersja:

```bash
mkdir -p ~/polybot && cd ~/polybot
curl -fsSL -H 'Accept: application/vnd.github.raw' \
  "https://api.github.com/repos/Gumos12345/poly-flash/contents/bot_v2_dry_v3.py?ref=cline/p2eft749" \
  -o bot_v2_dry_v3.py

# weryfikacja, że masz aktualną wersję (musi wypisać 3 flagi):
python bot_v2_dry_v3.py --help | grep -E 'explain|pre-hours|max-hours'
python bot_v2_dry_v3.py --report      # test: "brak otwartych pozycji"
```

Podgląd na żywo (opcjonalny skrypt):

```bash
curl -fsSL -H 'Accept: application/vnd.github.raw' \
  "https://api.github.com/repos/Gumos12345/poly-flash/contents/podglad.sh?ref=cline/p2eft749" \
  -o podglad.sh
chmod +x podglad.sh
```

## 3. Dry run (bez prawdziwych pieniędzy)

```bash
termux-wake-lock                      # blokada usypiania Androida (WAŻNE)
python bot_v2_dry_v3.py --scan --tags nba,ufc,epl   # rynki, które bot kupiłby TERAZ
python bot_v2_dry_v3.py --explain --tags nba,ufc,epl  # dlaczego reszta jest odrzucona
python bot_v2_dry_v3.py --pre-hours 24 --scan --tags nba   # test: poszerzone okno czasu (tylko ten przebieg)
python bot_v2_dry_v3.py --once         # jeden przebieg: otwórz pozycje + PnL
# test "czy w ogóle kupuje" bez czekania na okno 2 h (poszerzone okna tylko na ten przebieg):
python bot_v2_dry_v3.py --pre-hours 19 --max-hours 26 --once --tags nba

nohup python bot_v2_dry_v3.py --dry > dry.log 2>&1 &
tail -f dry.log                       # podgląd na żywo (Ctrl+C zamyka tylko podgląd)
# albo ładniejszy podgląd: log + PnL, odświeżanie co 60 s
./podglad.sh
```

Rano:

```bash
python bot_v2_dry_v3.py --report      # pozycje, PnL zrealizowany i mark-to-market
```

Zatrzymanie:

```bash
pkill -f bot_v2_dry_v3.py && termux-unlock
```

## 4. Backtest 30 dni (po dry runie)

```bash
python bot_v2_dry_v3.py --fetch-history --days 30 --max-markets 400   # buduje bt_cache2.json
python bot_v2_dry_v3.py --backtest                                    # wyniki pre/live/post
```

`--fetch-history` wykonuje ~1 zapytanie HTTP na rynek (400 rynków ≈ 400 zapytań),
więc lepiej na Wi-Fi. Cache zapisuje się w `bt_cache2.json` — kolejne backtesty są natychmiastowe.

## 5. Timery

Zostaw telefon na ładowarce, `termux-wake-lock` włączony. Bez tego Android
zabija proces po kilkunastu minutach snu i w logu zobaczysz tylko ostatni wpis.

## 6. Uwaga o „tym samym dniu”

* `PRE_GAME_WINDOW_H = 2` — wejście pre-game tylko do 2 h przed startem.
* `MAX_HOURS_TO_RESOLVE = 10` — pozycja musi się rozstrzygnąć w 10 h od wejścia
  (przy meczu + 2,5 h bufora rozliczenia).
* `SAME_CALENDAR_DAY = False` — gdy ustawisz `True`, bot dodatkowo wymaga, żeby
  rozliczenie wypadło przed lokalną północą (UTC+2 w Polsce). To wycina mecze NBA
  startujące po ~19:30 czasu polskiego.
