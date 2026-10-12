# pm-rust v4 — co zmienione i jak uruchomic

Pliki:
- `finance_6h_v4.sh` — gotowy skrypt do uruchomienia (ma w sobie poprawiony `src/main.rs` w base64),
- `src/main.rs` — poprawione zrodlo (do podgladu/diffu),
- `v4-main-rs.patch` — diff wzgledem Twojej wersji v3.

## Korekta po analizie `live_fills.csv` (2026-10-12)

Pierwotnie zakladalem, ze bledy LIVE przy otwieraniu pozycji to `orderMinSize=5 share'ow`
(przy stawce 1$ i ask > 0.20 nie da sie kupic 5 share'ow). **Dane uzytkownika tego nie potwierdzaja:**
w `live_fills.csv` sa wpisy `BUY ... 1.00 ... MATCHED` z SELL po 3.33, 2.44, 1.32 share'a, czyli
zlecenia na 1-3 share'y byly normalnie wypelniane. Dlatego:

- **USUNIETE podnoszenie stawki do `ask*5`** — to zwiekszyloby pozycje 1,5-3,8x bez powodu.
  Zostalo tylko logowanie `[FIN-INFO]` pod `DEBUG_CAT=1`.
- Przyczyna bledow LIVE jest nadal otwarta (kandydaci: saldo/allowance, autoryzacja fundera,
  wyczerpany budzet) — rozstrzygnie `grep -v MATCHED live_fills.csv` + log z `[LIVE ERROR]`.

Dodane logowanie (do audytu, bo `live_fills.csv` nie zapisuje cen):
```
[LIVE OPEN ] A40_40 slug  @ 0.3100  stake=1.00$  shares=3.23
[LIVE CLOSE] A40_40 slug  shares=3.23 entry=0.3100 bid=0.4400 pnl=+41.94% reason=TP
```

## Co poprawione (i dlaczego)

1. ~~**Min. rozmiar zlecenia**~~ — patrz korekta wyzej (nie podnosimy stawki).


2. **Time-exit Finance: 2h -> 12h (konfigurowalne).**
   Na 2h backtest daje ~0%/pozycja (win ~48%), bo edge ujawnia sie pozniej:
   | hold | -40/+40 | -30/+30 |
   |---|---|---|
   | 2h | +1,0% (win 33,6%) | -1,2% (win 32,4%) |
   | 6h | +13,6% | +9,8% |
   | 12h | +23,8% | +16,9% |
   | 24h | +27,0% | +24,0% |
   | 72h | +26,4% | +28,7% |
   (dane: 480 rynkow Finance, 30 dni CLOB, wejscie po ask, wyjscie po bid, spread 0.02,
   fee 0.04 dwustronnie, filtr ask <= 0.20; ROI na pozycje).
   W kodzie: `fin_time_exit_sec()`, `FIN_EXIT_HOURS` (domyslnie 12).

3. **Zakres ceny: ask <= 0.25** (`FIN_MAX_ASK`). Sygnaly z ask <= 0.20 dawaly ~+27%/pozycja,
   a drozsze rynki rozwadnialy wynik do ~+12%.

4. **Realne oplaty w paperze**: `fee = shares * rate * p * (1-p)`, dwustronnie, rate wg kategorii
   (Finance 0.04). Wczesniej: 2% tylko od sprzedazy → `dry_stats.txt` zawyzal wyniki o ~3 p.p./transakcje.

5. **`LIVE_MAX_EXPOSURE` domyslnie 25$** (skrypt v3 ustawial 100000, co wylaczalo bezpiecznik z kodu).

6. **Banner** wypisuje tylko realnie wlaczone strategie (Finance), z aktualnymi progami.

## Jak uruchomic

```bash
cd ~
curl -O https://raw.githubusercontent.com/Gumos12345/poly-flash/cline/vamzpxbx/pm-rust/finance_6h_v4.sh
bash finance_6h_v4.sh build          # w DRUGIEJ sesji Termux; stary bot chodzi dalej
# gdy build przejdzie bez bledow:
#   Ctrl+C starego bota, potem:
bash finance_6h_v4.sh run
```

Diagnostyka (bez przebudowy):
```bash
DEBUG_CAT=1 bash finance_6h_v4.sh run     # linie [FIN-SUMMARY] / [FIN-SKIP]
FIN_EXIT_HOURS=24 bash finance_6h_v4.sh run
MAX_SPREAD_CENTS=0.02 bash finance_6h_v4.sh run
```

## Czego NIE obiecuje

Liczby z backtestu sa na cenach z historii CLOB (mid/last). „TP trafiony" w historii nie znaczy,
ze sprzedasz po tej cenie w cienkim rynku. Dlatego: najpierw **paper** (`dry`), porownanie
`dry_stats.txt` z oczekiwaniem, i dopiero potem realne pieniadze. SL -90% praktycznie nie dziala —
realna strata to rozliczenie rynku do zera (ok. 16% transakcji = -100% stawki).

Uwaga: nie mialem tu kompilatora Rust, wiec v4 nie byl kompilowany — dlatego uruchamiaj najpierw
`build` w drugiej sesji (jak w instrukcji): gdyby kompilacja sie nie udala, stary bot dalej chodzi.
