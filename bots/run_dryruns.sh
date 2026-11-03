#!/usr/bin/env bash
# Uruchamia oba dry-runy równolegle w tle (Termux / VPS / PC).
#   ./run_dryruns.sh            # start obu
#   ./run_dryruns.sh stop       # zatrzymanie
#   ./run_dryruns.sh report     # tabele z zapisanego stanu (bez sieci)
set -u
cd "$(dirname "$0")"
mkdir -p state reports logs
case "${1:-start}" in
  start)
    for s in 1 2; do
      if pgrep -f "dryrun${s}_master.py" >/dev/null; then echo "dryrun$s już działa"; continue; fi
      setsid nohup python3 "dryrun${s}_master.py" --bank 50 --stake 1.25 --sleep 3 \
        > "logs/dryrun${s}.log" 2>&1 < /dev/null &
      echo "uruchomiono dryrun$s (log: logs/dryrun${s}.log)"
    done
    sleep 3; pgrep -af 'dryrun[12]_master.py' || echo "nic nie działa - sprawdź logi"
    ;;
  stop)
    pkill -f 'dryrun1_master.py'; pkill -f 'dryrun2_master.py'; echo "zatrzymano"
    ;;
  report)
    python3 dryrun1_master.py --report
    python3 dryrun2_master.py --report
    ;;
  *)  echo "użycie: $0 [start|stop|report]";;
esac
