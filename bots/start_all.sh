#!/usr/bin/env bash
# Start obu dry-runów w tle (najpierw zatrzymuje poprzednie, zeruje stan). Stop: stop_all.sh
cd "$(dirname "$0")"
mkdir -p state reports logs
./stop_all.sh >/dev/null 2>&1
rm -f state/dryrun1.json state/dryrun2.json reports/dryrun1_* reports/dryrun2_*
setsid nohup python3 dryrun1_master.py --reset --bank 50 --stake 1.25 --sleep 2 > logs/dryrun1.log 2>&1 < /dev/null &
sleep 1
setsid nohup python3 dryrun2_master.py --reset --bank 50 --stake 1.25 --sleep 2 > logs/dryrun2.log 2>&1 < /dev/null &
echo "start: $(date -u +%H:%M:%S) — podgląd: tail -f logs/dryrun1.log"
