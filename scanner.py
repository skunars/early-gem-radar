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
    """DEX Screener API'den JSON veri al."""
    try:
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
            },
        )

        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    except HTTPError as e:
        print(f"❌ HTTP HATASI: {e.code} - {url}")
        return None

    except URLError as e:
        print(f"❌ BAĞLANTI HATASI: {e.reason}")
        return None

    except Exception as e:
        print(f"❌ API HATASI: {e}")
        return None


def get_latest_profiles():
    """DEX Screener'daki son token profillerini al."""
    data = api_get(LATEST_PROFILES_URL)

    if not data:
        return []

    if not isinstance(data, list):
        return []

    return data


def get_token_pairs(chain_id, token_address):
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


def safe_float(value, default=0):
    try:
        if value is None:
            return default

        return float(value)

    except (ValueError, TypeError):
        return default


def get_best_pair(pairs):
    """Likiditesi en yüksek işlem çiftini seç."""

    valid_pairs = []

    for pair in pairs:

        liquidity = safe_float(
            pair.get("liquidity", {}).get("usd")
        )

        if liquidity > 0:
            valid_pairs.append(pair)

    if not valid_pairs:
        return None

    return max(
        valid_pairs,
        key=lambda x: safe_float(
            x.get("liquidity", {}).get("usd")
        ),
    )


def calculate_age_hours(pair):
    """İşlem çiftinin yaklaşık yaşını saat olarak hesapla."""

    created_at = pair.get("pairCreatedAt")

    if not created_at:
        return None

    try:
        created_ms = int(created_at)

        created = datetime.fromtimestamp(
            created_ms / 1000,
            tz=timezone.utc,
        )

        now = datetime.now(timezone.utc)

        age = now - created

        return max(age.total_seconds() / 3600, 0)

    except Exception:
        return None


def calculate_score(pair):
    """
    İlk fırsat skoru.

    NOT:
    Token fiyatı kesinlikle skorlamada kullanılmaz.
    """

    liquidity = safe_float(
        pair.get("liquidity", {}).get("usd")
    )

    volume_24h = safe_float(
        pair.get("volume", {}).get("h24")
    )

    price_change_24h = safe_float(
        pair.get("priceChange", {}).get("h24")
    )

    txns_24h = pair.get("txns", {}).get("h24", {})

    buys = int(
        safe_float(txns_24h.get("buys"))
    )

    sells = int(
        safe_float(txns_24h.get("sells"))
    )

    age_hours = calculate_age_hours(pair)

    score = 0

    # 1. Likidite
    if liquidity >= 100000:
        score += 25
    elif liquidity >= 50000:
        score += 20
    elif liquidity >= MIN_LIQUIDITY_USD:
        score += 15

    # 2. Hacim
    if volume_24h >= 500000:
        score += 20
    elif volume_24h >= 100000:
        score += 15
    elif volume_24h >= MIN_VOLUME_24H_USD:
        score += 10

    # 3. Erkenlik
    if age_hours is not None:

        if age_hours <= 6:
            score += 25

        elif age_hours <= 24:
            score += 20

        elif age_hours <= 72:
            score += 15

        elif age_hours <= 168:
            score += 8

    # 4. Momentum
    if price_change_24h >= 50:
        score += 15
    elif price_change_24h >= 20:
        score += 12
    elif price_change_24h >= 5:
        score += 8
    elif price_change_24h > 0:
        score += 4

    # 5. Alıcı/satıcı dengesi
    total_txns = buys + sells

    if total_txns > 0:

        buy_ratio = buys / total_txns

        if buy_ratio >= 0.65:
            score += 15

        elif buy_ratio >= 0.55:
            score += 10

        elif buy_ratio >= 0.50:
            score += 5

    return min(score, 100)


def get_signal(score):
    """Skora göre ilk radar durumu."""

    if score >= BUY_CANDIDATE_SCORE:
        return "🟢 AL ADAYI"

    if score >= WATCH_SCORE:
        return "🟡 TAKİP"

    return "⚪ ELE"


def analyze_token(profile):
    """Tek tokenı analiz et."""

    chain_id = profile.get("chainId")
    token_address = profile.get("tokenAddress")

    if not chain_id or not token_address:
        return None

    pairs = get_token_pairs(
        chain_id,
        token_address,
    )

    best_pair = get_best_pair(pairs)

    if not best_pair:
        return None

    liquidity = safe_float(
        best_pair.get("liquidity", {}).get("usd")
    )

    volume_24h = safe_float(
        best_pair.get("volume", {}).get("h24")
    )

    # Çok zayıf piyasaları daha baştan ele.
    if liquidity < MIN_LIQUIDITY_USD:
        return None

    if volume_24h < MIN_VOLUME_24H_USD:
        return None

    score = calculate_score(best_pair)

    signal = get_signal(score)

    base_token = best_pair.get(
        "baseToken",
        {}
    )

    result = {
        "name": base_token.get("name", "Unknown"),
        "symbol": base_token.get("symbol", "UNKNOWN"),
        "chain": chain_id,
        "token_address": token_address,
        "dex": best_pair.get("dexId"),
        "pair_address": best_pair.get("pairAddress"),
        "dex_url": best_pair.get("url"),

        "price_usd": safe_float(
            best_pair.get("priceUsd")
        ),

        "liquidity_usd": liquidity,
        "volume_24h_usd": volume_24h,

        "market_cap": safe_float(
            best_pair.get("marketCap")
        ),

        "fdv": safe_float(
            best_pair.get("fdv")
        ),

        "price_change_24h": safe_float(
            best_pair.get(
                "priceChange",
                {}
            ).get("h24")
        ),

        "age_hours": calculate_age_hours(
            best_pair
        ),

        "score": score,
        "signal": signal,

        "buys_24h": int(
            safe_float(
                best_pair.get(
                    "txns",
                    {}
                ).get(
                    "h24",
                    {}
                ).get("buys")
            )
        ),

        "sells_24h": int(
            safe_float(
                best_pair.get(
                    "txns",
                    {}
                ).get(
                    "h24",
                    {}
                ).get("sells")
            )
        ),
    }

    return result


def print_candidate(candidate):
    """Adayı terminalde okunabilir şekilde göster."""

    print()
    print("=" * 65)

    print(
        f"{candidate['signal']} | "
        f"{candidate['symbol']}"
    )

    print(
        f"İsim: {candidate['name']}"
    )

    print(
        f"Chain: {candidate['chain']}"
    )

    print(
        f"DEX: {candidate['dex']}"
    )

    print(
        f"Fiyat: ${candidate['price_usd']}"
    )

    print(
        f"Likidite: ${candidate['liquidity_usd']:,.0f}"
    )

    print(
        f"24s Hacim: ${candidate['volume_24h_usd']:,.0f}"
    )

    print(
        f"Market Cap: ${candidate['market_cap']:,.0f}"
    )

    print(
        f"FDV: ${candidate['fdv']:,.0f}"
    )

    print(
        f"24s Değişim: "
        f"{candidate['price_change_24h']:.2f}%"
    )

    age = candidate["age_hours"]

    if age is not None:
        print(
            f"Pair Yaşı: {age:.1f} saat"
        )

    print(
        f"24s Alış: {candidate['buys_24h']} | "
        f"Satış: {candidate['sells_24h']}"
    )

    print(
        f"SKOR: {candidate['score']}/100"
    )

    print(
        f"Token: {candidate['token_address']}"
    )

    print(
        f"Pair: {candidate['pair_address']}"
    )

    print(
        f"DEX: {candidate['dex_url']}"
    )

    print("=" * 65)


def main():

    print()
    print("=" * 65)
    print(f"🚀 {PROJECT_NAME}")
    print("🔎 GERÇEK DEX VERİ TARAMASI")
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
    print("📡 DEX Screener verisi alınıyor...")

    profiles = get_latest_profiles()

    print(
        f"📥 {len(profiles)} token profili bulundu."
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

        candidate = analyze_token(
            profile
        )

        if candidate:
            candidates.append(candidate)

        # API'yi gereksiz zorlamamak için
        # küçük bekleme.
        time.sleep(0.15)

    candidates.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    print()
    print("=" * 65)
    print(
        f"🎯 UYGUN ADAY SAYISI: "
        f"{len(candidates)}"
    )
    print("=" * 65)

    for candidate in candidates[:10]:
        print_candidate(candidate)

    print()
    print("✅ Tarama tamamlandı.")
    print(
        "ℹ️ Telegram bildirimi bu aşamada KAPALI."
    )
    print(
        "ℹ️ Fiyat, aday seçimi için filtre olarak kullanılmadı."
    )


if __name__ == "__main__":
    main()
