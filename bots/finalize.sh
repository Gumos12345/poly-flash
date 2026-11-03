#!/usr/bin/env bash
# Zamkniecie przebiegow: raporty CSV/MD + zbiorcze podsumowanie + (opcjonalnie) commit.
cd "$(dirname "$0")"
python3 dryrun1_master.py --report >/dev/null 2>&1 || true
python3 dryrun2_master.py --report >/dev/null 2>&1 || true
python3 make_summary.py
ls -la reports/*.csv reports/*.md results_summary.md 2>/dev/null
