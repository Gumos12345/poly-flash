#!/usr/bin/env bash
cd "$(dirname "$0")"
for p in $(ps -eo pid,args | awk '/dryrun_(both|1_master|2_master)\.py/ && !/awk/ && !/stop_all/ {print $1}'); do kill "$p" 2>/dev/null; done
sleep 1
echo "stop: $(date -u +%H:%M:%S)"
