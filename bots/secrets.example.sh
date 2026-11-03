# Skopiuj do secrets.sh, wpisz swoje dane, ustaw chmod 600.
# NIGDY nie wrzucaj tego pliku do git/czatu.
export PM_PRIVATE_KEY="0x..."        # klucz prywatny portfela (Bitget: Pokaz klucz prywatny)
export PM_FUNDER="0x..."             # adres portfela z USDC na Polymarket (proxy z UI albo EOA)
export PM_SIG_TYPE=2                 # 0=EOA, 1=Magic/email, 2=proxy przegladarkowy, 3=smart/kontrakt
