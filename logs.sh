#!/usr/bin/env bash
# Podglad logow na zywo. Ctrl+C konczy TYLKO podglad - bot dalej chodzi.
#
# Uzycie:
#   ./logs.sh          # dry.log + raport.log (ostatnie 20 linii, potem na zywo)
#   ./logs.sh dry      # tylko dry.log
#   ./logs.sh key      # tylko wazne zdarzenia: wejscia, PnL, bledy
cd "$(dirname "$0")" || exit 1
MODE="${1:-all}"
case "$MODE" in
    dry)  exec tail -n 30 -F dry.log ;;
    key)  exec tail -n 0 -F dry.log | grep --line-buffered -E 'KUPNO|pozycje=|loop-err|stop' ;;
    *)    exec tail -n 20 -F dry.log raport.log ;;
esac
