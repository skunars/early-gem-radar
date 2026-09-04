import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


GOPLUS_BASE_URL = (
    "https://api.gopluslabs.io/api/v1/token_security"
)


USER_AGENT = "EarlyGemRadar/1.0"


def api_get(url):
    """GoPlus API'den JSON veri al."""

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
            timeout=20
        ) as response:

            return json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

    except HTTPError as e:

        print(
            f"❌ GoPlus HTTP hatası: "
            f"{e.code}"
        )

        return None

    except URLError as e:

        print(
            f"❌ GoPlus bağlantı hatası: "
            f"{e.reason}"
        )

        return None

    except Exception as e:

        print(
            f"❌ GoPlus hatası: "
            f"{e}"
        )

        return None


def get_security(
    chain_id,
    token_address
):
    """
    Token güvenlik bilgilerini GoPlus'tan alır.
    """

    # DEX Screener chain ID
    # -> GoPlus chain ID
    chain_map = {

        "ethereum": "1",

        "bsc": "56",

        "arbitrum": "42161",

        "polygon": "137",

        "base": "8453",

        "optimism": "10",

        "avalanche": "43114",

        # Robinhood Chain
        "robinhood": "4663",
    }

    # Solana şimdilik ayrı ele alınacak.
    if chain_id == "solana":

        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": (
                "Solana güvenlik kontrolü "
                "bir sonraki aşamada eklenecek."
            ),
        }

    goplus_chain = chain_map.get(
        chain_id
    )

    if not goplus_chain:

        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": (
                f"Desteklenmeyen chain: "
                f"{chain_id}"
            ),
        }

    # Güncel GoPlus endpoint
    url = (
        f"{GOPLUS_BASE_URL}/"
        f"{goplus_chain}"
        f"?contract_addresses="
        f"{token_address}"
    )

    data = api_get(url)

    if not data:

        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": (
                "GoPlus API'den veri alınamadı."
            ),
        }

    result = (
        data
        .get("result", {})
        .get(token_address.lower())
    )

    if result is None:

        # Bazı API cevaplarında adres
        # farklı büyük/küçük harf olabilir.
        result = None

        for address, value in (
            data
            .get("result", {})
            .items()
        ):

            if (
                address.lower()
                == token_address.lower()
            ):

                result = value
                break

    if result is None:

        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": (
                "Token güvenlik verisi "
                "bulunamadı."
            ),
        }

    risks = []

    def is_true(key):

        return str(
            result.get(
                key,
                "0"
            )
        ).lower() in (
            "1",
            "true",
        )

    # ==================================================
    # KRİTİK GÜVENLİK KONTROLLERİ
    # ==================================================

    if is_true("is_honeypot"):

        risks.append(
            "HONEYPOT"
        )

    if is_true("cannot_sell_all"):

        risks.append(
            "SATIŞ KISITLAMASI"
        )

    if is_true("is_blacklisted"):

        risks.append(
            "BLACKLIST"
        )

    if is_true("is_mintable"):

        risks.append(
            "MINT YETKİSİ"
        )

    if is_true("hidden_owner"):

        risks.append(
            "GİZLİ OWNER"
        )

    if is_true(
        "can_take_back_ownership"
    ):

        risks.append(
            "OWNER GERİ ALABİLİR"
        )

    if is_true(
        "owner_change_balance"
    ):

        risks.append(
            "OWNER BALANCE DEĞİŞTİREBİLİR"
        )

    # Proxy tek başına scam demek değildir.
    # Bu nedenle kritik risk listesine
    # eklemiyoruz.

    # Anti-whale de tek başına scam
    # göstergesi değildir.

    # ==================================================
    # VERGİ KONTROLÜ
    # ==================================================

    try:

        buy_tax = float(
            result.get(
                "buy_tax",
                0
            ) or 0
        )

    except (
        ValueError,
        TypeError
    ):

        buy_tax = 0

    try:

        sell_tax = float(
            result.get(
                "sell_tax",
                0
            ) or 0
        )

    except (
        ValueError,
        TypeError
    ):

        sell_tax = 0

    if buy_tax >= 10:

        risks.append(
            f"YÜKSEK BUY TAX "
            f"%{buy_tax:.1f}"
        )

    if sell_tax >= 10:

        risks.append(
            f"YÜKSEK SELL TAX "
            f"%{sell_tax:.1f}"
        )

    # ==================================================
    # RİSK SEVİYESİ
    # ==================================================

    critical_risks = [
        "HONEYPOT",
        "SATIŞ KISITLAMASI",
        "BLACKLIST",
        "MINT YETKİSİ",
        "GİZLİ OWNER",
        "OWNER GERİ ALABİLİR",
        "OWNER BALANCE DEĞİŞTİREBİLİR",
    ]

    has_critical_risk = any(
        risk in critical_risks
        for risk in risks
    )

    if
