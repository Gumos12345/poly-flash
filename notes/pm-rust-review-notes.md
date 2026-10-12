# pm-rust / kategoria_finance_wersja_ostateczna_dzialajaca.sh — analiza wklejenia (2025, sesja 1)

## 1. Co dostalem
Uzytkownik wkleil do czatu plik `kategoria_finance_wersja_ostateczna_dzialajaca.sh`
(Termux/Android, bot Polymarket w Rust). Skrypt jest samowystarczalny: zawiera
`Cargo.toml` + `src/main.rs` zakodowany w base64 w heredoc `B64EOF`.

**Wklejenie jest UCIETE** — konczy sie w polowie bloku base64, na linii:
`Ly8vIEVmZWt0eXdueSBmdW5kZXIgKHBvIGF1dG8tcmVzb2x1Y2ppIHcgTElWR` (~`// Efekt... funder (po auto-resolucji w LIVE`)
czyli mam tylko poczatek `src/main.rs`. Brakuje: reszty main.rs (strategie, Gamma/CLOB,
petla, skladanie zlecen) oraz ogona samego skryptu bash (po heredoc: kompilacja,
uruchomienie bota, `doctor`).

Zdekodowany prefiks (1.4 KB, tylko komentarze + `use`) zapisany w:
`notes/pm-rust-main-rs-fragment_prefix.txt`

## 2. Co widac w czesci bash (verbatim)
- `MODE="${1:-live}"` — domyslnym trybem jest LIVE; jedyne tryby: `live`(default)/`dry`/`doctor`/`build`/`run`.
- tryb `run`: `export LIVE=1`, `export CONFIRM_LIVE=I_UNDERSTAND_THE_RISK`, `export LIVE_MAX_EXPOSURE="${LIVE_MAX_EXPOSURE:-100000}"`,
  `START_BUDGET="${START_BUDGET:-20.9}"`, `MAX_POSITIONS=20`, `MAX_SPREAD_CENTS=0.03`, potem `exec ./target/release/pm-rust`.
- `run` **zawsze** wymusza live (nie da sie odpalic paper po `build`) i nie ma zadnego pytania/potwierdzenia.
- Komentarz naglowka: 3 strategie tylko Finance (tag 120), SL -90%, time-exit 2h, max 7 poz./strategie, MAX_POSITIONS=20,
  stawka startowa 1$ (+10% co +20% bankrolla), START_BUDGET=20.9.

## 3. Zdekodowany prefiks main.rs — co zawiera
- naglowek z opisem strategii S5..S9, S4, S3, S2, SPT, CAT (czyli opisane jako aktywne!),
- `use std::collections::HashMap`, `std::fs::{self, OpenOptions}`.

## 4. Znalezione anomalie (DO WERYFIKACJI — czesc przez base64, mozliwe artefakty wklejenia)
1. **`CONFIRM_LIVE` — wartosc w kodzie vs w skrypcie.** W zdekodowanym base64 (komentarz w main.rs)
   wychodzi `CONFIRM_LIVE=I_UNDERSTAND_**TH**_RISK` (bez `E`), a skrypt eksportuje `I_UNDERSTAND_**THE**_RISK`.
   Jesli to nie artefakt wklejenia, `live()` zwraca `false` i bot w trybie `run`/LIVE chodzi jako PAPER.
   Sprawdzenie u klienta:
   ```bash
   grep -o 'I_UNDERSTAND_[A-Z_]*' ~/pm-rust/src/main.rs | sort -u
   grep -o 'I_UNDERSTAND_[A-Z_]*' ~/kategoria_finance_wersja_ostateczna_dzialajaca.sh | sort -u
   ```
2. **Budzet: `START_BUDGET` vs `LIVE_BUDGET`.** Skrypt ustawia i wypisuje `START_BUDGET=20.9`,
   a base64 main.rs pokazuje `std::env::var("LIVE_BUDGET")` (komentarz: „domyslnie 0.88$ (maly test), nadpisz LIVE_BUDGET=5”).
   Sprawdzenie:
   ```bash
   grep -n 'START_BUDGET\|LIVE_BUDGET\|PAPER_BUDGET' ~/pm-rust/src/main.rs
   ```
3. **Blob base64 wyglada na nie-bajtowo wierny.** W zdekodowanym prefiksie sa dwa miejsca,
   gdzie z tekstu zniknely 2 bajty na granicy linii (`…_THE_RISK\n//` -> `…_TH_RISK//`,
   `…transakcji\n//` -> `…transakcj//`). To nie sa przypadkowe literowki — wyglada na zgubione
   bajty przy generowaniu/wklejaniu base64. Sprawdzenie u klienta:
   ```bash
   sed -n '/^base64 -d > src\/main.rs/,/^B64EOF$/p' ~/kategoria_finance_wersja_ostateczna_dzialajaca.sh \
     | sed '1d;$d' | tr -d '\n' | base64 -d | diff - ~/pm-rust/src/main.rs && echo BLOB_OK
   ```
4. **Naglowek main.rs nadal opisuje S2..S9/SPORTS/CAT**, a naglowek skryptu twierdzi, ze wszystkie
   poza 3 strategiami Finance sa WYLACZONE. Do sprawdzenia w brakujacej czesci: czy konfiguracja
   faktycznie wylacza pozostale strategie (bo to bezposrednio przeklada sie na ryzyko).
5. **Brak potwierdzenia dla LIVE + domyslny tryb live** — jeden bledny `bash skrypt.sh` bez argumentu
   odpala tryb LIVE (o ile live() przejdzie). Sugestia: domyslnie `dry`, a `live` tylko jawnie.
6. `LIVE_MAX_EXPOSURE` domyslnie `100000` przy budzecie ~20$ => limit ekspozycji praktycznie wylaczony.

## 5. Czego potrzebuje, zeby zrobic prawdziwy przeglad
Plik jako TEKST (`src/main.rs` i caly `.sh`), nie base64:
- najlatwiej: gist / repo na GitHubie -> link (ja pobieram),
- albo wklejenie `src/main.rs` w kawalkach po ~300-400 linii (bez base64),
- albo ogon skryptu (po `B64EOF`), ktorego zabraklo.
