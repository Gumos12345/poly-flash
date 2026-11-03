#!/usr/bin/env bash
# OBA dry-runy w JEDNYM procesie (mniej zapytań, ~2x szybciej na telefonie).
# Start: ./start_both.sh   Stop: ./stop_all.sh   Raport: python3 report_rich.py
cd "$(dirname "$0")"
mkdir -p state reports logs
./stop_all.sh >/dev/null 2>&1
rm -f state/dryrun1.json state/dryrun2.json reports/dryrun1_* reports/dryrun2_*
setsid nohup python3 dryrun_both.py --reset --bank 50 --stake 1.25 --sleep 2 > logs/both.log 2>&1 < /dev/null &
echo "start OBA: $(date -u +%H:%M:%S) — podgląd: tail -f logs/both.log"
