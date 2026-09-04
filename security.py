import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


GOPLUS_BASE_URL = "https://api.gopluslabs.io/api/v1/token_security"
GOPLUS_SOLANA_URL = "https://api.gopluslabs.io/api/v1/solana/token_security"

USER_AGENT = "EarlyGemRadar/1.0"


def api_get(url):
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
        print(f"GoPlus HTTP hatasi: {e.code}")
        return None

    except URLError as e:
        print(f"GoPlus baglanti hatasi: {e.reason}")
        return None

    except Exception as e:
        print(f"GoPlus hatasi: {e}")
        return None


def get_security(chain_id, token_address):

    # SOLANA
    if chain_id == "solana":

        url = (
            f"{GOPLUS_SOLANA_URL}"
            f"?contract_addresses={token_address}"
        )

        data = api_get(url)

        if not data:
            return {
                "available": False,
                "risk": "UNKNOWN",
                "reason": "GoPlus Solana API'den veri alinamadi.",
            }

        result_data = data.get("result", {})

        result = None

        if isinstance(result_data, dict):

            result = result_data.get(token_address)

            if result is None:
                for address, value in result_data.items():
                    if address.lower() == token_address.lower():
                        result = value
                        break

        if result is None:
            return {
                "available": False,
                "risk": "UNKNOWN",
                "reason": "Solana token guvenlik verisi bulunamadi.",
            }

        risks = []

        def solana_true(key):
            return str(
                result.get(key, "0")
            ).lower() in ("1", "true")

        if solana_true("is_honeypot"):
            risks.append("HONEYPOT")

        if solana_true("is_mintable"):
            risks.append("MINT YETKISI")

        if solana_true("is_freezeable"):
            risks.append("FREEZE YETKISI")

        if solana_true("is_blacklisted"):
            risks.append("BLACKLIST")

        if solana_true("is_token2022"):
            risks.append("TOKEN-2022")

        if solana_true("is_locked"):
            risks.append("LOCKED")

        critical_risks = {
            "HONEYPOT",
            "MINT YETKISI",
            "FREEZE YETKISI",
            "BLACKLIST",
        }

        if any(
            risk in critical_risks
            for risk in risks
        ):
            risk_level = "HIGH"

        elif risks:
            risk_level = "MEDIUM"

        else:
            risk_level = "LOW"

        return {
            "available": True,
            "risk": risk_level,
            "risks": risks,
            "buy_tax": 0,
            "sell_tax": 0,
            "raw": result,
        }

    # EVM CHAINLER
    chain_map = {
        "ethereum": "1",
        "bsc": "56",
        "arbitrum": "42161",
        "polygon": "137",
        "base": "8453",
        "optimism": "10",
        "avalanche": "43114",
        "robinhood": "4663",
    }

    goplus_chain = chain_map.get(chain_id)

    if not goplus_chain:
        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": f"Desteklenmeyen chain: {chain_id}",
        }

    url = (
        f"{GOPLUS_BASE_URL}/{goplus_chain}"
        f"?contract_addresses={token_address}"
    )

    data = api_get(url)

    if not data:
        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": "GoPlus API'den veri alinamadi.",
        }

    result_data = data.get("result", {})

    result = None

    if isinstance(result_data, dict):

        result = result_data.get(
            token_address.lower()
        )

        if result is None:
            for address, value in result_data.items():
                if address.lower() == token_address.lower():
                    result = value
                    break

    if result is None:
        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": "Token guvenlik verisi bulunamadi.",
        }

    risks = []

    def is_true(key):
        return str(
            result.get(key, "0")
        ).lower() in ("1", "true")

    if is_true("is_honeypot"):
        risks.append("HONEYPOT")

    if is_true("cannot_sell_all"):
        risks.append("SATIS KISITLAMASI")

    if is_true("is_blacklisted"):
        risks.append("BLACKLIST")

    if is_true("is_mintable"):
        risks.append("MINT YETKISI")

    if is_true("hidden_owner"):
        risks.append("GIZLI OWNER")

    if is_true("can_take_back_ownership"):
        risks.append("OWNER GERI ALABILIR")

    if is_true("owner_change_balance"):
        risks.append(
            "OWNER BALANCE DEGISTIREBILIR"
        )

    try:
        buy_tax = float(
            result.get("buy_tax", 0) or 0
        )
    except (ValueError, TypeError):
        buy_tax = 0

    try:
        sell_tax = float(
            result.get("sell_tax", 0) or 0
        )
    except (ValueError, TypeError):
        sell_tax = 0

    if buy_tax >= 10:
        risks.append(
            f"YUKSEK BUY TAX %{buy_tax:.1f}"
        )

    if sell_tax >= 10:
        risks.append(
            f"YUKSEK SELL TAX %{sell_tax:.1f}"
        )

    critical_risks = {
        "HONEYPOT",
        "SATIS KISITLAMASI",
        "BLACKLIST",
        "MINT YETKISI",
        "GIZLI OWNER",
        "OWNER GERI ALABILIR",
        "OWNER BALANCE DEGISTIREBILIR",
    }

    if any(
        risk in critical_risks
        for risk in risks
    ):
        risk_level = "HIGH"

    elif risks:
        risk_level = "MEDIUM"

    else:
        risk_level = "LOW"

    return {
        "available": True,
        "risk": risk_level,
        "risks": risks,
        "buy_tax": buy_tax,
        "sell_tax": sell_tax,
        "raw": result,
    }
