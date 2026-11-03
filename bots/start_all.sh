#!/usr/bin/env bash
# Start obu dry-runów w tle. Stop: stop_all.sh
cd "$(dirname "$0")"
mkdir -p state reports logs
rm -f state/dryrun1.json state/dryrun2.json reports/dryrun1_* reports/dryrun2_*
setsid nohup python3 dryrun1_master.py --reset --bank 50 --stake 1.25 --sleep 2 > logs/dryrun1.log 2>&1 < /dev/null &
sleep 1
setsid nohup python3 dryrun2_master.py --reset --bank 50 --stake 1.25 --sleep 2 > logs/dryrun2.log 2>&1 < /dev/null &
echo "start: $(date -u +%H:%M:%S)"
