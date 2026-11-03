#!/usr/bin/env bash
cd "$(dirname "$0")"
for p in $(ps -eo pid,args | awk '/dryrun[12]_master\.py/ && !/awk/ && !/start_all/ {print $1}'); do kill "$p"; done
sleep 1
echo "stop: $(date -u +%H:%M:%S)"
