import os
import requests

API_KEY = os.getenv("HADITH_API_KEY")

if not API_KEY:
    raise SystemExit("ERROR: HADITH_API_KEY is not set.")

url = "https://hadithapi.com/api/hadiths"

params = {
    "apiKey": API_KEY,
    "book": "sahih-bukhari",
    "paginate": 1
}

response = requests.get(url, params=params, timeout=30)

print("HTTP STATUS:", response.status_code)
print("RESPONSE:")

try:
    data = response.json()
    print(data)
except Exception:
    print(response.text)

if response.status_code != 200:
    raise SystemExit("API TEST FAILED")

print("API TEST PASSED")
