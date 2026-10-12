#!/data/data/com.termux/files/usr/bin/bash
# ============================================================================
#  wyslij-mi.sh -- wrzuca kod bota (main.rs + skrypt) na publiczny paste
#  i wypisuje linki, ktore mozna wkleic do czatu.
#
#  UZYCIE (w Termux):
#     bash wyslij-mi.sh
#
#  WAZNE: skrypt wysyla TYLKO kod (src/main.rs, .sh). NIE wysyla ~/.poly_env
#  ani klucza prywatnego. Linki z 0x0.st / termbin.com sa PUBLICZNE - kazdy,
#  kto zna link, widzi plik. Dlatego nigdy nie wysylaj tu klucza prywatnego.
# ============================================================================
set -u

SRC="$HOME/pm-rust/src/main.rs"
SH="$HOME/kategoria_finance_wersja_ostateczna_dzialajaca.sh"
PARTS=500   # ile linii na jedna czesc

pkg install -y curl netcat-openbsd coreutils >/dev/null 2>&1 || true

up() { # $1 = plik do wyslania
  local f="$1" out
  [ -f "$f" ] || { echo "brak pliku: $f"; return 1; }
  out="$(curl -sS -m 90 -A 'wyslij-mi/1.0' -F "file=@$f" https://0x0.st 2>/dev/null)"
  case "$out" in
    http*) printf '%-40s %s\n' "$(basename "$f")" "$out" ;;
    *)
      out="$(cat "$f" | nc termbin.com 9999 2>/dev/null)"
      printf '%-40s %s\n' "$(basename "$f")" "${out:-NIE UDALO SIE}"
      ;;
  esac
}

echo "== wysylam kod =="
if [ -f "$SRC" ]; then
  rm -f "$HOME"/pm_part_*
  split -l "$PARTS" -d -a 2 "$SRC" "$HOME/pm_part_"
  for p in "$HOME"/pm_part_*; do up "$p"; done
  rm -f "$HOME"/pm_part_*
  echo "linie w main.rs: $(wc -l < "$SRC")"
else
  echo "brak $SRC"
fi
up "$SH"

echo
echo "Wklej powyzsze linki do czatu (z podpisem, ktora czesc to ktora)."
