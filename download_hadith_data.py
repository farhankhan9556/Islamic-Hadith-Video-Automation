import json
import time
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(exist_ok=True)


DATASETS = {
    "urd-bukhari.json": [
        "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/urd-bukhari.json",
        "https://raw.githubusercontent.com/fawazahmed0/hadith-api/1/editions/urd-bukhari.json",
    ],

    "urd-muslim.json": [
        "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/urd-muslim.json",
        "https://raw.githubusercontent.com/fawazahmed0/hadith-api/1/editions/urd-muslim.json",
    ],
}


def download_file(filename, urls):

    output = DATA_DIR / filename

    # If already downloaded, don't download again.
    if output.exists() and output.stat().st_size > 1000:

        print(f"Already exists: {output}")

        return


    for url in urls:

        print()
        print("Downloading:")
        print(url)

        try:

            response = requests.get(
                url,
                timeout=120,
                headers={
                    "User-Agent":
                    "Mozilla/5.0"
                }
            )

            response.raise_for_status()

            data = response.json()

            # Basic validation
            if not isinstance(data, dict):
                raise ValueError(
                    "Downloaded data is not a JSON object."
                )

            if "hadiths" not in data:
                raise ValueError(
                    "JSON does not contain 'hadiths'."
                )

            hadiths = data["hadiths"]

            if not isinstance(hadiths, list):
                raise ValueError(
                    "'hadiths' is not a list."
                )

            if len(hadiths) < 10:
                raise ValueError(
                    "Dataset contains too few Hadiths."
                )

            # Save formatted JSON
            output.write_text(
                json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2
                ),
                encoding="utf-8"
            )

            print(
                f"Downloaded {len(hadiths)} Hadiths."
            )

            print(
                f"Saved: {output}"
            )

            return

        except Exception as e:

            print(
                "Download failed:",
                e
            )

            time.sleep(2)


    raise RuntimeError(
        f"Could not download {filename}"
    )


def main():

    print("=" * 60)
    print("DOWNLOADING URDU HADITH DATABASE")
    print("=" * 60)

    for filename, urls in DATASETS.items():

        download_file(
            filename,
            urls
        )

    print()
    print("=" * 60)
    print("HADITH DATABASE READY")
    print("=" * 60)


if __name__ == "__main__":
    main()
