#!/data/data/com.termux/files/usr/bin/bash
# install.sh - instaluje caly zestaw botow arbitrazowych z brancha cline/p2eft749
# Uzycie:  curl -fsSL -H 'Accept: application/vnd.github.raw' \
#            "https://api.github.com/repos/Gumos12345/poly-flash/contents/install.sh?ref=cline/p2eft749" -o install.sh
#          bash install.sh
set -u
REPO="Gumos12345/poly-flash"
REF="cline/p2eft749"
DEST="${1:-$HOME/polybot2}"

echo "== Instalacja do: $DEST =="
mkdir -p "$DEST" || exit 1
cd "$DEST" || exit 1

FILES="ws_arb.py mono.py arb_stats.py arb_bt.py sniper.py mm_paper.py arb.py drift.py fresh.py bot_v2_dry_v3.py analyze.py bt_full.py hunter.sh podglad.sh logs.sh monitor.sh TERMUX_README.md"

ok=0
for f in $FILES; do
    if curl -fsSL -H 'Accept: application/vnd.github.raw' \
        "https://api.github.com/repos/$REPO/contents/$f?ref=$REF" -o "$f" 2>/dev/null; then
        ok=$((ok+1))
    else
        echo "  ! nie pobrano: $f"
        rm -f "$f"
    fi
done
echo "pobrano plikow: $ok"

chmod +x ./*.sh 2>/dev/null

echo
echo "== Zaleznosci =="
command -v python3 >/dev/null || { pkg install -y python; }
python3 -c "import websockets" 2>/dev/null || pip install -q websockets
python3 -c "import py_clob_client" 2>/dev/null || pip install -q py-clob-client
python3 -c "import websockets; print('  websockets OK')" 2>/dev/null || echo "  ! websockets brak"
python3 -c "import py_clob_client; print('  py-clob-client OK')" 2>/dev/null || echo "  ! py-clob-client brak (potrzebny tylko do --live)"

echo
echo "== Kompilacja =="
python3 -m py_compile *.py && echo "  OK"

echo
echo "== Selftest =="
python3 ws_arb.py --selftest
python3 mm_paper.py --selftest 2>/dev/null | tail -2

echo
echo "== Gotowe =="
echo "  katalog: $DEST"
echo
echo "DRY RUN:"
echo "  cd $DEST"
echo "  nohup python3 -u ws_arb.py --dry --tags nba,nfl,epl,soccer,mlb,nhl \\"
echo "    --min-edge 0.02 --max-sum 0.95 --min-depth 5 --bankroll 24 \\"
echo "    --compound --per-event > ws_arb24.log 2>&1 &"
echo "  tail -F ws_arb24.log"
echo
echo "BACKTEST ARBITRAZU (realne transakcje):"
echo "  python3 -u arb_bt.py --mode mono --days 7 --max-markets 25"
echo
echo "STATYSTYKI Z LOGOW:"
echo "  python3 arb_stats.py --days 7 --pairs-per-day 4"
echo
echo "LIVE (po wplacie, z nowym kluczem):"
echo "  export POLY_PRIVATE_KEY=0x... POLYMARKET_DEPOSIT_WALLET=0x... POLY_SIGNATURE_TYPE=3"
echo "  POLY_PROBE_SIG=1 python3 bot_v2_dry_v3.py --preflight"
echo "  python3 -u ws_arb.py --live --tags nba,nfl,epl,soccer,mlb,nhl \\"
echo "    --min-edge 0.02 --max-sum 0.95 --min-depth 5 --bankroll 25 \\"
echo "    --from-balance 0.90 --max-trades 1 --per-event"
