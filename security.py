# EARLY GEM RADAR - SECURITY ENGINE

import json
import urllib.request
import urllib.parse
import urllib.error


GOPLUS_BASE_URL = "https://api.gopluslabs.io/api/v1/token_security"
GOPLUS_SOLANA_URL = "https://api.gopluslabs.io/api/v1/solana/token_security"


# =========================================================
# YARDIMCI FONKSİYONLAR
# =========================================================

def value_is_true(value):
    if value is True:
        return True

    if value is False or value is None:
        return False

    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
    }


def structured_status_is_true(value):
    if isinstance(value, dict):
        return value_is_true(value.get("status"))

    return value_is_true(value)


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def get_result(data):
    if not isinstance(data, dict):
        return None

    result = data.get("result")

    if isinstance(result, dict):
        return result

    return None


def get_token_data(result):
    """
    GoPlus result bazen doğrudan token verisini,
    bazen de adres -> token verisi şeklinde döndürür.
    """

    if not isinstance(result, dict):
        return None

    known_keys = {
        "is_honeypot",
        "is_mintable",
        "mintable",
        "freezable",
        "closable",
        "metadata_mutable",
        "buy_tax",
        "sell_tax",
    }

    # Doğrudan token datası
    if any(key in result for key in known_keys):
        return result

    # Adres -> token datası
    for value in result.values():
        if isinstance(value, dict):
            return value

    return None


# =========================================================
# EVM ANALİZİ
# =========================================================

def analyze_evm_security(data):

    result = get_result(data)
    token = get_token_data(result)

    if not token:
        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": "GoPlus token sonucu bulunamadı",
            "risks": [],
            "buy_tax": 0,
            "sell_tax": 0,
        }

    risks = []

    # -----------------------------------------------------
    # HONEYPOT / SATIŞ
    # -----------------------------------------------------

    if value_is_true(token.get("is_honeypot")):
        risks.append("HONEYPOT")

    if value_is_true(token.get("cannot_sell_all")):
        risks.append("SATIŞ KISITLAMASI")

    if value_is_true(token.get("cannot_buy")):
        risks.append("ALIM KISITLAMASI")

    # -----------------------------------------------------
    # BLACKLIST
    # -----------------------------------------------------

    if value_is_true(token.get("is_blacklisted")):
        risks.append("BLACKLIST RİSKİ")

    if value_is_true(token.get("transfer_pausable")):
        risks.append("TRANSFER DURDURULABİLİR")

    # -----------------------------------------------------
    # MINT / OWNER
    # -----------------------------------------------------

    if value_is_true(token.get("is_mintable")):
        risks.append("MINT YETKİSİ")

    if value_is_true(token.get("owner_change_balance")):
        risks.append("OWNER BAKİYE DEĞİŞTİREBİLİR")

    if value_is_true(token.get("hidden_owner")):
        risks.append("GİZLİ OWNER")

    if value_is_true(token.get("can_take_back_ownership")):
        risks.append("OWNER GERİ ALINABİLİR")

    # -----------------------------------------------------
    # CONTRACT
    # -----------------------------------------------------

    if "is_open_source" in token:
        if not value_is_true(token.get("is_open_source")):
            risks.append("KAYNAK KODU AÇIK DEĞİL")

    if value_is_true(token.get("is_proxy")):
        risks.append("PROXY CONTRACT")

    # -----------------------------------------------------
    # TAX
    # -----------------------------------------------------

    buy_tax_raw = safe_float(token.get("buy_tax", 0))
    sell_tax_raw = safe_float(token.get("sell_tax", 0))

    buy_tax = buy_tax_raw * 100
    sell_tax = sell_tax_raw * 100

    if buy_tax >= 10:
        risks.append(
            f"YÜKSEK BUY TAX %{buy_tax:.1f}"
        )

    if sell_tax >= 10:
        risks.append(
            f"YÜKSEK SELL TAX %{sell_tax:.1f}"
        )

    if buy_tax >= 20:
        risks.append("ÇOK YÜKSEK BUY TAX")

    if sell_tax >= 20:
        risks.append("ÇOK YÜKSEK SELL TAX")

    # -----------------------------------------------------
    # FAKE / SCAM
    # -----------------------------------------------------

    if value_is_true(token.get("fake_token")):
        risks.append("FAKE TOKEN")

    if value_is_true(token.get("is_airdrop_scam")):
        risks.append("AIRDROP SCAM")

    # -----------------------------------------------------
    # HOLDER YOĞUNLUĞU
    # -----------------------------------------------------

    top_holder_percent = 0.0
    top5_percent = 0.0

    holders = token.get("holders")

    if isinstance(holders, list):

        percentages = []

        for holder in holders:

            if not isinstance(holder, dict):
                continue

            percent = safe_float(
                holder.get("percent"),
                0
            )

            if percent > 0:
                percentages.append(percent)

        percentages.sort(reverse=True)

        if percentages:
            top_holder_percent = percentages[0]

        if percentages:
            top5_percent = sum(percentages[:5])

    if top_holder_percent >= 0.30:
        risks.append(
            f"TOP HOLDER %{top_holder_percent * 100:.1f}"
        )

    if top5_percent >= 0.50:
        risks.append(
            f"TOP 5 HOLDER %{top5_percent * 100:.1f}"
        )

    # -----------------------------------------------------
    # RİSK SEVİYESİ
    # -----------------------------------------------------

    high_risk_items = {
        "HONEYPOT",
        "SATIŞ KISITLAMASI",
        "ALIM KISITLAMASI",
        "BLACKLIST RİSKİ",
        "MINT YETKİSİ",
        "OWNER BAKİYE DEĞİŞTİREBİLİR",
        "FAKE TOKEN",
        "AIRDROP SCAM",
        "ÇOK YÜKSEK BUY TAX",
        "ÇOK YÜKSEK SELL TAX",
    }

    high_risk = False

    for risk_text in risks:
        for high_item in high_risk_items:
            if high_item in risk_text:
                high_risk = True
                break

        if high_risk:
            break

    if high_risk:
        risk_level = "HIGH"
    elif risks:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return {
        "available": True,
        "risk": risk_level,
        "reason": "GoPlus EVM security analizi tamamlandı",
        "risks": risks,
        "buy_tax": buy_tax,
        "sell_tax": sell_tax,
        "top_holder_percent": top_holder_percent,
        "top5_percent": top5_percent,
    }


# =========================================================
# SOLANA ANALİZİ
# =========================================================

def analyze_solana_security(data):

    result = get_result(data)
    token = get_token_data(result)

    if not token:
        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": "GoPlus Solana token sonucu bulunamadı",
            "risks": [],
            "buy_tax": 0,
            "sell_tax": 0,
        }

    risks = []

    # -----------------------------------------------------
    # MINT
    # -----------------------------------------------------

    if structured_status_is_true(
        token.get("mintable")
    ):
        risks.append("MINT YETKİSİ")

    # -----------------------------------------------------
    # FREEZE
    # -----------------------------------------------------

    if structured_status_is_true(
        token.get("freezable
