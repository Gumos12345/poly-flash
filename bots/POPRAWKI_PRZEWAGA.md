# Jak przenieść ulepszenia z dry-runów do `najr_live_UP_HOLD.py`

Ten plik to konkretne, sprawdzone w dry-runach zmiany „pod przewagę, jakość i skuteczność BIN”.
Każda pozycja: co zmienić, gdzie (numeracja z obecnej wersji bota) i dlaczego.

## 1. Model: ogony Studenta zamiast normalnego (mniej „pewniaków”)
**Gdzie:** `cdf_for(tf, rem)` (linia ~407).
**Co:** dla `5m`/`15m` też zwracać `t5_cdf` (jest już w pliku, linia ~390), np.
```python
def cdf_for(tf, rem=0):
    if tf in ("fin", "1d", "5m", "15m") or (tf == "strike" and rem > 1800):
        return t5_cdf
    return norm_cdf
```
**Dlaczego:** przy tym samym z-score t5 daje mniejszą pewność. W dry-runie warianty v2/v3 (t5) miały
mniej fałszywych wejść po dużych ruchach — dokładnie tam, gdzie normalny rozkład „kłamie”.

## 2. Zmienność: mieszanka krótka/długa zależna od fazy okna
**Gdzie:** `Bot.sigma_for` (linia ~1583) / `sigma` (~1567).
**Co:** na starcie okna licz szerzej (240 barów), przy końcu węższej (60 barów):
`k = 0.35 + 0.65*(1 - rem/per)`; `sigma = k*sigma_short + (1-k)*sigma_long`.
**Dlaczego:** świeży „oddech” rynku jest lepszy blisko rozstrzygnięcia; na starcie jest tylko szumem.

## 3. Przewaga netto z realną opłatą (nie stały haircut)
**Gdzie:** `s_bin` (linia ~1079, `BIN_HAIRCUT = 0.03`).
**Co:** `edge = fair - a - fee_per_share(a)` gdzie `fee_per_share` = `0.07*p*(1-p)` (funkcja już jest, ~488).
**Dlaczego:** przy p=0.5 opłata to 1.75c, przy p=0.85 tylko 0.9c — stały haircut karze tanie strony
zbyt mocno, a drogie zbyt słabo.

## 4. Twardy filtr spreadu + bid z ask drugiej strony
**Gdzie:** `Ctx` (linia ~1172) i `s_bin`.
**Co:** jeśli brak bidów po stronie, przyjmij `bid = 1 - ask(drugiej strony)` i odrzucaj wejścia przy
`ask - bid > 0.20` (a w wariantach jakościowych > 0.04–0.06).
**Dlaczego:** to był realny błąd złapany w dry-runie: wejście po ask 0.27 przy bid 0.11 dawało
„przewagę” 18c, która znikała w sekundę (stop-loss -0.68 $).

## 5. Głębokość książki ≥ 3–5× stawki
**Gdzie:** `s_bin` tuż po `a = c.ask(side)`.
**Co:** `if sum(size for _,size in book["asks"][:5]) < 3*stake/a: continue`.
**Dlaczego:** 1.25 $ na książce, gdzie na najlepszym poziomie jest 0.4 udziału, to poślizg 30%+.

## 6. Trwałość sygnału (persist)
**Gdzie:** `Bot.step` / `scan` — nowy licznik `self.edge_streak[(slug, side)]`.
**Co:** wchodź dopiero, gdy `edge >= próg` utrzymuje się 2 cykle (przy pętli 1 s to ~2–3 s).
**Dlaczego:** pojedyncze „iskry” w książce to zwykle podbite zlecenie albo chwilowy brak płynności.

## 7. Anty-chase
**Co:** jeśli `ask` wzrósł o > 4–6c w ostatnich 25–40 s, nie wchodź (gonisz cenę po fakcie).
**Dlaczego:** najgorsze wejścia w dry-runie to te po skoku ceny, gdy przewaga już zniknęła.

## 8. Zgodność z nierównowagą książki (imbalance)
**Co:** dla `Up` wymagaj `imb >= 0.52–0.55` (top-5 bid/ask), dla `Down` symetrycznie;
`Ctx.imbalance()` już istnieje (linia ~1218).
**Dlaczego:** filtr przepływu informacyjnego — działa jak veto na sygnały „pod prąd” książki.

## 9. Parametry startowe, które wypadły najlepiej w dry-runach
```
--fair-min 0.45..0.50        (było 0.40)
--bin-max-px-5m 0.70..0.90   (było 0.95)
--bin-max-odds 4..6          (nie kupuj taniej niż 17-25c — chyba że wariant MIN_*)
--edge-5m / --edge-15m 0.04..0.06 po odjęciu realnej opłaty
TP 0.70..0.80 (bid)          — HOLD tylko dla wariantów z filtrem jakości
```

## 10. Kill-switch na drawdown i limit korelacji
**Co:** zatrzymaj wariant/strategię przy obsunięciu > 20–25% kapitału; max 1 pozycja na okno 5m
(rynki 7 monet w tym samym oknie są silnie skorelowane — 7 pozycji = jedna wielka pozycja).

## 11. NAJWAŻNIEJSZE (zmierzone w tym dry-runie): pułapka „taniej strony”
Obecne ustawienia bota (`min_px 0.03`, `edge 5c`) wchodziły w stronę po **0.07–0.16 $**, gdy model
dawał 0.41–0.43 $ — czyli „przewaga” 26–33 c. Wynik na żywych książkach: **4/4 straty** (`S1_BASE`),
bo model przy krótkich oknach **systematycznie przepłaca ogony** (nie widzi dryfu i mikrostruktury,
którą rynek już wycenił).

Konkretne zabezpieczenie (do wdrożenia w `s_bin`):
```python
if edge > 0.25:                 # "za piękne, by było prawdziwe" = model i książka się rozjechały
    continue
if a < 0.10 and fair < 0.55:    # tania strona bez bardzo mocnego potwierdzenia modelu
    continue
```
oraz `--fair-min 0.45..0.50` i `--bin-max-odds 4..6` (nie kupuj taniej niż 17–25 c).
**Dlaczego to działa:** duża „przewaga” na tanim końcu to prawie zawsze skutek tego, że rynek
wycenia już nową informację, a model liczy z opóźnionego spotu i zmienności.

## Uwaga metodologiczna
Wszystkie liczby z tych dry-runów są **papierowe** i przy małym n (kilkadziesiąt transakcji na wariant)
obarczone dużym błędem. Przed przełączeniem czegokolwiek na `--live` zostaw przebiegi na kilka dni
i patrz na: `n ≥ 100`, `WR vs śr. cena wejścia`, `DD%` oraz stabilność `edge` po opłacie.
