import json
import urllib.request
import urllib.parse
import urllib.error


EVM_URL = "https://api.gopluslabs.io/api/v1/token_security"
SOLANA_URL = "https://api.gopluslabs.io/api/v1/solana/token_security"


CHAINS = {
    "ethereum": "1",
    "bsc": "56",
    "polygon": "137",
    "arbitrum": "42161",
    "optimism": "10",
    "base": "8453",
    "avalanche": "43114",
    "robinhood": "4663",
    "robinhood-chain": "4663",
    "robinhood_chain": "4663",
}


def get_token(data):
    result = data.get("result")

    if not isinstance(result, dict):
        return None

    if "is_honeypot" in result:
        return result

    if "mintable" in result:
        return result

    for value in result.values():
        if isinstance(value, dict):
            return value

    return None


def true_value(value):
    if isinstance(value, dict):
        value = value.get("status")

    return str(value).lower() in ("1", "true", "yes")


def analyse(token, solana=False):
    if not token:
        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": "Token sonucu bulunamadı",
            "risks": [],
            "buy_tax": 0,
            "sell_tax": 0,
        }

    risks = []

    if solana:
        if true_value(token.get("mintable")):
            risks.append("MINT YETKİSİ")

        if true_value(token.get("freezable")):
            risks.append("FREEZE YETKİSİ")

        if true_value(token.get("closable")):
            risks.append("TOKEN KAPATILABİLİR")

        if true_value(token.get("metadata_mutable")):
            risks.append("METADATA DEĞİŞTİRİLEBİLİR")

        if true_value(token.get("transfer_fee_upgradable")):
            risks.append("TRANSFER FEE DEĞİŞTİRİLEBİLİR")

        if true_value(token.get("balance_mutable_authority")):
            risks.append("BALANCE MUTASYON YETKİSİ")

        if true_value(token.get("creator_malicious")):
            risks.append("KÖTÜ NİYETLİ CREATOR")

        if true_value(token.get("token_malicious")):
            risks.append("KÖTÜ NİYETLİ TOKEN")

        high = any(
            x in risks
            for x in [
                "MINT YETKİSİ",
                "FREEZE YETKİSİ",
                "BALANCE MUTASYON YETKİSİ",
                "KÖTÜ NİYETLİ CREATOR",
                "KÖTÜ NİYETLİ TOKEN",
            ]
        )

    else:
        if true_value(token.get("is_honeypot")):
            risks.append("HONEYPOT")

        if true_value(token.get("cannot_sell_all")):
            risks.append("SATIŞ KISITLAMASI")

        if true_value(token.get("cannot_buy")):
            risks.append("ALIM KISITLAMASI")

        if true_value(token.get("is_mintable")):
            risks.append("MINT YETKİSİ")

        if true_value(token.get("owner_change_balance")):
            risks.append("OWNER BAKİYE DEĞİŞTİREBİLİR")

        if true_value(token.get("hidden_owner")):
            risks.append("GİZLİ OWNER")

        if true_value(token.get("fake_token")):
            risks.append("FAKE TOKEN")

        buy_tax = float(token.get("buy_tax") or 0) * 100
        sell_tax = float(token.get("sell_tax") or 0) * 100

        if buy_tax >= 10:
            risks.append("YÜKSEK BUY TAX")

        if sell_tax >= 10:
            risks.append("YÜKSEK SELL TAX")

        high = any(
            x in risks
            for x in [
                "HONEYPOT",
                "SATIŞ KISITLAMASI",
                "ALIM KISITLAMASI",
                "MINT YETKİSİ",
                "OWNER BAKİYE DEĞİŞTİREBİLİR",
                "FAKE TOKEN",
            ]
        )

    if high:
        risk = "HIGH"
    elif risks:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return {
        "available": True,
        "risk": risk,
        "reason": "GoPlus güvenlik kontrolü tamamlandı",
        "risks": risks,
        "buy_tax": 0 if solana else buy_tax,
        "sell_tax": 0 if solana else sell_tax,
    }


def get_security(chain, token_address):

    chain = str(chain).lower().strip()

    try:

        query = urllib.parse.urlencode({
            "contract_addresses": token_address
        })

        if chain == "solana":

            url = f"{SOLANA_URL}?{query}"
            solana = True

        elif chain in CHAINS:

            url = f"{EVM_URL}/{CHAINS[chain]}?{query}"
            solana = False

        else:

            return {
                "available": False,
                "risk": "UNKNOWN",
                "reason": "Desteklenmeyen chain",
                "risks": [],
                "buy_tax": 0,
                "sell_tax": 0,
            }

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Early-Gem-Radar/1.0"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=15
        ) as response:

            data = json.loads(
                response.read().decode("utf-8")
            )

        return analyse(
            get_token(data),
            solana
        )

    except urllib.error.HTTPError as error:

        print(
            f"❌ GoPlus HTTP HATASI: {error.code}"
        )

        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": f"HTTP {error.code}",
            "risks": [],
            "buy_tax": 0,
            "sell_tax": 0,
        }

    except Exception as error:

        print(
            f"❌ GoPlus HATA: {error}"
        )

        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": str(error),
            "risks": [],
            "buy_tax": 0,
            "sell_tax": 0,
        }
