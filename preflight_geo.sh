#!/data/data/com.termux/files/usr/bin/bash
# preflight_geo.sh - sprawdza geoblokade Polymarket przed live
UA="Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
D=$(curl -s -m 10 -A "$UA" https://polymarket.com/api/geoblock)
IP=$(echo "$D" | grep -o '"ip":"[^"]*"' | cut -d'"' -f4)
CC=$(echo "$D" | grep -o '"country":"[^"]*"' | cut -d'"' -f4)
BL=$(echo "$D" | grep -o '"blocked":[a-z]*' | cut -d: -f2)
echo "IP=$IP kraj=$CC blocked=$BL"
if [ "$BL" = "true" ]; then
  echo "STOP: region zablokowany - zmien exit VPN (dozwolone np. CZ)"
  exit 1
fi
echo "OK - mozna handlowac"
