#!/usr/bin/env bash
# Zapis snapshotu wyników do wyniki/ (ten katalog JEST w repo, bot go nie nadpisuje).
cd "$(dirname "$0")"
python3 report_rich.py >/dev/null 2>&1 || true
python3 make_summary.py >/dev/null 2>&1 || true
T=$(date -u +%Y%m%d_%H%M)
cp -f RAPORT.html "wyniki/RAPORT_${T}.html" 2>/dev/null || true
cp -f reports/RAPORT.csv "wyniki/RAPORT_${T}.csv" 2>/dev/null || true
cp -f results_summary.md wyniki/results_summary.md 2>/dev/null || true
cp -f RAPORT.html wyniki/RAPORT_latest.html 2>/dev/null || true
cp -f reports/RAPORT.csv wyniki/RAPORT_latest.csv 2>/dev/null || true
echo "snapshot: wyniki/RAPORT_${T}.html (+ latest)"
