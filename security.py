import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


GOPLUS_BASE_URL = (
    "https://api.gopluslabs.io/api/v1/token_security"
)

GOPLUS_SOLANA_URL = (
    "https://api.gopluslabs.io/api/v1/solana/token_security"
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
            f"❌ GoPlus HTTP HATASI: "
            f"{e.code}"
        )

        return None

    except URLError as e:

        print(
            f"❌ GoPlus BAĞLANTI HATASI: "
            f"{e.reason}"
        )

        return None

    except Exception as e:

        print(
            f"❌ GoPlus API HATASI: "
            f"{e}"
        )

        return None


def value_is_true(value):
    """
    Basit True/False alanlarını kontrol eder.
    """

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value == 1

    if isinstance(value, str):

        return value.lower() in (
            "1",
            "true",
            "yes",
            "y",
        )

    return False


def structured_status_is_true(value):
    """
    Solana GoPlus alanları çoğunlukla:

    {
        "status": "1",
        ...
    }

    şeklindedir.

    Hem yapılandırılmış hem basit
    True/False formatını destekler.
    """

    if isinstance(value, dict):

        return value_is_true(
            value.get("status")
        )

    return value_is_true(value)


def get_result(data, token_address):
    """
    GoPlus response içindeki token sonucunu bul.
    """

    if not isinstance(data, dict):
        return None

    result = data.get(
        "result",
        {}
    )

    if not isinstance(result, dict):
        return None

    # Adres doğrudan key olabilir.
    if token_address in result:

        return result[
            token_address
        ]

    # Büyük/küçük harf farkına karşı.
    token_lower = token_address.lower()

    for address, value in result.items():

        if str(address).lower() == token_lower:

            return value

    # Bazı response'larda result
    # doğrudan token objesi olabilir.
    if (
        "token_name" in result
        or "token_symbol" in result
        or "mintable" in result
        or "is_honeypot" in result
    ):

        return result

    return None


def analyze_evm_security(result):
    """
    EVM token güvenlik analizi.

    GoPlus EVM Token Security API.
    """

    risks = []

    if not isinstance(result, dict):

        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": "Geçersiz API sonucu",
            "risks": [],
            "buy_tax": 0,
            "sell_tax": 0,
        }

    # --------------------------------------------------
    # KRİTİK KONTROLLER
    # --------------------------------------------------

    if value_is_true(
        result.get("is_honeypot")
    ):

        risks.append(
            "HONEYPOT"
        )

    if value_is_true(
        result.get("cannot_sell_all")
    ):

        risks.append(
            "SATIŞ KISITLAMASI"
        )

    if value_is_true(
        result.get("cannot_buy")
    ):

        risks.append(
            "ALIŞ KISITLAMASI"
        )

    if value_is_true(
        result.get("is_blacklisted")
    ):

        risks.append(
            "BLACKLIST"
        )

    if value_is_true(
        result.get("is_mintable")
    ):

        risks.append(
            "MINT YETKİSİ"
        )

    if value_is_true(
        result.get("owner_change_balance")
    ):

        risks.append(
            "OWNER BAKİYE DEĞİŞTİREBİLİR"
        )

    if value_is_true(
        result.get("hidden_owner")
    ):

        risks.append(
            "GİZLİ OWNER"
        )

    if value_is_true(
        result.get(
            "can_take_back_ownership"
        )
    ):

        risks.append(
            "OWNERSHIP GERİ ALINABİLİR"
        )

    # --------------------------------------------------
    # VERGİ
    # --------------------------------------------------

    buy_tax = 0
    sell_tax = 0

    try:
        buy_tax = float(
            result.get(
                "buy_tax",
                0
            ) or 0
        )
    except Exception:
        buy_tax = 0

    try:
        sell_tax = float(
            result.get(
                "sell_tax",
                0
            ) or 0
        )
    except Exception:
        sell_tax = 0

    # GoPlus vergi değerleri
    # 0-1 aralığında olabilir.
    #
    # 0.10 = %10
    # 1.00 = %100

    if buy_tax >= 0.10:

        risks.append(
            f"YÜKSEK BUY TAX %{buy_tax * 100:.1f}"
        )

    if sell_tax >= 0.10:

        risks.append(
            f"YÜKSEK SELL TAX %{sell_tax * 100:.1f}"
        )

    # --------------------------------------------------
    # KRİTİK RİSK
    # --------------------------------------------------

    critical_risks = {
        "HONEYPOT",
        "SATIŞ KISITLAMASI",
        "ALIŞ KISITLAMASI",
        "BLACKLIST",
        "MINT YETKİSİ",
        "OWNER BAKİYE DEĞİŞTİREBİLİR",
        "GİZLİ OWNER",
        "OWNERSHIP GERİ ALINABİLİR",
    }

    has_critical = any(
        risk in critical_risks
        for risk in risks
    )

    if has_critical:

        risk_level = "HIGH"

    elif risks:

        risk_level = "MEDIUM"

    else:

        risk_level = "LOW"

    return {
        "available": True,
        "risk": risk_level,
        "reason": (
            "Güvenlik kontrolü tamamlandı"
        ),
        "risks": risks,
        "buy_tax": buy_tax * 100,
        "sell_tax": sell_tax * 100,
    }


def analyze_solana_security(result):
    """
    Solana GoPlus güvenlik analizi.

    Solana alanlarının önemli bir bölümü
    {"status": "1", ...}
    şeklinde yapılandırılmıştır.
    """

    risks = []

    if not isinstance(result, dict):

        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": "Geçersiz Solana API sonucu",
            "risks": [],
            "buy_tax": 0,
            "sell_tax": 0,
        }

    # --------------------------------------------------
    # MINT
    # --------------------------------------------------

    if structured_status_is_true(
        result.get("mintable")
    ):

        risks.append(
            "MINT YETKİSİ"
        )

    # --------------------------------------------------
    # FREEZE
    # --------------------------------------------------

    if structured_status_is_true(
        result.get("freezable")
    ):

        risks.append(
            "FREEZE YETKİSİ"
        )

    # --------------------------------------------------
    # CLOSE
    # --------------------------------------------------

    if structured_status_is_true(
        result.get("closable")
    ):

        risks.append(
            "TOKEN KAPATMA YETKİSİ"
        )

    # --------------------------------------------------
    # BALANCE DEĞİŞTİRME
    # --------------------------------------------------

    if structured_status_is_true(
        result.get(
            "balance_mutable_authority"
        )
    ):

        risks.append(
            "BAKİYE DEĞİŞTİRME YETKİSİ"
        )

    # --------------------------------------------------
    # METADATA
    # --------------------------------------------------

    if structured_status_is_true(
        result.get(
            "metadata_mutable"
        )
    ):

        metadata = result.get(
            "metadata_mutable"
        )

        # Metadata authority kötü adres
        # olarak işaretlenmişse daha ciddi.
        if isinstance(
            metadata,
            dict
        ):

            authority = metadata.get(
                "metadata_upgrade_authority",
                {}
            )

            if isinstance(
                authority,
                dict
            ) and value_is_true(
                authority.get(
                    "malicious_address"
                )
            ):

                risks.append(
                    "KÖTÜCÜL METADATA AUTHORITY"
                )

            else:

                risks.append(
                    "DEĞİŞTİRİLEBİLİR METADATA"
                )

        else:

            risks.append(
                "DEĞİŞTİRİLEBİLİR METADATA"
            )

    # --------------------------------------------------
    # TRANSFER FEE
    # --------------------------------------------------

    if structured_status_is_true(
        result.get(
            "transfer_fee_upgradable"
        )
    ):

        risks.append(
            "TRANSFER FEE DEĞİŞTİRİLEBİLİR"
        )

    # --------------------------------------------------
    # DEFAULT ACCOUNT STATE
    # --------------------------------------------------

    if structured_status_is_true(
        result.get(
            "default_account_state_upgradable"
        )
    ):

        risks.append(
            "ACCOUNT STATE DEĞİŞTİRİLEBİLİR"
        )

    # --------------------------------------------------
    # TRANSFER HOOK
    # --------------------------------------------------

    if structured_status_is_true(
        result.get(
            "transfer_hook_upgradable"
        )
    ):

        risks.append(
            "TRANSFER HOOK DEĞİŞTİRİLEBİLİR"
        )

    # --------------------------------------------------
    # TRANSFER HOOK
    # --------------------------------------------------

    transfer_hook = result.get(
        "transfer_hook"
    )

    if isinstance(
        transfer_hook,
        dict
    ):

        malicious = value_is_true(
            transfer_hook.get(
                "malicious_address"
            )
        )

        if malicious:

            risks.append(
                "KÖTÜCÜL TRANSFER HOOK"
            )

    # --------------------------------------------------
    # NON-TRANSFERABLE
    # --------------------------------------------------

    if value_is_true(
        result.get(
            "non_transferable"
        )
    ):

        risks.append(
            "TRANSFER EDİLEMEZ TOKEN"
        )

    # --------------------------------------------------
    # CREATOR KÖTÜCÜL ADRES
    # --------------------------------------------------

    creators = result.get(
        "creator"
    )

    if isinstance(
        creators,
        dict
    ):

        if value_is_true(
            creators.get(
                "malicious_address"
            )
        ):

            risks.append(
                "KÖTÜCÜL CREATOR"
            )

    elif isinstance(
        creators,
        list
    ):

        for creator in creators:

            if isinstance(
                creator,
                dict
            ) and value_is_true(
                creator.get(
                    "malicious_address"
                )
            ):

                risks.append(
                    "KÖTÜCÜL CREATOR"
                )

                break

    # --------------------------------------------------
    # HOLDER KONTROLÜ
    # --------------------------------------------------

    holders = result.get(
        "holders"
    )

    top_holder_percent = 0
    top5_percent = 0
    top10_percent = 0

    if isinstance(
        holders,
        list
    ):

        percentages = []

        for holder in holders:

            if not isinstance(
                holder,
                dict
            ):
                continue

            try:

                percent = float(
                    holder.get(
                        "percent",
                        0
                    ) or 0
                )

                percentages.append(
                    percent
                )

            except Exception:
                continue

        percentages.sort(
            reverse=True
        )

        if percentages:

            top_holder_percent = (
                percentages[0]
            )

            top5_percent = sum(
                percentages[:5]
            )

            top10_percent = sum(
                percentages[:10]
            )

    # Aşırı yoğunlaşma varsa dikkat.
    if top_holder_percent >= 0.30:

        risks.append(
            "TEK HOLDER YÜKSEK YOĞUNLAŞMA"
        )

    elif top5_percent >= 0.50:

        risks.append(
            "TOP 5 HOLDER YÜKSEK YOĞUNLAŞMA"
        )

    # --------------------------------------------------
    # MALICIOUS TOKEN
    # --------------------------------------------------

    if value_is_true(
        result.get(
            "malicious_address"
        )
    ):

        risks.append(
            "KÖTÜCÜL TOKEN"
        )

    # --------------------------------------------------
    # TRUSTED TOKEN
    # --------------------------------------------------
    #
    # trusted_token = 1 olması olumlu olabilir.
    # trusted_token != 1 tek başına risk değildir.
    #
    # Bu nedenle burada risk eklemiyoruz.
    #

    # --------------------------------------------------
    # KRİTİK RİSKLER
    # --------------------------------------------------

    critical_keywords = (
        "MINT YETKİSİ",
        "FREEZE YETKİSİ",
        "TOKEN KAPATMA YETKİSİ",
        "BAKİYE DEĞİŞTİRME YETKİSİ",
        "KÖTÜCÜL",
        "TRANSFER EDİLEMEZ TOKEN",
    )

    has_critical = any(
        any(
            keyword in risk
            for keyword in critical_keywords
        )
        for risk in risks
    )

    # --------------------------------------------------
    # ORTA RİSKLER
    # --------------------------------------------------

    if has_critical:

        risk_level = "HIGH"

    elif risks:

        risk_level = "MEDIUM"

    else:

        risk_level = "LOW"

    return {
        "available": True,
        "risk": risk_level,
        "reason": (
            "Solana güvenlik kontrolü tamamlandı"
        ),
        "risks": risks,
        "buy_tax": 0,
        "sell_tax": 0,
        "top_holder_percent":
            top_holder_percent,
        "top5_holder_percent":
            top5_percent,
        "top10_holder_percent":
            top10_percent,
    }


def get_security(
    chain,
    token_address,
):
    """
    Chain'e göre doğru GoPlus
    güvenlik API'sini kullan.
    """

    if not chain:
        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": "Chain belirtilmedi",
            "risks": [],
            "buy_tax": 0,
            "sell_tax": 0,
        }

    if not token_address:
        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": "Token adresi belirtilmedi",
            "risks": [],
            "buy_tax": 0,
            "sell_tax": 0,
        }

    chain_lower = str(
        chain
    ).lower()

    # --------------------------------------------------
    # SOLANA
    # --------------------------------------------------

    if chain_lower == "solana":

        url = (
            f"{GOPLUS_SOLANA_URL}"
            f"?contract_addresses="
            f"{token_address}"
        )

        data = api_get(url)

        if not data:

            return {
                "available": False,
                "risk": "UNKNOWN",
                "reason": (
                    "Solana GoPlus API yanıt vermedi"
                ),
                "risks": [],
                "buy_tax": 0,
                "sell_tax": 0,
            }

        result = get_result(
            data,
            token_address,
        )

        if not result:

            return {
                "available": False,
                "risk": "UNKNOWN",
                "reason": (
                    "Solana token sonucu bulunamadı"
                ),
                "risks": [],
                "buy_tax": 0,
                "sell_tax": 0,
            }

        return analyze_solana_security(
            result
        )

    # --------------------------------------------------
    # EVM CHAIN'LER
    # --------------------------------------------------

    chain_ids = {

        "ethereum": "1",

        "bsc": "56",

        "arbitrum": "42161",

        "polygon": "137",

        "base": "8453",

        "optimism": "10",

        "avalanche": "43114",

        "robinhood": "4663",

        "stable": "988",

        "plasma": "9745",

        "monad": "143",
    }

    chain_id = chain_ids.get(
        chain_lower
    )

    if not chain_id:

        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": (
                f"Desteklenmeyen chain: {chain}"
            ),
            "risks": [],
            "buy_tax": 0,
            "sell_tax": 0,
        }

    url = (
        f"{GOPLUS_BASE_URL}"
        f"?chain_id={chain_id}"
        f"&contract_addresses="
        f"{token_address}"
    )

    data = api_get(url)

    if not data:

        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": (
                "GoPlus API yanıt vermedi"
            ),
            "risks": [],
            "buy_tax": 0,
            "sell_tax": 0,
        }

    result = get_result(
        data,
        token_address,
    )

    if not result:

        return {
            "available": False,
            "risk": "UNKNOWN",
            "reason": (
                "Token sonucu bulunamadı"
            ),
            "risks": [],
            "buy_tax": 0,
            "sell_tax": 0,
        }

    return analyze_evm_security(
        result
    )
