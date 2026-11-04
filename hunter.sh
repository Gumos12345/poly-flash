#!/usr/bin/env bash
# hunter.sh - dwa boty w jednym: drabinki (mono) + swieze rynki (sniper).
# Logi: hunter_mono.log, hunter_sniper.log
#
#   ./hunter.sh            # start w tle
#   ./hunter.sh stop       # zatrzymanie
#   tail -F hunter_mono.log hunter_sniper.log
cd "$(dirname "$0")" || exit 1

if [ "$1" = "stop" ]; then
    pkill -f 'mono.py' 2>/dev/null
    pkill -f 'sniper.py' 2>/dev/null
    echo "zatrzymane"
    exit 0
fi

pkill -f 'mono.py' 2>/dev/null
pkill -f 'sniper.py' 2>/dev/null
sleep 1

# 1) drabinki progów: wszystkie sporty + crypto/pogoda/polityka, co 3 min
nohup bash -c 'while true; do date; python3 -u mono.py --pages 2 --min-edge 0.02; sleep 180; done' \
    > hunter_mono.log 2>&1 &

# 2) swieze rynki: ciagly nasluch
nohup python3 -u sniper.py --turbo --max-age 1800 --max-vol 50 --poll 0.5 \
    --max-check 20 --max-ask 0.25 --exit-min 0.10 --track 30 --minutes 100000 \
    > hunter_sniper.log 2>&1 &

sleep 2
echo "uruchomione:"
echo "  mono   -> hunter_mono.log   (pid $(pgrep -f 'mono.py --pages' | head -1))"
echo "  sniper -> hunter_sniper.log (pid $(pgrep -f 'sniper.py --turbo' | head -1))"
echo
echo "podglad:  tail -F hunter_mono.log hunter_sniper.log"
echo "stop:     ./hunter.sh stop"
