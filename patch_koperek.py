#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_koperek.py - dodaje do koperek.py wariant TP80 + stawke UD asymetryczna:
  * wzrost stawki +2% na +2% bankrolla (bez zmian)
  * SPADEK stawki -1% na -2% bankrolla (nowe)
  * limit 7 pozycji na strone (14 lacznie)
  * domyslny wariant live: ANTI_UD_TP80
  * x1.5 na nodze KONTRA (LIVE_MULT=1.5)

Uzycie:
  python3 patch_koperek.py            # patchuje koperek.py w biezacym katalogu
  python3 patch_koperek.py plik.py
"""
import io
import os
import shutil
import sys

p = sys.argv[1] if len(sys.argv) > 1 else "koperek.py"
if not os.path.exists(p):
    sys.exit(f"brak pliku {p}")

src = io.open(p, encoding="utf-8").read()
if "NAJR_STEP_DOWN" in src:
    sys.exit("juz zpatchowany (NAJR_STEP_DOWN istnieje) - nic nie zmieniam")

shutil.copy(p, p + ".bak")
changes = 0


def rep(old, new, tag):
    global src, changes
    if old not in src:
        sys.exit(f"NIE ZNALEZIONO: {tag}")
    if src.count(old) != 1:
        sys.exit(f"WIELE WYSTAPIEN ({src.count(old)}): {tag}")
    src = src.replace(old, new, 1)
    changes += 1
    print(f"  OK  {tag}")


# --- 1) nowe stale ---------------------------------------------------------
rep('LIVE_CFG["step_stake"] = NAJR_STEP',
    'LIVE_CFG["step_stake"] = NAJR_STEP\n'
    'NAJR_STEP_DOWN = float(os.environ.get("NAJR_STEP_DOWN", "0.01"))   # -1% stawki na -2% bankrolla\n'
    'LIVE_MULT = float(os.environ.get("LIVE_MULT", "1.5"))             # mnoznik stawki na nodze KONTRA (x1.5)\n'
    'LIVE_MAX_SIDE = int(os.environ.get("LIVE_MAX_SIDE", "7"))         # max pozycji na JEDNA strone (Up / Down)',
    "stale NAJR_STEP_DOWN / LIVE_MULT / LIVE_MAX_SIDE")

# --- 2) max_total 7 -> 14 --------------------------------------------------
rep('"max_pos": 7, "max_pos_fin": 7, "max_total": 7',
    '"max_pos": 7, "max_pos_fin": 7, "max_total": 14',
    "LIVE_CFG max_total = 14")

# --- 3) asymetryczna stawka LIVE (gora +2%, dol -1%) -----------------------
rep('''        st = base * (1.0 + step_stake) ** k
        return round(min(max(st, LIVE_CFG["min_stake"]), LIVE_CFG["max_stake"], CFG["max_order"]), 2)''',
    '''        st = base * (1.0 + step_stake) ** k if k >= 0 else base * (1.0 - NAJR_STEP_DOWN) ** (-k)
        return round(min(max(st, LIVE_CFG["min_stake"]), LIVE_CFG["max_stake"], CFG["max_order"]), 2)''',
    "live_ladder_stake: asymetria +2% / -1%")

# --- 4) asymetryczna stawka DRY (ta sama reguła) --------------------------
rep('''        st = base * (1.0 + step_stake) ** k
        return round(min(max(st, L["min_stake"]), L["max_stake"], CFG["max_order"]), 2)''',
    '''        st = base * (1.0 + step_stake) ** k if k >= 0 else base * (1.0 - NAJR_STEP_DOWN) ** (-k)
        return round(min(max(st, L["min_stake"]), L["max_stake"], CFG["max_order"]), 2)''',
    "ladder_stake: asymetria +2% / -1%")

# --- 5) domyslny wariant live TP80 ---------------------------------------
rep('LIVE_VARIANT = os.environ.get("NAJR_LIVE", "ANTI_UD_HOLD").strip()',
    'LIVE_VARIANT = os.environ.get("NAJR_LIVE", "ANTI_UD_TP80").strip()',
    "domyslny LIVE_VARIANT = ANTI_UD_TP80")

# --- 6) limit 7 na strone + x1.5 na kontrze -------------------------------
rep('        stake = self.stake_for(s["id"])',
    '        stake = self.stake_for(s["id"])\n'
    '        if counter and stake > 0:                       # x1.5 na nodze kontry\n'
    '            stake = round(min(stake * LIVE_MULT, LIVE_CFG["max_stake"], CFG["max_order"]), 2)',
    "mnoznik x1.5 na kontrze")

rep('            if LIVE_CFG["max_total"] and len(mine_open) >= LIVE_CFG["max_total"]:',
    '            n_side = sum(1 for x in mine_open if x.get("side") == sg.side)\n'
    '            if LIVE_MAX_SIDE and n_side >= LIVE_MAX_SIDE:\n'
    '                self.warn_once("maxside", f"limit {LIVE_MAX_SIDE} pozycji na strone {sg.side} - czekam")\n'
    '                return False\n'
    '            if LIVE_CFG["max_total"] and len(mine_open) >= LIVE_CFG["max_total"]:',
    "limit 7 pozycji na strone")

io.open(p, "w", encoding="utf-8").write(src)
print(f"\nzapisano {p} ({changes} zmian). Backup: {p}.bak")
print("\nTest skladni:")
os.system(f'{sys.executable} -m py_compile "{p}" && echo "  KOMPILACJA OK"')