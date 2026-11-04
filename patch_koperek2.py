#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_koperek2.py - wersja ODPORNA (regex, dziala tez na zmodyfikowanym pliku).

Zmiany:
  1. NAJR_STEP_DOWN (spadek stawki -1% na -2% bankrolla) + LIVE_MULT (x1.5) + LIVE_MAX_SIDE (7)
  2. max_total 7 -> 14
  3. stawka: k>=0 -> *(1+step_stake)^k ; k<0 -> *(1-NAJR_STEP_DOWN)^(-k)   [wszystkie wystapienia]
  4. domyslny wariant live: ANTI_UD_TP80
  5. limit 7 pozycji na strone
  6. x1.5 na nodze kontry

Uzycie: python3 patch_koperek2.py [plik.py]
"""
import io
import os
import re
import shutil
import sys

p = sys.argv[1] if len(sys.argv) > 1 else "koperek.py"
if not os.path.exists(p):
    sys.exit(f"brak pliku {p}")

src = io.open(p, encoding="utf-8").read()
print(f"plik: {p}  ({len(src)} bajtow)")

if "NAJR_STEP_DOWN" in src:
    sys.exit("juz zpatchowany (NAJR_STEP_DOWN istnieje)")

shutil.copy(p, p + ".bak2")
report = []


def sub(pattern, repl, tag, expect=None, flags=0):
    global src
    new, n = re.subn(pattern, repl, src, flags=flags)
    if n == 0:
        report.append(f"  POMIN  {tag} (0 wystapien)")
        return
    if expect is not None and n != expect:
        report.append(f"  UWAGA  {tag}: {n} wystapien (oczekiwano {expect})")
    else:
        report.append(f"  OK     {tag} ({n}x)")
    src = new


# 1) stale
sub(r'LIVE_CFG\["step_stake"\] = NAJR_STEP',
    'LIVE_CFG["step_stake"] = NAJR_STEP\n'
    'NAJR_STEP_DOWN = float(os.environ.get("NAJR_STEP_DOWN", "0.01"))   # -1% stawki na -2% bankrolla\n'
    'LIVE_MULT = float(os.environ.get("LIVE_MULT", "1.5"))             # mnoznik stawki na nodze KONTRA\n'
    'LIVE_MAX_SIDE = int(os.environ.get("LIVE_MAX_SIDE", "7"))         # max pozycji na JEDNA strone',
    "stale NAJR_STEP_DOWN / LIVE_MULT / LIVE_MAX_SIDE", expect=1)

# 2) max_total 7 -> 14
sub(r'"max_pos":\s*7,\s*"max_pos_fin":\s*7,\s*"max_total":\s*7',
    '"max_pos": 7, "max_pos_fin": 7, "max_total": 14',
    "max_total = 14", expect=1)

# 3) asymetryczna stawka - WSZYSTKIE wystapienia (live + dry)
sub(r'st = base \* \(1\.0 \+ step_stake\) \*\* k(?! if k)',
    'st = (base * (1.0 + step_stake) ** k if k >= 0 '
    'else base * (1.0 - NAJR_STEP_DOWN) ** (-k))',
    "stawka asymetryczna +2%/-1%")

# 4) domyslny wariant
sub(r'os\.environ\.get\("NAJR_LIVE",\s*"ANTI_UD_HOLD"\)',
    'os.environ.get("NAJR_LIVE", "ANTI_UD_TP80")',
    "domyslny LIVE_VARIANT = ANTI_UD_TP80", expect=1)

# 5) x1.5 na kontrze
sub(r'(\n(\s+)stake = self\.stake_for\(s\["id"\]\))',
    r'\1\n\2if counter and stake > 0:            # x1.5 na nodze kontry\n'
    r'\2    stake = round(min(stake * LIVE_MULT, LIVE_CFG["max_stake"], CFG["max_order"]), 2)',
    "mnoznik x1.5 na kontrze", expect=1)

# 6) limit na strone
sub(r'(\n(\s+)if LIVE_CFG\["max_total"\] and len\(mine_open\) >= LIVE_CFG\["max_total"\]:)',
    r'\n\2n_side = sum(1 for x in mine_open if x.get("side") == sg.side)\n'
    r'\2if LIVE_MAX_SIDE and n_side >= LIVE_MAX_SIDE:\n'
    r'\2    self.warn_once("maxside", f"limit {LIVE_MAX_SIDE} pozycji na strone {sg.side} - czekam")\n'
    r'\2    return False\1',
    "limit 7 pozycji na strone", expect=1)

print("\n".join(report))

io.open(p, "w", encoding="utf-8").write(src)
print(f"\nzapisano (backup: {p}.bak2)")

ok = os.system(f'{sys.executable} -m py_compile "{p}"')
print("KOMPILACJA OK" if ok == 0 else "!!! BLAD KOMPILACJI - przywroc backup")

print("\nweryfikacja:")
for pat, name in ((r'NAJR_STEP_DOWN', "NAJR_STEP_DOWN"),
                  (r'LIVE_MULT', "LIVE_MULT"),
                  (r'LIVE_MAX_SIDE', "LIVE_MAX_SIDE"),
                  (r'ANTI_UD_TP80', "TP80"),
                  (r'"max_total": 14', "max_total 14"),
                  (r'NAJR_STEP_DOWN\) \*\* \(-k\)', "wzór asymetryczny")):
    n = len(re.findall(pat, src))
    print(f"  {'OK ' if n else 'BRAK'} {name}: {n}")