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
        key=lambda x: safe_float(
            x.get(
                "liquidity",
                {}
            ).get("usd")
        ),
    )


def calculate_age_hours(pair):
    """İşlem çiftinin yaklaşık yaşını saat olarak hesapla."""

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
            age.total_seconds() / 3600,
            0,
        )

    except Exception:
        return None


def calculate_score(pair):
    """
    İlk fırsat skoru.

    NOT:
    Token fiyatı kesinlikle
    skorlamada kullanılmaz.
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
            txns_24h.get("buys")
        )
    )

    sells = int(
        safe_float(
            txns_24h.get("sells")
        )
    )

    age_hours = calculate_age_hours(
        pair
    )

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

    return min(
        score,
        100
    )


def get_signal(score):
    """Skora göre radar durumu."""

    if score >= BUY_CANDIDATE_SCORE:
        return "🟢 AL ADAYI"

    if score >= WATCH_SCORE:
        return "🟡 TAKİP"

    return "⚪ ELE"


def get_final_signal(score, security):
    """
    Skor + güvenlik sonucuna göre
    nihai radar sinyalini belirler.
    """

    risk = security.get(
        "risk",
        "UNKNOWN"
    )

    available = security.get(
        "available",
        False
    )

    # Güvenlik API'si HIGH risk verdiyse
    # kesinlikle AL ADAYI olmasın.
    if risk == "HIGH":
        return "🔴 UZAK DUR"

    # Güvenlik verisi yoksa
    # şimdilik agresif AL sinyali verme.
    if not available:
        if score >= WATCH_SCORE:
            return "🟡 TAKİP"

        return "⚪ ELE"

    return get_signal(score)


def analyze_token(profile):
    """Tek tokenı analiz et."""

    chain_id = profile.get(
        "chainId"
    )

    token_address = profile.get(
        "tokenAddress"
    )

    if not chain_id or not token_address:
        return None

    pairs = get_token_pairs(
        chain_id,
        token_address,
    )

    best_pair = get_best_pair(
        pairs
