from security import get_security


# Test için Ethereum üzerinde örnek bir kontrat.
# Burada amaç sadece API bağlantısını kontrol etmek.
TEST_CHAIN = "ethereum"
TEST_TOKEN = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"


print("🛡️ EARLY GEM RADAR - GÜVENLİK TESTİ")
print("=" * 60)

result = get_security(
    TEST_CHAIN,
    TEST_TOKEN,
)

print("API kullanılabilir:", result.get("available"))
print("Risk:", result.get("risk"))
print("Sebep:", result.get("reason", "-"))

if result.get("available"):
    print("Buy Tax:", result.get("buy_tax"))
    print("Sell Tax:", result.get("sell_tax"))
    print("Riskler:", result.get("risks", []))

print("=" * 60)
print("✅ Güvenlik testi tamamlandı.")
