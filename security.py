import json
import urllib.request
import urllib.parse
import urllib.error


GOPLUS_EVM = "https://api.gopluslabs.io/api/v1/token_security"
GOPLUS_SOLANA = "https://api.gopluslabs.io/api/v1/solana/token_security"


def is_true(value):
    if isinstance(value, dict):
        value = value.get("status")

    return str(value).lower() in ("1", "true", "yes")


def number(value):
    try:
        return float(value)
    except Exception:
        return 0.0


def token_result(data):
    result = data.get("result")

    if not isinstance(result, dict):
        return None

    keys = {
        "is_honeypot",
        "is_mintable",
        "mintable",
        "freezable",
        "closable",
        "buy_tax",
        "sell_tax",
    }

    if any(key in result for key in keys):
        return result

    for value in result.values():
        if isinstance(value, dict):
            return value

    return None


def analyze_evm(data):
    token = token_result(data)

    if not token:
        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": "GoPlus sonucu bulunamadı",
            "risks": [],
            "buy_tax": 0,
            "sell_tax": 0,
        }

    risks = []

    if is_true(token.get("is_honeypot")):
        risks.append("HONEYPOT")

    if is_true(token.get("cannot_sell_all")):
        risks.append("SATIŞ KISITLAMASI")

    if is_true(token.get("cannot_buy")):
        risks.append("ALIM KISITLAMASI")

    if is_true(token.get("is_blacklisted")):
        risks.append("BLACKLIST")

    if is_true(token.get("is_mintable")):
        risks.append("MINT YETKİSİ")

    if is_true(token.get("owner_change_balance")):
        risks.append("OWNER BAKİYE DEĞİŞTİREBİLİR")

    if is_true(token.get("hidden_owner")):
        risks.append("GİZLİ OWNER")

    if is_true(token.get("can_take_back_ownership")):
        risks.append("OWNER GERİ ALINABİLİR")

    if "is_open_source" in token:
        if not is_true(token.get("is_open_source")):
            risks.append("KAYNAK KODU AÇIK DEĞİL")

    if is_true(token.get("is_proxy")):
        risks.append("PROXY CONTRACT")

    buy_tax = number(token.get("buy_tax")) * 100
    sell_tax = number(token.get("sell_tax")) * 100

    if buy_tax >= 10:
        risks.append("YÜKSEK BUY TAX")

    if sell_tax >= 10:
        risks.append("YÜKSEK SELL TAX")

    if is_true(token.get("fake_token")):
        risks.append("FAKE TOKEN")

    if is_true(token.get("is_airdrop_scam")):
        risks.append("AIRDROP SCAM")

    if "HONEYPOT" in risks:
        risk = "HIGH"
    elif "SATIŞ KISITLAMASI" in risks:
        risk = "HIGH"
    elif "ALIM KISITLAMASI" in risks:
        risk = "HIGH"
    elif "MINT YETKİSİ" in risks:
        risk = "HIGH"
    elif "FAKE TOKEN" in risks:
        risk = "HIGH"
    elif "AIRDROP SCAM" in risks:
        risk = "HIGH"
    elif risks:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return {
        "available": True,
        "risk": risk,
        "reason": "GoPlus EVM güvenlik kontrolü tamamlandı",
        "risks": risks,
        "buy_tax": buy_tax,
        "sell_tax": sell_tax,
    }


def analyze_solana(data):
    token = token_result(data)

    if not token:
        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": "GoPlus Solana sonucu bulunamadı",
            "risks": [],
            "buy_tax": 0,
            "sell_tax": 0,
        }

    risks = []

    if is_true(token.get("mintable")):
        risks.append("MINT YETKİSİ")

    if is_true(token.get("freezable")):
        risks.append("FREEZE YETKİSİ")

    if is_true(token.get("closable")):
        risks.append("TOKEN KAPATILABİLİR")

    if is_true(token.get("metadata_mutable")):
        risks.append("METADATA DEĞİŞTİRİLEBİLİR")

    if is_true(token.get("transfer_fee_upgradable")):
        risks.append("TRANSFER FEE DEĞİŞTİRİLEBİLİR")

    if is_true(token.get("default_account_state_upgradable")):
        risks.append("ACCOUNT STATE DEĞİŞTİRİLEBİLİR")

    if is_true(token.get("balance_mutable_authority")):
        risks.append("BALANCE MUTASYON YETKİSİ")

    if is_true(token.get("transfer_hook_upgradable")):
        risks.append("TRANSFER HOOK DEĞİŞTİRİLEBİLİR")

    if is_true(token.get("non_transferable")):
        risks.append("NON-TRANSFERABLE")

    if is_true(token.get("creator_malicious")):
        risks.append("KÖTÜ NİYETLİ CREATOR")

    if is_true(token.get("token_malicious")):
        risks.append("KÖTÜ NİYETLİ TOKEN")

    high_risks = {
        "MINT YETKİSİ",
        "FREEZE YETKİSİ",
        "BALANCE MUTASYON YETKİSİ",
        "KÖTÜ NİYETLİ CREATOR",
        "KÖTÜ NİYETLİ TOKEN",
    }

    if any(item in high_risks for item in risks):
        risk = "HIGH"
    elif risks:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    return {
        "available": True,
        "risk": risk,
        "reason": "GoPlus Solana güvenlik kontrolü tamamlandı",
        "risks": risks,
        "buy_tax": 0,
        "sell_tax": 0,
    }


def get_security(chain, token_address):

    chain = str(chain).lower().strip()
    token_address = str(token_address).strip()

    evm_chains = {
        "ethereum": "1",
        "bsc": "56",
        "polygon": "137",
        "arbitrum": "42161",
        "optimism": "10",
        "base": "8453",
        "avalanche": "43114",
        "fantom": "250",
        "linea": "59144",
        "scroll": "534352",
        "blast": "81457",
        "zksync": "324",
        "mantle": "5000",
        "mode": "34443",
        "robinhood": "4663",
        "robinhood-chain": "4663",
        "robinhood_chain": "4663",
    }

    try:

        params = urllib.parse.urlencode({
            "contract_addresses": token_address
        })

        if chain == "solana":

            url = f"{GOPLUS_SOLANA}?{params}"

            parser = analyze_solana

        elif chain in evm_chains:

            chain_id = evm_chains[chain]

            url = f"{GOPLUS_EVM}/{chain_id}?{params}"

            parser = analyze_evm

        else:

            return {
                "available": False,
                "risk": "UNKNOWN",
                "reason": f"Desteklenmeyen chain: {chain}",
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

            if response.status != 200:

                return {
                    "available": False,
                    "risk": "UNKNOWN",
                    "reason": f"HTTP {response.status}",
                    "risks": [],
                    "buy_tax": 0,
                    "sell_tax": 0,
                }

            raw
