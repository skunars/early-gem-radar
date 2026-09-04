import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


GOPLUS_URL = (
    "https://api.gopluslabs.io/api/v1/token_security"
)


def api_get(url):
    try:
        request = Request(
            url,
            headers={
                "User-Agent": "EarlyGemRadar/1.0",
                "Accept": "application/json",
            },
        )

        with urlopen(request, timeout=20) as response:
            return json.loads(
                response.read().decode("utf-8")
            )

    except HTTPError as e:
        print(f"❌ GoPlus HTTP hatası: {e.code}")
        return None

    except URLError as e:
        print(
            f"❌ GoPlus bağlantı hatası: "
            f"{e.reason}"
        )
        return None

    except Exception as e:
        print(f"❌ GoPlus hatası: {e}")
        return None


def get_security(chain_id, token_address):
    """
    Token güvenlik bilgilerini alır.

    Ethereum tabanlı ağlarda chain_id,
    GoPlus tarafından kullanılan zincir ID'si
    olmalıdır.
    """

    # Solana için bu ilk sürümde
    # EVM güvenlik API'sini kullanmıyoruz.
    if chain_id == "solana":
        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": "Solana güvenlik kontrolü henüz eklenmedi.",
        }

    # DEX Screener'daki bazı chain isimlerini
    # GoPlus chain ID'lerine çevir.
    chain_map = {
        "ethereum": "1",
        "bsc": "56",
        "arbitrum": "42161",
        "polygon": "137",
        "base": "8453",
        "optimism": "10",
        "avalanche": "43114",
    }

    goplus_chain = chain_map.get(chain_id)

    if not goplus_chain:
        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": f"Desteklenmeyen chain: {chain_id}",
        }

    url = (
        f"{GOPLUS_URL}"
        f"?chain_id={goplus_chain}"
        f"&contract_addresses={token_address}"
    )

    data = api_get(url)

    if not data:
        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": "Güvenlik API'sinden veri alınamadı.",
        }

    result = (
        data
        .get("result", {})
        .get(token_address.lower())
    )

    if result is None:
        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": "Token güvenlik verisi bulunamadı.",
        }

    risks = []

    def is_true(key):
        return str(
            result.get(key, "0")
        ).lower() in (
            "1",
            "true",
        )

    # Kritik riskler
    if is_true("is_honeypot"):
        risks.append("HONEYPOT")

    if is_true("cannot_sell_all"):
        risks.append("SATIŞ KISITLAMASI")

    if is_true("is_blacklisted"):
        risks.append("BLACKLIST")

    if is_true("is_mintable"):
        risks.append("MINT YETKİSİ")

    if is_true("is_proxy"):
        risks.append("PROXY KONTRAT")

    if is_true("is_anti_whale"):
        risks.append("ANTI-WHALE")

    # Vergiler
    buy_tax = result.get("buy_tax")
    sell_tax = result.get("sell_tax")

    try:
        buy_tax_value = float(buy_tax or 0)
    except (ValueError, TypeError):
        buy_tax_value = 0

    try:
        sell_tax_value = float(sell_tax or 0)
    except (ValueError, TypeError):
        sell_tax_value = 0

    if buy_tax_value >= 10:
        risks.append(
            f"YÜKSEK BUY TAX %{buy_tax_value:.1f}"
        )

    if sell_tax_value >= 10:
        risks.append(
            f"YÜKSEK SELL TAX %{sell_tax_value:.1f}"
        )

    # Owner / yönetim riskleri
    if is_true("owner_change_balance"):
        risks.append("OWNER BALANCE DEĞİŞTİREBİLİR")

    if is_true("can_take_back_ownership"):
        risks.append("OWNER GERİ ALINABİLİR")

    if is_true("hidden_owner"):
        risks.append("GİZLİ OWNER")

    if risks:
        risk_level = "HIGH"
    else:
        risk_level = "LOW"

    return {
        "available": True,
        "risk": risk_level,
        "risks": risks,
        "buy_tax": buy_tax_value,
        "sell_tax": sell_tax_value,
        "raw": result,
    }
