# EARLY GEM RADAR - HISTORY SYSTEM

import json
import os
from datetime import datetime, timezone


DATA_DIR = "data"
HISTORY_FILE = os.path.join(DATA_DIR, "candidates.json")


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def load_history():
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(HISTORY_FILE):
        return {}

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

    except Exception as e:
        print(f"⚠️ History okuma hatası: {e}")

    return {}


def save_history(history):
    os.makedirs(DATA_DIR, exist_ok=True)

    temp_file = HISTORY_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(
            history,
            f,
            ensure_ascii=False,
            indent=2
        )

    os.replace(
        temp_file,
        HISTORY_FILE
    )


def save_candidate(candidate):
    """Tek bir tokenın tarama sonucunu kaydeder."""

    if not candidate:
        return

    history = load_history()

    chain = str(
        candidate.get("chain", "")
    ).lower()

    address = str(
        candidate.get(
            "token_address",
            ""
        )
    ).lower()

    symbol = str(
        candidate.get(
            "symbol",
            "UNKNOWN"
        )
    )

    if address:
        key = f"{chain}:{address}"
    else:
        key = f"{chain}:{symbol.lower()}"

    timestamp = now_utc()

    if key not in history:

        history[key] = {
            "first_seen": timestamp,
            "last_seen": timestamp,

            "chain": chain,
            "address": address,

            "symbol": symbol,
            "name": candidate.get(
                "name"
            ),

            "dex": candidate.get(
                "dex"
            ),

            "pair_address": candidate.get(
                "pair_address"
            ),

            "dex_url": candidate.get(
                "dex_url"
            ),

            "initial": {},
            "latest": {},
            "scans": []
        }

    item = history[key]

    snapshot = {
        "timestamp": timestamp,

        "price_usd": candidate.get(
            "price_usd"
        ),

        "liquidity_usd": candidate.get(
            "liquidity_usd"
        ),

        "volume_24h_usd": candidate.get(
            "volume_24h_usd"
        ),

        "market_cap": candidate.get(
            "market_cap"
        ),

        "fdv": candidate.get(
            "fdv"
        ),

        "price_change_24h": candidate.get(
            "price_change_24h"
        ),

        "age_hours": candidate.get(
            "age_hours"
        ),

        "buys_24h": candidate.get(
            "buys_24h"
        ),

        "sells_24h": candidate.get(
            "sells_24h"
        ),

        "score": candidate.get(
            "score"
        ),

        "signal": candidate.get(
            "signal"
        ),

        "security_available": candidate.get(
            "security_available"
        ),

        "security_risk": candidate.get(
            "security_risk"
        ),

        "security_risks": candidate.get(
            "security_risks",
            []
        ),

        "buy_tax": candidate.get(
            "buy_tax"
        ),

        "sell_tax": candidate.get(
            "sell_tax"
        )
    }

    # İlk görüldüğü andaki bilgiler
    if not item["initial"]:

        item["initial"] = snapshot.copy()

    # Son görülen bilgiler
    item["latest"] = snapshot.copy()

    item["last_seen"] = timestamp

    # Tarama geçmişine ekle
    item["scans"].append(
        snapshot
    )

    # Her token için maksimum 1000 kayıt
    if len(item["scans"]) > 1000:

        item["scans"] = item[
            "scans"
        ][-1000:]

    history[key] = item

    save_history(history)


def save_candidates(candidates):
    """Tarama sonuçlarının tamamını kaydeder."""

    if not candidates:
        return

    count = 0

    for candidate in candidates:

        try:
            save_candidate(
                candidate
            )

            count += 1

        except Exception as e:

            print(
                f"⚠️ Token kayıt hatası: {e}"
            )

    print(
        f"💾 {count} aday geçmişe kaydedildi."
    )


def get_candidate(
    chain,
    address
):
    """Belirli bir tokenın geçmişini getirir."""

    history = load_history()

    key = (
        f"{str(chain).lower()}:"
        f"{str(address).lower()}"
    )

    return history.get(
        key
    )


def get_all_candidates():
    """Tüm geçmiş tokenları getirir."""

    return load_history()


def history_count():
    """Kayıtlı farklı token sayısını verir."""

    return len(
        load_history()
    )


if __name__ == "__main__":

    print()
    print(
        "📚 EARLY GEM RADAR"
    )

    print(
        "📊 HISTORY SYSTEM"
    )

    print("=" * 50)

    history = load_history()

    total_scans = 0

    for item in history.values():

        total_scans += len(
            item.get(
                "scans",
                []
            )
        )

    print(
        f"Farklı token: "
        f"{len(history)}"
    )

    print(
        f"Toplam tarama kaydı: "
        f"{total_scans}"
    )

    print(
        f"Dosya: "
        f"{HISTORY_FILE}"
    )

    print("=" * 50)

    print(
        "✅ History sistemi hazır."
    )
