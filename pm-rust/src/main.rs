// =============================================================================
//  pm-rust  --  Polymarket bot (DRY RUN):  SPORTY LIVE  +  CRYPTO
// -----------------------------------------------------------------------------
//  Strategie:
//    S5  - 5m  REBOUND     (crypto {asset}-updown-5m-<ts>)  -> kup "Up" po spadku
//    S6  - 15m REBOUND     (crypto {asset}-updown-15m-<ts>) -> kup "Up" po spadku
//    S7  - 1h  REBOUND     (crypto {name}-up-or-down-<date>-<h>-et)
//    S8  - 4h  REBOUND     (crypto {asset}-updown-4h-<ts>)
//    S9  - 1d  REBOUND     (crypto {name}-up-or-down-on-<date>)
//    S4  - 15m VOLUME SPIKE(crypto {asset}-updown-15m-<ts>)  [WYLACZONE]
//    S3  - MOMENTUM SCALP  (crypto, referencja Kraken)
//    S2  - MEAN REVERSION  (rynki wysokiego wolumenu: polityka/sport/inne)
//    SPT - LIVE SPORTY     (Gamma tag_id=1&live=true) -> mean reversion
//    CAT - 6 KATEGORII     (Finals/Tech/Esports/Politics/Weather/Culture, DROP40)
//
//  Domyslnie DRY RUN (paper trading).  LIVE tylko gdy:
//        LIVE=1  ORAZ  CONFIRM_LIVE=I_UNDERSTAND_THE_RISK
//
//  Pliki wyjsciowe DRY RUN:
//        dry_trades.csv     - historia transakcji
//        dry_stats.txt      - statystyki
//        positions_dry.json - otwarte pozycje
// =============================================================================

use std::collections::HashMap;
use std::fs::{self, OpenOptions};
use std::io::Write;
#[cfg(feature = "live")]
use std::str::FromStr;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::time;

// SDK jest potrzebny TYLKO do skladania prawdziwych zlecen (feature "live").
#[cfg(feature = "live")]
use polymarket_client_sdk_v2::auth::{LocalSigner, Signer as _};
#[cfg(feature = "live")]
use polymarket_client_sdk_v2::clob::types::request::BalanceAllowanceRequest;
#[cfg(feature = "live")]
use polymarket_client_sdk_v2::clob::types::{
    Amount, AssetType, OrderStatusType, OrderType, Side, SignatureType,
};
#[cfg(feature = "live")]
use polymarket_client_sdk_v2::clob::{Client, Config};
#[cfg(feature = "live")]
use polymarket_client_sdk_v2::types::{Address, Decimal, U256};
#[cfg(feature = "live")]
use polymarket_client_sdk_v2::{POLYGON, PRIVATE_KEY_VAR};

// =============================================================================
//  LIVE GATING
// =============================================================================
fn live() -> bool {
    static V: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
    *V.get_or_init(|| {
        let l = std::env::var("LIVE")
            .map(|v| v == "1" || v.eq_ignore_ascii_case("true"))
            .unwrap_or(false);
        let c = std::env::var("CONFIRM_LIVE")
            .map(|v| v == "I_UNDERSTAND_THE_RISK")
            .unwrap_or(false);
        l && c
    })
}

// =============================================================================
//  KONFIGURACJA
// =============================================================================
const PAPER_BUDGET_DEFAULT: f64 = 50.0;
const PAPER_FEE_PCT: f64 = 0.02;
const TRADES_FILE: &str = "dry_trades.csv";
const STATS_FILE: &str = "dry_stats.txt";

fn paper_budget() -> f64 {
    std::env::var("PAPER_BUDGET")
        .ok()
        .and_then(|v| v.trim().parse::<f64>().ok())
        .filter(|b| *b > 0.0)
        .unwrap_or(PAPER_BUDGET_DEFAULT)
}
fn starting_budget() -> f64 {
    if live() {
        // Budzet LIVE: domyslnie 0.88$ (maly test). Nadpisz: LIVE_BUDGET=5
        std::env::var("LIVE_BUDGET")
            .ok()
            .and_then(|v| v.trim().parse::<f64>().ok())
            .filter(|b| *b > 0.0)
            .unwrap_or(0.88)
    } else {
        paper_budget()
    }
}

// =============================================================================
//  ODCZYT BUDZETU ON-CHAIN  (pUSD / USDC.e)  z portfela Polymarket
// -----------------------------------------------------------------------------
//  Polymarket V2 trzyma srodki jako pUSD (Polymarket USD), NIE USDC.e.
//  Portfel to "Deposit Wallet" (adres w POLYMARKET_FUNDER). Bot czyta saldo
//  bezposrednio z lancucha (balanceOf) przez publiczne RPC Polygon, wiec
//  "widzi" prawdziwe srodki bez recznego ustawiania LIVE_BUDGET.
// =============================================================================
const PUSD_ADDRESS: &str = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB";
const USDC_E_ADDRESS: &str = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174";
// Domyslny portfel (Deposit Wallet) - uzywany, gdy brak POLYMARKET_FUNDER.
// Nadpisz wlasnym adresem w ~/.poly_env, jesli masz inny portfel.
const DEFAULT_FUNDER: &str = "0x8f586A4E10c55F5839a98ba232f79d3e40f728A4";
// Awaryjny budzet LIVE, gdy RPC nie odpowiada i brak LIVE_BUDGET.
const DEFAULT_LIVE_BUDGET: f64 = 11.20;
const POLYGON_RPCS: [&str; 6] = [
    "https://polygon-bor-rpc.publicnode.com",
    "https://polygon.drpc.org",
    "https://polygon-rpc.com",
    "https://polygon.llamarpc.com",
    "https://rpc.ankr.com/polygon",
    "https://1rpc.io/matic",
];

/// Adres portfela Polymarket (funder). Pusty/brak = None.
fn funder_address() -> Option<String> {
    let env = std::env::var("POLYMARKET_FUNDER")
        .ok()
        .map(|v| v.trim().to_string())
        .filter(|v| !v.is_empty());
    env.or_else(|| {
        if DEFAULT_FUNDER.is_empty() {
            None
        } else {
            Some(DEFAULT_FUNDER.to_string())
        }
    })
}

// =============================================================================
//  AUTO-ROZPOZNANIE WŁAŚCIWEGO PORTFELA (funder) Z KLUCZA PRYWATNEGO
// -----------------------------------------------------------------------------
//  Błąd "the order signer address has to be the address of the API KEY" pojawia
//  się, gdy bot użyje ZŁEGO adresu portfela (np. adresu "deposit" z UI zamiast
//  właściwego Deposit Wallet). Z danego klucza prywatnego wynika EOA, a dla EOA
//  istnieje DOKŁADNIE JEDEN właściwy Deposit Wallet. Bot sam go ustala przez
//  resolver (ten sam, o którym mowa w GitHub issue #70):
//      GET https://poly-market-research.replit.app/api/wallet/resolve/{eoa}
//  Priorytet:
//    1) POLYMARKET_FORCE_FUNDER=0x...  (+ POLYMARKET_FORCE_SIGTYPE)  - ręczne
//    2) auto-resolucja z EOA (domyślnie WŁĄCZONA; wyłącz: POLYMARKET_AUTO_FUNDER=0)
//    3) POLYMARKET_FUNDER z env / DEFAULT_FUNDER
// =============================================================================
#[cfg(feature = "live")]
const WALLET_RESOLVER_BASE: &str = "https://poly-market-research.replit.app/api/wallet/resolve";

/// (sig_type, funder) liczone raz na starcie i cache'owane.
#[cfg(feature = "live")]
static AUTH_PARAMS: std::sync::OnceLock<(u8, Option<String>)> = std::sync::OnceLock::new();

/// EOA (adres podpisujący) wyliczony z POLYMARKET_PRIVATE_KEY.
#[cfg(feature = "live")]
fn eoa_from_key() -> Option<String> {
    let pk = std::env::var(PRIVATE_KEY_VAR).ok()?;
    let signer = LocalSigner::from_str(pk.trim()).ok()?;
    Some(signer.address().to_string())
}

/// Pyta resolver o właściwy Deposit Wallet dla danego EOA.
/// Zwraca (funder, sig_type) albo None, gdy resolver nie odpowiada.
#[cfg(feature = "live")]
async fn resolve_wallet(http: &reqwest::Client, eoa: &str) -> Option<(Option<String>, u8)> {
    let url = format!("{}/{}", WALLET_RESOLVER_BASE, eoa.trim());
    let resp = http.get(&url).send().await.ok()?;
    if !resp.status().is_success() {
        return None;
    }
    let v: Value = resp.json().await.ok()?;
    // depositWallet (jeśli istnieje) = właściwy funder + sigType (zwykle 3)
    if let Some(dw) = v.get("depositWallet").and_then(|x| x.as_object()) {
        if let Some(addr) = dw.get("address").and_then(|x| x.as_str()) {
            if !addr.is_empty() {
                let sig = v
                    .get("resolved")
                    .and_then(|r| r.get("sigType"))
                    .and_then(|x| x.as_u64())
                    .unwrap_or(3) as u8;
                return Some((Some(addr.to_string()), sig));
            }
        }
    }
    // brak Deposit Wallet -> zwykły EOA (sig 0)
    let sig = v
        .get("resolved")
        .and_then(|r| r.get("sigType"))
        .and_then(|x| x.as_u64())
        .unwrap_or(0) as u8;
    Some((None, sig))
}

/// Ustala (sig_type, funder) wg priorytetu opisanego wyżej.
#[cfg(feature = "live")]
async fn compute_auth_params() -> (u8, Option<String>) {
    // 1) ręczne wymuszenie
    if let Ok(f) = std::env::var("POLYMARKET_FORCE_FUNDER") {
        let f = f.trim().to_string();
        if !f.is_empty() {
            let sig = std::env::var("POLYMARKET_FORCE_SIGTYPE")
                .ok()
                .and_then(|v| v.trim().parse::<u8>().ok())
                .unwrap_or(3);
            println!("[AUTH] FORCE_FUNDER: funder={} sig_type={}", f, sig);
            return (sig, Some(f));
        }
    }
    // 2) auto-resolucja z EOA
    let auto = std::env::var("POLYMARKET_AUTO_FUNDER")
        .map(|v| !(v == "0" || v.eq_ignore_ascii_case("false")))
        .unwrap_or(true);
    if auto {
        if let Some(eoa) = eoa_from_key() {
            if let Ok(http) = build_http_client() {
                if let Some((funder, sig)) = resolve_wallet(&http, &eoa).await {
                    match &funder {
                        Some(f) => {
                            println!(
                                "[AUTH] auto-resolve: EOA={} -> Deposit Wallet={} (sig_type={})",
                                eoa, f, sig
                            );
                            return (sig, Some(f.clone()));
                        }
                        None => {
                            println!(
                                "[AUTH] auto-resolve: EOA={} -> brak Deposit Wallet (sig_type={})",
                                eoa, sig
                            );
                            return (sig, None);
                        }
                    }
                }
                println!("[AUTH] auto-resolve: resolver nie odpowiedzial - uzywam env/DEFAULT");
            }
        }
    }
    // 3) env / DEFAULT
    let sig = std::env::var("POLYMARKET_SIGNATURE_TYPE")
        .ok()
        .and_then(|v| v.trim().parse::<u8>().ok())
        .unwrap_or(3);
    (sig, funder_address())
}

/// Zwraca (sig_type, funder) - liczone raz, potem z cache.
#[cfg(feature = "live")]
async fn auth_params() -> (u8, Option<String>) {
    if let Some(v) = AUTH_PARAMS.get() {
        return v.clone();
    }
    let computed = compute_auth_params().await;
    let _ = AUTH_PARAMS.set(computed.clone());
    computed
}

/// Efektywny funder (po auto-resolucji w LIVE; w DRY zwykły env/DEFAULT).
async fn effective_funder() -> Option<String> {
    #[cfg(feature = "live")]
    let f = {
        let (_, f) = auth_params().await;
        f
    };
    #[cfg(not(feature = "live"))]
    let f = funder_address();
    f
}

/// Saldo ERC-20 (balanceOf) w jednostkach tokena (6 miejsc dla pUSD/USDC).
/// Probuje kolejnych RPC az do skutku. None = nie udalo sie odczytac.
async fn erc20_balance(
    http: &reqwest::Client,
    token: &str,
    holder: &str,
    debug: bool,
) -> Option<f64> {
    let holder = holder.trim_start_matches("0x").to_lowercase();
    if holder.len() != 40 {
        if debug {
            println!("   [dbg] zly adres portfela: '{}'", holder);
        }
        return None;
    }
    let data = format!("0x70a08231000000000000000000000000{}", holder);
    for rpc in POLYGON_RPCS {
        let body = serde_json::json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [{"to": token, "data": data}, "latest"]
        });
        let resp = match http.post(rpc).json(&body).send().await {
            Ok(r) => r,
            Err(e) => {
                if debug {
                    println!("   [dbg] {} -> blad sieci: {}", rpc, e);
                }
                continue;
            }
        };
        let v: Value = match resp.json().await {
            Ok(v) => v,
            Err(e) => {
                if debug {
                    println!("   [dbg] {} -> blad JSON: {}", rpc, e);
                }
                continue;
            }
        };
        if let Some(hex) = v.get("result").and_then(|r| r.as_str()) {
            let hex = hex.trim_start_matches("0x");
            if let Ok(raw) = u128::from_str_radix(hex, 16) {
                if debug {
                    println!("   [dbg] {} -> OK (0x{} = {})", rpc, hex, raw);
                }
                return Some(raw as f64 / 1_000_000.0);
            }
        } else if debug {
            let err = v
                .get("error")
                .map(|e| e.to_string())
                .unwrap_or_else(|| "(brak result)".to_string());
            println!("   [dbg] {} -> {}", rpc, err);
        }
    }
    None
}

/// Saldo portfela Polymarket: pUSD + USDC.e (na wypadek starszych srodkow).
/// None = brak fundera / RPC nie odpowiada.
async fn fetch_onchain_budget(http: &reqwest::Client) -> Option<f64> {
    let funder = effective_funder().await?;
    let pusd = erc20_balance(http, PUSD_ADDRESS, &funder, false).await;
    let usdc = erc20_balance(http, USDC_E_ADDRESS, &funder, false).await;
    if pusd.is_none() && usdc.is_none() {
        return None;
    }
    Some(pusd.unwrap_or(0.0) + usdc.unwrap_or(0.0))
}

/// Ustala budzet LIVE:
///   1) LIVE_BUDGET (jesli ustawione > 0) = reczne nadpisanie,
///   2) inaczej saldo on-chain portfela (pUSD/USDC.e),
///   3) inaczej wartosc domyslna 0.88.
async fn resolve_live_budget(http: &reqwest::Client) -> f64 {
    if let Ok(v) = std::env::var("LIVE_BUDGET") {
        if let Ok(b) = v.trim().parse::<f64>() {
            if b > 0.0 {
                println!("[BUDGET] LIVE_BUDGET (reczne nadpisanie) = {:.2} $", b);
                return b;
            }
        }
    }
    match fetch_onchain_budget(http).await {
        Some(b) if b > 0.0 => {
            println!(
                "[BUDGET] wykryto on-chain w portfelu {} : {:.2} $ (pUSD/USDC.e)",
                effective_funder().await.unwrap_or_default(),
                b
            );
            b
        }
        Some(b) => {
            println!(
                "[BUDGET] portfel {} ma {:.2} $ (pUSD/USDC.e) - przy 0 bot nie handluje",
                effective_funder().await.unwrap_or_default(),
                b
            );
            b
        }
        None => {
            println!(
                "[BUDGET] UWAGA: nie udalo sie odczytac salda on-chain (RPC/proxy). \
                 Uzywam awaryjnego budzetu {:.2} $. Sprawdz: ./target/release/pm-rust --balance",
                DEFAULT_LIVE_BUDGET
            );
            std::env::var("LIVE_BUDGET")
                .ok()
                .and_then(|v| v.trim().parse::<f64>().ok())
                .filter(|b| *b > 0.0)
                .unwrap_or(DEFAULT_LIVE_BUDGET)
        }
    }
}
fn state_file() -> &'static str {
    if live() {
        "positions.json"
    } else {
        "positions_dry.json"
    }
}

const CRYPTO_ASSETS: [&str; 15] = [
    "btc", "eth", "sol", "xrp", "doge", "bnb", "ada", "avax", "link", "matic", "ltc", "dot",
    "shib", "pepe", "ton",
];
const S5_ENABLED: bool = false; // S5 5m REBOUND NA LIVE
const S4_ENABLED: bool = false; // S4 VOLUME SPIKE (15m) - WYLACZONE: udowodniona strata (t=-2.4..-4.3)
const S3_ENABLED: bool = false; // S3 WYLACZONE: rynki 5m crypto wolumen ~5-40$ (martwe) -> -EV
const S2_ENABLED: bool = false; // WYLACZONE: SPT-only (Finance+Culture)
const SPORTS_ENABLED: bool = false; // WYLACZONE: SPT-only (Finance+Culture)

const S5_MIN_PRICE: f64 = 0.30;
const S5_REBOUND_PCT: f64 = 0.05;
const S5_MAX_PRICE: f64 = 0.60;
const S5_TP: f64 = 0.20;
const S5_SL: f64 = 0.10;
const S5_EXIT_SEC: u64 = 150;

const S4_MIN_PRICE: f64 = 0.30;
const S4_MAX_PRICE: f64 = 0.70;
const S4_TP: f64 = 0.10;
const S4_SL: f64 = 0.12;

// --- S6: 15m REBOUND (ZOPTYMALIZOWANA) --------------------------------------
// Parametry wybrane na 529 realnych rynkach 15m (CLOB prices-history, 1-min).
// 5-fold walk-forward: 5/5 foldow dodatnich, mean ~+5.7% / transakcje (t=+2.96).
// STARA konfiguracja (rebound 6%, exit 300s, TP 20%, SL 15%) dawala -6.7%
// (0/5 foldow) -> zostala WYELIMINOWANA i zastepiona ponizsza.
const S6_ENABLED: bool = false;      // S6 15m REBOUND NA LIVE
const S6_LOOKBACK_SEC: u64 = 180;   // okno "ostatniego maksimum"
const S6_REBOUND_PCT: f64 = 0.04;   // wejscie gdy spadek >=4% od maksimum
const S6_MIN_PRICE: f64 = 0.20;
const S6_MAX_PRICE: f64 = 0.80;
const S6_TP: f64 = 10.0;            // brak TP (hold do time-exit)
const S6_SL: f64 = 0.20;
const S6_EXIT_SEC: u64 = 180;       // time-exit

// --- S7: 1h REBOUND ---------------------------------------------------------
// 112 realnych rynkow 1h. 5-fold: 5/5 foldow dodatnich, mean ~+10.8%, min +7.2%,
// win ~84%, t=+2.27 (najlepszy wariant 1h - maximin po najgorszym foldzie).
const S7_ENABLED: bool = false; // WYLACZONE: brak stop-loss (SL=1.00) -> tylko strategie z SL
const S7_LOOKBACK_SEC: u64 = 360;
const S7_REBOUND_PCT: f64 = 0.40;   // wejscie gdy spadek >=40% (gleboki dip)
const S7_MIN_PRICE: f64 = 0.20;
const S7_MAX_PRICE: f64 = 0.80;
const S7_TP: f64 = 0.30;
const S7_SL: f64 = 1.00;            // brak SL (time-exit ogranicza ekspozycje)
const S7_EXIT_SEC: u64 = 2700;      // time-exit (45 min)

// --- S8: 4h REBOUND ---------------------------------------------------------
// 41 realnych rynkow 4h. 5-fold: 4/5 foldow dodatnich, mean ~+11.2%.
const S8_ENABLED: bool = false; // S8 WYLACZONE: rynki 4h crypto wolumen <1000$ (brak ceny) -> -EV
const S8_LOOKBACK_SEC: u64 = 1440;
const S8_REBOUND_PCT: f64 = 0.25;
const S8_MIN_PRICE: f64 = 0.20;
const S8_MAX_PRICE: f64 = 0.70;
const S8_TP: f64 = 10.0;            // brak TP
const S8_SL: f64 = 0.50;
const S8_EXIT_SEC: u64 = 2160;      // time-exit (36 min)

// --- S9: 1d REBOUND ---------------------------------------------------------
// 295 realnych rynkow 1d (maj-lipiec 2025). 5-fold: 4/5 foldow dodatnich,
// mean ~+7.8%, min -2.6%, t=+2.80 (maximin: najmniejsza wariancja miedzy foldami).
const S9_ENABLED: bool = false; // WYLACZONE: brak stop-loss (SL=1.00) -> tylko strategie z SL
const S9_LOOKBACK_SEC: u64 = 4320;
const S9_REBOUND_PCT: f64 = 0.25;
const S9_MIN_PRICE: f64 = 0.20;
const S9_MAX_PRICE: f64 = 0.70;
const S9_TP: f64 = 10.0;            // brak TP
const S9_SL: f64 = 1.00;            // brak SL
const S9_EXIT_SEC: u64 = 8640;      // time-exit (2.4h)

const S3_MIN_VOLUME: f64 = 500.0;
const S3_KRAKEN_MOVE_THRESHOLD: f64 = 0.0005;
const S3_KRAKEN_VOLUME_RATIO: f64 = 1.3;
const S3_TP: f64 = 0.25;   // bylo 0.10 - wiekszy TP (sweep: najlepszy in-sample)
const S3_SL: f64 = 0.15;   // bylo 0.12

const S2_DROP_THRESHOLD: f64 = 0.05;  // bylo 0.20 - dip>=5% (spojne train+test)
const S2_MIN_PRICE: f64 = 0.15;
const S2_MAX_PRICE: f64 = 0.90;
const S2_TP: f64 = 0.30;   // BACKTEST: ciasny TP (szybki zysk, wysoki WR)
const S2_SL: f64 = 0.90;   // BACKTEST: szeroki SL

const SPORTS_TP: f64 = 0.30;   // DROP40: TP30 = najwyzsze PF i WR (skuteczniejszy niz TP40)
const SPORTS_SL: f64 = 0.90;   // szeroki SL (ciasny SL wycinal zwyciezcow)
const SPORTS_DROP_THRESHOLD: f64 = 0.40;   // DROP40: wejscie po spadku >=40% od maksimum (okno 300s)
const SPORTS_MIN_VOLUME: f64 = 250.0; // DROP40: dolny prog zyskownych bucketow (250/1k/5k)
const SPORTS_MAX_VOLUME: f64 = 20000.0; // DROP40: 20k+ byl JEDYNYM nie-zyskownym bucketem -> odcinamy
const SPORTS_MIN_PRICE: f64 = 0.15; // unikamy longshotow (mniejsza strata ogonowa)
const SPORTS_MAX_PRICE: f64 = 0.90;

const MIN_MARKET_VOLUME: f64 = 3000.0;
// Maksymalny spread (ask-bid) dopuszczany przy wejsciu. Domyslnie 3 grosze (0.03$).
// Uwaga: porownania uzywaja eps=1e-9, bo float potrafi dac 0.020000000000000018 > 0.02
// i odrzucic realny rynek o spreadzie dokladnie 2 grosze.
// Nadpisz: MAX_SPREAD_CENTS=0.05
fn max_spread_cents() -> f64 {
    std::env::var("MAX_SPREAD_CENTS")
        .ok()
        .and_then(|v| v.trim().parse::<f64>().ok())
        .filter(|&v| v > 0.0)
        .unwrap_or(0.03)
}
const MIN_SEC_TO_EXPIRY: u64 = 90;

const TIME_EXIT_15M_SEC: u64 = 210;
const SPORTS_TIME_EXIT_SEC: u64 = 7200;

// Ile rynkow sportowych (najwyzszy wolumen) skanowac na cykl - zeby petla byla szybka.
// Nadpisywalne: SPORTS_MAX_MARKETS=500
fn sports_max_markets() -> usize {
    std::env::var("SPORTS_MAX_MARKETS")
        .ok()
        .and_then(|v| v.trim().parse::<usize>().ok())
        .filter(|&n| n > 0)
        .unwrap_or(2000)
}

// Ile STRON eventow pobierac z Gamma API (100 eventow na strone).
// Domyslnie 5 -> do 500 eventow (realnie ~161 dostepnych).
// Nadpisz: SPORTS_MAX_PAGES=3
fn sports_max_pages() -> usize {
    std::env::var("SPORTS_MAX_PAGES")
        .ok()
        .and_then(|v| v.trim().parse::<usize>().ok())
        .filter(|&n| n > 0)
        .unwrap_or(5)
}

// Filtr plynnosci (minimalny wolumen rynku). Domyslnie 5000.
// Nadpisywalne bez przebudowy: SPORTS_MIN_VOLUME=1000
fn sports_min_volume() -> f64 {
    std::env::var("SPORTS_MIN_VOLUME")
        .ok()
        .and_then(|v| v.trim().parse::<f64>().ok())
        .filter(|&v| v >= 0.0)
        .unwrap_or(SPORTS_MIN_VOLUME)
}

// Gorny prog wolumenu (DROP40): 20k+ byl jedynym nie-zyskownym bucketem.
// Nadpisz bez przebudowy: SPORTS_MAX_VOLUME=100000 (wylacza gorny limit)
fn sports_max_volume() -> f64 {
    std::env::var("SPORTS_MAX_VOLUME")
        .ok()
        .and_then(|v| v.trim().parse::<f64>().ok())
        .filter(|&v| v > 0.0)
        .unwrap_or(SPORTS_MAX_VOLUME)
}

// Prog wejscia SPT: minimalny spadek ceny od maksimum z ostatnich 5 min (rebound).
// BACKTEST: 0.15->PF1.76, 0.20->PF2.54, 0.25->PF6.0, 0.30->PF5.2 (@spread 3c).
// Nadpisz bez przebudowy: SPORTS_DROP=0.20
fn sports_drop_threshold() -> f64 {
    std::env::var("SPORTS_DROP")
        .ok()
        .and_then(|v| v.trim().parse::<f64>().ok())
        .filter(|&v| v > 0.0 && v < 1.0)
        .unwrap_or(SPORTS_DROP_THRESHOLD)
}

#[allow(dead_code)]
const MAX_EXPOSURE_PCT: f64 = 1.0;
const STAKE_USD_MIN: f64 = 1.0;   // stawka bazowa = 1$
const STAKE_USD_MAX: f64 = 25.0;  // gorny bezpiecznik (dynamiczny staking moze rosnac)
const STAKE_PCT_OF_BANKROLL: f64 = 1.0;
const MIN_BANKROLL_TO_TRADE: f64 = 1.50;
// DYNAMICZNY STAKING: co +20% wzrostu bankrolla -> stawka +10%.
// stake = 1$ * 1.10^(floor(ln(equity/initial)/ln(1.20)))
const STAKE_GROWTH_STEP: f64 = 0.20;
const STAKE_GROWTH_MULT: f64 = 1.10;
const KILL_SWITCH_DROP_PCT: f64 = 0.30;

// ===========================================================================
//  LIMIT POZYCJI: 16 bazowo (4 strategie x 4 pozycje) + DYNAMICZNY WZROST.
//  Co +25% wzrostu bankrolla -> +1 do limitu otwartych pozycji.
//  limit = 16 + floor((equity/initial - 1) / 0.25)
//  (np. 20.9$ -> 16 ; ~26$ -> 17 ; ~31$ -> 18 ; ~36$ -> 19 ; ~41$ -> 20 ...)
//  Nadpisz na sztywno: MAX_POSITIONS=20 (ustawia stala wartosc).
// ===========================================================================
const MAX_POSITIONS_BASE: usize = 16;
const POS_GROWTH_STEP: f64 = 0.25;
fn max_positions(state: &BotState) -> usize {
    if let Some(n) = std::env::var("MAX_POSITIONS")
        .ok()
        .and_then(|v| v.trim().parse::<usize>().ok())
        .filter(|&n| n > 0)
    {
        return n;
    }
    let init = if state.initial_budget > 0.0 {
        state.initial_budget
    } else {
        state.budget
    };
    if init <= 0.0 {
        return MAX_POSITIONS_BASE;
    }
    let growth = (state.equity() / init).max(1.0);
    let steps = ((growth - 1.0) / POS_GROWTH_STEP).floor();
    let steps = if steps.is_finite() && steps > 0.0 {
        steps as usize
    } else {
        0
    };
    MAX_POSITIONS_BASE + steps
}
// LIVE: twardy limit lacznej ekspozycji (suma size_usd otwartych pozycji).
// Nadpisz: LIVE_MAX_EXPOSURE=5
fn live_max_exposure() -> f64 {
    std::env::var("LIVE_MAX_EXPOSURE")
        .ok()
        .and_then(|v| v.trim().parse::<f64>().ok())
        .filter(|b| *b > 0.0)
        .unwrap_or(25.0)
}
const SCAN_INTERVAL_SEC: u64 = 2;
// Co ile sekund wypisac heartbeat (widac ze bot zyje i skanuje rynki)
const HEARTBEAT_SEC: u64 = 20;
// Co ile sekund synchronizowac GOTOWKE (cash) z prawdziwym saldem portfela on-chain (pUSD).
// To sprawia, ze bot widzi realne saldo (np. 13.6$) i realny zysk.
const CASH_SYNC_SEC: u64 = 20;
// Co ile sekund sprawdzac, czy otwarte pozycje sie ROZLICZYLY (reconciliacja z rynkiem).
// Zapobiega wiecznemu probowaniu SELL na pozycji, ktora juz wygasla/zostala auto-redeemowana.
const RECONCILE_SEC: u64 = 5;
// Po ilu sekundach od otwarcia uznajemy, ze brak tokenu w portfelu (Data API) to trwaly
// stan (a nie chwilowy lag API) i zamykamy pozycje lokalnie jako PHANTOM/ZNIKLA.
// To leczy przypadki typu "will-the-us-invade-iran-before-2027": pozycja nie istnieje
// on-chain, ale rynek wygasa dopiero w 2027 -> stara logika reconcile jej NIE lapala.
const PHANTOM_GRACE_SEC: u64 = 180;

#[allow(dead_code)]
const SELL_RETRY_SEC: u64 = 1;
#[allow(dead_code)]
const SELL_VERIFY_WAIT_SEC: u64 = 5;
const SCALP_EXIT_BEFORE_END: u64 = 30;
#[allow(dead_code)]
const BALANCE_SYNC_SEC: u64 = 10;
#[allow(dead_code)]
const BALANCE_HOLD_SEC: u64 = 20;
const REENTRY_COOLDOWN_SEC: u64 = 120;

const KRAKEN_POLL_SEC: u64 = 2;
const KRAKEN_LOOKBACK_SEC: u64 = 30;
#[allow(dead_code)]
const KRAKEN_MOVE_THRESHOLD: f64 = 0.0003;
#[allow(dead_code)]
const KRAKEN_VOLUME_RATIO: f64 = 1.2;

// Ile aktywow crypto skanowac na cykl. Domyslnie WSZYSTKIE (15) - zeby bot widzial
// caly rynek crypto, a nie tylko 5. Pobieranie rynkow jest rownolegle (JoinSet),
// wiec skanowanie wszystkich 15 aktywow nie spowalnia petli.
// Nadpisz: CRYPTO_PER_CYCLE=5
fn crypto_per_cycle() -> usize {
    std::env::var("CRYPTO_PER_CYCLE")
        .ok()
        .and_then(|v| v.trim().parse::<usize>().ok())
        .filter(|&n| n > 0)
        .unwrap_or(CRYPTO_ASSETS.len())
}

// Endpointy
const GAMMA_API: &str = "https://gamma-api.polymarket.com";
const CLOB_API: &str = "https://clob.polymarket.com";
// Data API (read-only): /positions, /value, /activity, /closed-positions.
// Uzywane do RECONCILIACJI - pokazuje prawdziwy stan portfela (co bot faktycznie trzyma).
const DATA_API: &str = "https://data-api.polymarket.com";
const KRAKEN_API: &str = "https://api.kraken.com/0/public/Ticker";
#[allow(dead_code)]
const CLOB_HOST_DEFAULT: &str = "https://clob.polymarket.com";

// =============================================================================
//  POMOCNICZE
// =============================================================================
fn now_secs() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// Log realnych zlecen LIVE (buy/sell) do live_fills.csv.
/// Zapisuje faktyczna odpowiedz CLOB: order_id + status (nie tylko lokalny bid).
fn append_fill(now: u64, side: &str, token_id: &str, amount: &str, order_id: &str, status: &str) {
    let path = "live_fills.csv";
    let header_needed = !std::path::Path::new(path).exists();
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(path) {
        if header_needed {
            let _ = writeln!(f, "ts,side,token_id,amount,order_id,status");
        }
        let _ = writeln!(f, "{},{},{},{},{},{}", now, side, token_id, amount, order_id, status);
    }
}

/// Slug rynku 5m/15m crypto:  {asset}-updown-{min}m-{window_start_ts}
fn make_slug(asset: &str, minutes: u64, now: u64) -> String {
    let win = minutes * 60;
    let ts = (now / win) * win;
    format!("{}-updown-{}m-{}", asset, minutes, ts)
}

// ---------------------------------------------------------------------------
//  INTERWALY 1h / 4h / 1d  (S7 / S8 / S9)
// ---------------------------------------------------------------------------
//  4h: slug epochowy  {asset}-updown-4h-<ts>   (ts = poczatek okna 4h)
//  1h: slug datowy   {full}-up-or-down-<month>-<day>-<year>-<h>am/pm-et
//  1d: slug datowy   {full}-up-or-down-on-<month>-<day>-<year>
//  Slugi 1h/1d uzywaja czasu ET (EDT=UTC-4 / EST=UTC-5) i PELNEJ nazwy aktywa.
// ---------------------------------------------------------------------------

const MONTHS_EN: [&str; 12] = [
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
];

/// Pelna nazwa aktywa uzywana w slugach 1h/1d (btc -> bitcoin itd.).
fn full_name(asset: &str) -> Option<&'static str> {
    match asset {
        "btc" => Some("bitcoin"),
        "eth" => Some("ethereum"),
        "sol" => Some("solana"),
        "xrp" => Some("xrp"),
        "doge" => Some("dogecoin"),
        "bnb" => Some("bnb"),
        "hype" => Some("hype"),
        "ada" => Some("cardano"),
        "avax" => Some("avalanche"),
        "link" => Some("chainlink"),
        "matic" => Some("polygon"),
        "ltc" => Some("litecoin"),
        "dot" => Some("polkadot"),
        _ => None,
    }
}

/// Godzina ET w formacie slugowym: 0 -> "12am", 13 -> "1pm".
fn et_hour_label(h: u64) -> String {
    match h {
        0 => "12am".to_string(),
        1..=11 => format!("{}am", h),
        12 => "12pm".to_string(),
        _ => format!("{}pm", h - 12),
    }
}

/// (rok, miesiac, dzien, godzina) z epoki UTC (algorytm Howarda Hinnanta).
fn civil_from_epoch(ts: u64) -> (i64, i64, i64, u64) {
    let days = (ts / 86400) as i64;
    let secs = ts % 86400;
    let z = days + 719468;
    let era = (if z >= 0 { z } else { z - 146096 }) / 146097;
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    (y, m, d, secs / 3600)
}

/// Slug 4h + jego wygasniecie (ts + 4h).
fn make_slug_4h(asset: &str, now: u64) -> (String, u64) {
    let win = 14400u64;
    let ts = (now / win) * win;
    (format!("{}-updown-4h-{}", asset, ts), ts + win)
}

/// Kandydaci slugow 1h (EDT=UTC-4 oraz EST=UTC-5; biezaca i nastepna godzina ET).
/// Zwraca do 4 par (slug, wygasniecie) - bot wybierze ten, ktory realnie istnieje.
fn hourly_candidates(asset: &str, now: u64) -> Vec<(String, u64)> {
    let Some(full) = full_name(asset) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    for offset in [4u64, 5u64] {
        for extra in [0u64, 3600u64] {
            let et = now.saturating_sub(offset * 3600) + extra;
            let et_hour_start = (et / 3600) * 3600;
            let start_utc = et_hour_start + offset * 3600;
            let exp = start_utc + 3600;
            let (y, m, d, h) = civil_from_epoch(et_hour_start);
            let slug = format!(
                "{}-up-or-down-{}-{}-{}-{}-et",
                full,
                MONTHS_EN[(m - 1) as usize],
                d,
                y,
                et_hour_label(h)
            );
            out.push((slug, exp));
        }
    }
    out
}

/// Kandydaci slugow 1d (dzisiaj / jutro; zamkniecie 16:00 UTC dla EDT, 17:00 dla EST).
fn daily_candidates(asset: &str, now: u64) -> Vec<(String, u64)> {
    let Some(full) = full_name(asset) else {
        return Vec::new();
    };
    let mut out = Vec::new();
    let day = 86400u64;
    let today = (now / day) * day;
    for delta in [0u64, 1u64] {
        let base = today + delta * day;
        for close_hour in [16u64, 17u64] {
            let exp = base + close_hour * 3600;
            let (y, m, d, _) = civil_from_epoch(base);
            let slug = format!(
                "{}-up-or-down-on-{}-{}-{}",
                full,
                MONTHS_EN[(m - 1) as usize],
                d,
                y
            );
            out.push((slug, exp));
        }
    }
    out
}

/// Wygaśnięcie rynku crypto z slug (ts + dlugosc okna). None dla slugow nie-crypto.
fn slug_expiry_secs(slug: &str) -> Option<u64> {
    if !slug.contains("-updown-") {
        return None;
    }
    let ts: u64 = slug.rsplit('-').next()?.parse().ok()?;
    let minutes = if slug.contains("-updown-15m-") {
        15
    } else if slug.contains("-updown-4h-") {
        240
    } else {
        5
    };
    Some(ts + minutes * 60)
}

fn value_to_string(v: &Value) -> String {
    if let Some(s) = v.as_str() {
        s.to_string()
    } else if let Some(n) = v.as_f64() {
        n.to_string()
    } else {
        v.to_string()
    }
}

/// Gamma zwraca outcomes/outcomePrices/clobTokenIds jako JSON-string LUB tablice.
fn parse_json_str_array(v: Option<&Value>) -> Vec<String> {
    let Some(v) = v else {
        return Vec::new();
    };
    if let Some(s) = v.as_str() {
        if let Ok(arr) = serde_json::from_str::<Vec<Value>>(s) {
            return arr.iter().map(value_to_string).collect();
        }
        return Vec::new();
    }
    if let Some(arr) = v.as_array() {
        return arr.iter().map(value_to_string).collect();
    }
    Vec::new()
}

#[derive(Clone, Debug)]
struct TokenInfo {
    outcome: String,
    token_id: String,
    price: f64,
}

fn parse_gamma_market(market: &Value) -> Vec<TokenInfo> {
    let outcomes = parse_json_str_array(market.get("outcomes"));
    let prices = parse_json_str_array(market.get("outcomePrices"));
    let tokens = parse_json_str_array(market.get("clobTokenIds"));
    let mut out = Vec::new();
    for (i, tid) in tokens.iter().enumerate() {
        if tid.is_empty() {
            continue;
        }
        let outcome = outcomes.get(i).cloned().unwrap_or_default();
        let price = prices
            .get(i)
            .and_then(|p| p.parse::<f64>().ok())
            .unwrap_or(0.0);
        out.push(TokenInfo {
            outcome,
            token_id: tid.clone(),
            price,
        });
    }
    out
}

fn market_volume(market: &Value) -> f64 {
    market
        .get("volumeNum")
        .and_then(|v| v.as_f64())
        .or_else(|| {
            market
                .get("volume")
                .and_then(|v| v.as_str())
                .and_then(|s| s.parse::<f64>().ok())
        })
        .unwrap_or(0.0)
}

fn market_slug(market: &Value) -> String {
    market
        .get("slug")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string()
}

// =============================================================================
//  HTTP  (Gamma REST + CLOB REST)
// =============================================================================
async fn fetch_market_by_slug(http: &reqwest::Client, slug: &str) -> Option<Value> {
    let url = format!("{}/markets?slug={}", GAMMA_API, slug);
    let resp = http
        .get(&url)
        .timeout(Duration::from_secs(8))
        .send()
        .await
        .ok()?;
    if !resp.status().is_success() {
        return None;
    }
    let v: Value = resp.json().await.ok()?;
    v.as_array()?.first().cloned()
}

/// Pobiera rynek po slug, takze juz ROZLICZONY (closed=true). Gamma domyslnie NIE zwraca
/// zamknietych rynkow - dlatego przy reconciliacji trzeba dodac &closed=true.
async fn fetch_market_by_slug_closed(http: &reqwest::Client, slug: &str) -> Option<Value> {
    let url = format!("{}/markets?slug={}&closed=true", GAMMA_API, slug);
    let resp = http
        .get(&url)
        .timeout(Duration::from_secs(8))
        .send()
        .await
        .ok()?;
    if !resp.status().is_success() {
        return None;
    }
    let v: Value = resp.json().await.ok()?;
    v.as_array()?.first().cloned()
}

/// Czy rynek jest ROZLICZONY? (Gamma: closed=true lub acceptingOrders=false + status resolved)
fn is_market_resolved(market: &Value) -> bool {
    let closed = market
        .get("closed")
        .and_then(|b| b.as_bool())
        .unwrap_or(false);
    if closed {
        return true;
    }
    let status = market
        .get("umaResolutionStatus")
        .and_then(|s| s.as_str())
        .unwrap_or("");
    if status.eq_ignore_ascii_case("resolved") {
        return true;
    }
    // Fallback: brak przyjmowania zlecen + ceny rozstrzygniete (0/1) => rozliczony.
    let accepting = market
        .get("acceptingOrders")
        .and_then(|b| b.as_bool())
        .unwrap_or(true);
    if !accepting {
        let prices = parse_json_str_array(market.get("outcomePrices"));
        let resolved = prices
            .iter()
            .all(|p| p == "0" || p == "1" || p == "0.0" || p == "1.0");
        if !prices.is_empty() && resolved {
            return true;
        }
    }
    false
}

/// Wartosc wyplaty za 1 udzial dla danego tokenu po rozliczeniu rynku.
/// 1.0 = nasza strona wygrala, 0.0 = przegrala. None = nie udalo sie ustalic.
fn resolution_payout(market: &Value, token_id: &str) -> Option<f64> {
    let tokens = parse_json_str_array(market.get("clobTokenIds"));
    let prices = parse_json_str_array(market.get("outcomePrices"));
    let idx = tokens.iter().position(|t| t == token_id)?;
    let p = prices.get(idx)?.parse::<f64>().ok()?;
    Some(p.clamp(0.0, 1.0))
}

/// Pobiera zbior token_id, ktore portfel FAKTYCZNIE trzyma (Data API /positions).
/// None = nie udalo sie odczytac (nie traktujemy wtedy braku jako dowodu).
async fn fetch_held_token_ids(http: &reqwest::Client) -> Option<std::collections::HashSet<String>> {
    let funder = effective_funder().await?;
    let url = format!("{}/positions?user={}&sizeThreshold=0&limit=500", DATA_API, funder);
    let resp = http
        .get(&url)
        .timeout(Duration::from_secs(10))
        .send()
        .await
        .ok()?;
    if !resp.status().is_success() {
        return None;
    }
    let v: Value = resp.json().await.ok()?;
    let arr = v.as_array()?;
    let mut set = std::collections::HashSet::new();
    for p in arr {
        if let Some(asset) = p.get("asset").and_then(|a| a.as_str()) {
            set.insert(asset.to_string());
        }
    }
    Some(set)
}

/// Pobiera wiele rynkow po slug ROWNOLEGLE (JoinSet) - duze przyspieszenie petli.
async fn fetch_markets_by_slugs(
    http: &reqwest::Client,
    slugs: &[String],
) -> HashMap<String, Value> {
    let mut set = tokio::task::JoinSet::new();
    for s in slugs {
        let http = http.clone();
        let s = s.clone();
        set.spawn(async move {
            let m = fetch_market_by_slug(&http, &s).await;
            (s, m)
        });
    }
    let mut out = HashMap::new();
    while let Some(res) = set.join_next().await {
        if let Ok((s, Some(m))) = res {
            out.insert(s, m);
        }
    }
    out
}

/// Pobiera tickery Krakena dla wielu aktywow ROWNOLEGLE.
async fn kraken_tickers(
    http: &reqwest::Client,
    assets: &[&str],
) -> Vec<(String, f64, f64)> {
    let mut set = tokio::task::JoinSet::new();
    for a in assets {
        let http = http.clone();
        let a = a.to_string();
        set.spawn(async move {
            let t = kraken_ticker(&http, &a).await;
            (a, t)
        });
    }
    let mut out = Vec::new();
    while let Some(res) = set.join_next().await {
        if let Ok((a, Some((last, vol)))) = res {
            out.push((a, last, vol));
        }
    }
    out
}

async fn fetch_top_markets(http: &reqwest::Client, limit: usize) -> Vec<Value> {
    let url = format!(
        "{}/markets?closed=false&active=true&limit={}&order=volumeNum&ascending=false",
        GAMMA_API, limit
    );
    let resp = match http.get(&url).timeout(Duration::from_secs(12)).send().await {
        Ok(r) => r,
        Err(_) => return Vec::new(),
    };
    if !resp.status().is_success() {
        return Vec::new();
    }
    let v: Value = match resp.json().await {
        Ok(v) => v,
        Err(_) => return Vec::new(),
    };
    v.as_array().cloned().unwrap_or_default()
}

// Cache listy rynkow sportowych. Endpoint /events?live=true zwraca ~12 MB, a bot
// wolal go co 2 s -> na telefonie przekraczalo timeout i zwracalo 0 rynkow.
// Teraz: pobieramy raz na SPORTS_REFRESH_SEC (domyslnie 60 s), a jesli pobranie
// sie nie uda, uzywamy ostatniej dobrej listy (nigdy nie zerujemy).
static SPORTS_CACHE: std::sync::Mutex<Option<(u64, Vec<Value>)>> = std::sync::Mutex::new(None);

fn sports_refresh_sec() -> u64 {
    std::env::var("SPORTS_REFRESH_SEC")
        .ok()
        .and_then(|v| v.trim().parse::<u64>().ok())
        .filter(|&n| n > 0)
        .unwrap_or(60)
}

async fn fetch_live_sports_markets(http: &reqwest::Client, now: u64) -> Vec<Value> {
    // 1. Swiezy cache -> zwroc od razu (bez sieci).
    if let Ok(g) = SPORTS_CACHE.lock() {
        if let Some((ts, ref v)) = *g {
            if !v.is_empty() && now.saturating_sub(ts) < sports_refresh_sec() {
                return v.clone();
            }
        }
    }
    // 2. Pobierz z sieci.
    let fresh = fetch_live_sports_markets_net(http).await;
    if !fresh.is_empty() {
        if let Ok(mut g) = SPORTS_CACHE.lock() {
            *g = Some((now, fresh.clone()));
        }
        return fresh;
    }
    // 3. Pobranie nieudane -> ostatnia dobra lista (jesli jest).
    if let Ok(g) = SPORTS_CACHE.lock() {
        if let Some((_, ref v)) = *g {
            if !v.is_empty() {
                return v.clone();
            }
        }
    }
    Vec::new()
}

async fn fetch_live_sports_markets_net(http: &reqwest::Client) -> Vec<Value> {
    // API Gamma zwraca max 100 eventow na strone, ale jest PAGINACJA (offset).
    // Wczesniej bot bral tylko pierwsza strone (100 eventow). Teraz pobieramy
    // kolejne strony (offset=0,100,200,...) az strona zwroci < 100 eventow,
    // z twardym limitem SPORTS_MAX_PAGES (domyslnie 5). To daje wszystkie
    // dostepne eventy sportowe live (~161) zamiast 100.
    let mut out = Vec::new();
    let max_pages = sports_max_pages();
    for page in 0..max_pages {
        let offset = page * 100;
        let url = format!(
            "{}/events?tag_id=1&live=true&closed=false&limit=100&offset={}",
            GAMMA_API, offset
        );
        let resp = match http.get(&url).timeout(Duration::from_secs(30)).send().await {
            Ok(r) => r,
            Err(_) => break,
        };
        if !resp.status().is_success() {
            break;
        }
        let v: Value = match resp.json().await {
            Ok(v) => v,
            Err(_) => break,
        };
        let events = match v.as_array() {
            Some(a) => a.clone(),
            None => break,
        };
        let n_events = events.len();
        for ev in &events {
            if let Some(markets) = ev.get("markets").and_then(|m| m.as_array()) {
                for m in markets {
                    let book = m
                        .get("enableOrderBook")
                        .and_then(|b| b.as_bool())
                        .unwrap_or(false);
                    let accepting = m
                        .get("acceptingOrders")
                        .and_then(|b| b.as_bool())
                        .unwrap_or(false);
                    let closed = m.get("closed").and_then(|b| b.as_bool()).unwrap_or(false);
                    let archived = m
                        .get("archived")
                        .and_then(|b| b.as_bool())
                        .unwrap_or(false);
                    if book && accepting && !closed && !archived {
                        out.push(m.clone());
                    }
                }
            }
        }
        // Ostatnia strona (mniej niz 100 eventow) -> konczymy.
        if n_events < 100 {
            break;
        }
    }
    // Sortuj po wolumenie (malejaco) i ogranicz liczbe rynkow na cykl.
    out.sort_by(|a, b| {
        market_volume(b)
            .partial_cmp(&market_volume(a))
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    out.truncate(sports_max_markets());
    out
}

async fn get_price(http: &reqwest::Client, token_id: &str, side: &str) -> Option<f64> {
    let url = format!("{}/price?token_id={}&side={}", CLOB_API, token_id, side);
    let resp = http
        .get(&url)
        .timeout(Duration::from_secs(6))
        .send()
        .await
        .ok()?;
    if !resp.status().is_success() {
        return None;
    }
    let v: Value = resp.json().await.ok()?;
    v.get("price")
        .and_then(|p| p.as_str())
        .and_then(|s| s.parse::<f64>().ok())
}

#[allow(dead_code)]
async fn get_ask(http: &reqwest::Client, token_id: &str) -> Option<f64> {
    get_price(http, token_id, "sell").await // ASK = side SELL
}
async fn get_bid(http: &reqwest::Client, token_id: &str) -> Option<f64> {
    get_price(http, token_id, "buy").await // BID = side BUY
}

/// Zbiorcze ceny: token_id -> (ask/buy, bid/sell)
async fn get_prices_batch(
    http: &reqwest::Client,
    token_ids: &[String],
) -> HashMap<String, (f64, f64)> {
    // Endpoint /prices odrzuca payload > 500 wpisow ("Payload exceeds the limit").
    // 250 tokenow = 500 wpisow (BUY+SELL) = dokladny maksymalny bezpieczny rozmiar
    // (test: 250 tokenow -> OK, 300 -> HTTP 400). Wczesniej 200 (bezpieczny zapas).
    // ROWNOLEGLE: chunki leca JEDNOCZESNIE (tokio::spawn), wiec nawet ~2800 tokenow
    // (~12 chunkow) konczy sie w czasie ~1 rundy, a nie 12 rund -> petla 2s zostaje szybka.
    const CHUNK: usize = 250;
    let mut handles = Vec::new();
    for chunk in token_ids.chunks(CHUNK) {
        let http = http.clone();
        let chunk: Vec<String> = chunk.to_vec();
        handles.push(tokio::spawn(async move {
            let mut m: HashMap<String, (f64, f64)> = HashMap::new();
            let body: Vec<Value> = chunk
                .iter()
                .flat_map(|t| {
                    vec![
                        serde_json::json!({"token_id": t, "side": "BUY"}),
                        serde_json::json!({"token_id": t, "side": "SELL"}),
                    ]
                })
                .collect();
            let resp = match http
                .post(format!("{}/prices", CLOB_API))
                .json(&body)
                .timeout(Duration::from_secs(10))
                .send()
                .await
            {
                Ok(r) => r,
                Err(_) => return m,
            };
            if !resp.status().is_success() {
                return m;
            }
            let v: Value = match resp.json().await {
                Ok(v) => v,
                Err(_) => return m,
            };
            if let Some(obj) = v.as_object() {
                for (tid, sides) in obj {
                    let buy = sides
                        .get("BUY")
                        .and_then(|x| x.as_str())
                        .and_then(|s| s.parse::<f64>().ok())
                        .unwrap_or(0.0);
                    let sell = sides
                        .get("SELL")
                        .and_then(|x| x.as_str())
                        .and_then(|s| s.parse::<f64>().ok())
                        .unwrap_or(0.0);
                    m.insert(tid.clone(), (sell, buy)); // (ask=SELL, bid=BUY)
                }
            }
            m
        }));
    }
    let mut out = HashMap::new();
    for h in handles {
        if let Ok(m) = h.await {
            out.extend(m);
        }
    }
    out
}

// =============================================================================
//  KRAKEN (referencja dla S3)
// =============================================================================
fn kraken_pair(asset: &str) -> Option<&'static str> {
    Some(match asset {
        "btc" => "XBTUSD",
        "eth" => "ETHUSD",
        "sol" => "SOLUSD",
        "xrp" => "XRPUSD",
        "doge" => "DOGEUSD",
        "ada" => "ADAUSD",
        "avax" => "AVAXUSD",
        "link" => "LINKUSD",
        "ltc" => "LTCUSD",
        "dot" => "DOTUSD",
        "bnb" => "BNBUSD",
        _ => return None,
    })
}

async fn kraken_ticker(http: &reqwest::Client, asset: &str) -> Option<(f64, f64)> {
    let pair = kraken_pair(asset)?;
    let url = format!("{}/Ticker?pair={}", KRAKEN_API, pair);
    let resp = http
        .get(&url)
        .timeout(Duration::from_secs(6))
        .send()
        .await
        .ok()?;
    let v: Value = resp.json().await.ok()?;
    let result = v.get("result")?.as_object()?;
    let (_, t) = result.iter().next()?;
    let last = t.get("c")?.as_array()?.first()?.as_str()?.parse::<f64>().ok()?;
    let vol = t.get("v")?.as_array()?.first()?.as_str()?.parse::<f64>().ok()?;
    Some((last, vol))
}

#[derive(Default)]
struct KrakenTracker {
    hist: HashMap<String, Vec<(u64, f64, f64)>>, // asset -> (ts, price, vol)
}
impl KrakenTracker {
    fn push(&mut self, asset: &str, price: f64, vol: f64, now: u64) {
        let e = self.hist.entry(asset.to_string()).or_default();
        e.push((now, price, vol));
        if e.len() > 600 {
            let d = e.len() - 600;
            e.drain(0..d);
        }
    }
    fn value_lookback(&self, asset: &str, lookback: u64, now: u64) -> Option<f64> {
        let e = self.hist.get(asset)?;
        for (t, p, _) in e.iter().rev() {
            if now.saturating_sub(*t) >= lookback {
                return Some(*p);
            }
        }
        e.first().map(|(_, p, _)| *p)
    }
    fn vol_ratio(&self, asset: &str, now: u64) -> Option<f64> {
        let e = self.hist.get(asset)?;
        let recent: Vec<f64> = e
            .iter()
            .filter(|(t, _, _)| now.saturating_sub(*t) <= KRAKEN_LOOKBACK_SEC)
            .map(|(_, _, v)| *v)
            .collect();
        if recent.len() < 2 {
            return Some(1.0);
        }
        let last = *recent.last()?;
        let prev = recent[0];
        if prev <= 0.0 {
            return Some(1.0);
        }
        Some(last / prev)
    }
}

// =============================================================================
//  PRICE TRACKER (dla rebound / mean reversion)
// =============================================================================
#[derive(Default)]
struct PriceTracker {
    hist: HashMap<String, Vec<(u64, f64)>>,
    // tokeny, dla ktorych juz probowalismy wczytac historie 6h z CLOB (bootstrap)
    boot: std::collections::HashSet<String>,
}
impl PriceTracker {
    fn push(&mut self, token_id: &str, price: f64, now: u64) {
        let e = self.hist.entry(token_id.to_string()).or_default();
        // 1 punkt na minute (zapamietujemy MAKSIMUM z minuty) -> 400 punktow = ok. 6h40m
        // historii (potrzebne do okna 6h w FINANCE; high() i tak szuka tylko maksimum).
        if let Some(last) = e.last_mut() {
            if now.saturating_sub(last.0) < 60 {
                if price > last.1 {
                    last.1 = price;
                }
                return;
            }
        }
        e.push((now, price));
        if e.len() > 400 {
            let d = e.len() - 400;
            e.drain(0..d);
        }
    }
    // Wstawia historie z CLOB (srodek ceny) PRZED punktami zebranymi na zywo.
    // half = polowa aktualnego spreadu -> przeliczamy srodek na ask (tak jak backtest).
    fn seed(&mut self, token_id: &str, pts: &[(u64, f64)], half: f64) {
        let e = self.hist.entry(token_id.to_string()).or_default();
        let first = e.first().map(|x| x.0).unwrap_or(u64::MAX);
        let mut v: Vec<(u64, f64)> = pts
            .iter()
            .filter(|(t, _)| *t < first)
            .map(|(t, p)| (*t, *p + half))
            .collect();
        v.sort_by(|a, b| a.0.cmp(&b.0));
        v.extend(e.iter().cloned());
        if v.len() > 400 {
            let d = v.len() - 400;
            v.drain(0..d);
        }
        *e = v;
        self.boot.insert(token_id.to_string());
    }
    fn high(&self, token_id: &str, lookback_sec: u64, now: u64) -> Option<f64> {
        let e = self.hist.get(token_id)?;
        let mut hi = f64::MIN;
        let mut any = false;
        for (t, p) in e.iter().rev() {
            if now.saturating_sub(*t) > lookback_sec {
                break;
            }
            if *p > hi {
                hi = *p;
            }
            any = true;
        }
        if any {
            Some(hi)
        } else {
            None
        }
    }
}

// =============================================================================
//  STAN + POZYCJE
// =============================================================================
#[derive(Serialize, Deserialize, Clone, Debug)]
struct Position {
    key: String,
    token_id: String,
    slug: String,
    strategy: String,
    entry_price: f64,
    size_usd: f64,
    shares: f64,
    tp: f64,
    sl: f64,
    expiry: u64,
    kind: String,
    opened_at: u64,
    high_water: f64,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
struct BotState {
    budget: f64,
    available_budget: f64,
    realized_pnl: f64,
    wins: u32,
    losses: u32,
    trades: u32,
    positions: HashMap<String, Position>,
    traded_slugs: HashMap<String, u64>,
    last_entry: HashMap<String, u64>,
    // Kapital poczatkowy (do liczenia zysku). Stare pliki stanu nie maja tego pola -> default 0.
    #[serde(default)]
    initial_budget: f64,
}
impl BotState {
    fn new(budget: f64) -> Self {
        Self {
            budget,
            available_budget: budget,
            realized_pnl: 0.0,
            wins: 0,
            losses: 0,
            trades: 0,
            positions: HashMap::new(),
            traded_slugs: HashMap::new(),
            last_entry: HashMap::new(),
            initial_budget: budget,
        }
    }
    fn open_value(&self) -> f64 {
        self.positions
            .values()
            .map(|p| p.shares * p.entry_price)
            .sum()
    }
    fn equity(&self) -> f64 {
        self.available_budget + self.open_value()
    }
    /// Zysk = equity - kapital poczatkowy.
    fn profit(&self) -> f64 {
        let base = if self.initial_budget > 0.0 {
            self.initial_budget
        } else {
            self.budget
        };
        self.equity() - base
    }
    fn prune(&mut self, now: u64) {
        let cutoff = now.saturating_sub(3600);
        self.traded_slugs.retain(|_, t| *t >= cutoff);
        let cooldown_cutoff = now.saturating_sub(REENTRY_COOLDOWN_SEC * 4);
        self.last_entry.retain(|_, t| *t >= cooldown_cutoff);
    }
}

fn save_state(state: &BotState) {
    if let Ok(s) = serde_json::to_string_pretty(state) {
        let _ = fs::write(state_file(), s);
    }
}

fn load_state(budget: f64) -> BotState {
    if let Ok(s) = fs::read_to_string(state_file()) {
        if let Ok(st) = serde_json::from_str::<BotState>(&s) {
            return st;
        }
    }
    BotState::new(budget)
}

fn append_trade(pos: &Position, exit_price: f64, pnl: f64, ret_pct: f64, reason: &str, now: u64) {
    let header_needed = !std::path::Path::new(TRADES_FILE).exists();
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(TRADES_FILE) {
        if header_needed {
            let _ = writeln!(
                f,
                "closed_at,strategy,kind,slug,key,entry,exit,size_usd,shares,pnl_usd,pnl_pct,reason,opened_at"
            );
        }
        let _ = writeln!(
            f,
            "{},{},{},{},{},{:.4},{:.4},{:.2},{:.2},{:.4},{:.2},{},{}",
            now,
            pos.strategy,
            pos.kind,
            pos.slug,
            pos.key,
            pos.entry_price,
            exit_price,
            pos.size_usd,
            pos.shares,
            pnl,
            ret_pct,
            reason,
            pos.opened_at
        );
    }
}

fn write_stats(state: &BotState, now: u64) {
    let winrate = if state.trades > 0 {
        state.wins as f64 / state.trades as f64 * 100.0
    } else {
        0.0
    };
    let base = if state.initial_budget > 0.0 {
        state.initial_budget
    } else {
        state.budget
    };
    let profit_pct = if base > 0.0 {
        state.profit() / base * 100.0
    } else {
        0.0
    };
    let txt = format!(
        "=== STATS ===\n\
         updated        : {}\n\
         live           : {}\n\
         kapital start  : {:.2} $\n\
         cash           : {:.2} $\n\
         open value     : {:.2} $\n\
         equity         : {:.2} $\n\
         profit         : {:+.2} $  ({:+.1} %)\n\
         realized pnl   : {:+.4} $\n\
         trades         : {}  (W {} / L {})\n\
         winrate        : {:.1} %\n\
         open positions : {}\n",
        now,
        live(),
        base,
        state.available_budget,
        state.open_value(),
        state.equity(),
        state.profit(),
        profit_pct,
        state.realized_pnl,
        state.trades,
        state.wins,
        state.losses,
        winrate,
        state.positions.len()
    );
    let _ = fs::write(STATS_FILE, txt);
}

fn dynamic_stake(state: &BotState) -> f64 {
    let init = if state.initial_budget > 0.0 { state.initial_budget } else { state.budget };
    if init <= 0.0 {
        return STAKE_USD_MIN;
    }
    let growth = (state.equity() / init).max(1e-9);
    let steps = (growth.ln() / (1.0 + STAKE_GROWTH_STEP).ln()).floor();
    let steps = if steps.is_finite() && steps > 0.0 { steps } else { 0.0 };
    (STAKE_USD_MIN * STAKE_GROWTH_MULT.powf(steps)).clamp(STAKE_USD_MIN, STAKE_USD_MAX)
}

// Ile otwartych pozycji ma dana strategia (do limitu 4 na strategie).
fn strategy_count(state: &BotState, strategy: &str) -> usize {
    state
        .positions
        .values()
        .filter(|p| p.strategy == strategy)
        .count()
}

fn stake_allowed(state: &BotState) -> f64 {
    if state.positions.len() >= max_positions(state) {
        return 0.0;
    }
    let equity = state.equity();
    if equity < MIN_BANKROLL_TO_TRADE {
        return 0.0;
    }
    let mut stake = dynamic_stake(state);
    stake = stake.min(state.available_budget);
    // LIVE: twardy limit calkowitej ekspozycji (suma otwartych size_usd).
    if live() {
        let exposure: f64 = state.positions.values().map(|p| p.size_usd).sum();
        let remaining = live_max_exposure() - exposure;
        if remaining < STAKE_USD_MIN {
            return 0.0;
        }
        stake = stake.min(remaining);
    }
    if stake < STAKE_USD_MIN {
        0.0
    } else {
        stake
    }
}

fn kill_switch(state: &BotState) -> bool {
    if state.budget <= 0.0 {
        return false;
    }
    let drop = (state.budget - state.equity()) / state.budget;
    drop >= KILL_SWITCH_DROP_PCT
}

// =============================================================================
//  SILNIK PAPER-TRADINGU
// =============================================================================
#[allow(clippy::too_many_arguments)]
fn paper_open(
    state: &mut BotState,
    key: &str,
    token_id: &str,
    slug: &str,
    price: f64,
    stake: f64,
    strategy: &str,
    tp: f64,
    sl: f64,
    expiry: u64,
    kind: &str,
    now: u64,
) {
    if state.positions.contains_key(key) {
        return;
    }
    if price <= 0.0 || price >= 1.0 {
        return;
    }
    let stake = stake.min(state.available_budget);
    if stake < STAKE_USD_MIN {
        return;
    }
    let shares = stake / price;
    state.available_budget -= stake;
    state.positions.insert(
        key.to_string(),
        Position {
            key: key.to_string(),
            token_id: token_id.to_string(),
            slug: slug.to_string(),
            strategy: strategy.to_string(),
            entry_price: price,
            size_usd: stake,
            shares,
            tp,
            sl,
            expiry,
            kind: kind.to_string(),
            opened_at: now,
            high_water: price,
        },
    );
    state.traded_slugs.insert(slug.to_string(), now);
    state.last_entry.insert(key.to_string(), now);
    println!(
        "[PAPER OPEN ] {:<3} {:<44} @ {:.4}  stake={:.2}$ shares={:.2} exp={}  {}",
        strategy, slug, price, stake, shares, expiry, key
    );
}

/// Otwarcie pozycji: w DRY RUN tylko papier; w LIVE najpierw sklada prawdziwe
/// zlecenie przez SDK, a potem i tak zapisuje pozycje do sledzenia (TP/SL).
#[allow(clippy::too_many_arguments)]
async fn open_position(
    state: &mut BotState,
    key: &str,
    token_id: &str,
    slug: &str,
    price: f64,
    stake: f64,
    strategy: &str,
    tp: f64,
    sl: f64,
    expiry: u64,
    kind: &str,
    now: u64,
) {
    // =====================================================================
    //  TWARDY GUARD: NIE otwieramy zadnej pozycji BEZ realnego stop-lossu.
    //  sl >= 1.0 (lub sl <= 0) oznacza "brak SL": sl_price = cena*(1-sl) <= 0,
    //  wiec stop-loss nigdy sie nie uruchomi. To gwarantuje, ze zadna
    //  strategia bez stop-lossu nie wejdzie w rynek -- nawet gdyby ktos
    //  przypadkiem wlaczyl ja flaga *_ENABLED.
    // =====================================================================
    if !(sl > 0.0 && sl < 1.0) {
        println!(
            "[GUARD] {:<44} -> POMIJAM: strategia '{}' bez stop-lossu (sl={:.2})",
            slug, strategy, sl
        );
        return;
    }
    if live() {
        match live_buy(token_id, stake).await {
            Ok(()) => println!(
                "[LIVE OPEN ] {:<3} {:<44} @ {:.4}  stake={:.2}$",
                strategy, slug, price, stake
            ),
            Err(e) => {
                println!("[LIVE ERROR] {} -> {} (pozycja pominięta)", slug, e);
                return;
            }
        }
    }
    paper_open(
        state, key, token_id, slug, price, stake, strategy, tp, sl, expiry, kind, now,
    );
}

/// Zamkniecie pozycji: w LIVE najpierw sklada prawdziwe zlecenie SPRZEDAZY
/// (market SELL, FOK, amount w shares), a dopiero po sukcesie robi ksiegowanie.
/// Gdy sprzedaz sie nie uda -> NIE zamyka lokalnie (sprobuje w nastepnej petli).
async fn close_position(state: &mut BotState, key: &str, exit_price: f64, reason: &str, now: u64) {
    if live() {
        let pos = match state.positions.get(key) {
            Some(p) => p.clone(),
            None => return,
        };
        match live_sell(&pos.token_id, pos.shares).await {
            Ok(()) => println!(
                "[LIVE CLOSE] {:<3} {:<44} shares={:.2} reason={}",
                pos.strategy, pos.slug, pos.shares, reason
            ),
            Err(e) => {
                let es = e.to_string();
                if es.contains("balance") || es.contains("allowance") {
                    // Jesli realne saldo to juz tylko "drob" (< 0.01 share), pozycja jest
                    // praktycznie pusta (rozliczona/auto-redeem) -> zamknij LOKALNIE, zeby
                    // nie blokowac kapitalu ani limitu pozycji.
                    let dust = parse_balance_from_err(&es).map(|b| b < 0.01).unwrap_or(false);
                    if dust {
                        println!(
                            "[LIVE WARN] SELL {} -> saldo ~0 (drob) -> zamykam lokalnie.",
                            pos.slug
                        );
                        paper_close(state, key, exit_price, reason, now);
                        return;
                    }
                    println!(
                        "[LIVE WARN] SELL {} odrzucone (saldo/allowance): {} -> sprobuje ponownie w nastepnej petli.",
                        pos.slug, es
                    );
                } else {
                    println!(
                        "[LIVE ERROR] SELL {} -> {} (pozycja NIE zamknieta, ponowie w nastepnej petli)",
                        pos.slug, e
                    );
                }
                return;
            }
        }
    }
    paper_close(state, key, exit_price, reason, now);
}

fn paper_close(state: &mut BotState, key: &str, exit_price: f64, reason: &str, now: u64) {
    let Some(pos) = state.positions.remove(key) else {
        return;
    };
    let gross = pos.shares * exit_price;
    let fee = gross * PAPER_FEE_PCT;
    let net = gross - fee;
    let pnl = net - pos.size_usd;
    state.available_budget += net;
    state.realized_pnl += pnl;
    state.trades += 1;
    if pnl >= 0.0 {
        state.wins += 1;
    } else {
        state.losses += 1;
    }
    let ret_pct = if pos.size_usd > 0.0 {
        pnl / pos.size_usd * 100.0
    } else {
        0.0
    };
    println!(
        "[PAPER CLOSE] {:<3} {:<44} exit={:.4}  pnl={:+.4}$ ({:+.2}%)  {:<4}  {}",
        pos.strategy, pos.slug, exit_price, pnl, ret_pct, reason, key
    );
    append_trade(&pos, exit_price, pnl, ret_pct, reason, now);
}

// =============================================================================
//  RECONCILIACJA - wykrywanie ROZLICZONYCH pozycji (koniec wiecznego SELL)
// -----------------------------------------------------------------------------
//  Problem: rynek 5m/15m wygasa i pozycja jest AUTO-REDEEMOWANA przez Polymarket.
//  Token znika z portfela (balance=0), a bot dalej probuje go SPRZEDAC -> blad 400
//  "not enough balance", w nieskonczonej petli. Kapital zostaje "zablokowany".
//  Rozwiazanie: wykryc rozliczenie i zamknac pozycje lokalnie (bez zlecenia).
// =============================================================================
/// Termin wygasniecia rynku dla pozycji (crypto up/down ze sluga; inaczej pole expiry).
fn position_market_expiry(pos: &Position) -> u64 {
    if let Some(e) = slug_expiry_secs(&pos.slug) {
        return e;
    }
    pos.expiry
}

/// Rozlicza pozycje, ktora sie juz zakonczyla. Usuwa ja lokalnie i ksieguje statystyki.
/// NIE dolicza gotowki do available_budget - gotowka jest synchronizowana z prawdziwego
/// salda on-chain (pUSD), inaczej liczylibysmy wyplate podwojnie.
fn settle_resolved(state: &mut BotState, key: &str, payout_per_share: f64, now: u64, reason: &str) {
    let Some(pos) = state.positions.remove(key) else {
        return;
    };
    let proceeds = pos.shares * payout_per_share;
    let pnl = proceeds - pos.size_usd;
    state.realized_pnl += pnl;
    state.trades += 1;
    if pnl >= 0.0 {
        state.wins += 1;
    } else {
        state.losses += 1;
    }
    let ret_pct = if pos.size_usd > 0.0 {
        pnl / pos.size_usd * 100.0
    } else {
        0.0
    };
    println!(
        "[ROZLICZONE] {:<3} {:<44} payout={:.4}/udz  pnl={:+.4}$ ({:+.2}%)  {}  {}",
        pos.strategy, pos.slug, payout_per_share, pnl, ret_pct, reason, key
    );
    append_trade(&pos, payout_per_share, pnl, ret_pct, reason, now);
}

/// Sprawdza, czy otwarte pozycje sie ROZLICZYLY i zamyka je (bez skladania zlecen).
/// Zrodlo prawdy: Gamma (closed=true) -> outcomePrices (1/0).
/// Safety net: Data API /positions (jesli portfel juz tego nie trzyma).
async fn reconcile_positions(http: &reqwest::Client, state: &mut BotState, now: u64) {
    let keys: Vec<String> = state.positions.keys().cloned().collect();
    if keys.is_empty() {
        return;
    }
    // Zbior tokenow faktycznie trzymanych on-chain (JEDEN request na cykl, na starcie).
    let held = fetch_held_token_ids(http).await;

    // 0) PHANTOM / ZNIKLA: portfel NIE trzyma tego tokenu, a pozycja jest starsza niz
    //    PHANTOM_GRACE_SEC. Data API ma chwilowy lag po zakupie, dlatego swiezo
    //    otwartych pozycji NIE ruszamy. Gdy held == None (API padlo) nic nie zamykamy.
    //    To lapie m.in. "will-the-us-invade-iran-before-2027" (rynek wygasa 2027,
    //    wiec stara sciezka "po wygasnieciu" nigdy go nie dotykala).
    // POPRAWKA (bug DRY RUN): w paper tradingu pozycje NIE sa trzymane on-chain,
    // wiec kontrola "portfela nie ma tokenu" zawsze dawala falszywe PHANTOM (-100%).
    // Ten safety-net ma sens wylacznie w LIVE, gdzie naprawde kupujemy tokeny.
    if live() {
        if let Some(held) = &held {
            let phantom: Vec<String> = keys
                .iter()
                .cloned()
                .filter(|k| {
                    state
                        .positions
                        .get(k)
                        .map(|p| {
                            let age = now.saturating_sub(p.opened_at);
                            !held.contains(&p.token_id) && age >= PHANTOM_GRACE_SEC
                        })
                        .unwrap_or(false)
                })
                .collect();
            for key in phantom {
                // Jesli rynek zdazyl sie rozliczyc -> prawdziwy payout (1/0), inaczej 0.
                let payout = match state.positions.get(&key) {
                    Some(p) => fetch_market_by_slug_closed(http, &p.slug)
                        .await
                        .filter(|m| is_market_resolved(m))
                        .and_then(|m| resolution_payout(&m, &p.token_id))
                        .unwrap_or(0.0),
                    None => 0.0,
                };
                settle_resolved(state, &key, payout, now, "PHANTOM");
            }
        }
    }

    // Tylko pozycje PO wygasnieciu rynku (przed wygasnieciem sa jeszcze handlowalne).
    let due: Vec<String> = state
        .positions
        .keys()
        .cloned()
        .filter(|k| {
            state
                .positions
                .get(k)
                .map(|p| {
                    let e = position_market_expiry(p);
                    e > 0 && now >= e
                })
                .unwrap_or(false)
        })
        .collect();
    if due.is_empty() {
        return;
    }
    for key in due {
        let Some(pos) = state.positions.get(&key).cloned() else {
            continue;
        };
        let exp = position_market_expiry(&pos);
        // 1) Rozliczenie w Gamma (closed=true).
        if let Some(m) = fetch_market_by_slug_closed(http, &pos.slug).await {
            if is_market_resolved(&m) {
                let payout = resolution_payout(&m, &pos.token_id).unwrap_or(0.0);
                settle_resolved(state, &key, payout, now, "ROZLICZONE");
                continue;
            }
        }
        // 2) Safety net: portfel juz tego NIE trzyma (Data API) i minelo >5 min od
        //    wygasniecia -> pozycja zniknela (auto-redeem). Zamykamy.
        if let Some(held) = &held {
            if !held.contains(&pos.token_id) && now >= exp.saturating_add(300) {
                settle_resolved(state, &key, 0.0, now, "ZNIKLA(API)");
                continue;
            }
        }
        // 3) Awaryjnie: bardzo stara pozycja po wygasnieciu -> zamknij (nie blokuj kapitalu).
        if now >= exp.saturating_add(900) {
            settle_resolved(state, &key, 0.0, now, "WYGASLA");
        }
    }
}

// =============================================================================
//  WYJSCIA (TP / SL / TIME)
// =============================================================================
async fn manage_exits(http: &reqwest::Client, state: &mut BotState, now: u64) {
    let keys: Vec<String> = state.positions.keys().cloned().collect();
    for key in keys {
        let Some(pos) = state.positions.get(&key).cloned() else {
            continue;
        };
        // Po wygasnieciu rynku NIE probujemy sprzedawac (rynek zamkniety / pozycja
        // auto-redeemowana) - rozliczeniem zajmuje sie reconcile_positions().
        let market_exp = position_market_expiry(&pos);
        if market_exp > 0 && now >= market_exp {
            continue;
        }
        let bid = match get_bid(http, &pos.token_id).await {
            Some(b) if b > 0.0 => b,
            _ => continue,
        };
        if let Some(p) = state.positions.get_mut(&key) {
            if bid > p.high_water {
                p.high_water = bid;
            }
        }
        let tp_price = pos.entry_price * (1.0 + pos.tp);
        let sl_price = pos.entry_price * (1.0 - pos.sl);
        let time_exit = if pos.kind == "crypto" {
            let by_expiry = pos.expiry.saturating_sub(SCALP_EXIT_BEFORE_END);
            // time-exit zalezny od strategii (S6/15m trzyma dluzej niz S5/5m)
            let hold = match pos.strategy.as_str() {
                "S6" => S6_EXIT_SEC,
                "S7" => S7_EXIT_SEC,
                "S8" => S8_EXIT_SEC,
                "S9" => S9_EXIT_SEC,
                "S4" => TIME_EXIT_15M_SEC,
                _ => S5_EXIT_SEC.max(TIME_EXIT_15M_SEC),
            };
            let by_hold = pos.opened_at + hold;
            by_expiry.min(by_hold)
        } else {
            pos.opened_at + SPORTS_TIME_EXIT_SEC
        };

        if bid >= tp_price {
            close_position(state, &key, bid, "TP", now).await;
        } else if bid <= sl_price {
            close_position(state, &key, bid, "SL", now).await;
        } else if now >= time_exit {
            close_position(state, &key, bid, "TIME", now).await;
        }
    }
}

// =============================================================================
//  STRATEGIE
// =============================================================================

/// Wybiera "faworyta" (najwyzej wyceniona strona) w przedziale cenowym.
fn pick_favorite(tokens: &[TokenInfo], lo: f64, hi: f64) -> Option<TokenInfo> {
    tokens
        .iter()
        .filter(|t| t.price >= lo && t.price <= hi)
        .max_by(|a, b| {
            a.price
                .partial_cmp(&b.price)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .cloned()
}

/// S5 - 5m REBOUND: kup "Up" gdy cena spadla z ostatniego maksimum.
async fn scan_s5(
    http: &reqwest::Client,
    state: &mut BotState,
    tracker: &mut PriceTracker,
    assets: &[&str],
    now: u64,
) {
    if !S5_ENABLED {
        return;
    }
    // 1. wyznacz slugi do sprawdzenia
    let mut jobs: Vec<(String, u64)> = Vec::new(); // (slug, exp)
    for asset in assets {
        let mut slug = make_slug(asset, 5, now);
        let mut exp = slug_expiry_secs(&slug).unwrap_or(0);
        if exp.saturating_sub(now) < MIN_SEC_TO_EXPIRY {
            let next = (now / 300 + 1) * 300;
            slug = format!("{}-updown-5m-{}", asset, next);
            exp = slug_expiry_secs(&slug).unwrap_or(0);
        }
        if exp == 0 || exp.saturating_sub(now) < MIN_SEC_TO_EXPIRY {
            continue;
        }
        if state.traded_slugs.contains_key(&slug) {
            continue;
        }
        jobs.push((slug, exp));
    }
    if jobs.is_empty() {
        return;
    }
    // 2. pobierz rynki rownolegle
    let slugs: Vec<String> = jobs.iter().map(|(s, _)| s.clone()).collect();
    let markets = fetch_markets_by_slugs(http, &slugs).await;
    // 3. zbierz tokeny "Up" i ich id
    let mut token_ids: Vec<String> = Vec::new();
    let mut cand: Vec<(String, u64, TokenInfo)> = Vec::new();
    for (slug, exp) in &jobs {
        let Some(market) = markets.get(slug) else {
            continue;
        };
        if !market
            .get("enableOrderBook")
            .and_then(|b| b.as_bool())
            .unwrap_or(false)
        {
            continue;
        }
        let tokens = parse_gamma_market(market);
        if tokens.len() < 2 {
            continue;
        }
        for t in tokens {
            if t.outcome.to_lowercase().contains("up") {
                token_ids.push(t.token_id.clone());
                cand.push((slug.clone(), *exp, t));
            }
        }
    }
    if token_ids.is_empty() {
        return;
    }
    // 4. ceny batch
    let prices = get_prices_batch(http, &token_ids).await;
    // 5. logika wejscia
    let mut opened: std::collections::HashSet<String> = std::collections::HashSet::new();
    for (slug, exp, t) in cand {
        if opened.contains(&slug) {
            continue;
        }
        let stake = stake_allowed(state);
        if stake < STAKE_USD_MIN {
            return;
        }
        let (ask, bid) = match prices.get(&t.token_id) {
            Some(&(a, b)) if a > 0.0 && b > 0.0 => (a, b),
            _ => continue,
        };
        if (ask - bid) > max_spread_cents() + 1e-9 {
            continue;
        }
        tracker.push(&t.token_id, ask, now);
        if ask < S5_MIN_PRICE || ask > S5_MAX_PRICE {
            continue;
        }
        let hi = tracker.high(&t.token_id, 240, now).unwrap_or(ask);
        let drop = if hi > 0.0 { (hi - ask) / hi } else { 0.0 };
        if drop >= S5_REBOUND_PCT {
            let key = format!("{}_{}", slug, t.outcome);
            println!(
                "S5 REBOUND 5m  {}  @ {:.4}  drop={:.1}%  hi={:.4}  | {}",
                slug,
                ask,
                drop * 100.0,
                hi,
                t.outcome
            );
            open_position(
                state, &key, &t.token_id, &slug, ask, stake, "S5", S5_TP, S5_SL, exp, "crypto",
                now,
            )
            .await;
            opened.insert(slug);
        }
    }
}

/// S4 - 15m VOLUME SPIKE: kup faworyta na rynku 15m o wysokim wolumenie.
async fn scan_s4(http: &reqwest::Client, state: &mut BotState, assets: &[&str], now: u64) {
    if !S4_ENABLED {
        return;
    }
    let mut jobs: Vec<(String, u64)> = Vec::new();
    for asset in assets {
        let slug = make_slug(asset, 15, now);
        let exp = slug_expiry_secs(&slug).unwrap_or(0);
        if exp == 0 || exp.saturating_sub(now) < MIN_SEC_TO_EXPIRY {
            continue;
        }
        if state.traded_slugs.contains_key(&slug) {
            continue;
        }
        jobs.push((slug, exp));
    }
    if jobs.is_empty() {
        return;
    }
    let slugs: Vec<String> = jobs.iter().map(|(s, _)| s.clone()).collect();
    let markets = fetch_markets_by_slugs(http, &slugs).await;
    let mut token_ids: Vec<String> = Vec::new();
    let mut cand: Vec<(String, u64, f64, TokenInfo)> = Vec::new();
    for (slug, exp) in &jobs {
        let Some(market) = markets.get(slug) else {
            continue;
        };
        let vol = market_volume(market);
        if vol < MIN_MARKET_VOLUME {
            continue;
        }
        let tokens = parse_gamma_market(market);
        if tokens.len() < 2 {
            continue;
        }
        let Some(fav) = pick_favorite(&tokens, S4_MIN_PRICE, S4_MAX_PRICE) else {
            continue;
        };
        token_ids.push(fav.token_id.clone());
        cand.push((slug.clone(), *exp, vol, fav));
    }
    if token_ids.is_empty() {
        return;
    }
    let prices = get_prices_batch(http, &token_ids).await;
    for (slug, exp, vol, fav) in cand {
        let stake = stake_allowed(state);
        if stake < STAKE_USD_MIN {
            return;
        }
        let (ask, bid) = match prices.get(&fav.token_id) {
            Some(&(a, b)) if a > 0.0 && b > 0.0 => (a, b),
            _ => continue,
        };
        if (ask - bid) > max_spread_cents() + 1e-9 {
            continue;
        }
        if ask < S4_MIN_PRICE || ask > S4_MAX_PRICE {
            continue;
        }
        let key = format!("{}_{}", slug, fav.outcome);
        println!(
            "S4 VOL SPIKE 15m  {}  vol={:.0}  @ {:.4}  | {}",
            slug, vol, ask, fav.outcome
        );
        open_position(
            state, &key, &fav.token_id, &slug, ask, stake, "S4", S4_TP, S4_SL, exp, "crypto", now,
        )
        .await;
    }
}

/// S6 - 15m REBOUND: kup "Up" na rynku 15m gdy cena spadla z ostatniego maksimum.
/// Lustrzane odbicie strategii S5 (5m) dostrojone do okna 15-minutowego.
async fn scan_s6(
    http: &reqwest::Client,
    state: &mut BotState,
    tracker: &mut PriceTracker,
    assets: &[&str],
    now: u64,
) {
    if !S6_ENABLED {
        return;
    }
    // 1. wyznacz slugi 15m do sprawdzenia
    let mut jobs: Vec<(String, u64)> = Vec::new(); // (slug, exp)
    for asset in assets {
        let mut slug = make_slug(asset, 15, now);
        let mut exp = slug_expiry_secs(&slug).unwrap_or(0);
        if exp.saturating_sub(now) < MIN_SEC_TO_EXPIRY {
            let next = (now / 900 + 1) * 900;
            slug = format!("{}-updown-15m-{}", asset, next);
            exp = slug_expiry_secs(&slug).unwrap_or(0);
        }
        if exp == 0 || exp.saturating_sub(now) < MIN_SEC_TO_EXPIRY {
            continue;
        }
        if state.traded_slugs.contains_key(&slug) {
            continue;
        }
        jobs.push((slug, exp));
    }
    if jobs.is_empty() {
        return;
    }
    // 2. pobierz rynki rownolegle
    let slugs: Vec<String> = jobs.iter().map(|(s, _)| s.clone()).collect();
    let markets = fetch_markets_by_slugs(http, &slugs).await;
    // 3. zbierz tokeny "Up" i ich id
    let mut token_ids: Vec<String> = Vec::new();
    let mut cand: Vec<(String, u64, TokenInfo)> = Vec::new();
    for (slug, exp) in &jobs {
        let Some(market) = markets.get(slug) else {
            continue;
        };
        if !market
            .get("enableOrderBook")
            .and_then(|b| b.as_bool())
            .unwrap_or(false)
        {
            continue;
        }
        let tokens = parse_gamma_market(market);
        if tokens.len() < 2 {
            continue;
        }
        for t in tokens {
            if t.outcome.to_lowercase().contains("up") {
                token_ids.push(t.token_id.clone());
                cand.push((slug.clone(), *exp, t));
            }
        }
    }
    if token_ids.is_empty() {
        return;
    }
    // 4. ceny batch
    let prices = get_prices_batch(http, &token_ids).await;
    // 5. logika wejscia
    let mut opened: std::collections::HashSet<String> = std::collections::HashSet::new();
    for (slug, exp, t) in cand {
        if opened.contains(&slug) {
            continue;
        }
        let stake = stake_allowed(state);
        if stake < STAKE_USD_MIN {
            return;
        }
        let (ask, bid) = match prices.get(&t.token_id) {
            Some(&(a, b)) if a > 0.0 && b > 0.0 => (a, b),
            _ => continue,
        };
        if (ask - bid) > max_spread_cents() + 1e-9 {
            continue;
        }
        tracker.push(&t.token_id, ask, now);
        if ask < S6_MIN_PRICE || ask > S6_MAX_PRICE {
            continue;
        }
        let hi = tracker
            .high(&t.token_id, S6_LOOKBACK_SEC, now)
            .unwrap_or(ask);
        let drop = if hi > 0.0 { (hi - ask) / hi } else { 0.0 };
        if drop >= S6_REBOUND_PCT {
            let key = format!("{}_{}", slug, t.outcome);
            println!(
                "S6 REBOUND 15m  {}  @ {:.4}  drop={:.1}%  hi={:.4}  | {}",
                slug,
                ask,
                drop * 100.0,
                hi,
                t.outcome
            );
            open_position(
                state, &key, &t.token_id, &slug, ask, stake, "S6", S6_TP, S6_SL, exp, "crypto",
                now,
            )
            .await;
            opened.insert(slug);
        }
    }
}

/// S7 - 1h REBOUND: kup "Up" na rynku 1h gdy cena spadla z ostatniego maksimum.
/// Slug 1h jest datowy (ET) - budujemy kilku kandydatow (EDT/EST, biezaca/nastepna h).
async fn scan_s7(
    http: &reqwest::Client,
    state: &mut BotState,
    tracker: &mut PriceTracker,
    assets: &[&str],
    now: u64,
) {
    if !S7_ENABLED {
        return;
    }
    let mut jobs: Vec<(String, u64)> = Vec::new();
    for asset in assets {
        for (slug, exp) in hourly_candidates(asset, now) {
            if exp.saturating_sub(now) < MIN_SEC_TO_EXPIRY {
                continue;
            }
            if state.traded_slugs.contains_key(&slug) {
                continue;
            }
            if jobs.iter().any(|(s, _)| s == &slug) {
                continue;
            }
            jobs.push((slug, exp));
        }
    }
    if jobs.is_empty() {
        return;
    }
    let slugs: Vec<String> = jobs.iter().map(|(s, _)| s.clone()).collect();
    let markets = fetch_markets_by_slugs(http, &slugs).await;
    let mut token_ids: Vec<String> = Vec::new();
    let mut cand: Vec<(String, u64, TokenInfo)> = Vec::new();
    for (slug, exp) in &jobs {
        let Some(market) = markets.get(slug) else {
            continue;
        };
        if !market
            .get("enableOrderBook")
            .and_then(|b| b.as_bool())
            .unwrap_or(false)
        {
            continue;
        }
        if market.get("closed").and_then(|b| b.as_bool()).unwrap_or(false) {
            continue;
        }
        let tokens = parse_gamma_market(market);
        if tokens.len() < 2 {
            continue;
        }
        for t in tokens {
            if t.outcome.to_lowercase().contains("up") {
                token_ids.push(t.token_id.clone());
                cand.push((slug.clone(), *exp, t));
            }
        }
    }
    if token_ids.is_empty() {
        return;
    }
    let prices = get_prices_batch(http, &token_ids).await;
    let mut opened: std::collections::HashSet<String> = std::collections::HashSet::new();
    for (slug, exp, t) in cand {
        if opened.contains(&slug) {
            continue;
        }
        let stake = stake_allowed(state);
        if stake < STAKE_USD_MIN {
            return;
        }
        let (ask, bid) = match prices.get(&t.token_id) {
            Some(&(a, b)) if a > 0.0 && b > 0.0 => (a, b),
            _ => continue,
        };
        if (ask - bid) > max_spread_cents() + 1e-9 {
            continue;
        }
        tracker.push(&t.token_id, ask, now);
        if ask < S7_MIN_PRICE || ask > S7_MAX_PRICE {
            continue;
        }
        let hi = tracker.high(&t.token_id, S7_LOOKBACK_SEC, now).unwrap_or(ask);
        let drop = if hi > 0.0 { (hi - ask) / hi } else { 0.0 };
        if drop >= S7_REBOUND_PCT {
            let key = format!("{}_{}", slug, t.outcome);
            println!(
                "S7 REBOUND 1h   {}  @ {:.4}  drop={:.1}%  hi={:.4}  | {}",
                slug,
                ask,
                drop * 100.0,
                hi,
                t.outcome
            );
            open_position(
                state, &key, &t.token_id, &slug, ask, stake, "S7", S7_TP, S7_SL, exp, "crypto", now,
            )
            .await;
            opened.insert(slug);
        }
    }
}

/// S8 - 4h REBOUND: kup "Up" na rynku 4h gdy cena spadla z ostatniego maksimum.
/// Slug 4h jest epochowy: {asset}-updown-4h-<ts>.
async fn scan_s8(
    http: &reqwest::Client,
    state: &mut BotState,
    tracker: &mut PriceTracker,
    assets: &[&str],
    now: u64,
) {
    if !S8_ENABLED {
        return;
    }
    let mut jobs: Vec<(String, u64)> = Vec::new();
    for asset in assets {
        let (slug, exp) = make_slug_4h(asset, now);
        if exp.saturating_sub(now) < MIN_SEC_TO_EXPIRY {
            continue;
        }
        if state.traded_slugs.contains_key(&slug) {
            continue;
        }
        jobs.push((slug, exp));
    }
    if jobs.is_empty() {
        return;
    }
    let slugs: Vec<String> = jobs.iter().map(|(s, _)| s.clone()).collect();
    let markets = fetch_markets_by_slugs(http, &slugs).await;
    let mut token_ids: Vec<String> = Vec::new();
    let mut cand: Vec<(String, u64, TokenInfo)> = Vec::new();
    for (slug, exp) in &jobs {
        let Some(market) = markets.get(slug) else {
            continue;
        };
        if !market
            .get("enableOrderBook")
            .and_then(|b| b.as_bool())
            .unwrap_or(false)
        {
            continue;
        }
        if market.get("closed").and_then(|b| b.as_bool()).unwrap_or(false) {
            continue;
        }
        let tokens = parse_gamma_market(market);
        if tokens.len() < 2 {
            continue;
        }
        for t in tokens {
            if t.outcome.to_lowercase().contains("up") {
                token_ids.push(t.token_id.clone());
                cand.push((slug.clone(), *exp, t));
            }
        }
    }
    if token_ids.is_empty() {
        return;
    }
    let prices = get_prices_batch(http, &token_ids).await;
    let mut opened: std::collections::HashSet<String> = std::collections::HashSet::new();
    for (slug, exp, t) in cand {
        if opened.contains(&slug) {
            continue;
        }
        let stake = stake_allowed(state);
        if stake < STAKE_USD_MIN {
            return;
        }
        let (ask, bid) = match prices.get(&t.token_id) {
            Some(&(a, b)) if a > 0.0 && b > 0.0 => (a, b),
            _ => continue,
        };
        if (ask - bid) > max_spread_cents() + 1e-9 {
            continue;
        }
        tracker.push(&t.token_id, ask, now);
        if ask < S8_MIN_PRICE || ask > S8_MAX_PRICE {
            continue;
        }
        let hi = tracker.high(&t.token_id, S8_LOOKBACK_SEC, now).unwrap_or(ask);
        let drop = if hi > 0.0 { (hi - ask) / hi } else { 0.0 };
        if drop >= S8_REBOUND_PCT {
            let key = format!("{}_{}", slug, t.outcome);
            println!(
                "S8 REBOUND 4h   {}  @ {:.4}  drop={:.1}%  hi={:.4}  | {}",
                slug,
                ask,
                drop * 100.0,
                hi,
                t.outcome
            );
            open_position(
                state, &key, &t.token_id, &slug, ask, stake, "S8", S8_TP, S8_SL, exp, "crypto", now,
            )
            .await;
            opened.insert(slug);
        }
    }
}

/// S9 - 1d REBOUND: kup "Up" na rynku 1d gdy cena spadla z ostatniego maksimum.
/// Slug 1d jest datowy: {full}-up-or-down-on-<month>-<day>-<year>.
async fn scan_s9(
    http: &reqwest::Client,
    state: &mut BotState,
    tracker: &mut PriceTracker,
    assets: &[&str],
    now: u64,
) {
    if !S9_ENABLED {
        return;
    }
    let mut jobs: Vec<(String, u64)> = Vec::new();
    for asset in assets {
        for (slug, exp) in daily_candidates(asset, now) {
            if exp.saturating_sub(now) < MIN_SEC_TO_EXPIRY {
                continue;
            }
            if state.traded_slugs.contains_key(&slug) {
                continue;
            }
            if jobs.iter().any(|(s, _)| s == &slug) {
                continue;
            }
            jobs.push((slug, exp));
        }
    }
    if jobs.is_empty() {
        return;
    }
    let slugs: Vec<String> = jobs.iter().map(|(s, _)| s.clone()).collect();
    let markets = fetch_markets_by_slugs(http, &slugs).await;
    let mut token_ids: Vec<String> = Vec::new();
    let mut cand: Vec<(String, u64, TokenInfo)> = Vec::new();
    for (slug, exp) in &jobs {
        let Some(market) = markets.get(slug) else {
            continue;
        };
        if !market
            .get("enableOrderBook")
            .and_then(|b| b.as_bool())
            .unwrap_or(false)
        {
            continue;
        }
        if market.get("closed").and_then(|b| b.as_bool()).unwrap_or(false) {
            continue;
        }
        let tokens = parse_gamma_market(market);
        if tokens.len() < 2 {
            continue;
        }
        for t in tokens {
            if t.outcome.to_lowercase().contains("up") {
                token_ids.push(t.token_id.clone());
                cand.push((slug.clone(), *exp, t));
            }
        }
    }
    if token_ids.is_empty() {
        return;
    }
    let prices = get_prices_batch(http, &token_ids).await;
    let mut opened: std::collections::HashSet<String> = std::collections::HashSet::new();
    for (slug, exp, t) in cand {
        if opened.contains(&slug) {
            continue;
        }
        let stake = stake_allowed(state);
        if stake < STAKE_USD_MIN {
            return;
        }
        let (ask, bid) = match prices.get(&t.token_id) {
            Some(&(a, b)) if a > 0.0 && b > 0.0 => (a, b),
            _ => continue,
        };
        if (ask - bid) > max_spread_cents() + 1e-9 {
            continue;
        }
        tracker.push(&t.token_id, ask, now);
        if ask < S9_MIN_PRICE || ask > S9_MAX_PRICE {
            continue;
        }
        let hi = tracker.high(&t.token_id, S9_LOOKBACK_SEC, now).unwrap_or(ask);
        let drop = if hi > 0.0 { (hi - ask) / hi } else { 0.0 };
        if drop >= S9_REBOUND_PCT {
            let key = format!("{}_{}", slug, t.outcome);
            println!(
                "S9 REBOUND 1d   {}  @ {:.4}  drop={:.1}%  hi={:.4}  | {}",
                slug,
                ask,
                drop * 100.0,
                hi,
                t.outcome
            );
            open_position(
                state, &key, &t.token_id, &slug, ask, stake, "S9", S9_TP, S9_SL, exp, "crypto", now,
            )
            .await;
            opened.insert(slug);
        }
    }
}

/// S3 - MOMENTUM SCALP: kierunek z Krakena, wejscie na rynku 5m.
async fn scan_s3(
    http: &reqwest::Client,
    state: &mut BotState,
    kraken: &mut KrakenTracker,
    assets: &[&str],
    now: u64,
) {
    if !S3_ENABLED {
        return;
    }
    // 1. tickery Krakena rownolegle
    let tickers = kraken_tickers(http, assets).await;
    // 2. wybierz aktywa z sygnalem momentum
    let mut jobs: Vec<(String, u64, bool, f64, f64)> = Vec::new();
    for (asset, last, vol) in &tickers {
        kraken.push(asset, *last, *vol, now);
        let Some(prev) = kraken.value_lookback(asset, KRAKEN_LOOKBACK_SEC, now) else {
            continue;
        };
        if prev <= 0.0 {
            continue;
        }
        let move_pct = (*last - prev) / prev;
        if move_pct.abs() < S3_KRAKEN_MOVE_THRESHOLD {
            continue;
        }
        let vol_ratio = kraken.vol_ratio(asset, now).unwrap_or(1.0);
        if vol_ratio < S3_KRAKEN_VOLUME_RATIO {
            continue;
        }
        let want_up = move_pct > 0.0;
        let slug = make_slug(asset, 5, now);
        let exp = slug_expiry_secs(&slug).unwrap_or(0);
        if exp == 0 || exp.saturating_sub(now) < MIN_SEC_TO_EXPIRY {
            continue;
        }
        if state.traded_slugs.contains_key(&slug) {
            continue;
        }
        jobs.push((slug, exp, want_up, move_pct, vol_ratio));
    }
    if jobs.is_empty() {
        return;
    }
    let slugs: Vec<String> = jobs.iter().map(|(s, _, _, _, _)| s.clone()).collect();
    let markets = fetch_markets_by_slugs(http, &slugs).await;
    // 3. zbierz tokeny zgodne z kierunkiem
    let mut token_ids: Vec<String> = Vec::new();
    let mut cand: Vec<(String, u64, f64, f64, TokenInfo)> = Vec::new();
    for (slug, exp, want_up, move_pct, vol_ratio) in &jobs {
        let Some(market) = markets.get(slug) else {
            continue;
        };
        let vol_market = market_volume(market);
        if vol_market < S3_MIN_VOLUME {
            continue;
        }
        let tokens = parse_gamma_market(market);
        if tokens.len() < 2 {
            continue;
        }
        for t in tokens {
            let is_up = t.outcome.to_lowercase().contains("up");
            if is_up == *want_up {
                token_ids.push(t.token_id.clone());
                cand.push((slug.clone(), *exp, *move_pct, *vol_ratio, t));
                break;
            }
        }
    }
    if token_ids.is_empty() {
        return;
    }
    let prices = get_prices_batch(http, &token_ids).await;
    for (slug, exp, move_pct, vol_ratio, t) in cand {
        let stake = stake_allowed(state);
        if stake < STAKE_USD_MIN {
            return;
        }
        let (ask, bid) = match prices.get(&t.token_id) {
            Some(&(a, b)) if a > 0.0 && b > 0.0 => (a, b),
            _ => continue,
        };
        if (ask - bid) > max_spread_cents() + 1e-9 {
            continue;
        }
        let key = format!("{}_{}", slug, t.outcome);
        println!(
            "S3 MOMENTUM 5m  {}  kraken_move={:+.3}%  vol_ratio={:.2}  @ {:.4}  | {}",
            slug,
            move_pct * 100.0,
            vol_ratio,
            ask,
            t.outcome
        );
        open_position(
            state, &key, &t.token_id, &slug, ask, stake, "S3", S3_TP, S3_SL, exp, "crypto", now,
        )
        .await;
    }
}

/// S2 - MEAN REVERSION: rynki wysokiego wolumenu (polityka/sport/inne).
async fn scan_s2(
    http: &reqwest::Client,
    state: &mut BotState,
    tracker: &mut PriceTracker,
    now: u64,
) {
    if !S2_ENABLED {
        return;
    }
    let markets = fetch_top_markets(http, 40).await;
    // 1. zbierz tokeny kandydatow
    let mut token_ids: Vec<String> = Vec::new();
    let mut cand: Vec<(String, TokenInfo)> = Vec::new();
    for market in &markets {
        let slug = market_slug(market);
        if slug.is_empty() || slug.contains("-updown-") {
            continue;
        }
        let vol = market_volume(market);
        if vol < MIN_MARKET_VOLUME {
            continue;
        }
        if state.traded_slugs.contains_key(&slug) {
            continue;
        }
        let tokens = parse_gamma_market(market);
        if tokens.len() < 2 {
            continue;
        }
        for t in tokens {
            token_ids.push(t.token_id.clone());
            cand.push((slug.clone(), t));
        }
    }
    if token_ids.is_empty() {
        return;
    }
    // 2. ceny batch (zamiast setek pojedynczych zapytan)
    let prices = get_prices_batch(http, &token_ids).await;
    let mut opened: std::collections::HashSet<String> = std::collections::HashSet::new();
    for (slug, t) in cand {
        if opened.contains(&slug) {
            continue;
        }
        let stake = stake_allowed(state);
        if stake < STAKE_USD_MIN {
            return;
        }
        let (ask, bid) = match prices.get(&t.token_id) {
            Some(&(a, b)) if a > 0.0 && b > 0.0 => (a, b),
            _ => continue,
        };
        if (ask - bid) > max_spread_cents() + 1e-9 {
            continue;
        }
        tracker.push(&t.token_id, ask, now);
        if ask < S2_MIN_PRICE || ask > S2_MAX_PRICE {
            continue;
        }
        let hi = tracker.high(&t.token_id, 600, now).unwrap_or(ask);
        let drop = if hi > 0.0 { (hi - ask) / hi } else { 0.0 };
        // Bramka kosztowa: sygnal musi pokryc spread (round-trip) + fee + margines.
        let cost_frac = (ask - bid) / ask + 2.0 * PAPER_FEE_PCT;
        if drop >= S2_DROP_THRESHOLD.max(cost_frac + 0.03) {
            let key = format!("{}_{}", slug, t.outcome);
            println!(
                "S2 MEAN REV  {}  @ {:.4}  drop={:.1}%  hi={:.4}  | {}",
                slug,
                ask,
                drop * 100.0,
                hi,
                t.outcome
            );
            open_position(
                state, &key, &t.token_id, &slug, ask, stake, "S2", S2_TP, S2_SL, 0, "other",
                now,
            )
            .await;
            opened.insert(slug);
        }
    }
}

// =============================================================================
//  FILTR SPORTOW (DROP40): wykluczamy sporty o udowodnionej stracie.
//  NFL, ATP (tenis), ITF (tenis), F1, Dota2 (esport) + wszystko nierozpoznane
//  ("OTHER"). Zostaja tylko sporty z dodatnim PF w backtescie drop40.
// =============================================================================
const EXCLUDED_SPORT_PREFIXES: [&str; 5] = ["nfl", "atp", "itf", "f1", "dota2"];
const KNOWN_SPORT_PREFIXES: &[&str] = &[
    // US
    "cfb", "mlb", "nba", "wnba", "nhl", "ufc", "box", "cfl", "pga",
    // tenis (tylko WTA; ATP/ITF wykluczone)
    "wta",
    // esport (bez Dota2)
    "cs2", "csgo", "lol", "val", "blast",
    // pilka nozna
    "spl", "epl", "efa", "elc", "sea", "por", "nor", "nor1", "arg", "arg1", "uel", "ucl",
    "mls", "lal", "es2", "ser", "itsb", "it1", "bun", "bund", "bl2", "lig", "lfl", "fl1",
    "ere", "rus", "jpn", "kor", "bra", "bra1", "mex", "mex1", "tur", "sco", "esp", "ita",
    "ger", "fra", "eng", "swd", "den", "pol", "rou", "rou1", "aut", "sui", "bel", "gre",
    "chn", "aus", "col", "chi", "chi1", "per", "per1", "uru", "ecu", "crc", "egy1", "ukr1",
    // inne
    "kbo", "npb", "cpbl", "liiga", "cycling", "modus", "pdcdarts", "rutopft", "ruurc",
    "crint", "cricwcl", "criccsat20w",
];

fn sport_allowed(slug: &str) -> bool {
    let s = slug.to_lowercase();
    let parts: Vec<&str> = s.split('-').collect();
    let first = parts.first().copied().unwrap_or("");
    let second = parts.get(1).copied().unwrap_or("");
    if EXCLUDED_SPORT_PREFIXES.contains(&first) || EXCLUDED_SPORT_PREFIXES.contains(&second) {
        return false;
    }
    if KNOWN_SPORT_PREFIXES.contains(&first) || KNOWN_SPORT_PREFIXES.contains(&second) {
        return true;
    }
    // koszykowka: prefiksy "bk..." (bkaba, bknbl, bkseriea, ...)
    if first.starts_with("bk") && first.len() >= 4 {
        return true;
    }
    // pilka nozna generycznie
    if s.contains("soccer") || s.contains("united") || s.contains("city") {
        return true;
    }
    false // nierozpoznane -> "OTHER" -> wykluczone
}

/// SPT - LIVE SPORTY: mean reversion (spadek z maksimum) na rynkach na zywo.
async fn scan_sports(
    http: &reqwest::Client,
    state: &mut BotState,
    tracker: &mut PriceTracker,
    now: u64,
) -> usize {
    if !SPORTS_ENABLED {
        return 0;
    }
    let markets = fetch_live_sports_markets(http, now).await;
    if markets.is_empty() {
        return 0;
    }
    let live_count = markets.len();
    let mut all_tokens: Vec<String> = Vec::new();
    let mut parsed: Vec<(String, Vec<TokenInfo>)> = Vec::new();
    for market in &markets {
        let slug = market_slug(market);
        if slug.is_empty() {
            continue;
        }
        // Filtr plynnosci: pomijamy martwe rynki (maly wolumen => szeroki spread => -EV).
        // DROP40: zostawiamy tylko ZYSKOWNE buckety wolumenu (250-20k$); 20k+ byl strata.
        let vol = market_volume(market);
        if vol < sports_min_volume() || vol > sports_max_volume() {
            continue;
        }
        // Filtr sportu: wykluczamy NFL, ATP, ITF, F1, Dota2 oraz nierozpoznane (OTHER).
        if !sport_allowed(&slug) {
            continue;
        }
        // Filtr typu rynku: exact-score byl nie-zyskowny.
        if slug.contains("exact-score") {
            continue;
        }
        // MONEYLINE zablokowany: w statystykach live PF ~1.06 (na granicy zysku).
        if is_moneyline(market) {
            continue;
        }
        let tokens = parse_gamma_market(market);
        for t in &tokens {
            all_tokens.push(t.token_id.clone());
        }
        parsed.push((slug, tokens));
    }
    let prices = get_prices_batch(http, &all_tokens).await;

    for (slug, tokens) in &parsed {
        if state.traded_slugs.contains_key(slug) {
            continue;
        }
        let stake = stake_allowed(state);
        if stake < STAKE_USD_MIN {
            return live_count;
        }
        for t in tokens {
            let (ask, bid) = match prices.get(&t.token_id) {
                Some(&(a, b)) if a > 0.0 && b > 0.0 => (a, b),
                _ => continue,
            };
            if (ask - bid) > max_spread_cents() + 1e-9 {
                continue;
            }
            tracker.push(&t.token_id, ask, now);
            if ask < SPORTS_MIN_PRICE || ask > SPORTS_MAX_PRICE {
                continue;
            }
            let hi = tracker.high(&t.token_id, 300, now).unwrap_or(ask);
            let drop = if hi > 0.0 { (hi - ask) / hi } else { 0.0 };
            if drop >= sports_drop_threshold() {
                let key = format!("{}_{}", slug, t.outcome);
                println!(
                    "SPORTS LIVE  {}  @ {:.4}  drop={:.1}%  hi={:.4}  | {}",
                    slug,
                    ask,
                    drop * 100.0,
                    hi,
                    t.outcome
                );
                open_position(
                    state,
                    &key,
                    &t.token_id,
                    slug,
                    ask,
                    stake,
                    "SPT",
                    SPORTS_TP,
                    SPORTS_SL,
                    0,
                    "sports",
                    now,
                )
                .await;
                break;
            }
        }
    }
    live_count
}

// =============================================================================
//  KATEGORIE (DROP40) - zyskowna dywersyfikacja poza sportami live
// -----------------------------------------------------------------------------
//  Backtest (11384 transakcji, spread mierzony) - Profit Factor wg kategorii:
//    Finals 15.95 (n=2821) | Tech 13.94 (633) | Esports 13.84 (2140)
//    Politics 11.39 (969) | Weather 6.71 (1730) | Culture 5.92 (1592)
//  Te same parametry DROP40 co SPT (sporty live):
//    wejscie: spadek >=40% od maksimum z okna 300 s
//    wyjscie: TP +30%, SL -90%, time-exit 7200 s
//    filtry:  spread <= 3c, wolumen 250-20000$, cena 0.15-0.90
//  WYKLUCZAMY sporty live (gameStartTime niepuste) - te obsluguje scan_sports.
//  Nadpisz bez przebudowy: CATEGORIES_ENABLED=0 | CAT_DROP=0.30 | CAT_REFRESH_SEC=120
// =============================================================================
const CAT_DROP_THRESHOLD: f64 = 0.40;
const CAT_TP: f64 = 0.30;
const CAT_SL: f64 = 0.90;
const CAT_LOOKBACK_SEC: u64 = 21600; // okno 6h (bylo 300 s)
// FILTR WOLUMENU USUNIETY (0 = bez filtra). Backtest 48h / ~2000 rynkow Finance pokazal,
// ze cienkie rynki maja WYZSZA skutecznosc (wolumen 100-500$ -> ~84% vs >=2k$ -> ~64%),
// wiec stary prog 100$ wycinal najlepsze rynki. Zamiast wolumenu filtrujemy REALNA ksiazke:
// spread <= MAX_SPREAD_CENTS ORAZ bid <= ask (twardy guard w scan_finance4).
// Nadpisz: CAT_MIN_VOLUME=100 (przywraca stary prog)
const CAT_MIN_VOLUME: f64 = 0.0;
const CAT_MAX_VOLUME: f64 = 1.0e12; // bez gornego limitu
const CAT_MIN_PRICE: f64 = 0.15;
const CAT_MAX_PRICE: f64 = 0.90;

// (nazwa kategorii, tag_id Gamma) - TYLKO FINANCE (tag 120).
// Bot gra wylacznie 4 strategiami na Finance; inne kategorie wylaczone.
const CATEGORY_TAGS: [(&str, &str); 1] = [("Finance", "120")];

fn categories_enabled() -> bool {
    std::env::var("CATEGORIES_ENABLED")
        .map(|v| !(v == "0" || v.eq_ignore_ascii_case("false")))
        .unwrap_or(true)
}

fn cat_drop_threshold() -> f64 {
    std::env::var("CAT_DROP")
        .ok()
        .and_then(|v| v.trim().parse::<f64>().ok())
        .filter(|&v| v > 0.0 && v < 1.0)
        .unwrap_or(CAT_DROP_THRESHOLD)
}

fn cat_refresh_sec() -> u64 {
    std::env::var("CAT_REFRESH_SEC")
        .ok()
        .and_then(|v| v.trim().parse::<u64>().ok())
        .filter(|&n| n > 0)
        .unwrap_or(90)
}

// Ile STRON rynkow pobierac z Gamma API (100 rynkow/strona) dla kategorii CAT.
// Domyslnie 25 -> do 2500 rynkow (wszystkie Finance, ~2100 dostepnych).
// UWAGA: wczesniej bylo 3 strony = TYLKO 300 rynkow (top po wolumenie), co pomijalo
// ~99% transakcji (backtest: z 432 transakcji tylko 4 pochodzily z top-300 rynkow!).
// Nadpisz bez przebudowy: CAT_MAX_PAGES=10 (mniejszy skan / szybsza petla)
fn cat_max_pages() -> usize {
    std::env::var("CAT_MAX_PAGES")
        .ok()
        .and_then(|v| v.trim().parse::<usize>().ok())
        .filter(|&n| n > 0)
        .unwrap_or(25)
}

// Minimalny wolumen rynku dla kategorii CAT. Domyslnie 100$.
// Nadpisz bez przebudowy: CAT_MIN_VOLUME=250
fn cat_min_volume() -> f64 {
    std::env::var("CAT_MIN_VOLUME")
        .ok()
        .and_then(|v| v.trim().parse::<f64>().ok())
        .filter(|&v| v >= 0.0)
        .unwrap_or(CAT_MIN_VOLUME)
}

// Per-kategoria prog wolumenu. Esports i Politics zostaja na 250$ (wyzsza jakosc),
// reszta na domyslnym CAT_MIN_VOLUME (100$). Nadpisz globalnie: CAT_MIN_VOLUME=250
fn cat_min_volume_for(cat: &str) -> f64 {
    match cat {
        "Esports" | "Politics" => 250.0,
        _ => cat_min_volume(),
    }
}

static CAT_CACHE: std::sync::Mutex<Option<(u64, Vec<(String, Value)>)>> = std::sync::Mutex::new(None);

// Czy rynek jest sportem LIVE? (gameStartTime niepuste) -> wtedy NIE dotykamy go
// w scan_categories (obsluguje go scan_sports z wlasnymi filtrami sportowymi).
fn is_sports_live(market: &Value) -> bool {
    match market.get("gameStartTime") {
        Some(Value::String(s)) => !s.is_empty() && s.as_str() != "null",
        _ => false,
    }
}

// Czy to rynek MONEYLINE? (pole Gamma sportsMarketType zawiera "moneyline").
// Zablokowane: w statystykach live PF ~1.06 (na granicy zysku).
fn is_moneyline(market: &Value) -> bool {
    market
        .get("sportsMarketType")
        .and_then(|v| v.as_str())
        .map(|s| s.to_lowercase().contains("moneyline"))
        .unwrap_or(false)
}

// Pobiera rynki dla danego tag_id (Gamma /markets) z paginacja. Zwraca surowe Value.
async fn fetch_markets_by_tag(http: &reqwest::Client, tag_id: &str) -> Vec<Value> {
    let mut out = Vec::new();
    let max_pages = cat_max_pages() as u64;
    for page in 0..max_pages {
        let offset = page * 100;
        let url = format!(
            "{}/markets?closed=false&active=true&limit=100&offset={}&tag_id={}&order=volumeNum&ascending=false",
            GAMMA_API, offset, tag_id
        );
        let resp = match http.get(&url).timeout(Duration::from_secs(25)).send().await {
            Ok(r) => r,
            Err(_) => break,
        };
        if !resp.status().is_success() {
            break;
        }
        let v: Value = match resp.json().await {
            Ok(v) => v,
            Err(_) => break,
        };
        let arr = match v.as_array() {
            Some(a) => a.clone(),
            None => break,
        };
        let n = arr.len();
        out.extend(arr);
        if n < 100 {
            break;
        }
    }
    out
}

// Zbiera rynki z 6 zyskownych kategorii (dedup po slug), z cache zeby nie katowac API.
// Zwraca (nazwa_kategorii, market) - potrzebne do per-kategoria progu wolumenu.
async fn fetch_category_markets(http: &reqwest::Client, now: u64) -> Vec<(String, Value)> {
    if let Ok(g) = CAT_CACHE.lock() {
        if let Some((ts, ref v)) = *g {
            if !v.is_empty() && now.saturating_sub(ts) < cat_refresh_sec() {
                return v.clone();
            }
        }
    }
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut out: Vec<(String, Value)> = Vec::new();
    for (name, tag) in CATEGORY_TAGS.iter() {
        for m in fetch_markets_by_tag(http, *tag).await {
            let slug = market_slug(&m);
            if slug.is_empty() || seen.contains(&slug) {
                continue;
            }
            let book = m
                .get("enableOrderBook")
                .and_then(|b| b.as_bool())
                .unwrap_or(false);
            let accepting = m
                .get("acceptingOrders")
                .and_then(|b| b.as_bool())
                .unwrap_or(false);
            let closed = m.get("closed").and_then(|b| b.as_bool()).unwrap_or(false);
            let archived = m
                .get("archived")
                .and_then(|b| b.as_bool())
                .unwrap_or(false);
            if !(book && accepting && !closed && !archived) {
                continue;
            }
            // NIE dotykamy sportow live (maja gameStartTime) - to domena scan_sports.
            if is_sports_live(&m) {
                continue;
            }
            seen.insert(slug);
            out.push((name.to_string(), m));
        }
    }
    out.sort_by(|a, b| {
        market_volume(&b.1)
            .partial_cmp(&market_volume(&a.1))
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    if !out.is_empty() {
        if let Ok(mut g) = CAT_CACHE.lock() {
            *g = Some((now, out.clone()));
        }
    }
    out
}

// KAT - skanuje 6 zyskownych kategorii (DROP40). Zwraca liczbe rozwazanych rynkow.
// ===========================================================================
//  FINANCE-4  --  4 strategie mean-reversion TYLKO na rynkach FINANCE (tag 120).
//  Zasady:
//   * 2 strategie (okno 6h, spread <= 0.03$, SL -90%, time-exit 2h):
//                  A40_40 (-40%/TP+40%), C30_30 (-30%/TP+30%)
//   * NIE dubluja sie: jeden rynek wchodzi tylko raz (dedup po slug w traded_slugs).
//     Kolejnosc priorytetu: A (-40%) PRZED B (-20%), bo kazdy spadek -40% jest tez
//     spadkiem -20% -> A ma pierwszenstwo na duzych spadkach. W obrebie grupy
//     pierwsza jest wersja o wyzszej oczekiwanej wartosci (TP+40% dla A, TP+30% dla B).
//   * Kazda strategia max 10 otwartych pozycji (razem limit MAX_POSITIONS = 20).
//   * Wejscie: spadek >= prog od maksimum z okna 6h (21600 s); spread <= MAX_SPREAD_CENTS;
//     cena 0.15-0.90; BEZ filtra wolumenu (0$); ksiazka musi byc realna (bid <= ask).
//   * Wyjscie: TP (per strategia), SL -90%, time-exit 7200 s.
// ===========================================================================
#[derive(Clone, Copy)]
struct FinStrat {
    name: &'static str,
    drop: f64,
    tp: f64,
}
// Kolejnosc = priorytet: najglebszy spadek pierwszy (A -40% -> C -30%).
const FIN_STRATS: [FinStrat; 2] = [
    FinStrat { name: "A40_40", drop: 0.40, tp: 0.40 },
    FinStrat { name: "C30_30", drop: 0.30, tp: 0.30 },
];
const FIN_SL: f64 = 0.90;
const FIN_MAX_PER_STRATEGY: usize = 10;

// ===========================================================================
//  BOOTSTRAP HISTORII 6h: przy starcie (i dla nowych tokenow) wczytujemy ostatnie 6h
//  cen z CLOB prices-history (1 pkt/min), zeby okno 6h dzialalo OD RAZU, bez
//  czekania 6 godzin na zebranie danych. Wylacz: BOOT_HISTORY=0
// ===========================================================================
const BOOT_BATCH: usize = 400; // tokenow na jedno skanowanie (reszta w kolejnych petlach)
const BOOT_PARALLEL: usize = 25; // rownolegle zapytania

async fn fetch_hist_points(http: reqwest::Client, token: String, now: u64) -> Vec<(u64, f64)> {
    let urls = [
        format!(
            "{}/prices-history?market={}&startTs={}&endTs={}&fidelity=1",
            CLOB_API,
            token,
            now.saturating_sub(CAT_LOOKBACK_SEC),
            now
        ),
        format!(
            "{}/prices-history?market={}&interval=6h&fidelity=1",
            CLOB_API, token
        ),
    ];
    for url in urls.iter() {
        let resp = match http.get(url).timeout(Duration::from_secs(12)).send().await {
            Ok(r) => r,
            Err(_) => continue,
        };
        if !resp.status().is_success() {
            continue;
        }
        let v: Value = match resp.json().await {
            Ok(v) => v,
            Err(_) => continue,
        };
        let mut out: Vec<(u64, f64)> = Vec::new();
        if let Some(arr) = v.get("history").and_then(|h| h.as_array()) {
            for p in arr {
                let t = p.get("t").and_then(|x| x.as_u64());
                let pr = p.get("p").and_then(|x| x.as_f64());
                if let (Some(t), Some(pr)) = (t, pr) {
                    out.push((t, pr));
                }
            }
        }
        if !out.is_empty() {
            return out;
        }
    }
    Vec::new()
}

async fn bootstrap_history(
    http: &reqwest::Client,
    tracker: &mut PriceTracker,
    prices: &HashMap<String, (f64, f64)>,
    now: u64,
) {
    if std::env::var("BOOT_HISTORY").map(|v| v == "0").unwrap_or(false) {
        return;
    }
    let mut todo: Vec<(String, f64)> = Vec::new();
    for (tok, &(ask, bid)) in prices.iter() {
        if tracker.boot.contains(tok) {
            continue;
        }
        if !(ask > 0.0 && bid > 0.0 && bid <= ask) {
            continue;
        }
        if (ask - bid) > max_spread_cents() + 1e-9 {
            continue;
        }
        if ask < CAT_MIN_PRICE || ask > CAT_MAX_PRICE {
            continue;
        }
        todo.push((tok.clone(), (ask - bid) / 2.0));
        if todo.len() >= BOOT_BATCH {
            break;
        }
    }
    if todo.is_empty() {
        return;
    }
    println!("[BOOT] wczytuje historie 6h z CLOB dla {} tokenow...", todo.len());
    let mut loaded = 0usize;
    for chunk in todo.chunks(BOOT_PARALLEL) {
        let mut handles = Vec::new();
        for (tok, half) in chunk.iter() {
            let h = http.clone();
            let t = tok.clone();
            let half = *half;
            handles.push(tokio::spawn(async move {
                let pts = fetch_hist_points(h, t.clone(), now).await;
                (t, half, pts)
            }));
        }
        for h in handles {
            if let Ok((t, half, pts)) = h.await {
                if !pts.is_empty() {
                    loaded += 1;
                }
                tracker.seed(&t, &pts, half);
            }
        }
    }
    println!("[BOOT] gotowe: {} z {} tokenow ma historie 6h", loaded, todo.len());
}

async fn scan_finance4(
    http: &reqwest::Client,
    state: &mut BotState,
    tracker: &mut PriceTracker,
    now: u64,
) -> usize {
    if !categories_enabled() {
        return 0;
    }
    let markets = fetch_category_markets(http, now).await;
    if markets.is_empty() {
        return 0;
    }
    let n_markets = markets.len();
    let mut all_tokens: Vec<String> = Vec::new();
    let mut parsed: Vec<(String, Vec<TokenInfo>)> = Vec::new();
    for (cat, market) in &markets {
        let slug = market_slug(market);
        if slug.is_empty() {
            continue;
        }
        let vol = market_volume(market);
        if vol < cat_min_volume_for(cat) || vol > CAT_MAX_VOLUME {
            continue;
        }
        if slug.contains("exact-score") {
            continue;
        }
        let tokens = parse_gamma_market(market);
        for t in &tokens {
            all_tokens.push(t.token_id.clone());
        }
        parsed.push((slug, tokens));
    }
    let prices = get_prices_batch(http, &all_tokens).await;
    bootstrap_history(http, tracker, &prices, now).await;
    let dbg = std::env::var("DEBUG_CAT").is_ok();
    if dbg {
        println!(
            "[FIN-DEBUG] markets={} parsed={} tokens={} prices={}",
            n_markets,
            parsed.len(),
            all_tokens.len(),
            prices.len()
        );
    }

    // Iterujemy strategie w kolejnosci priorytetu. Dedup: rynek raz wziety
    // (traded_slugs) jest pomijany przez WSZYSTKIE kolejne strategie -> zero dublowania.
    for cfg in FIN_STRATS.iter() {
        for (slug, tokens) in &parsed {
            if state.traded_slugs.contains_key(slug) {
                continue;
            }
            if strategy_count(state, cfg.name) >= FIN_MAX_PER_STRATEGY {
                break;
            }
            let stake = stake_allowed(state);
            if stake < STAKE_USD_MIN {
                return n_markets;
            }
            for t in tokens {
                let (ask, bid) = match prices.get(&t.token_id) {
                    Some(&(a, b)) if a > 0.0 && b > 0.0 => (a, b),
                    _ => continue,
                };
                // TWARDY GUARD: odrzucamy ksiazki skrzyzowane (bid > ask) i zerowe (bid == ask).
                // W cienkich rynkach to czesto martwe/stare kwotowania -> NIE da sie ich
                // zrealizowac, a backtest liczy je jako zysk. bid <= ask gwarantuje realny,
                // dwustronny rynek (mozna kupic po ask i sprzedac po bid).
                if !(bid <= ask) {
                    continue;
                }
                if (ask - bid) > max_spread_cents() + 1e-9 {
                    continue;
                }
                tracker.push(&t.token_id, ask, now);
                if ask < CAT_MIN_PRICE || ask > CAT_MAX_PRICE {
                    continue;
                }
                let hi = tracker.high(&t.token_id, CAT_LOOKBACK_SEC, now).unwrap_or(ask);
                let drop = if hi > 0.0 { (hi - ask) / hi } else { 0.0 };
                if drop >= cfg.drop {
                    let key = format!("{}_{}", slug, t.outcome);
                    println!(
                        "FIN {:<6} {}  @ {:.4}  drop={:.1}%  hi={:.4}  tp=+{:.0}%  | {}",
                        cfg.name,
                        slug,
                        ask,
                        drop * 100.0,
                        hi,
                        cfg.tp * 100.0,
                        t.outcome
                    );
                    open_position(
                        state,
                        &key,
                        &t.token_id,
                        slug,
                        ask,
                        stake,
                        cfg.name,
                        cfg.tp,
                        FIN_SL,
                        0,
                        "finance",
                        now,
                    )
                    .await;
                    break; // jedna pozycja na rynek na strategie
                }
            }
        }
    }
    n_markets
}

// =============================================================================
//  LIVE ORDER (SDK) - uzywane TYLKO gdy live()==true
// =============================================================================
#[cfg(feature = "live")]
async fn live_buy(token_id: &str, usd: f64) -> Result<()> {
    let pk = std::env::var(PRIVATE_KEY_VAR)
        .map_err(|_| anyhow!("brak POLYMARKET_PRIVATE_KEY w srodowisku"))?;
    let host = std::env::var("CLOB_API_URL").unwrap_or_else(|_| CLOB_HOST_DEFAULT.to_string());

    let signer = LocalSigner::from_str(&pk)?.with_chain_id(Some(POLYGON));

    // Auto-resolucja: (sig_type, funder) z klucza prywatnego (EOA -> Deposit Wallet).
    let (sig_num, funder) = auth_params().await;
    let sig_type = match sig_num {
        0 => SignatureType::Eoa,
        1 => SignatureType::Proxy,
        2 => SignatureType::GnosisSafe,
        _ => SignatureType::Poly1271,
    };

    let mut builder = Client::new(&host, Config::default())?
        .authentication_builder(&signer)
        .signature_type(sig_type);

    // Uwaga: dla sig_type=EOA NIE wolno podawac fundera (SDK to odrzuca).
    if sig_num != 0 {
        if let Some(f) = &funder {
            builder = builder.funder(Address::from_str(f.trim())?);
        }
    }

    let client = builder.authenticate().await?;
    let token = U256::from_str(token_id)?;
    let amount = Amount::usdc(Decimal::from_str(&format!("{:.2}", usd))?)?;

    // Odswiez cache salda/allowance po stronie CLOB (kolateral = pUSD). Bez tego CLOB
    // moze miec nieaktualne saldo i odrzucic zlecenie ("not enough balance").
    let _ = client
        .update_balance_allowance(
            BalanceAllowanceRequest::builder()
                .asset_type(AssetType::Collateral)
                .build(),
        )
        .await;

    let resp = client
        .market_order()
        .token_id(token)
        .side(Side::Buy)
        .amount(amount)
        .order_type(OrderType::FOK)
        .build_sign_and_post(&signer)
        .await?;

    println!(
        "[LIVE BUY] token={} order_id={} status={} success={}",
        token_id, resp.order_id, resp.status, resp.success
    );
    append_fill(
        now_secs(),
        "BUY",
        token_id,
        &format!("{:.2}", usd),
        &resp.order_id.to_string(),
        &resp.status.to_string(),
    );

    // Weryfikacja wypelnienia: NIE zapisujemy pozycji, jesli zlecenie nie zostalo
    // zrealizowane (inaczej powstaje "phantom" pozycja, ktorej nie da sie sprzedac).
    if !resp.success {
        return Err(anyhow!("BUY odrzucone (success=false): {:?}", resp.error_msg));
    }
    match resp.status {
        OrderStatusType::Matched | OrderStatusType::Live | OrderStatusType::Delayed => Ok(()),
        other => Err(anyhow!("BUY nie wypelnione (status={:?})", other)),
    }
}

/// Zaokraglenie W DOL do `decimals` miejsc po przecinku. Dla SELL to kluczowe:
/// NIGDY nie mozemy zawyzyc ilosci ponad realne saldo na portfelu.
#[allow(dead_code)]
fn floor_to(x: f64, decimals: u32) -> f64 {
    let f = 10f64.powi(decimals as i32);
    if f <= 0.0 || !x.is_finite() {
        return x;
    }
    (x * f).floor() / f
}

/// Wyciaga REALNE saldo (w shares) z komunikatu bledu CLOB, np.:
///   "not enough balance / allowance: the balance is not enough -> balance: 1538462, order amount: 1560000"
/// Wartosci sa w jednostkach 1e-6 (6 miejsc po przecinku) -> dzielimy przez 1e6.
#[allow(dead_code)]
fn parse_balance_from_err(s: &str) -> Option<f64> {
    let mut found: Option<f64> = None;
    let mut rest = s;
    while let Some(idx) = rest.find("balance:") {
        let after = &rest[idx + "balance:".len()..];
        let num: String = after
            .trim_start()
            .chars()
            .take_while(|c| c.is_ascii_digit())
            .collect();
        if !num.is_empty() {
            if let Ok(raw) = num.parse::<f64>() {
                found = Some(raw / 1_000_000.0);
            }
        }
        rest = &rest[idx + "balance:".len()..];
    }
    found
}

/// SPRZEDAZ przez SDK. UWAGA: dla SELL `amount` MUSI byc w SHARES
/// (nie w USDC) i miec <= 2 miejsca po przecinku (LOT_SIZE_SCALE).
///
/// NAPRAWA "not enough balance / allowance": zapisana liczba shares (stake/cena
/// z momentu DECYZJI) bywa minimalnie wieksza od faktycznie kupionych shares
/// (realne wypelnienie wypada po innej cenie). Wtedy CLOB odrzuca SELL, pozycja
/// nigdy sie nie zamyka i blokuje limit. Dlatego:
///   1) zaokraglamy ilosc W DOL (nie w gore!),
///   2) jesli CLOB zwroci realne saldo w bledzie -> sprzedajemy DOKLADNIE tyle,
///      ile portfel faktycznie trzyma (z ponowieniem).
#[cfg(feature = "live")]
async fn live_sell(token_id: &str, shares: f64) -> Result<()> {
    let pk = std::env::var(PRIVATE_KEY_VAR)
        .map_err(|_| anyhow!("brak POLYMARKET_PRIVATE_KEY w srodowisku"))?;
    let host = std::env::var("CLOB_API_URL").unwrap_or_else(|_| CLOB_HOST_DEFAULT.to_string());

    let signer = LocalSigner::from_str(&pk)?.with_chain_id(Some(POLYGON));

    // Auto-resolucja: (sig_type, funder) z klucza prywatnego (EOA -> Deposit Wallet).
    let (sig_num, funder) = auth_params().await;
    let sig_type = match sig_num {
        0 => SignatureType::Eoa,
        1 => SignatureType::Proxy,
        2 => SignatureType::GnosisSafe,
        _ => SignatureType::Poly1271,
    };

    let mut builder = Client::new(&host, Config::default())?
        .authentication_builder(&signer)
        .signature_type(sig_type);

    // Uwaga: dla sig_type=EOA NIE wolno podawac fundera (SDK to odrzuca).
    if sig_num != 0 {
        if let Some(f) = &funder {
            builder = builder.funder(Address::from_str(f.trim())?);
        }
    }

    let client = builder.authenticate().await?;
    let token = U256::from_str(token_id)?;

    // Start: zapisana liczba shares ZAOKRAGLONA W DOL do 2 miejsc.
    // (Wczesniej {:.2} ZAOKRAGLALO w gore, np. 1.538462 -> "1.54" > realne saldo.)
    let mut attempt = floor_to(shares, 2);
    let mut last_err: Option<anyhow::Error> = None;

    for _try in 0..5 {
        if attempt < 0.01 {
            break;
        }
        let amt = format!("{:.2}", attempt);
        let amount = Amount::shares(Decimal::from_str(&amt)?)?;

        // Odswiez cache salda/allowance dla KONDYCJONALNEGO tokenu (outcome). Jesli pozycja
        // zostala juz rozliczona/auto-redeemowana, CLOB zwroci balance=0.
        let _ = client
            .update_balance_allowance(
                BalanceAllowanceRequest::builder()
                    .asset_type(AssetType::Conditional)
                    .token_id(token)
                    .build(),
            )
            .await;

        let res = client
            .market_order()
            .token_id(token)
            .side(Side::Sell)
            .amount(amount)
            .order_type(OrderType::FOK)
            .build_sign_and_post(&signer)
            .await;

        match res {
            Ok(resp) => {
                println!(
                    "[LIVE SELL] token={} shares={} order_id={} status={} success={}",
                    token_id, amt, resp.order_id, resp.status, resp.success
                );
                append_fill(
                    now_secs(),
                    "SELL",
                    token_id,
                    &amt,
                    &resp.order_id.to_string(),
                    &resp.status.to_string(),
                );
                if !resp.success {
                    let msg = format!("{:?}", resp.error_msg);
                    if let Some(bal) = parse_balance_from_err(&msg) {
                        let corrected = floor_to(bal, 2);
                        if corrected >= 0.01 && corrected < attempt {
                            println!(
                                "[LIVE SELL] korekta ilosci {} -> {} (realne saldo {:.6} shares)",
                                amt, corrected, bal
                            );
                            attempt = corrected;
                            last_err = Some(anyhow!("SELL odrzucone (success=false): {}", msg));
                            continue;
                        }
                    }
                    return Err(anyhow!("SELL odrzucone (success=false): {:?}", resp.error_msg));
                }
                return match resp.status {
                    OrderStatusType::Matched | OrderStatusType::Live | OrderStatusType::Delayed => {
                        Ok(())
                    }
                    other => Err(anyhow!("SELL nie wypelnione (status={:?})", other)),
                };
            }
            Err(e) => {
                let es = e.to_string();
                if let Some(bal) = parse_balance_from_err(&es) {
                    let corrected = floor_to(bal, 2);
                    if corrected >= 0.01 && corrected < attempt {
                        println!(
                            "[LIVE SELL] korekta ilosci {} -> {} (realne saldo {:.6} shares)",
                            amt, corrected, bal
                        );
                        attempt = corrected;
                        last_err = Some(anyhow!("{}", es));
                        continue;
                    }
                }
                // `e` jest typu SDK (polymarket_client_sdk_v2::error::Error), a funkcja
                // zwraca anyhow::Result -> trzeba jawnie skonwertowac (return Err NIE
                // robi automatycznej konwersji tak jak operator `?`).
                return Err(e.into());
            }
        }
    }

    Err(last_err.unwrap_or_else(|| anyhow!("SELL: nie udalo sie dobrac ilosci shares")))
}

// Stub gdy SDK nie jest wkompilowane (build DRY RUN bez feature "live").
#[cfg(not(feature = "live"))]
async fn live_buy(_token_id: &str, _usd: f64) -> Result<()> {
    Err(anyhow!(
        "ten build nie ma wkompilowanego SDK (feature \"live\"). \
         Przebuduj: cargo build --release --features live"
    ))
}

#[cfg(not(feature = "live"))]
async fn live_sell(_token_id: &str, _shares: f64) -> Result<()> {
    Err(anyhow!(
        "ten build nie ma wkompilowanego SDK (feature \"live\"). \
         Przebuduj: cargo build --release --features live"
    ))
}

// =============================================================================
//  MAIN
// =============================================================================
/// Buduje klienta HTTP z WBUDOWANYMI korzeniami TLS (webpki-roots).
/// Na Termux/Android domyslny mechanizm reqwest ("rustls-platform-verifier")
/// panikuje ("Expect rustls-platform-verifier to be initialized"), bo wymaga
/// kontekstu aplikacji Android. Podajemy wlasny rustls::ClientConfig, ktory
/// korzysta z wbudowanych certyfikatow - dziala wszedzie, takze na telefonie.
fn build_http_client() -> Result<reqwest::Client> {
    let mut roots = rustls::RootCertStore::empty();
    roots.extend(webpki_roots::TLS_SERVER_ROOTS.iter().cloned());

    let provider = std::sync::Arc::new(rustls::crypto::ring::default_provider());
    let mut tls = rustls::ClientConfig::builder_with_provider(provider)
        .with_safe_default_protocol_versions()?
        .with_root_certificates(roots)
        .with_no_client_auth();
    tls.alpn_protocols = vec![b"h2".to_vec(), b"http/1.1".to_vec()];

    let client = reqwest::Client::builder()
        .user_agent("pm-rust/1.0")
        .timeout(Duration::from_secs(15))
        .use_preconfigured_tls(tls)
        .build()?;
    Ok(client)
}

#[tokio::main]
async fn main() -> Result<()> {
    // Provider kryptograficzny rustls (ring).
    let _ = rustls::crypto::ring::default_provider().install_default();

    let http = build_http_client()?;

    // Tryb diagnostyczny: `pm-rust --doctor` -> EOA + resolver + wybrany portfel.
    if std::env::args().any(|a| a == "--doctor") {
        println!("=== DIAGNOSTYKA PORTFELA (auto-resolve fundera) ===");
        #[cfg(feature = "live")]
        {
            match eoa_from_key() {
                Some(eoa) => {
                    println!("EOA (z klucza)   : {}", eoa);
                    match build_http_client() {
                        Ok(c) => {
                            let url = format!("{}/{}", WALLET_RESOLVER_BASE, eoa);
                            println!("resolver         : {}", url);
                            match c.get(&url).send().await {
                                Ok(r) => {
                                    let st = r.status();
                                    match r.text().await {
                                        Ok(t) => println!("resolver HTTP {} : {}", st, t),
                                        Err(e) => println!("resolver: blad tresci: {}", e),
                                    }
                                }
                                Err(e) => println!("resolver: blad polaczenia: {}", e),
                            }
                        }
                        Err(e) => println!("nie moge zbudowac klienta HTTP: {}", e),
                    }
                    let (sig, funder) = auth_params().await;
                    println!("WYBRANE sig_type : {}", sig);
                    println!(
                        "WYBRANY funder   : {}",
                        funder.unwrap_or_else(|| "(brak / EOA)".into())
                    );
                }
                None => println!("BLAD: nie moge wyliczyc EOA z POLYMARKET_PRIVATE_KEY"),
            }
        }
        #[cfg(not(feature = "live"))]
        println!("(build bez feature 'live' - diagnostyka EOA niedostepna)");
        return Ok(());
    }

    // Tryb diagnostyczny: `pm-rust --balance` -> tylko odczyt portfela i wyjscie.
    if std::env::args().any(|a| a == "--balance") {
        println!("=== ODCZYT PORTFELA POLYMARKET ===");
        let eff = effective_funder().await;
        match &eff {
            Some(f) => {
                let src = if std::env::var("POLYMARKET_FUNDER")
                    .ok()
                    .map(|v| !v.trim().is_empty())
                    .unwrap_or(false)
                {
                    "env/DEFAULT (lub auto-resolve)"
                } else {
                    "DOMYSLNY (DEFAULT_FUNDER)"
                };
                println!("funder ({}) : {}", src, f);
            }
            None => println!("funder : BRAK - ustaw POLYMARKET_FUNDER=0x..."),
        }
        let (pusd, usdc) = match eff {
            Some(f) => (
                erc20_balance(&http, PUSD_ADDRESS, &f, true).await,
                erc20_balance(&http, USDC_E_ADDRESS, &f, true).await,
            ),
            None => (None, None),
        };
        match pusd {
            Some(v) => println!("pUSD   (V2 collateral)     : {:.6} $", v),
            None => println!("pUSD   (V2 collateral)     : blad odczytu"),
        }
        match usdc {
            Some(v) => println!("USDC.e (starszy collateral): {:.6} $", v),
            None => println!("USDC.e (starszy collateral): blad odczytu"),
        }
        println!("RAZEM                      : {:.6} $", pusd.unwrap_or(0.0) + usdc.unwrap_or(0.0));
        return Ok(());
    }

    // Budzet: w LIVE czytamy prawdziwe saldo portfela on-chain (pUSD/USDC.e),
    // chyba ze uzytkownik recznie ustawil LIVE_BUDGET.
    let onchain = if live() { fetch_onchain_budget(&http).await } else { None };
    let budget = if live() {
        resolve_live_budget(&http).await
    } else {
        starting_budget()
    };
    let mut state = load_state(budget);

    // LIVE: najpierw RECONCILIACJA (usun pozycje, ktore sie juz rozliczyly), potem
    // synchronizacja gotowki z prawdziwego salda on-chain (pUSD/USDC.e).
    if live() {
        reconcile_positions(&http, &mut state, now_secs()).await;
        if let Some(b) = onchain {
            if b > 0.0 {
                state.available_budget = b;
            }
        }
        // Kapital poczatkowy (do liczenia zysku ORAZ kotwica dynamicznego stakingu/limitu).
        // Nadpisz: START_BUDGET=20.9. Jawnie ustawiony START_BUDGET ZAWSZE wygrywa
        // (nawet gdy stary positions.json ma zapisane inne initial_budget).
        let env_start = std::env::var("START_BUDGET")
            .ok()
            .and_then(|v| v.trim().parse::<f64>().ok())
            .filter(|b| *b > 0.0);
        if let Some(b) = env_start {
            state.initial_budget = b;
        } else if state.initial_budget <= 0.0 {
            state.initial_budget = DEFAULT_LIVE_BUDGET;
        }
        state.budget = state.initial_budget;
    }

    println!("===================================================================");
    println!("  pm-rust  --  POLYMARKET BOT");
    println!(
        "  TRYB: {}",
        if live() {
            "*** LIVE (PRAWDZIWE PIENIADZE) ***"
        } else {
            "DRY RUN (paper trading)"
        }
    );
    println!("  budget start : {:.2} $", state.budget);
    println!("  cash         : {:.2} $", state.available_budget);
    println!(
        "  equity       : {:.2} $   profit: {:+.2} $",
        state.equity(),
        state.profit()
    );
    println!("  open pos.    : {}", state.positions.len());
    if live() {
        let f = effective_funder()
            .await
            .unwrap_or_else(|| "(brak - ustaw POLYMARKET_FUNDER)".to_string());
        println!("  funder       : {}  [auto-resolve/env]", f);
    }
    println!(
        "  pliki        : {} | {} | {}",
        TRADES_FILE,
        STATS_FILE,
        state_file()
    );
    println!("  strategie    : S5(5m rebound) S6(15m rebound) S7(1h rebound) S8(4h rebound) S9(1d rebound) S4(15m vol) S3(momentum) S2(mean rev) SPT(live) CAT(6 kategorii DROP40)");
    println!("===================================================================");

    let mut tracker = PriceTracker::default();
    let mut kraken = KrakenTracker::default();
    let mut cursor: usize = 0;
    let mut last_kraken = 0u64;
    let mut last_stats = 0u64;
    let mut last_prune = 0u64;
    let mut last_heartbeat = 0u64;
    let mut last_reconcile = 0u64;
    let mut last_cash_sync = 0u64;

    loop {
        let now = now_secs();

        if kill_switch(&state) {
            println!(
                "[KILL SWITCH] equity spadla o >= {:.0}% od budzetu - wstrzymuje nowe wejscia.",
                KILL_SWITCH_DROP_PCT * 100.0
            );
        }

        // 1) RECONCILIACJA: zamknij pozycje, ktore sie juz ROZLICZYLY (bez skladania zlecen).
        if now.saturating_sub(last_reconcile) >= RECONCILE_SEC {
            reconcile_positions(&http, &mut state, now).await;
            last_reconcile = now;
        }

        // 2) Sync GOTOWKI z prawdziwego salda on-chain (pUSD) - TYLKO W LIVE.
        //    POPRAWKA (bug DRY RUN): w paper tradingu ta synchronizacja nadpisywala
        //    papierowy budzet realnym saldem portfela (10.86$), przez co statystyki
        //    paper byly niemiarodajne.
        if live() && now.saturating_sub(last_cash_sync) >= CASH_SYNC_SEC {
            if let Some(b) = fetch_onchain_budget(&http).await {
                state.available_budget = b;
            }
            last_cash_sync = now;
        }

        // wyjscia
        let _t0 = std::time::Instant::now();
        manage_exits(&http, &mut state, now).await;
        let _t1 = std::time::Instant::now();

        // rotacja aktywow crypto (domyslnie WSZYSTKIE 15 aktywow na cykl)
        let n = CRYPTO_ASSETS.len();
        let per = crypto_per_cycle().min(n);
        let mut assets: Vec<&str> = Vec::new();
        for i in 0..per {
            assets.push(CRYPTO_ASSETS[(cursor + i) % n]);
        }
        cursor = (cursor + per) % n;

        // strategie crypto
        scan_s5(&http, &mut state, &mut tracker, &assets, now).await;
        let _t2 = std::time::Instant::now();
        scan_s4(&http, &mut state, &assets, now).await;
        scan_s6(&http, &mut state, &mut tracker, &assets, now).await;
        scan_s7(&http, &mut state, &mut tracker, &assets, now).await;
        scan_s8(&http, &mut state, &mut tracker, &assets, now).await;
        scan_s9(&http, &mut state, &mut tracker, &assets, now).await;
        let _t3 = std::time::Instant::now();
        if now.saturating_sub(last_kraken) >= KRAKEN_POLL_SEC {
            scan_s3(&http, &mut state, &mut kraken, &assets, now).await;
            last_kraken = now;
        }
        let _t4 = std::time::Instant::now();

        // strategie rynkowe
        scan_s2(&http, &mut state, &mut tracker, now).await;
        let _t5 = std::time::Instant::now();
        let sports_live = scan_sports(&http, &mut state, &mut tracker, now).await;
        let cat_markets = scan_finance4(&http, &mut state, &mut tracker, now).await;
        let _t6 = std::time::Instant::now();

        if std::env::var("DEBUG_TIMING").is_ok() {
            eprintln!(
                "[TIME] exits={:?} s5={:?} s4+s6-s9={:?} s3={:?} s2={:?} sports={:?}",
                _t1 - _t0,
                _t2 - _t1,
                _t3 - _t2,
                _t4 - _t3,
                _t5 - _t4,
                _t6 - _t5
            );
        }

        // heartbeat - widac ze bot zyje i skanuje
        if now.saturating_sub(last_heartbeat) >= HEARTBEAT_SEC {
            last_heartbeat = now;
            println!(
                "[SCAN] t={} crypto_assets={} (cykl: {})  sports_live_rynkow={}  kat_rynkow={}  open_pos={}  cash={:.2}$  equity={:.2}$  profit={:+.2}$",
                now,
                assets.len(),
                assets.join(","),
                sports_live,
                cat_markets,
                state.positions.len(),
                state.available_budget,
                state.equity(),
                state.profit()
            );
        }

        // porzadki + zapis
        if now.saturating_sub(last_prune) >= 60 {
            state.prune(now);
            last_prune = now;
        }
        save_state(&state);
        if now.saturating_sub(last_stats) >= 5 {
            write_stats(&state, now);
            last_stats = now;
            println!(
                "[STATS] cash={:.2}$ equity={:.2}$ pnl={:+.4}$ trades={} open={}",
                state.available_budget,
                state.equity(),
                state.realized_pnl,
                state.trades,
                state.positions.len()
            );
        }

        time::sleep(Duration::from_secs(SCAN_INTERVAL_SEC)).await;
    }
}
