#!/usr/bin/env bash
# Migawka wynikow co 5 min do logs/snapshots.txt
cd "$(dirname "$0")"
while true; do
  { date -u +%H:%M:%S
    python3 - <<'PY'
import json
for s in ('dryrun1','dryrun2'):
    d=json.load(open('state/%s.json'%s)); b=d['books']
    cl=sum(len(v['closed']) for v in b.values()); op=sum(len(v['positions']) for v in b.values())
    pnl=sum(v['realized'] for v in b.values())
    print('  %s zamkniete=%d otwarte=%d PnL_sum=%.2f'%(s,cl,op,pnl))
PY
  } >> logs/snapshots.txt
  sleep 300
done
