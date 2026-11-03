# Dry-runy wariantowe (Polymarket 5m/15m Up/Down)

Dwa równoległe, **papierowe** przebiegi (zero prawdziwych zleceń) na żywych orderbookach
Polymarket (CLOB) i cenach Binance. Każdy wariant ma własny bankroll **50 $**, stawkę startową
**1.25 $** (2.5% kapitału) i własną drabinkę stawki.

## Pliki

| plik | rola |
|---|---|
| `poly_dryrun_engine.py` | silnik: dane, model, księgi wariantów, TP/SL/rozliczenie, raporty (bez zależności) |
| `dryrun1_master.py` | **przebieg 1** — 25 wariantów: drabinki 1/2/3/4%/50%, max szansa 70/80/90, min szansa 20–60, okna 5m po 2/3 min, 15m po 5/7/10 min + 5 ulepszeń |
| `dryrun2_master.py` | **przebieg 2** — 42 warianty „pod przewagę i skuteczność”: model v3 (mid rynku), ogony t5, podwójna zmienność, persist, głębokość, spread, anti-chase, imbalance, SL, kill-switch, TP 60–90/HOLD, sniper, korelacja |
| `run_dryruns.sh` | start/stop/raport obu przebiegów |
| `state/dryrun{1,2}.json` | stan (bankroll, otwarte pozycje, zamknięte transakcje) — przeżywa restart |
| `reports/dryrun{1,2}_report.md/.csv` | wyniki (ranking + rozbicie 5m/15m + parametry) |
| `reports/dryrun{1,2}_trades.jsonl` | po jednej linii na zamkniętą transakcję (audyt) |

## Uruchomienie

```bash
cd bots
./run_dryruns.sh                 # oba przebiegi w tle
tail -f logs/dryrun1.log         # podgląd
./run_dryruns.sh report          # tabele z zapisanego stanu (bez sieci)
./run_dryruns.sh stop            # stop (stan zostaje zapisany)
```

albo pojedynczo: `python3 dryrun1_master.py --bank 50 --stake 1.25 --minutes 480`.
`--reset` zeruje statystyki, `--list` pokazuje warianty, `--report` drukuje tabelę.

## Jak liczony jest wynik (paper trading)

* **Wejście**: ask z CLOB; fill symulowany po kolejnych poziomach książki (realny poślizg).
* **Opłata**: taker 0.07·p·(1−p) na udział (krypto) — zawsze odejmowana od przewagi.
* **Przewaga**: `edge = p_model − ask − fee`. Wejście tylko gdy `edge ≥ próg` i spełnione filtry.
* **Wyjście**: TP po **bid** (też po poziomach książki), SL, albo rozliczenie rynku (Gamma:
  `outcomePrices` 0/1; fallback: TWAP60 z klines 1s vs cena otwarcia).
* **Drabinka stawki**: poziom = ⌊log(kapitał/50)/log(1+step_bank)⌋, stawka = 1.25·(1+step_stake)^poziom.
  Dla kroku 50%: 50 $→1.25 $, 75 $→1.875 $, 112.5 $→2.8125 $ (dokładnie jak w zamówieniu).
  Warianty 1/2/3/4% przeliczają stawkę co każdy taki próg wzrostu kapitału („reset” schodka).

## Czego pilnować w wynikach

1. **n** — przy < 30 transakcjach wariantu wynik jest szumem, nie sygnałem.
2. **WR vs śr. px** — próg opłacalności to ~cena wejścia + opłata. Wysokie WR przy wysokim px bywa złudne.
3. **DD%** — maksymalne obsunięcie kapitału; więcej niż ~25% = za duża stawka względem kapitału.
4. **edge** — średnia przewaga w momencie wejścia; powinna być dodatnia po opłacie, inaczej filtr przepuszcza śmieci.
5. **5m vs 15m** — osobne rozbicie w raporcie; krótkie okna mają więcej szumu i cieńszą książkę.
