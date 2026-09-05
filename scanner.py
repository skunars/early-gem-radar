import json
import os
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
from history import save_candidates


# ============================================================
# EARLY GEM RADAR
# ============================================================

DEX_API = "https://api.dexscreener.com"

LATEST_PROFILES_URL = (
    f"{DEX_API}/token-profiles/latest/v1"
)

USER_AGENT = "EarlyGemRadar/2.0"


# ============================================================
# PAPER TRADE AYARLARI
# ============================================================

STAKE_TL = 100.0

# Sert zarar durdurma
HARD_STOP_PERCENT = 12.0

# Kâr başladıktan sonra devreye giren trailing
TRAIL_START_PERCENT = 10.0

# Peak'ten maksimum geri verme oranları
TRAIL_LEVELS = [
    (10.0, 7.0),
    (20.0, 6.0),
    (30.0, 5.0),
    (50.0, 4.0),
    (75.0, 3.5),
    (100.0, 3.0),
    (150.0, 2.5),
    (200.0, 2.0),
    (300.0, 1.5),
]

# Çok uzun süre hareketsiz kalan işlemleri temizlemek için
MAX_HOLD_HOURS = 72


# ============================================================
# DOSYA AYARLARI
# ============================================================

DATA_DIR = "data"

PAPER_TRADES_FILE = os.path.join(
    DATA_DIR,
    "paper_trades.json"
)

RADAR_STATE_FILE = os.path.join(
    DATA_DIR,
    "radar_state.json"
)


# ============================================================
# GENEL YARDIMCI FONKSİYONLAR
# ============================================================

def utc_now():
    return datetime.now(
        timezone.utc
    )


def utc_iso():
    return utc_now().isoformat()


def ensure_data_dir():
    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )


def load_json(
    filename,
    default,
):
    try:

        if not os.path.exists(filename):
            return default

        with open(
            filename,
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        return data

    except Exception as e:

        print(
            f"⚠️ JSON okuma hatası "
            f"{filename}: {e}"
        )

        return default


def save_json(
    filename,
    data,
):
    ensure_data_dir()

    temp_file = (
        filename
        + ".tmp"
    )

    try:

        with open(
            temp_file,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2,
            )

        os.replace(
            temp_file,
            filename,
        )

    except Exception as e:

        print(
            f"❌ JSON kayıt hatası "
            f"{filename}: {e}"
        )


def safe_float(
    value,
    default=0.0,
):
    try:

        if value is None:
            return default

        return float(value)

    except (
        ValueError,
        TypeError,
    ):
        return default


def safe_int(
    value,
    default=0,
):
    try:

        return int(
            float(value)
        )

    except (
        ValueError,
        TypeError,
    ):
        return default


# ============================================================
# API
# ============================================================

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

        with urlopen(
            request,
            timeout=20,
        ) as response:

            return json.loads(
                response
                .read()
                .decode("utf-8")
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

    data = api_get(
        LATEST_PROFILES_URL
    )

    if not data:
        return []

    if not isinstance(
        data,
        list,
    ):
        return []

    return data


def get_token_pairs(
    chain_id,
    token_address,
):

    url = (
        f"{DEX_API}/token-pairs/v1/"
        f"{chain_id}/{token_address}"
    )

    data = api_get(url)

    if not data:
        return []

    if not isinstance(
        data,
        list,
    ):
        return []

    return data


# ============================================================
# PAIR
# ============================================================

def get_best_pair(
    pairs,
):

    valid_pairs = []

    for pair in pairs:

        liquidity = safe_float(
            pair.get(
                "liquidity",
                {}
            ).get("usd")
        )

        if liquidity > 0:

            valid_pairs.append(
                pair
            )

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


def calculate_age_hours(
    pair,
):

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

        age = (
            utc_now()
            - created
        )

        return max(
            age.total_seconds()
            / 3600,
            0,
        )

    except Exception:

        return None


# ============================================================
# SECURITY
# ============================================================

def calculate_security_score(
    security,
):

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
        return 10

    if risk == "LOW":
        return 25

    return 0


# ============================================================
# BUY / SELL ORANI
# ============================================================

def get_buy_ratio(
    pair,
):

    txns_24h = pair.get(
        "txns",
        {}
    ).get(
        "h24",
        {}
    )

    buys = safe_int(
        txns_24h.get(
            "buys"
        )
    )

    sells = safe_int(
        txns_24h.get(
            "sells"
        )
    )

    total = (
        buys + sells
    )

    if total <= 0:
        return 0.0

    return buys / total


# ============================================================
# EARLYNESS SCORE
# ============================================================

def calculate_earlyness_score(
    pair,
    previous_state,
):
    """
    0-100 arası erkenlik skoru.

    Amaç:
    Sadece yükselmiş coin bulmak değil,
    yükselişin mümkün olduğunca erken
    aşamasını bulmak.
    """

    price_change = safe_float(
        pair.get(
            "priceChange",
            {}
        ).get("h24")
    )

    age = calculate_age_hours(
        pair
    )

    liquidity = safe_float(
        pair.get(
            "liquidity",
            {}
        ).get("usd")
    )

    volume = safe_float(
        pair.get(
            "volume",
            {}
        ).get("h24")
    )

    buy_ratio = get_buy_ratio(
        pair
    )

    pair_address = pair.get(
        "pairAddress"
    )

    previous = previous_state.get(
        pair_address,
        {}
    )

    previous_price = safe_float(
        previous.get(
            "price"
        )
    )

    current_price = safe_float(
        pair.get(
            "priceUsd"
        )
    )

    acceleration_score = 0

    if (
        previous_price > 0
        and current_price > 0
    ):

        short_move = (
            (
                current_price
                / previous_price
            ) - 1
        ) * 100

        # Son 15 dakika içinde hareket
        # hızlanıyorsa erkenlik puanı artar.
        if short_move >= 20:
            acceleration_score = 15

        elif short_move >= 10:
            acceleration_score = 12

        elif short_move >= 5:
            acceleration_score = 9

        elif short_move >= 2:
            acceleration_score = 6

        elif short_move >= 0:
            acceleration_score = 3

    score = 0

    # --------------------------------------------------------
    # YAŞ
    # --------------------------------------------------------

    if age is not None:

        if age <= 1:
            score += 25

        elif age <= 3:
            score += 23

        elif age <= 6:
            score += 21

        elif age <= 12:
            score += 18

        elif age <= 24:
            score += 15

        elif age <= 48:
            score += 10

        elif age <= 72:
            score += 6

        else:
            score += 2

    # --------------------------------------------------------
    # FİYAT HAREKETİ
    # --------------------------------------------------------

    if 0 <= price_change <= 30:
        score += 25

    elif 30 < price_change <= 60:
        score += 22

    elif 60 < price_change <= 100:
        score += 18

    elif 100 < price_change <= 200:
        score += 13

    elif 200 < price_change <= 500:
        score += 7

    elif 500 < price_change <= 1000:
        score += 3

    elif price_change > 1000:
        score += 0

    else:
        score += 0

    # --------------------------------------------------------
    # ALIŞ BASKISI
    # --------------------------------------------------------

    if buy_ratio >= 0.70:
        score += 20

    elif buy_ratio >= 0.60:
        score += 17

    elif buy_ratio >= 0.55:
        score += 13

    elif buy_ratio >= 0.50:
        score += 9

    elif buy_ratio >= 0.45:
        score += 4

    # --------------------------------------------------------
    # LİKİDİTE / HACİM
    # --------------------------------------------------------

    if liquidity >= 250000:
        score += 10

    elif liquidity >= 100000:
        score += 9

    elif liquidity >= 50000:
        score += 8

    elif liquidity >= 25000:
        score += 6

    elif liquidity >= MIN_LIQUIDITY_USD:
        score += 3

    volume_ratio = 0

    if liquidity > 0:
        volume_ratio = (
            volume / liquidity
        )

    if volume_ratio >= 5:
        score += 5

    elif volume_ratio >= 2:
        score += 4

    elif volume_ratio >= 1:
        score += 3

    elif volume_ratio >= 0.5:
        score += 1

    # --------------------------------------------------------
    # HAREKET HIZLANMASI
    # --------------------------------------------------------

    score += acceleration_score

    return min(
        score,
        100,
    )


# ============================================================
# ANA SKOR
# ============================================================

def calculate_score(
    pair,
    security,
    earlyness_score,
):
    """
    Maksimum 100.

    Güvenlik        25
    Likidite        20
    Hacim           15
    Erkenlik        15
    Momentum        10
    Alıcı dengesi   10
    Earlyness bonus  5
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

    price_change = safe_float(
        pair.get(
            "priceChange",
            {}
        ).get("h24")
    )

    buy_ratio = get_buy_ratio(
        pair
    )

    score = 0

    # --------------------------------------------------------
    # 1. GÜVENLİK — 25
    # --------------------------------------------------------

    score += calculate_security_score(
        security
    )

    # --------------------------------------------------------
    # 2. LİKİDİTE — 20
    # --------------------------------------------------------

    if liquidity >= 250000:
        score += 20

    elif liquidity >= 100000:
        score += 18

    elif liquidity >= 50000:
        score += 15

    elif liquidity >= 25000:
        score += 11

    elif liquidity >= MIN_LIQUIDITY_USD:
        score += 7

    # --------------------------------------------------------
    # 3. HACİM — 15
    # --------------------------------------------------------

    if liquidity > 0:

        ratio = (
            volume_24h
            / liquidity
        )

        if (
            volume_24h >= 500000
            and ratio >= 2
        ):
            score += 15

        elif (
            volume_24h >= 100000
            and ratio >= 1
        ):
            score += 12

        elif (
            volume_24h >= 50000
            and ratio >= 0.7
        ):
            score += 9

        elif volume_24h >= MIN_VOLUME_24H_USD:
            score += 5

    # --------------------------------------------------------
    # 4. ERKENLİK — 15
    # --------------------------------------------------------

    age = calculate_age_hours(
        pair
    )

    if age is not None:

        if age <= 1:
            score += 15

        elif age <= 3:
            score += 14

        elif age <= 6:
            score += 13

        elif age <= 12:
            score += 11

        elif age <= 24:
            score += 9

        elif age <= 48:
            score += 6

        elif age <= 72:
            score += 4

        else:
            score += 1

    # --------------------------------------------------------
    # 5. MOMENTUM — 10
    # --------------------------------------------------------

    # NEGATİF HAREKET ARTIK PUAN ALAMAZ
    if price_change < 0:

        momentum_score = 0

    elif price_change <= 20:

        momentum_score = 10

    elif price_change <= 50:

        momentum_score = 9

    elif price_change <= 100:

        momentum_score = 7

    elif price_change <= 200:

        momentum_score = 5

    elif price_change <= 500:

        momentum_score = 3

    elif price_change <= 1000:

        momentum_score = 1

    else:

        momentum_score = 0

    score += momentum_score

    # --------------------------------------------------------
    # 6. ALICI DENGESİ — 10
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 7. EARLYNESS BONUS — 5
    # --------------------------------------------------------

    if earlyness_score >= 80:
        score += 5

    elif earlyness_score >= 70:
        score += 4

    elif earlyness_score >= 60:
        score += 3

    elif earlyness_score >= 50:
        score += 1

    return min(
        score,
        100,
    )


# ============================================================
# RİSK DÜZELTMELERİ
# ============================================================

def apply_risk_adjustments(
    score,
    pair,
    security,
):
    """
    Tehlikeli adayların skorunu düşürür.
    """

    price_change = safe_float(
        pair.get(
            "priceChange",
            {}
        ).get("h24")
    )

    liquidity = safe_float(
        pair.get(
            "liquidity",
            {}
        ).get("usd")
    )

    buy_ratio = get_buy_ratio(
        pair
    )

    risk = security.get(
        "risk",
        "UNKNOWN"
    )

    available = security.get(
        "available",
        False
    )

    buy_tax = safe_float(
        security.get(
            "buy_tax",
            0
        )
    )

    sell_tax = safe_float(
        security.get(
            "sell_tax",
            0
        )
    )

    adjusted = score

    # --------------------------------------------------------
    # SERT DÜŞÜŞ
    # --------------------------------------------------------

    if price_change <= -50:

        adjusted -= 35

    elif price_change <= -30:

        adjusted -= 25

    elif price_change <= -20:

        adjusted -= 15

    elif price_change < -10:

        adjusted -= 8

    # --------------------------------------------------------
    # AŞIRI YÜKSELİŞ
    # --------------------------------------------------------

    # Otomatik olarak silmiyoruz.
    # Sadece erkenlik avantajını azaltıyoruz.

    if price_change >= 1000:

        adjusted -= 20

    elif price_change >= 500:

        adjusted -= 12

    elif price_change >= 300:

        adjusted -= 7

    elif price_change >= 200:

        adjusted -= 4

    # --------------------------------------------------------
    # ÇOK DÜŞÜK LİKİDİTE
    # --------------------------------------------------------

    if liquidity < 15000:

        adjusted -= 20

    elif liquidity < 25000:

        adjusted -= 10

    # --------------------------------------------------------
    # SATICI BASKISI
    # --------------------------------------------------------

    if buy_ratio < 0.40:

        adjusted -= 15

    elif buy_ratio < 0.45:

        adjusted -= 8

    # --------------------------------------------------------
    # GÜVENLİK
    # --------------------------------------------------------

    if risk == "HIGH":

        adjusted -= 50

    elif (
        not available
        and adjusted >= BUY_CANDIDATE_SCORE
    ):

        adjusted -= 10

    # --------------------------------------------------------
    # VERGİ
    # --------------------------------------------------------

    total_tax = (
        buy_tax
        + sell_tax
    )

    if total_tax >= 10:

        adjusted -= 20

    elif total_tax >= 5:

        adjusted -= 10

    elif total_tax >= 2:

        adjusted -= 5

    return max(
        min(
            adjusted,
            100,
        ),
        0,
    )


# ============================================================
# SİNYAL
# ============================================================

def get_final_signal(
    score,
    security,
):

    risk = security.get(
        "risk",
        "UNKNOWN"
    )

    available = security.get(
        "available",
        False
    )

    if risk == "HIGH":

        return "🔴 UZAK DUR"

    if not available:

        if score >= BUY_CANDIDATE_SCORE:

            return "🟡 TAKİP"

        if score >= WATCH_SCORE:

            return "🟡 TAKİP"

        return "⚪ ELE"

    if risk == "MEDIUM":

        if score >= BUY_CANDIDATE_SCORE:

            return "🟡 TAKİP"

        if score >= WATCH_SCORE:

            return "🟡 TAKİP"

        return "⚪ ELE"

    if risk == "LOW":

        if score >= BUY_CANDIDATE_SCORE:

            return "🟢 AL ADAYI"

        if score >= WATCH_SCORE:

            return "🟡 TAKİP"

        return "⚪ ELE"

    return "⚪ ELE"


# ============================================================
# TOKEN ANALİZİ
# ============================================================

def analyze_token(
    profile,
    previous_state,
):

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

    print(
        f"   🛡️ Güvenlik kontrolü: "
        f"{token_address[:12]}..."
    )

    security = get_security(
        chain_id,
        token_address,
    )

    earlyness_score = (
        calculate_earlyness_score(
            best_pair,
            previous_state,
        )
    )

    raw_score = calculate_score(
        best_pair,
        security,
        earlyness_score,
    )

    final_score = apply_risk_adjustments(
        raw_score,
        best_pair,
        security,
    )

    signal = get_final_signal(
        final_score,
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

    buys = safe_int(
        txns_24h.get(
            "buys"
        )
    )

    sells = safe_int(
        txns_24h.get(
            "sells"
        )
    )

    result = {

        "name":
            base_token.get(
                "name",
                "Unknown"
            ),

        "symbol":
            base_token.get(
                "symbol",
                "UNKNOWN"
            ),

        "chain":
            chain_id,

        "token_address":
            token_address,

        "dex":
            best_pair.get(
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
            final_score,

        "raw_score":
            raw_score,

        "earlyness_score":
            earlyness_score,

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
            buys,

        "sells_24h":
            sells,

        "buy_ratio":
            round(
                get_buy_ratio(
                    best_pair
                ),
                4,
            ),

        "scan_time":
            utc_iso(),
    }

    return result


# ============================================================
# PAPER TRADE
# ============================================================

def load_paper_trades():

    data = load_json(
        PAPER_TRADES_FILE,
        [],
    )

    if not isinstance(
        data,
        list,
    ):

        return []

    return data


def save_paper_trades(
    trades,
):

    save_json(
        PAPER_TRADES_FILE,
        trades,
    )


def get_open_trades(
    trades,
):

    return [
        trade
        for trade in trades
        if trade.get(
            "status"
        ) == "OPEN"
    ]


def is_trade_open_for_pair(
    trades,
    pair_address,
):

    for trade in trades:

        if (
            trade.get(
                "status"
            ) == "OPEN"
            and trade.get(
                "pair_address"
            ) == pair_address
        ):

            return True

    return False


def get_trailing_drawdown(
    peak_profit,
):

    selected = 0

    for (
        profit_level,
        drawdown
    ) in TRAIL_LEVELS:

        if peak_profit >= profit_level:

            selected = drawdown

    return selected


def calculate_trade_profit_tl(
    entry_price,
    current_price,
):

    if (
        entry_price <= 0
        or current_price <= 0
    ):

        return 0.0

    percent = (
        (
            current_price
            / entry_price
        ) - 1
    ) * 100

    return (
        STAKE_TL
        * percent
        / 100
    )


def open_paper_trade(
    candidate,
    trades,
):

    pair_address = candidate[
        "pair_address"
    ]

    if is_trade_open_for_pair(
        trades,
        pair_address,
    ):

        return False

    entry_price = safe_float(
        candidate[
            "price_usd"
        ]
    )

    if entry_price <= 0:

        return False

    now = utc_iso()

    trade = {

        "trade_id":
            f"{candidate['chain']}_"
            f"{pair_address}_"
            f"{int(time.time())}",

        "status":
            "OPEN",

        "stake_tl":
            STAKE_TL,

        "name":
            candidate[
                "name"
            ],

        "symbol":
            candidate[
                "symbol"
            ],

        "chain":
            candidate[
                "chain"
            ],

        "token_address":
            candidate[
                "token_address"
            ],

        "pair_address":
            pair_address,

        "dex":
            candidate[
                "dex"
            ],

        "entry_time":
            now,

        "entry_price":
            entry_price,

        "entry_score":
            candidate[
                "score"
            ],

        "raw_score":
            candidate[
                "raw_score"
            ],

        "earlyness_score":
            candidate[
                "earlyness_score"
            ],

        "peak_price":
            entry_price,

        "peak_profit_pct":
            0.0,

        "max_drawdown_pct":
            0.0,

        "current_profit_pct":
            0.0,

        "current_profit_tl":
            0.0,

        "highest_milestone":
            0,

        "milestones_hit":
            [],

        "exit_time":
            None,

        "exit_price":
            None,

        "exit_reason":
            None,

        "final_profit_pct":
            None,

        "final_profit_tl":
            None,

        "hold_hours":
            None,
    }

    trades.append(
        trade
    )

    print(
        f"💰 PAPER OPEN "
        f"{candidate['symbol']} "
        f"| 100 TL "
        f"| score={candidate['score']} "
        f"| early={candidate['earlyness_score']} "
        f"| entry={entry_price}"
    )

    return True


# ============================================================
# AÇIK PAPER TRADE GÜNCELLEME
# ============================================================

def update_open_paper_trades(
    trades,
):

    open_trades = get_open_trades(
        trades
    )

    if not open_trades:

        return

    print()
    print(
        "📊 Açık paper işlemler "
        "güncelleniyor..."
    )

    milestones = [
        5,
        10,
        20,
        30,
        50,
        75,
        100,
        150,
        200,
        300,
    ]

    changed = False

    for trade in open_trades:

        chain = trade.get(
            "chain"
        )

        token_address = trade.get(
            "token_address"
        )

        pair_address = trade.get(
            "pair_address"
        )

        if (
            not chain
            or not token_address
        ):

            continue

        try:

            pairs = get_token_pairs(
                chain,
                token_address,
            )

            pair = None

            for candidate_pair in pairs:

                if (
                    candidate_pair.get(
                        "pairAddress"
                    )
                    == pair_address
                ):

                    pair = candidate_pair
                    break

            if not pair:

                pair = get_best_pair(
                    pairs
                )

            if not pair:

                continue

            current_price = safe_float(
                pair.get(
                    "priceUsd"
                )
            )

            entry_price = safe_float(
                trade.get(
                    "entry_price"
                )
            )

            if (
                current_price <= 0
                or entry_price <= 0
            ):

                continue

            profit_pct = (
                (
                    current_price
                    / entry_price
                ) - 1
            ) * 100

            profit_tl = (
                STAKE_TL
                * profit_pct
                / 100
            )

            peak_price = safe_float(
                trade.get(
                    "peak_price"
                ),
                entry_price,
            )

            if current_price > peak_price:

                peak_price = current_price

                trade[
                    "peak_price"
                ] = current_price

            peak_profit_pct = (
                (
                    peak_price
                    / entry_price
                ) - 1
            ) * 100

            trade[
                "peak_profit_pct"
            ] = round(
                peak_profit_pct,
                4,
            )

            trade[
                "current_profit_pct"
            ] = round(
                profit_pct,
                4,
            )

            trade[
                "current_profit_tl"
            ] = round(
                profit_tl,
                4,
            )

            # ------------------------------------------------
            # MAX DRAW DOWN
            # ------------------------------------------------

            if peak_profit_pct > 0:

                drawdown = (
                    peak_profit_pct
                    - profit_pct
                )

                if drawdown > safe_float(
                    trade.get(
                        "max_drawdown_pct"
                    )
                ):

                    trade[
                        "max_drawdown_pct"
                    ] = round(
                        drawdown,
                        4,
                    )

            # ------------------------------------------------
            # MILESTONE
            # ------------------------------------------------

            for milestone in milestones:

                if (
                    profit_pct >= milestone
                    and milestone
                    not in trade.get(
                        "milestones_hit",
                        []
                    )
                ):

                    trade.setdefault(
                        "milestones_hit",
                        []
                    ).append(
                        milestone
                    )

                    if milestone > safe_int(
                        trade.get(
                            "highest_milestone"
                        )
                    ):

                        trade[
                            "highest_milestone"
                        ] = milestone

                    print(
                        f"🚀 {trade['symbol']} "
                        f"+{milestone}% "
                        f"| 100 TL → "
                        f"{STAKE_TL + "
                        profit_tl:.2f} TL"
                    )

                    changed = True

            # ------------------------------------------------
            # ÇIKIŞ KONTROLLERİ
            # ------------------------------------------------

            exit_reason = None

            # 1. HARD STOP
            if profit_pct <= -HARD_STOP_PERCENT:

                exit_reason = (
                    "HARD_STOP"
                )

            # 2. TRAILING
            elif peak_profit_pct >= TRAIL_START_PERCENT:

                allowed_drawdown = (
                    get_trailing_drawdown(
                        peak_profit_pct
                    )
                )

                if (
                    allowed_drawdown > 0
                    and (
                        peak_profit_pct
                        - profit_pct
                    )
                    >= allowed_drawdown
                ):

                    exit_reason = (
                        "TRAILING_STOP"
                    )

            # 3. 72 SAAT KONTROLÜ
            if exit_reason is None:

                try:

                    entry_time = datetime.fromisoformat(
                        trade[
                            "entry_time"
                        ]
                    )

                    hold_hours = (
                        utc_now()
                        - entry_time
                    ).total_seconds() / 3600

                    if hold_hours >= MAX_HOLD_HOURS:

                        exit_reason = (
                            "MAX_HOLD_TIME"
                        )

                except Exception:

                    pass

            # ------------------------------------------------
            # KAPAT
            # ------------------------------------------------

            if exit_reason:

                close_paper_trade(
                    trade,
                    current_price,
                    profit_pct,
                    profit_tl,
                    exit_reason,
                )

                changed = True

            print(
                f"   {trade['symbol']} "
                f"| PnL "
                f"{profit_pct:+.2f}% "
                f"| {profit_tl:+.2f} TL "
                f"| Peak "
                f"{peak_profit_pct:+.2f}%"
            )

        except Exception as e:

            print(
                f"   ❌ "
                f"{trade.get('symbol')} "
                f"güncelleme hatası: "
                f"{e}"
            )

    if changed:

        save_paper_trades(
            trades
        )


def close_paper_trade(
    trade,
    exit_price,
    profit_pct,
    profit_tl,
    reason,
):

    trade[
        "status"
    ] = "CLOSED"

    trade[
        "exit_time"
    ] = utc_iso()

    trade[
        "exit_price"
    ] = exit_price

    trade[
        "exit_reason"
    ] = reason

    trade[
        "final_profit_pct"
    ] = round(
        profit_pct,
        4,
    )

    trade[
        "final_profit_tl"
    ] = round(
        profit_tl,
        4,
    )

    try:

        entry_time = datetime.fromisoformat(
            trade[
                "entry_time"
            ]
        )

        hold_hours = (
            utc_now()
            - entry_time
        ).total_seconds() / 3600

        trade[
            "hold_hours"
        ] = round(
            hold_hours,
            2,
        )

    except Exception:

        trade[
            "hold_hours"
        ] = None

    print(
        f"🏁 PAPER CLOSE "
        f"{trade['symbol']} "
        f"| {reason} "
        f"| {profit_pct:+.2f}% "
        f"| {profit_tl:+.2f} TL"
    )


# ============================================================
# DUPLICATE TOKEN KONTROLÜ
# ============================================================

def deduplicate_candidates(
    candidates,
):

    unique = {}

    for candidate in candidates:

        pair_address = candidate.get(
            "pair_address"
        )

        if not pair_address:

            continue

        existing = unique.get(
            pair_address
        )

        if (
            existing is None
            or candidate[
                "score"
            ] > existing[
                "score"
            ]
        ):

            unique[
                pair_address
            ] = candidate

    return list(
        unique.values()
    )


# ============================================================
# RADAR STATE
# ============================================================

def load_radar_state():

    data = load_json(
        RADAR_STATE_FILE,
        {},
    )

    if not isinstance(
        data,
        dict,
    ):

        return {}

    return data


def update_radar_state(
    candidates,
):

    state = {}

    for candidate in candidates:

        pair_address = candidate.get(
            "pair_address"
        )

        if not pair_address:

            continue

        state[
            pair_address
        ] = {

            "price":
                candidate[
                    "price_usd"
                ],

            "time":
                utc_iso(),

            "symbol":
                candidate[
                    "symbol"
                ],

            "chain":
                candidate[
                    "chain"
                ],

            "token_address":
                candidate[
                    "token_address"
                ],
        }

    save_json(
        RADAR_STATE_FILE,
        state,
    )


# ============================================================
# TERMİNAL GÖRÜNÜMÜ
# ============================================================

def print_candidate(
    candidate,
):

    print()
    print(
        "=" * 70
    )

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
        f"24s Değişim: "
        f"{candidate['price_change_24h']:.2f}%"
    )

    age = candidate[
        "age_hours"
    ]

    if age is not None:

        print(
            f"Pair Yaşı: "
            f"{age:.2f} saat"
        )

    print(
        f"Alış: "
        f"{candidate['buys_24h']} | "
        f"Satış: "
        f"{candidate['sells_24h']} | "
        f"Buy Ratio: "
        f"{candidate['buy_ratio'] * 100:.1f}%"
    )

    print(
        f"RAW SCORE: "
        f"{candidate['raw_score']}/100"
    )

    print(
        f"EARLYNESS: "
        f"{candidate['earlyness_score']}/100"
    )

    print(
        f"FINAL SCORE: "
        f"{candidate['score']}/100"
    )

    print()
    print(
        "🛡️ GÜVENLİK"
    )

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
            + ", ".join(
                risks
            )
        )

    else:

        print(
            "Riskler: Yok"
        )

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

    print(
        "=" * 70
    )


# ============================================================
# PAPER İSTATİSTİK
# ============================================================

def print_paper_statistics(
    trades,
):

    closed = [
        t
        for t in trades
        if t.get(
            "status"
        ) == "CLOSED"
    ]

    opened = [
        t
        for t in trades
        if t.get(
            "status"
        ) == "OPEN"
    ]

    winners = [
        t
        for t in closed
        if safe_float(
            t.get(
                "final_profit_tl"
            )
        ) > 0
    ]

    losers = [
        t
        for t in closed
        if safe_float(
            t.get(
                "final_profit_tl"
            )
        ) < 0
    ]

    net_pnl = sum(
        safe_float(
            t.get(
                "final_profit_tl"
            )
        )
        for t in closed
    )

    total_peak_profit = sum(
        max(
            safe_float(
                t.get(
                    "peak_profit_pct"
                )
            ),
            0,
        )
        for t in closed
    )

    print()
    print(
        "=" * 70
    )

    print(
        "📊 PAPER TRADE İSTATİSTİKLERİ"
    )

    print(
        f"Toplam işlem: "
        f"{len(trades)}"
    )

    print(
        f"Açık işlem: "
        f"{len(opened)}"
    )

    print(
        f"Kapanmış işlem: "
        f"{len(closed)}"
    )

    print(
        f"Kazanan: "
        f"{len(winners)}"
    )

    print(
        f"Kaybeden: "
        f"{len(losers)}"
    )

    if closed:

        win_rate = (
            len(winners)
            / len(closed)
        ) * 100

        avg_profit = (
            net_pnl
            / len(closed)
        )

        avg_peak = (
            total_peak_profit
            / len(closed)
        )

        print(
            f"Win Rate: "
            f"{win_rate:.2f}%"
        )

        print(
            f"Ortalama sonuç: "
            f"{avg_profit:+.2f} TL"
        )

        print(
            f"Ortalama Peak: "
            f"+{avg_peak:.2f}%"
        )

    print(
        f"NET PAPER PNL: "
        f"{net_pnl:+.2f} TL"
    )

    print(
        f"Teorik açık sermaye: "
        f"{len(opened) * STAKE_TL:.2f} TL"
    )

    print(
        "=" * 70
    )


# ============================================================
# ANA
# ============================================================

def main():

    ensure_data_dir()

    print()
    print(
        "=" * 70
    )

    print(
        f"🚀 {PROJECT_NAME}"
    )

    print(
        "🔎 EARLY GEM RADAR v2"
    )

    print(
        "💰 100 TL PAPER TRADE"
    )

    print(
        "🧠 EARLYNESS SCORE AKTİF"
    )

    print(
        "🛡️ GELİŞMİŞ RİSK FİLTRESİ"
    )

    print(
        "=" * 70
    )

    print(
        f"Minimum likidite: "
        f"${MIN_LIQUIDITY_USD:,.0f}"
    )

    print(
        f"Minimum 24s hacim: "
        f"${MIN_VOLUME_24H_USD:,.0f}"
    )

    print(
        f"Paper stake: "
        f"{STAKE_TL:.2f} TL"
    )

    print(
        f"Hard stop: "
        f"-{HARD_STOP_PERCENT:.1f}%"
    )

    print(
        f"Trailing başlangıcı: "
        f"+{TRAIL_START_PERCENT:.1f}%"
    )

    # --------------------------------------------------------
    # PAPER TRADELERİ YÜKLE
    # --------------------------------------------------------

    trades = load_paper_trades()

    print(
        f"💾 Paper kayıtları: "
        f"{len(trades)}"
    )

    # --------------------------------------------------------
    # ÖNCE AÇIK İŞLEMLERİ GÜNCELLE
    # --------------------------------------------------------

    update_open_paper_trades(
        trades
    )

    # --------------------------------------------------------
    # STATE
    # --------------------------------------------------------

    previous_state = (
        load_radar_state()
    )

    # --------------------------------------------------------
    # PROFİLLER
    # --------------------------------------------------------

    print()
    print(
        "📡 DEX Screener verisi "
        "alınıyor..."
    )

    profiles = (
        get_latest_profiles()
    )

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
                profile,
                previous_state,
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

        time.sleep(
            0.15
        )

    # --------------------------------------------------------
    # DUPLICATE TEMİZLE
    # --------------------------------------------------------

    candidates = (
        deduplicate_candidates(
            candidates
        )
    )

    # --------------------------------------------------------
    # SKOR SIRALAMASI
    # --------------------------------------------------------

    candidates.sort(
        key=lambda x: (
            x["score"],
            x["earlyness_score"],
        ),
        reverse=True,
    )

    print()
    print(
        "=" * 70
    )

    print(
        f"🎯 UYGUN ADAY SAYISI: "
        f"{len(candidates)}"
    )

    print(
        "=" * 70
    )

    # --------------------------------------------------------
    # EN İYİ ADAYLAR
    # --------------------------------------------------------

    for candidate in candidates[:15]:

        print_candidate(
            candidate
        )

    # --------------------------------------------------------
    # PAPER TRADE AÇ
    # --------------------------------------------------------

    open_trades = get_open_trades(
        trades
    )

    open_count = len(
        open_trades
    )

    max_open_trades = 10

    new_trades = 0

    # Sadece gerçek AL ADAYI
    # ve güvenlik LOW olanlar
    for candidate in candidates:

        if open_count >= max_open_trades:

            break

        if candidate[
            "signal"
        ] != "🟢 AL ADAYI":

            continue

        # Çok sert düşen coin
        if candidate[
            "price_change_24h"
        ] <= -10:

            continue

        # Satıcı baskısı
        if candidate[
            "buy_ratio"
        ] < 0.45:

            continue

        # Çok yüksek vergi
        total_tax = (
            candidate[
                "buy_tax"
            ]
            +
            candidate[
                "sell_tax"
            ]
        )

        if total_tax >= 5:

            continue

        opened = open_paper_trade(
            candidate,
            trades,
        )

        if opened:

            open_count += 1
            new_trades += 1

    # --------------------------------------------------------
    # PAPER KAYDET
    # --------------------------------------------------------

    save_paper_trades(
        trades
    )

    # --------------------------------------------------------
    # CANDIDATES GEÇMİŞİ
    # --------------------------------------------------------

    save_candidates(
        candidates
    )

    # --------------------------------------------------------
    # RADAR STATE
    # --------------------------------------------------------

    update_radar_state(
        candidates
    )

    # --------------------------------------------------------
    # İSTATİSTİK
    # --------------------------------------------------------

    print_paper_statistics(
        trades
    )

    print()
    print(
        "=" * 70
    )

    print(
        "✅ TARAMA TAMAMLANDI"
    )

    print(
        f"Yeni paper işlem: "
        f"{new_trades}"
    )

    print(
        f"Açık paper işlem: "
        f"{len(get_open_trades(trades))}"
    )

    print(
        "📁 Paper kayıt: "
        f"{PAPER_TRADES_FILE}"
    )

    print(
        "📁 Radar state: "
        f"{RADAR_STATE_FILE}"
    )

    print(
        "🤖 Telegram: KAPALI"
    )

    print(
        "💰 Paper stake: "
        f"{STAKE_TL:.2f} TL"
    )

    print(
        "=" * 70
    )


if __name__ == "__main__":
    main()
