import json
import os
import time
from pathlib import Path

import requests


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

DATA_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# API SETTINGS
# ============================================================

API_KEY = os.getenv(
    "HADITH_API_KEY",
    ""
).strip()

API_URL = (
    "https://www.hadithapi.com/"
    "public/api/hadiths/"
)

PAGE_SIZE = 200


# ============================================================
# CHECK API KEY
# ============================================================

if not API_KEY:

    raise SystemExit(
        "ERROR: HADITH_API_KEY is not set."
    )


# ============================================================
# EXTRACT RECORDS
# ============================================================

def extract_records(payload):

    if not isinstance(
        payload,
        dict
    ):
        return [], {}

    hadiths = payload.get(
        "hadiths"
    )

    if isinstance(
        hadiths,
        dict
    ):

        records = hadiths.get(
            "data",
            []
        )

        if not isinstance(
            records,
            list
        ):
            records = []

        return records, hadiths

    if isinstance(
        hadiths,
        list
    ):

        return hadiths, payload

    data = payload.get(
        "data"
    )

    if isinstance(
        data,
        list
    ):

        return data, payload

    return [], {}


# ============================================================
# DOWNLOAD ONE COLLECTION
# ============================================================

def download_collection(
    book_slug,
    output_filename
):

    print()
    print("=" * 70)
    print(
        f"DOWNLOADING: {book_slug}"
    )
    print("=" * 70)

    all_records = []

    seen_numbers = set()

    page = 1

    while True:

        print(
            f"Requesting page {page}..."
        )

        params = {
            "apiKey": API_KEY,
            "book": book_slug,
            "paginate": PAGE_SIZE,
            "page": page
        }

        try:

            response = requests.get(
                API_URL,
                params=params,
                timeout=60
            )

        except requests.RequestException as error:

            raise RuntimeError(
                f"API request failed: {error}"
            )

        print(
            "HTTP STATUS:",
            response.status_code
        )

        if response.status_code == 401:

            raise RuntimeError(
                "Hadith API key is invalid."
            )

        if response.status_code == 403:

            raise RuntimeError(
                "Hadith API key is missing "
                "or access is forbidden."
            )

        if response.status_code == 404:

            raise RuntimeError(
                f"Book not found: {book_slug}"
            )

        response.raise_for_status()

        try:

            payload = response.json()

        except ValueError:

            raise RuntimeError(
                "Hadith API returned invalid JSON."
            )

        records, pagination = extract_records(
            payload
        )

        if not records:

            print(
                "No more records."
            )

            break

        new_records = 0

        for item in records:

            if not isinstance(
                item,
                dict
            ):
                continue

            number = (
                item.get("hadithNumber")
                or item.get("hadithnumber")
                or item.get("number")
                or item.get("id")
            )

            urdu = item.get(
                "hadithUrdu"
            )

            if number is None:

                continue

            if not isinstance(
                urdu,
                str
            ):

                continue

            if not urdu.strip():

                continue

            number = str(
                number
            ).strip()

            if not number:

                continue

            if number in seen_numbers:

                continue

            seen_numbers.add(
                number
            )

            all_records.append(
                item
            )

            new_records += 1

        print(
            "Records received:",
            len(records)
        )

        print(
            "New usable records:",
            new_records
        )

        # ----------------------------------------------------
        # Pagination
        # ----------------------------------------------------

        last_page = (
            pagination.get("last_page")
            or pagination.get("lastPage")
        )

        current_page = (
            pagination.get("current_page")
            or pagination.get("currentPage")
        )

        if last_page is not None:

            try:

                if page >= int(
                    last_page
                ):

                    break

            except (
                ValueError,
                TypeError
            ):

                pass

        if current_page is not None:

            try:

                current_page = int(
                    current_page
                )

                if page < current_page:

                    page = (
                        current_page + 1
                    )

                else:

                    page += 1

            except (
                ValueError,
                TypeError
            ):

                page += 1

        else:

            page += 1

        # Safety against an unexpected API response
        if new_records == 0:

            break

        if page > 100:

            raise RuntimeError(
                "Pagination exceeded 100 pages. "
                "Stopping to prevent an infinite loop."
            )

        time.sleep(
            0.15
        )

    if not all_records:

        raise RuntimeError(
            f"No usable Urdu Hadiths found "
            f"for {book_slug}."
        )

    output_file = (
        DATA_DIR /
        output_filename
    )

    output = {
        "hadiths": all_records
    }

    output_file.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print()
    print(
        f"SAVED: {output_file}"
    )

    print(
        "TOTAL USABLE HADITHS:",
        len(all_records)
    )

    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print(
        "HADITH DATABASE PREPARATION"
    )
    print("=" * 70)

    download_collection(
        "sahih-bukhari",
        "urd-bukhari.json"
    )

    download_collection(
        "sahih-muslim",
        "urd-muslim.json"
    )

    print()
    print("=" * 70)
    print(
        "HADITH DATABASE READY"
    )
    print("=" * 70)


if __name__ == "__main__":

    main()
