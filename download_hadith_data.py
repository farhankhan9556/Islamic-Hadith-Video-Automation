import os
import json
import requests
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

API_KEY = os.getenv("HADITH_API_KEY")

if not API_KEY:
    raise SystemExit("ERROR: HADITH_API_KEY is not set.")

API_URL = "https://hadithapi.com/api/hadiths"


def download_collection(book, filename):
    output = DATA_DIR / filename

    print("=" * 60)
    print(f"Downloading: {book}")
    print("=" * 60)

    params = {
        "apiKey": API_KEY,
        "book": book,
        "paginate": 100
    }

    response = requests.get(
        API_URL,
        params=params,
        timeout=60
    )

    print("HTTP STATUS:", response.status_code)

    response.raise_for_status()

    data = response.json()

    if not isinstance(data, dict):
        raise RuntimeError("Invalid API response.")

    # Save the complete API response.
    output.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(f"Saved: {output}")

    # Display a small verification.
    hadiths = data.get("hadiths")

    if isinstance(hadiths, dict):
        records = hadiths.get("data", [])
    elif isinstance(hadiths, list):
        records = hadiths
    else:
        records = []

    print("Hadith records received:", len(records))

    if records:
        first = records[0]

        print("\nFIRST HADITH CHECK")
        print("-" * 40)

        print("Hadith number:",
              first.get("hadithNumber"))

        print("Arabic:",
              first.get("hadithArabic"))

        print("Urdu:",
              first.get("hadithUrdu"))

        print("-" * 40)


def main():

    print("\n")
    print("=" * 60)
    print("HADITH API DATABASE")
    print("=" * 60)

    download_collection(
        "sahih-bukhari",
        "bukhari.json"
    )

    download_collection(
        "sahih-muslim",
        "muslim.json"
    )

    print("\n")
    print("=" * 60)
    print("HADITH DATABASE READY")
    print("=" * 60)


if __name__ == "__main__":
    main()
