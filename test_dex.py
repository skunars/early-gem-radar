import requests

url = "https://api.dexscreener.com/token-profiles/latest/v1"

try:
    response = requests.get(url, timeout=15)

    print("HTTP STATUS:", response.status_code)

    if response.status_code == 200:
        data = response.json()

        print("TOKEN SAYISI:", len(data))

        for token in data[:5]:
            print(
                token.get("tokenAddress"),
                token.get("chainId")
            )
    else:
        print("API HATASI:", response.text)

except Exception as e:
    print("BAĞLANTI HATASI:", e)
