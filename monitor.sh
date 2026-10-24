#!/usr/bin/env bash
# Monitor dry runu: dopisuje status do monitor.log (domyslnie co 5 min).
# Uzycie:
#   ./monitor.sh            # co 300 s, w tle lub na ekranie
#   ./monitor.sh 60         # co 60 s
#   COUNT=1 ./monitor.sh    # tylko jeden wpis (do testu)
#   nohup ./monitor.sh > /dev/null 2>&1 &     # w tle, sam dopisuje do monitor.log
cd "$(dirname "$0")" || exit 1
INTERVAL="${1:-300}"
OUT="monitor.log"
COUNT="${COUNT:-0}"
i=0
while true; do
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    pids="$(pgrep -f bot_v2_dry_v3.py | tr '\n' ' ')"
    iters="$(grep -c 'pozycje=' dry.log 2>/dev/null || true)"
    {
        echo "=== $ts ==="
        if [ -n "$pids" ]; then
            echo "bot:      DZIALA (pid: $pids)"
        else
            echo "bot:      NIE DZIALA"
        fi
        echo "obiegow:  ${iters:-0}  (linii 'pozycje=' w dry.log)"
        echo "ostatni:  $(grep 'pozycje=' dry.log 2>/dev/null | tail -1)"
        echo "--- raport ---"
        python bot_v2_dry_v3.py --report 2>&1 | tail -n 15
        echo
    } >> "$OUT"
    tail -n 8 "$OUT"
    i=$((i + 1))
    if [ "$COUNT" -gt 0 ] && [ "$i" -ge "$COUNT" ]; then
        break
    fi
    sleep "$INTERVAL"
done
