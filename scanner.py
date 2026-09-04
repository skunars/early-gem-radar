import json
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from config import (
    MIN_LIQUIDITY_USD,
    MIN_VOLUME_24H_USD,
    BUY_CANDIDATE_SCORE,
    WATCH_SCORE,
    PROJECT_NAME,
)

from security import get_security


DEX_API = "https://api.dexscreener.com"

LATEST_PROFILES_URL = (
    f"{DEX_API}/token-profiles/latest/v1"
)

USER_AGENT = "EarlyGemRadar/1.0"


def api_get(url):
    """API'den JSON veri al."""

    try:
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
        )

        with urlopen(request, timeout=20) as response:
            return json.loads(
                response.read().decode("utf-8")
            )

    except HTTPError as e:
        print(
            f"❌ HTTP HATASI: "
            f"{e.code} - {url}"
        )
        return None

    except URLError as e:
        print(
            f"❌ BAĞLANTI HATASI: "
            f"{e.reason}"
        )
        return None

    except Exception as e:
        print(
            f"❌ API HATASI: {e}"
        )
        return None


def get_latest_profiles():
    """DEX Screener'daki son token profillerini al."""

    data = api_get(
        LATEST_PROFILES_URL
    )

    if not data:
        return []

    if not isinstance(data, list):
        return []

    return data


def get_token_pairs(
    chain_id,
    token_address,
):
    """Tokenın DEX üzerindeki işlem çiftlerini al."""

    url = (
        f"{DEX_API}/token-pairs/v1/"
        f"{chain_id}/{token_address}"
    )

    data = api_get(url)

    if not data:
        return []

    if not isinstance(data, list):
        return []

    return data


def safe_float(
    value,
    default=0,
):
    """Güvenli şekilde sayıya çevir."""

    try:

        if value is None:
            return default

        return float(value)

    except (
        ValueError,
        TypeError,
    ):
        return default


def get_best_pair(pairs):
    """Likiditesi en yüksek işlem çiftini seç."""

    valid_pairs = []

    for pair in pairs:

        liquidity = safe_float(
            pair.get(
                "liquidity",
                {}
            ).get("usd")
        )

        if liquidity > 0:
            valid_pairs.append(pair)

    if not valid_pairs:
        return None

    return max(
        valid_pairs,
        key=lambda pair:
        safe_float(
            pair.get(
                "liquidity",
                {}
            ).get("usd")
        ),
    )


def calculate_age_hours(pair):
    """İşlem çiftinin yaşını saat olarak hesapla."""

    created_at = pair.get(
        "pairCreatedAt"
    )

    if not created_at:
        return None

    try:

        created_ms = int(
            created_at
        )

        created = datetime.fromtimestamp(
            created_ms / 1000,
            tz=timezone.utc,
        )

        now = datetime.now(
            timezone.utc
        )

        age = now - created

        return max(
            age.total_seconds()
            / 3600,
            0,
        )

    except Exception:
        return None


def calculate_security_score(
    security
):
    """
    Güvenlik sonucunu 0-25 arası
    fırsat skoruna dönüştürür.
    """

    available = security.get(
        "available",
        False
    )

    risk = security.get(
        "risk",
        "UNKNOWN"
    )

    if not available:
        return 0

    if risk == "HIGH":
        return 0

    if risk == "MEDIUM":
        return 12

    if risk == "LOW":
        return 25

    return 0


def calculate_score(
    pair,
    security,
):
    """
    Erken proje fırsat skoru.

    Maksimum: 100

    Güvenlik       25
    Likidite       20
    Hacim kalitesi 15
    Erkenlik       20
    Momentum       10
    Alıcı dengesi  10

    Token fiyatı skorlamada kullanılmaz.
    """

    liquidity = safe_float(
        pair.get(
            "liquidity",
            {}
        ).get("usd")
    )

    volume_24h = safe_float(
        pair.get(
            "volume",
            {}
        ).get("h24")
    )

    price_change_24h = safe_float(
        pair.get(
            "priceChange",
            {}
        ).get("h24")
    )

    txns_24h = pair.get(
        "txns",
        {}
    ).get(
        "h24",
        {}
    )

    buys = int(
        safe_float(
            txns_24h.get(
                "buys"
            )
        )
    )

    sells = int(
        safe_float(
            txns_24h.get(
                "sells"
            )
        )
    )

    age_hours = calculate_age_hours(
        pair
    )

    score = 0

    # --------------------------------------------------
    # 1. GÜVENLİK — 25 PUAN
    # --------------------------------------------------

    score += calculate_security_score(
        security
    )

    # --------------------------------------------------
    # 2. LİKİDİTE — 20 PUAN
    # --------------------------------------------------

    if liquidity >= 250000:
        score += 20

    elif liquidity >= 100000:
        score += 18

    elif liquidity >= 50000:
        score += 15

    elif liquidity >= 25000:
        score += 12

    elif liquidity >= MIN_LIQUIDITY_USD:
        score += 8

    # --------------------------------------------------
    # 3. HACİM KALİTESİ — 15 PUAN
    # --------------------------------------------------

    if liquidity > 0:

        volume_liquidity_ratio = (
            volume_24h / liquidity
        )

        if (
            volume_24h >= 500000
            and volume_liquidity_ratio >= 2
        ):
            score += 15

        elif (
            volume_24h >= 100000
            and volume_liquidity_ratio >= 1
        ):
            score += 12

        elif (
            volume_24h >= 50000
            and volume_liquidity_ratio >= 0.7
        ):
            score += 9

        elif volume_24h >= MIN_VOLUME_24H_USD:
            score += 5

    # --------------------------------------------------
    # 4. ERKENLİK — 20 PUAN
    # --------------------------------------------------

    if age_hours is not None:

        if age_hours <= 1:
            score += 20

        elif age_hours <= 3:
            score += 19

        elif age_hours <= 6:
            score += 18

        elif age_hours <= 12:
            score += 16

        elif age_hours <= 24:
            score += 14

        elif age_hours <= 48:
            score += 11

        elif age_hours <= 72:
            score += 8

        elif age_hours <= 168:
            score += 5

    # --------------------------------------------------
    # 5. MOMENTUM — 10 PUAN
    # --------------------------------------------------
    #
    # Aşırı pump'ı ödüllendirmiyoruz.
    # Ama sağlıklı yükselişe puan veriyoruz.
    #

    if (
        price_change_24h >= 0
        and price_change_24h <= 20
    ):
        score += 10

    elif price_change_24h <= 50:
        score += 9

    elif price_change_24h <= 100:
        score += 7

    elif price_change_24h <= 200:
        score += 5

    elif price_change_24h <= 500:
        score += 3

    elif price_change_24h > 500:
        score += 1

    elif price_change_24h < -30:
        score += 0

    # --------------------------------------------------
    # 6. ALICI / SATICI DENGESİ — 10 PUAN
    # --------------------------------------------------

    total_txns = (
        buys + sells
    )

    if total_txns > 0:

        buy_ratio = (
            buys / total_txns
        )

        if buy_ratio >= 0.70:
            score += 10

        elif buy_ratio >= 0.60:
            score += 8

        elif buy_ratio >= 0.55:
            score += 6

        elif buy_ratio >= 0.50:
            score += 4

        elif buy_ratio >= 0.45:
            score += 2

    return min(
        score,
        100
    )


def get_final_signal(
    score,
    security,
):
    """
    Fırsat skoru + güvenlik sonucuna
    göre nihai radar sinyali.
    """

    risk = security.get(
        "risk",
        "UNKNOWN"
    )

    available = security.get(
        "available",
        False
    )

    # --------------------------------------------------
    # KRİTİK GÜVENLİK RİSKİ
    # --------------------------------------------------

    if risk == "HIGH":
        return "🔴 UZAK DUR"

    # --------------------------------------------------
    # GÜVENLİK VERİSİ YOK
    # --------------------------------------------------

    if not available:

        if score >= WATCH_SCORE:
            return "🟡 TAKİP"

        return "⚪ ELE"

    # --------------------------------------------------
    # ORTA GÜVENLİK RİSKİ
    # --------------------------------------------------

    if risk == "MEDIUM":

        if score >= WATCH_SCORE:
            return "🟡 TAKİP"

        return "⚪ ELE"

    # --------------------------------------------------
    # TEMİZ GÜVENLİK
    # --------------------------------------------------

    if risk == "LOW":

        if score >= BUY_CANDIDATE_SCORE:
            return "🟢 AL ADAYI"

        if score >= WATCH_SCORE:
            return "🟡 TAKİP"

        return "⚪ ELE"

    return "⚪ ELE"


def analyze_token(
    profile
):
    """Tek tokenı analiz et."""

    chain_id = profile.get(
        "chainId"
    )

    token_address = profile.get(
        "tokenAddress"
    )

    if (
        not chain_id
        or not token_address
    ):
        return None

    pairs = get_token_pairs(
        chain_id,
        token_address,
    )

    best_pair = get_best_pair(
        pairs
    )

    if not best_pair:
        return None

    liquidity = safe_float(
        best_pair.get(
            "liquidity",
            {}
        ).get("usd")
    )

    volume_24h = safe_float(
        best_pair.get(
            "volume",
            {}
        ).get("h24")
    )

    # --------------------------------------------------
    # MİNİMUM PİYASA ŞARTLARI
    # --------------------------------------------------

    if (
        liquidity
        < MIN_LIQUIDITY_USD
    ):
        return None

    if (
        volume_24h
        < MIN_VOLUME_24H_USD
    ):
        return None

    # --------------------------------------------------
    # GÜVENLİK KONTROLÜ
    # --------------------------------------------------

    print(
        f"   🛡️ Güvenlik kontrolü: "
        f"{token_address[:12]}..."
    )

    security = get_security(
        chain_id,
        token_address,
    )

    # --------------------------------------------------
    # FIRSAT SKORU
    # --------------------------------------------------

    score = calculate_score(
        best_pair,
        security,
    )

    # --------------------------------------------------
    # NİHAİ SİNYAL
    # --------------------------------------------------

    signal = get_final_signal(
        score,
        security,
    )

    base_token = best_pair.get(
        "baseToken",
        {}
    )

    txns_24h = best_pair.get(
        "txns",
        {}
    ).get(
        "h24",
        {}
    )

    result = {

        "name": base_token.get(
            "name",
            "Unknown"
        ),

        "symbol": base_token.get(
            "symbol",
            "UNKNOWN"
        ),

        "chain": chain_id,

        "token_address":
            token_address,

        "dex": best_pair.get(
            "dexId"
        ),

        "pair_address":
            best_pair.get(
                "pairAddress"
            ),

        "dex_url":
            best_pair.get(
                "url"
            ),

        "price_usd":
            safe_float(
                best_pair.get(
                    "priceUsd"
                )
            ),

        "liquidity_usd":
            liquidity,

        "volume_24h_usd":
            volume_24h,

        "market_cap":
            safe_float(
                best_pair.get(
                    "marketCap"
                )
            ),

        "fdv":
            safe_float(
                best_pair.get(
                    "fdv"
                )
            ),

        "price_change_24h":
            safe_float(
                best_pair.get(
                    "priceChange",
                    {}
                ).get("h24")
            ),

        "age_hours":
            calculate_age_hours(
                best_pair
            ),

        "score":
            score,

        "signal":
            signal,

        "security_available":
            security.get(
                "available",
                False
            ),

        "security_risk":
            security.get(
                "risk",
                "UNKNOWN"
            ),

        "security_risks":
            security.get(
                "risks",
                []
            ),

        "buy_tax":
            safe_float(
                security.get(
                    "buy_tax",
                    0
                )
            ),

        "sell_tax":
            safe_float(
                security.get(
                    "sell_tax",
                    0
                )
            ),

        "buys_24h":
            int(
                safe_float(
                    txns_24h.get(
                        "buys"
                    )
                )
            ),

        "sells_24h":
            int(
                safe_float(
                    txns_24h.get(
                        "sells"
                    )
                )
            ),
    }

    return result


def print_candidate(
    candidate
):
    """Adayı terminalde okunabilir şekilde göster."""

    print()
    print("=" * 65)

    print(
        f"{candidate['signal']} | "
        f"{candidate['symbol']}"
    )

    print(
        f"İsim: "
        f"{candidate['name']}"
    )

    print(
        f"Chain: "
        f"{candidate['chain']}"
    )

    print(
        f"DEX: "
        f"{candidate['dex']}"
    )

    print(
        f"Fiyat: "
        f"${candidate['price_usd']}"
    )

    print(
        f"Likidite: "
        f"${candidate['liquidity_usd']:,.0f}"
    )

    print(
        f"24s Hacim: "
        f"${candidate['volume_24h_usd']:,.0f}"
    )

    print(
        f"Market Cap: "
        f"${candidate['market_cap']:,.0f}"
    )

    print(
        f"FDV: "
        f"${candidate['fdv']:,.0f}"
    )

    print(
        f"24s Değişim: "
        f"{candidate['price_change_24h']:.2f}%"
    )

    age = candidate[
        "age_hours"
    ]

    if age is not None:

        print(
            f"Pair Yaşı: "
            f"{age:.1f} saat"
        )

    print(
        f"24s Alış: "
        f"{candidate['buys_24h']} | "
        f"Satış: "
        f"{candidate['sells_24h']}"
    )

    print(
        f"SKOR: "
        f"{candidate['score']}/100"
    )

    print()
    print("🛡️ GÜVENLİK")

    print(
        f"API kullanılabilir: "
        f"{candidate['security_available']}"
    )

    print(
        f"Risk: "
        f"{candidate['security_risk']}"
    )

    print(
        f"Buy Tax: "
        f"%{candidate['buy_tax']:.2f}"
    )

    print(
        f"Sell Tax: "
        f"%{candidate['sell_tax']:.2f}"
    )

    risks = candidate[
        "security_risks"
    ]

    if risks:

        print(
            "Riskler: "
            + ", ".join(risks)
        )

    else:

        print(
            "Riskler: Yok"
        )

    print()

    print(
        f"Token: "
        f"{candidate['token_address']}"
    )

    print(
        f"Pair: "
        f"{candidate['pair_address']}"
    )

    print(
        f"DEX: "
        f"{candidate['dex_url']}"
    )

    print("=" * 65)


def main():

    print()
    print("=" * 65)

    print(
        f"🚀 {PROJECT_NAME}"
    )

    print(
        "🔎 GERÇEK DEX VERİ TARAMASI"
    )

    print(
        "🛡️ GÜVENLİK KONTROLLÜ MOD"
    )

    print("=" * 65)

    print(
        f"Minimum likidite: "
        f"${MIN_LIQUIDITY_USD:,.0f}"
    )

    print(
        f"Minimum 24s hacim: "
        f"${MIN_VOLUME_24H_USD:,.0f}"
    )

    print()
    print(
        "📡 DEX Screener verisi alınıyor..."
    )

    profiles = get_latest_profiles()

    print(
        f"📥 {len(profiles)} "
        f"token profili bulundu."
    )

    candidates = []

    for index, profile in enumerate(
        profiles,
        start=1,
    ):

        chain = profile.get(
            "chainId",
            "unknown"
        )

        address = profile.get(
            "tokenAddress",
            ""
        )

        print(
            f"[{index}/{len(profiles)}] "
            f"{chain} "
            f"{address[:12]}..."
        )

        try:

            candidate = analyze_token(
                profile
            )

            if candidate:
                candidates.append(
                    candidate
                )

        except Exception as e:

            print(
                f"   ❌ Token analiz hatası: "
                f"{e}"
            )

        # API'leri gereksiz zorlamamak için
        time.sleep(0.15)

    # --------------------------------------------------
    # SKORA GÖRE SIRALA
    # --------------------------------------------------

    candidates.sort(
        key=lambda x:
        x["score"],
        reverse=True,
    )

    print()
    print("=" * 65)

    print(
        f"🎯 UYGUN ADAY SAYISI: "
        f"{len(candidates)}"
    )

    print("=" * 65)

    # En yüksek 10 aday
    for candidate in candidates[:10]:

        print_candidate(
            candidate
        )

    print()
    print(
        "✅ Tarama tamamlandı."
    )

    print(
        "ℹ️ Telegram bildirimi "
        "bu aşamada KAPALI."
    )

    print(
        "ℹ️ Token fiyatı filtre "
        "olarak kullanılmadı."
    )

    print(
        "🛡️ Güvenlik kontrolü aktif."
    )


if __name__ == "__main__":
    main()
