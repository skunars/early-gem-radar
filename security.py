# EARLY GEM RADAR - SECURITY ENGINE

import json
import urllib.request
import urllib.parse


GOPLUS_BASE_URL = "https://api.gopluslabs.io/api/v1/token_security"
GOPLUS_SOLANA_URL = "https://api.gopluslabs.io/api/v1/solana/token_security"


# ---------------------------------------------------------
# YARDIMCI FONKSİYONLAR
# ---------------------------------------------------------

def value_is_true(value):
    """
    GoPlus bazı boolean değerleri:
    "1", 1, True gibi döndürebilir.
    """
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
    """
    Solana GoPlus bazı alanları obje şeklinde döndürür:

    {
        "status": "1",
        ...
    }

    Bu fonksiyon hem obje hem de normal boolean/string
    değerleri destekler.
    """

    if isinstance(value, dict):
        return value_is_true(value.get("status"))

    return value_is_true(value)


def get_result(data):
    """
    GoPlus cevabından result alanını güvenli şekilde alır.
    """

    if not isinstance(data, dict):
        return None

    result = data.get("result")

    if isinstance(result, dict):
        return result

    return None


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


# ---------------------------------------------------------
# EVM SECURITY
# ---------------------------------------------------------

def analyze_evm_security(data):
    """
    EVM GoPlus Token Security analizi.
    """

    result = get_result(data)

    if not result:
        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": "GoPlus result bulunamadı",
            "risks": [],
            "buy_tax": 0,
            "sell_tax": 0,
        }

    # GoPlus bazen adresi lowercase döndürebilir.
    # İlk/tek result kaydını al.
    if not any(
        key in result
        for key in [
            "is_honeypot",
            "cannot_sell_all",
            "is_mintable",
            "buy_tax",
            "sell_tax",
            "is_open_source",
        ]
    ):
        try:
            first_value = next(iter(result.values()))

            if isinstance(first_value, dict):
                result = first_value

        except Exception:
            pass

    risks = []

    # -----------------------------------------------------
    # HONEYPOT / SELL RISK
    # -----------------------------------------------------

    if value_is_true(result.get("is_honeypot")):
        risks.append("HONEYPOT")

    if value_is_true(result.get("cannot_sell_all")):
        risks.append("SATIŞ KISITLAMASI")

    if value_is_true(result.get("cannot_buy")):
        risks.append("ALIM KISITLAMASI")

    # -----------------------------------------------------
    # BLACKLIST
    # -----------------------------------------------------

    if value_is_true(result.get("is_blacklisted")):
        risks.append("BLACKLIST RİSKİ")

    if value_is_true(result.get("transfer_pausable")):
        risks.append("TRANSFER DURDURULABİLİR")

    # -----------------------------------------------------
    # MINT / OWNER
    # -----------------------------------------------------

    if value_is_true(result.get("is_mintable")):
        risks.append("MINT YETKİSİ")

    if value_is_true(result.get("owner_change_balance")):
        risks.append("OWNER BAKİYE DEĞİŞTİREBİLİR")

    if value_is_true(result.get("hidden_owner")):
        risks.append("GİZLİ OWNER")

    if value_is_true(result.get("can_take_back_ownership")):
        risks.append("OWNER GERİ ALINABİLİR")

    # -----------------------------------------------------
    # CONTRACT / SOURCE
    # -----------------------------------------------------

    if "is_open_source" in result:
        if not value_is_true(result.get("is_open_source")):
            risks.append("KAYNAK KODU AÇIK DEĞİL")

    if value_is_true(result.get("is_proxy")):
        risks.append("PROXY CONTRACT")

    # -----------------------------------------------------
    # TAX
    # -----------------------------------------------------

    buy_tax_raw = safe_float(result.get("buy_tax", 0))
    sell_tax_raw = safe_float(result.get("sell_tax", 0))

    # GoPlus tax değerleri 0-1 aralığında gelir.
    buy_tax = buy_tax_raw * 100
    sell_tax = sell_tax_raw * 100

    if buy_tax >= 10:
        risks.append(f"YÜKSEK BUY TAX %{buy_tax:.1f}")

    if sell_tax >= 10:
        risks.append(f"YÜKSEK SELL TAX %{sell_tax:.1f}")

    if buy_tax >= 20:
        risks.append("ÇOK YÜKSEK BUY TAX")

    if sell_tax >= 20:
        risks.append("ÇOK YÜKSEK SELL TAX")

    # -----------------------------------------------------
    # FAKE / AIRDROP / OTHER RISKS
    # -----------------------------------------------------

    if value_is_true(result.get("fake_token")):
        risks.append("FAKE TOKEN")

    if value_is_true(result.get("is_airdrop_scam")):
        risks.append("AIRDROP SCAM")

    other_risks = result.get("other_potential_risks")

    if other_risks:
        if isinstance(other_risks, str):
            risks.append(f"EK RİSK: {other_risks}")

    # -----------------------------------------------------
    # HOLDER CONCENTRATION
    # -----------------------------------------------------

    top_holder_percent = 0.0
    top5_percent = 0.0

    holder_list = result.get("holders")

    if isinstance(holder_list, list):

        percentages = []

        for holder in holder_list:

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
    # RISK SEVİYESİ
    # -----------------------------------------------------

    high_risk_words = {
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

    has_high_risk = any(
        any(word in risk for word in high_risk_words)
        for risk in risks
    )

    if has_high_risk:
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


# ---------------------------------------------------------
# SOLANA SECURITY
# ---------------------------------------------------------

def analyze_solana_security(data):
    """
    Solana GoPlus Token Security analizi.
    """

    result = get_result(data)

    if not result:
        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": "GoPlus Solana result bulunamadı",
            "risks": [],
            "buy_tax": 0,
            "sell_tax": 0,
        }

    # -----------------------------------------------------
    # Result içindeki token kaydını bul
    # -----------------------------------------------------

    token_data = result

    if not any(
        key in result
        for key in [
            "mintable",
            "freezable",
