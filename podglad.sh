#!/usr/bin/env bash
# Podglad na zywo dry runu: log bota + PnL (odswiezanie co N sekund).
# Uzycie:
#   ./podglad.sh          # odswiezanie co 60 s, az do Ctrl+C
#   ./podglad.sh 30       # co 30 s
#   COUNT=1 ./podglad.sh  # jeden przebieg (do testu)
cd "$(dirname "$0")" || exit 1
INTERVAL="${1:-60}"
COUNT="${COUNT:-0}"
i=0
while true; do
    clear
    printf '=== %s  (Ctrl+C konczy podglad, bot dalej chodzi) ===\n' "$(date '+%Y-%m-%d %H:%M:%S')"
    if [ -f dry.log ]; then
        echo "--- ostatnie 12 linii dry.log ---"
        tail -n 12 dry.log
    else
        echo "brak dry.log — bot nie uruchomiony albo uruchomiony w innym katalogu"
    fi
    echo
    echo "--- pozycje i PnL (--report) ---"
    python bot_v2_dry_v3.py --report 2>&1 | tail -n 20
    i=$((i + 1))
    if [ "$COUNT" -gt 0 ] && [ "$i" -ge "$COUNT" ]; then
        break
    fi
    sleep "$INTERVAL"
done
