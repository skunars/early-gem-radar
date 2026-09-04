import json
import os
from datetime import datetime, timezone

HISTORY_DIR = "data"
HISTORY_FILE = os.path.join(HISTORY_DIR, "candidates.json")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load_history():
    os.makedirs(HISTORY_DIR, exist_ok=True)

    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            return data

    except Exception as e:
        print(f"⚠️ History okuma hatası: {e}")

    return []


def _save_history(data):
    os.makedirs(HISTORY_DIR, exist_ok=True)

    temp_file = HISTORY_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    os.replace(temp_file, HISTORY_FILE)


def _token_key(candidate):
    chain = str(candidate.get("chain", "")).lower()
    address = str(
        candidate.get("token_address")
        or candidate.get("address")
        or candidate.get("tokenAddress")
        or ""
    ).lower()

    if address:
        return f"{chain}:{address}"

    symbol = str(candidate.get("symbol", "")).upper()
    name = str(candidate.get("name", "")).lower()

    return f"{chain}:symbol:{symbol}:name:{name}"


def record_candidates(candidates):
    """
    Scanner tarafından bulunan adayları geçmişe kaydeder.

    Aynı token tekrar tarandığında yeni bir aday kaydı oluşturmaz.
    Bunun yerine tokenin son durumunu günceller ve scan geçmişine
    yeni bir snapshot ekler.
    """

    history = _load_history()

    index = {}

    for i, item in enumerate(history):
        key = item.get("token_key")

        if key:
            index[key] = i

    added = 0
    updated = 0

    for candidate in candidates:
        key = _token_key(candidate)

        now = _now()

        snapshot = {
            "time": now,
            "price": candidate.get("price"),
            "liquidity_usd": candidate.get("liquidity_usd"),
            "volume_24h_usd": candidate.get("volume_24h_usd"),
            "price_change_24h": candidate.get("price_change_24h"),
            "score": candidate.get("score"),
            "signal": candidate.get("signal"),
            "security_risk": candidate.get("security_risk"),
            "buy_tax": candidate.get("buy_tax"),
            "sell_tax": candidate.get("sell_tax"),
        }

        if key not in index:
            item = {
                "token_key": key,
                "first_seen": now,
                "last_seen": now,

                "chain": candidate.get("chain"),
                "symbol": candidate.get("symbol"),
                "name": candidate.get("name"),
                "token_address": (
                    candidate.get("token_address")
                    or candidate.get("address")
                    or candidate.get("tokenAddress")
                ),
                "dex": candidate.get("dex"),

                "initial_price": candidate.get("price"),
                "initial_liquidity_usd": candidate.get("liquidity_usd"),
                "initial_volume_24h_usd": candidate.get("volume_24h_usd"),
                "initial_score": candidate.get("score"),
                "initial_signal": candidate.get("signal"),

                "snapshots": [
                    snapshot
                ],

                "performance": {
                    "price_1h": None,
                    "price_6h": None,
                    "price_24h": None,
                    "price_7d": None,
                    "price_30d": None,
                    "max_gain": None,
                    "max_loss": None,
                },
            }

            history.append(item)
            index[key] = len(history) - 1

            added += 1

        else:
            item = history[index[key]]

            item["last_seen"] = now

            snapshots = item.setdefault("snapshots", [])

            # Aynı dakikada gereksiz tekrarları önle
            if not snapshots or snapshots[-1].get("time", "")[:16] != now[:16]:
                snapshots.append(snapshot)

            updated += 1

    _save_history(history)

    print(
        f"💾 History: {added} yeni aday, "
        f"{updated} mevcut aday güncellendi."
    )

    print(f"📁 Kayıt dosyası: {HISTORY_FILE}")

    return history


def get_history():
    """Tüm kayıtlı adayları döndürür."""
    return _load_history()


def get_candidate(chain, token_address):
    """Belirli bir tokenin geçmiş kaydını getirir."""

    key = f"{str(chain).lower()}:{str(token_address).lower()}"

    history = _load_history()

    for item in history:
        if item.get("token_key") == key:
            return item

    return None


def history_count():
    """Kayıtlı toplam token sayısını döndürür."""
    return len(_load_history())


if __name__ == "__main__":
    history = _load_history()

    print("📊 EARLY GEM RADAR HISTORY")
    print("=" * 50)
    print(f"Kayıtlı token sayısı: {len(history)}")
    print(f"Dosya: {HISTORY_FILE}")
    print("=" * 50)

    for item in history[-10:]:
        print(
            item.get("symbol"),
            "|",
            item.get("chain"),
            "|",
            item.get("initial_signal"),
            "|",
            item.get("initial_score"),
        )
