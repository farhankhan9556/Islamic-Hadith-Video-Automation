import os
import re
import json
import html
import random
import shutil
import zipfile
import subprocess
import time
import unicodedata
from pathlib import Path
from datetime import datetime

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, features


# ============================================================
# SETTINGS
# ============================================================

WIDTH = 1080
HEIGHT = 1920

FPS = 24
VIDEO_SECONDS = 60

BATCH_SIZE = 3

PROJECT_DIR = Path(__file__).resolve().parent

DATA_FILE = PROJECT_DIR / "data" / "duas.json"
USED_FILE = PROJECT_DIR / "used_duas.json"

FONT_DIR = PROJECT_DIR / "fonts"
AUDIO_FILE = PROJECT_DIR / "audio" / "islamic_background.mp3"

OUTPUT_DIR = PROJECT_DIR / "output"
WORK_DIR = PROJECT_DIR / "work"

PEXELS_API_KEY = os.getenv(
    "PEXELS_API_KEY",
    ""
).strip()

PEXELS_URL = "https://api.pexels.com/v1/search"

QURANENC_API = "https://quranenc.com/api/v1"

# Known key, but the script will automatically discover
# the current key from QuranEnc first.
KNOWN_URDU_KEY = "urdu_junagarhi"


# ============================================================
# VISUAL SETTINGS
# ============================================================

CARD_X1 = 65
CARD_X2 = WIDTH - 65

CARD_Y1 = 125
CARD_Y2 = HEIGHT - 115

GOLD = (205, 168, 92, 255)
GOLD_LIGHT = (238, 213, 157, 255)

CREAM = (248, 243, 231, 245)

DARK_TEXT = (35, 30, 25, 255)

MUTED_TEXT = (87, 76, 63, 255)

GREEN = (39, 91, 68, 255)

WHITE = (255, 255, 255, 255)


# ============================================================
# SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": (
        "Islamic-Dua-Video-Automation/1.0 "
        "(GitHub Actions)"
    ),
    "Accept": "application/json",
})


# ============================================================
# FONT DISCOVERY
# ============================================================

def find_font(names):

    candidates = []

    for name in names:

        candidates.extend([
            FONT_DIR / name,

            Path(
                "/usr/share/fonts/truetype/noto"
            ) / name,

            Path(
                "/usr/share/fonts/opentype/noto"
            ) / name,

            Path(
                "/usr/share/fonts/truetype/dejavu"
            ) / name,
        ])

    for path in candidates:

        if path.exists():

            return str(path)

    # Ubuntu fontconfig fallback

    for name in names:

        try:

            result = subprocess.run(
                [
                    "fc-match",
                    "-f",
                    "%{file}",
                    name
                ],
                capture_output=True,
                text=True,
                check=False
            )

            path = result.stdout.strip()

            if path and Path(path).exists():

                return path

        except Exception:
            pass

    return None


ARABIC_FONT = find_font([
    "NotoNaskhArabic-Regular.ttf",
    "NotoSansArabic-Regular.ttf",
])

URDU_FONT = find_font([
    "NotoNastaliqUrdu-Regular.ttf",
    "NotoNaskhArabic-Regular.ttf",
    "NotoSansArabic-Regular.ttf",
])

TITLE_FONT = find_font([
    "NotoNastaliqUrdu-Regular.ttf",
    "NotoNaskhArabic-Regular.ttf",
])

ENGLISH_FONT = find_font([
    "DejaVuSans.ttf",
    "NotoSans-Regular.ttf",
])


# ============================================================
# ENVIRONMENT CHECK
# ============================================================

def check_environment():

    print("")
    print("=" * 70)
    print("ENVIRONMENT CHECK")
    print("=" * 70)

    if not features.check("raqm"):

        raise RuntimeError(
            "Pillow RAQM is not available. "
            "Check libraqm-dev/libfribidi-dev installation."
        )

    print(
        "Pillow RAQM:",
        features.check("raqm")
    )

    if not ARABIC_FONT:

        raise RuntimeError(
            "Arabic font not found."
        )

    if not URDU_FONT:

        raise RuntimeError(
            "Urdu font not found."
        )

    if not TITLE_FONT:

        raise RuntimeError(
            "Title font not found."
        )

    if not ENGLISH_FONT:

        raise RuntimeError(
            "English font not found."
        )

    print(
        "Arabic font:",
        ARABIC_FONT
    )

    print(
        "Urdu font:",
        URDU_FONT
    )

    print(
        "Title font:",
        TITLE_FONT
    )

    if not DATA_FILE.exists():

        raise RuntimeError(
            f"Missing: {DATA_FILE}"
        )

    if not AUDIO_FILE.exists():

        raise RuntimeError(
            f"Missing: {AUDIO_FILE}"
        )

    if not PEXELS_API_KEY:

        raise RuntimeError(
            "PEXELS_API_KEY GitHub Secret is missing."
        )

    print(
        "PEXELS_API_KEY: OK"
    )

    print(
        "Environment check passed."
    )


# ============================================================
# FILE HELPERS
# ============================================================

def load_json(path, default):

    if not path.exists():

        return default

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception as e:

        print(
            f"Warning: Could not read {path}: {e}"
        )

        return default


def save_json(path, data):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def clean_folder(path):

    if path.exists():

        for item in path.iterdir():

            if item.is_dir():

                shutil.rmtree(item)

            else:

                item.unlink()

    else:

        path.mkdir(
            parents=True,
            exist_ok=True
        )


def safe_filename(text):

    text = str(text)

    text = re.sub(
        r'[<>:"/\\|?*\x00-\x1F]',
        "_",
        text
    )

    text = re.sub(
        r"\s+",
        "_",
        text
    )

    return text[:100]


# ============================================================
# DUA HELPERS
# ============================================================

def get_dua_field(
    dua,
    *names,
    default=""
):

    for name in names:

        value = dua.get(name)

        if value is not None:

            value = str(value).strip()

            if value:

                return value

    return default


def dua_identifier(dua):

    dua_id = dua.get("id")

    if dua_id:

        return str(dua_id).strip()

    reference = get_dua_field(
        dua,
        "reference",
        "ref",
        "reference_text"
    )

    arabic = get_dua_field(
        dua,
        "arabic",
        "dua",
        "text"
    )

    return (
        f"{reference}|{arabic}"
        .strip()
        .lower()
    )


def load_duas():

    data = load_json(
        DATA_FILE,
        []
    )

    if not isinstance(data, list):

        raise RuntimeError(
            "data/duas.json must contain a JSON array."
        )

    valid = []

    for index, dua in enumerate(data):

        if not isinstance(dua, dict):

            print(
                f"Skipping invalid Dua entry #{index + 1}"
            )

            continue

        if not dua.get("sura"):

            print(
                f"Skipping Dua without sura: {dua}"
            )

            continue

        if not dua.get("ayah"):

            print(
                f"Skipping Dua without ayah: {dua}"
            )

            continue

        arabic = get_dua_field(
            dua,
            "arabic",
            "dua",
            "text"
        )

        if not arabic:

            print(
                f"Skipping Dua without Arabic: {dua}"
            )

            continue

        valid.append(dua)

    if len(valid) < BATCH_SIZE:

        raise RuntimeError(
            f"Only {len(valid)} valid duas found. "
            f"At least {BATCH_SIZE} are required."
        )

    print(
        f"Valid duas available: {len(valid)}"
    )

    return valid


def choose_three_duas(duas):

    used = load_json(
        USED_FILE,
        []
    )

    if not isinstance(used, list):

        used = []

    used = [
        str(x).strip()
        for x in used
        if str(x).strip()
    ]

    used_set = set(used)

    unused = [
        dua
        for dua in duas
        if dua_identifier(dua)
        not in used_set
    ]

    print(
        f"Unused duas available: {len(unused)}"
    )

    # --------------------------------------------------------
    # Normal cycle
    # --------------------------------------------------------

    if len(unused) >= BATCH_SIZE:

        selected = random.sample(
            unused,
            BATCH_SIZE
        )

        return selected, used

    # --------------------------------------------------------
    # New cycle
    # --------------------------------------------------------

    print(
        "Not enough unused duas remain."
    )

    print(
        "Starting a new Dua cycle."
    )

    selected = random.sample(
        duas,
        BATCH_SIZE
    )

    return selected, []


# ============================================================
# QURANENC API
# ============================================================

def api_get(
    url,
    params=None,
    attempts=3,
    timeout=45
):

    last_error = None

    for attempt in range(
        1,
        attempts + 1
    ):

        print(
            f"QuranEnc request "
            f"{attempt}/{attempts}: {url}"
        )

        try:

            response = SESSION.get(
                url,
                params=params,
                timeout=timeout
            )

            print(
                f"HTTP status: {response.status_code}"
            )

            if response.status_code == 429:

                print(
                    "QuranEnc rate limit. Waiting..."
                )

                time.sleep(
                    3 * attempt
                )

                continue

            if response.status_code >= 500:

                print(
                    "QuranEnc server error. Retrying..."
                )

                time.sleep(
                    2 * attempt
                )

                continue

            response.raise_for_status()

            return response.json()

        except requests.exceptions.RequestException as e:

            last_error = e

            print(
                f"Request error: {e}"
            )

            if attempt < attempts:

                time.sleep(
                    2 * attempt
                )

        except ValueError as e:

            last_error = e

            print(
                f"Invalid JSON returned by QuranEnc: {e}"
            )

            if attempt < attempts:

                time.sleep(
                    2 * attempt
                )

    raise RuntimeError(
        "QuranEnc request failed after "
        f"{attempts} attempts.\n"
        f"URL: {url}\n"
        f"Last error: {last_error}"
    )


def get_translation_catalog():

    urls = [
        (
            f"{QURANENC_API}/translations/"
            f"list/ur"
        ),
        (
            f"{QURANENC_API}/translations/"
            f"list/ur/"
        ),
    ]

    last_error = None

    for url in urls:

        try:

            data = api_get(
                url,
                params={
                    "localization": "ur"
                },
                attempts=2
            )

            if isinstance(data, list):

                return data

            if isinstance(data, dict):

                for key in [
                    "translations",
                    "data",
                    "results"
                ]:

                    value = data.get(key)

                    if isinstance(value, list):

                        return value

        except Exception as e:

            last_error = e

            print(
                f"Translation catalog attempt failed: {e}"
            )

    raise RuntimeError(
        "Could not obtain QuranEnc translation catalog.\n"
        f"Last error: {last_error}"
    )


def discover_urdu_translation():

    catalog = get_translation_catalog()

    print(
        f"QuranEnc translations returned: "
        f"{len(catalog)}"
    )

    # --------------------------------------------------------
    # First: exact known key
    # --------------------------------------------------------

    for item in catalog:

        if not isinstance(item, dict):

            continue

        key = str(
            item.get("key", "")
        ).strip()

        if key == KNOWN_URDU_KEY:

            version = str(
                item.get(
                    "version",
                    "unknown"
                )
            )

            title = str(
                item.get(
                    "title",
                    ""
                )
            )

            print(
                f"Using QuranEnc translation: "
                f"{key}"
            )

            print(
                f"Translation title: {title}"
            )

            print(
                f"Translation version: {version}"
            )

            return key, version, item

    # --------------------------------------------------------
    # Second: search Urdu + Junagarhi
    # --------------------------------------------------------

    for item in catalog:

        if not isinstance(item, dict):

            continue

        key = str(
            item.get("key", "")
        ).strip()

        title = str(
            item.get("title", "")
        ).lower()

        description = str(
            item.get("description", "")
        ).lower()

        combined = (
            f"{key} {title} {description}"
        ).lower()

        if (
            "junagarhi" in combined
            or
            "جوناگڑھی" in combined
        ):

            version = str(
                item.get(
                    "version",
                    "unknown"
                )
            )

            print(
                f"Discovered Urdu translation: "
                f"{key}"
            )

            print(
                f"Translation version: {version}"
            )

            return key, version, item

    # --------------------------------------------------------
    # Last resort
    # --------------------------------------------------------

    print(
        "Warning: Could not identify "
        "Junagarhi translation dynamically."
    )

    print(
        f"Using known key: {KNOWN_URDU_KEY}"
    )

    return (
        KNOWN_URDU_KEY,
        "unknown",
        {}
    )


def clean_quran_translation(text):

    if text is None:

        return ""

    text = str(text)

    text = html.unescape(
        text
    )

    text = unicodedata.normalize(
        "NFKC",
        text
    )

    # --------------------------------------------------------
    # HTML
    # --------------------------------------------------------

    # Superscript footnotes
    text = re.sub(
        r"<sup[^>]*>.*?</sup>",
        lambda m: (
            ""
            if re.search(
                r"\d",
                m.group(0)
            )
            else m.group(0)
        ),
        text,
        flags=re.IGNORECASE
    )

    # Remove remaining HTML tags
    text = re.sub(
        r"<[^>]+>",
        "",
        text
    )

    # --------------------------------------------------------
    # QuranEnc footnote markers
    # --------------------------------------------------------

    patterns = [

        # [1]
        r"[\[\［]\s*[0-9٠-٩]+\s*[\]\］]",

        # ^{[1]}
        r"\^\s*\{\s*[\[\［]\s*[0-9٠-٩]+\s*[\]\］]\s*\}",

        # ^{1}
        r"\^\s*\{\s*[0-9٠-٩]+\s*\}",

        # ﴿1﴾
        r"﴿\s*[0-9٠-٩]+\s*﴾",

        # (1)
        r"(?<![0-9٠-٩])\(\s*[0-9٠-٩]+\s*\)(?![0-9٠-٩])",

        # full-width numeric footnotes
        r"［\s*[0-9٠-٩]+\s*］",
    ]

    for pattern in patterns:

        text = re.sub(
            pattern,
            "",
            text
        )

    # --------------------------------------------------------
    # Superscript Unicode numbers
    # --------------------------------------------------------

    text = re.sub(
        r"[\u00B9\u00B2\u00B3\u2070-\u2079]",
        "",
        text
    )

    # --------------------------------------------------------
    # Invisible Unicode
    # --------------------------------------------------------

    text = re.sub(
        r"[\u200B-\u200F\u202A-\u202E\u2060\uFEFF]",
        "",
        text
    )

    # Soft hyphen
    text = text.replace(
        "\u00AD",
        ""
    )

    # --------------------------------------------------------
    # Cleanup
    # --------------------------------------------------------

    text = text.replace(
        "\r",
        " "
    )

    text = text.replace(
        "\n",
        " "
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    text = re.sub(
        r"\s+([،۔,.;:!?؟])",
        r"\1",
        text
    )

    return text.strip()


def validate_translation(text):

    if not text:

        raise RuntimeError(
            "QuranEnc returned an empty translation."
        )

    # These should never reach the video renderer.
    forbidden = [
        "□",
        "�",
        "<sup",
        "</sup>",
        "^{[",
        "［1］",
        "［2］",
        "［3］",
    ]

    for item in forbidden:

        if item in text:

            raise RuntimeError(
                "Translation contains an "
                f"unwanted rendering marker: {item}"
            )

    # Make sure there is actually Urdu/Arabic text.
    arabic_chars = re.findall(
        r"[\u0600-\u06FF]",
        text
    )

    if len(arabic_chars) < 5:

        raise RuntimeError(
            "QuranEnc translation does not contain "
            "enough Arabic-script characters."
        )

    return text


def fetch_ayah_translation(
    translation_key,
    sura,
    ayah
):

    url = (
        f"{QURANENC_API}/translation/"
        f"aya/{translation_key}/"
        f"{sura}/{ayah}"
    )

    data = api_get(
        url,
        attempts=3
    )

    if not isinstance(
        data,
        dict
    ):

        raise RuntimeError(
            "Unexpected QuranEnc ayah response."
        )

    translation = data.get(
        "translation"
    )

    if translation is None:

        raise RuntimeError(
            "QuranEnc ayah response does not "
            "contain 'translation'."
        )

    return clean_quran_translation(
        translation
    )


def fetch_sura_translation(
    translation_key,
    sura
):

    url = (
        f"{QURANENC_API}/translation/"
        f"sura/{translation_key}/{sura}"
    )

    data = api_get(
        url,
        attempts=3
    )

    if isinstance(data, dict):

        for key in [
            "translations",
            "data",
            "result"
        ]:

            if isinstance(
                data.get(key),
                list
            ):

                data = data[key]
                break

    if not isinstance(
        data,
        list
    ):

        raise RuntimeError(
            "Unexpected QuranEnc sura response."
        )

    result = {}

    for item in data:

        if not isinstance(
            item,
            dict
        ):

            continue

        aya = item.get("aya")

        translation = item.get(
            "translation"
        )

        if aya is None or translation is None:

            continue

        result[int(aya)] = (
            clean_quran_translation(
                translation
            )
        )

    return result


def fetch_quran_translation(
    translation_key,
    sura,
    ayah,
    ayah_end=None
):

    sura = int(sura)
    ayah = int(ayah)

    if ayah_end is None:

        ayah_end = ayah

    ayah_end = int(ayah_end)

    if ayah_end < ayah:

        raise RuntimeError(
            f"Invalid ayah range: "
            f"{sura}:{ayah}-{ayah_end}"
        )

    # --------------------------------------------------------
    # Try individual API first
    # --------------------------------------------------------

    results = []

    individual_failed = False

    for current_ayah in range(
        ayah,
        ayah_end + 1
    ):

        print(
            ""
        )

        print(
            f"Fetching QuranEnc "
            f"{sura}:{current_ayah}"
        )

        try:

            translation = fetch_ayah_translation(
                translation_key,
                sura,
                current_ayah
            )

            if translation:

                results.append(
                    translation
                )

        except Exception as e:

            individual_failed = True

            print(
                "Individual ayah request failed:"
            )

            print(
                str(e)
            )

            break

    if (
        not individual_failed
        and len(results)
        == (ayah_end - ayah + 1)
    ):

        final_text = clean_quran_translation(
            " ".join(results)
        )

        return validate_translation(
            final_text
        )

    # --------------------------------------------------------
    # FALLBACK: COMPLETE SURA
    # --------------------------------------------------------

    print("")
    print(
        "Falling back to QuranEnc "
        "complete-sura endpoint..."
    )

    sura_data = fetch_sura_translation(
        translation_key,
        sura
    )

    results = []

    for current_ayah in range(
        ayah,
        ayah_end + 1
    ):

        if current_ayah not in sura_data:

            raise RuntimeError(
                f"QuranEnc did not return "
                f"ayah {sura}:{current_ayah} "
                f"from the complete-sura endpoint."
            )

        results.append(
            sura_data[current_ayah]
        )

    final_text = clean_quran_translation(
        " ".join(results)
    )

    return validate_translation(
        final_text
    )


# ============================================================
# PEXELS
# ============================================================

BACKGROUND_SEARCHES = [
    "mosque architecture night",
    "beautiful mosque sunset",
    "islamic architecture",
    "mosque interior",
    "islamic geometric pattern",
    "mosque evening",
    "islamic architecture sunset",
]


def pexels_get(
    query,
    attempts=3
):

    last_error = None

    for attempt in range(
        1,
        attempts + 1
    ):

        try:

            response = SESSION.get(
                PEXELS_URL,
                headers={
                    "Authorization":
                        PEXELS_API_KEY
                },
                params={
                    "query": query,
                    "orientation": "portrait",
                    "size": "large",
                    "per_page": 20,
                    "page": random.randint(
                        1,
                        5
                    )
                },
                timeout=45
            )

            print(
                f"Pexels HTTP status: "
                f"{response.status_code}"
            )

            response.raise_for_status()

            return response.json()

        except Exception as e:

            last_error = e

            print(
                f"Pexels attempt "
                f"{attempt}/{attempts} failed: "
                f"{e}"
            )

            if attempt < attempts:

                time.sleep(
                    2 * attempt
                )

    raise RuntimeError(
        "Pexels request failed.\n"
        f"Last error: {last_error}"
    )


def download_background(index):

    queries = BACKGROUND_SEARCHES.copy()

    random.shuffle(
        queries
    )

    for query in queries:

        print(
            ""
        )

        print(
            f"Pexels search: {query}"
        )

        try:

            data = pexels_get(
                query
            )

            photos = data.get(
                "photos",
                []
            )

            if not photos:

                continue

            random.shuffle(
                photos
            )

            for photo in photos:

                src = photo.get(
                    "src",
                    {}
                )

                image_url = (
                    src.get("portrait")
                    or src.get("large2x")
                    or src.get("large")
                )

                if not image_url:

                    continue

                output = (
                    WORK_DIR /
                    f"background_{index}.jpg"
                )

                response = SESSION.get(
                    image_url,
                    timeout=60
                )

                response.raise_for_status()

                with open(
                    output,
                    "wb"
                ) as f:

                    f.write(
                        response.content
                    )

                if output.stat().st_size < 10000:

                    continue

                print(
                    f"Background downloaded: "
                    f"{output}"
                )

                return output

        except Exception as e:

            print(
                f"Pexels query failed: {e}"
            )

    raise RuntimeError(
        "Could not download a usable "
        "Pexels background."
    )


# ============================================================
# IMAGE / TEXT HELPERS
# ============================================================

def load_font(
    path,
    size
):

    return ImageFont.truetype(
        path,
        size
    )


def text_width(
    draw,
    text,
    font,
    direction="rtl",
    language="ur"
):

    box = draw.textbbox(
        (0, 0),
        text,
        font=font,
        direction=direction,
        language=language
    )

    return (
        box[2] - box[0]
    )


def wrap_text(
    draw,
    text,
    font,
    max_width,
    direction="rtl",
    language="ur"
):

    words = str(text).split()

    if not words:

        return []

    lines = []

    current = ""

    for word in words:

        candidate = (
            word
            if not current
            else current + " " + word
        )

        width = text_width(
            draw,
            candidate,
            font,
            direction,
            language
        )

        if width <= max_width:

            current = candidate

        else:

            if current:

                lines.append(
                    current
                )

            current = word

    if current:

        lines.append(
            current
        )

    return lines


def fit_text(
    draw,
    text,
    font_path,
    start_size,
    min_size,
    max_width,
    max_height,
    direction,
    language,
    line_gap=4
):

    for size in range(
        start_size,
        min_size - 1,
        -2
    ):

        font = load_font(
            font_path,
            size
        )

        lines = wrap_text(
            draw,
            text,
            font,
            max_width,
            direction,
            language
        )

        line_height = int(
            size * 1.45
        )

        total_height = (
            len(lines)
            * line_height
            +
            max(
                0,
                len(lines) - 1
            )
            * line_gap
        )

        if total_height <= max_height:

            return (
                font,
                lines,
                line_height,
                total_height
            )

    font = load_font(
        font_path,
        min_size
    )

    lines = wrap_text(
        draw,
        text,
        font,
        max_width,
        direction,
        language
    )

    line_height = int(
        min_size * 1.45
    )

    total_height = (
        len(lines)
        * line_height
        +
        max(
            0,
            len(lines) - 1
        )
        * line_gap
    )

    return (
        font,
        lines,
        line_height,
        total_height
    )


def draw_centered_lines(
    draw,
    lines,
    font,
    center_x,
    top_y,
    line_height,
    fill,
    direction,
    language,
    gap=4
):

    y = top_y

    for line in lines:

        box = draw.textbbox(
            (0, 0),
            line,
            font=font,
            direction=direction,
            language=language
        )

        width = (
            box[2] - box[0]
        )

        x = (
            center_x
            - width / 2
        )

        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
            direction=direction,
            language=language
        )

        y += (
            line_height
            + gap
        )

    return y


# ============================================================
# DECORATION
# ============================================================

def draw_decorations(draw):

    center = WIDTH // 2

    # Top ornamental diamond

    cy = 72

    points = [
        (center, cy - 18),
        (center + 18, cy),
        (center, cy + 18),
        (center - 18, cy),
    ]

    draw.polygon(
        points,
        outline=GOLD,
        width=2
    )

    draw.ellipse(
        (
            center - 4,
            cy - 4,
            center + 4,
            cy + 4
        ),
        fill=GOLD
    )

    # Horizontal ornaments

    draw.line(
        (
            130,
            72,
            385,
            72
        ),
        fill=GOLD,
        width=2
    )

    draw.line(
        (
            695,
            72,
            950,
            72
        ),
        fill=GOLD,
        width=2
    )

    # Small dots

    for x in [
        110,
        130,
        150,
        930,
        950,
        970
    ]:

        draw.ellipse(
            (
                x - 3,
                68,
                x + 3,
                74
            ),
            fill=GOLD
        )


# ============================================================
# CREATE POSTER
# ============================================================

def create_poster(
    dua,
    translation,
    output_path
):

    image = Image.new(
        "RGBA",
        (
            WIDTH,
            HEIGHT
        ),
        (
            0,
            0,
            0,
            0
        )
    )

    # --------------------------------------------------------
    # Card shadow
    # --------------------------------------------------------

    shadow = Image.new(
        "RGBA",
        (
            WIDTH,
            HEIGHT
        ),
        (
            0,
            0,
            0,
            0
        )
    )

    shadow_draw = ImageDraw.Draw(
        shadow
    )

    shadow_draw.rounded_rectangle(
        (
            CARD_X1 + 12,
            CARD_Y1 + 18,
            CARD_X2 + 12,
            CARD_Y2 + 18
        ),
        radius=48,
        fill=(
            0,
            0,
            0,
            160
        )
    )

    shadow = shadow.filter(
        ImageFilter.GaussianBlur(
            22
        )
    )

    image.alpha_composite(
        shadow
    )

    draw = ImageDraw.Draw(
        image
    )

    # --------------------------------------------------------
    # Main card
    # --------------------------------------------------------

    draw.rounded_rectangle(
        (
            CARD_X1,
            CARD_Y1,
            CARD_X2,
            CARD_Y2
        ),
        radius=48,
        fill=CREAM,
        outline=GOLD,
        width=4
    )

    draw.rounded_rectangle(
        (
            CARD_X1 + 16,
            CARD_Y1 + 16,
            CARD_X2 - 16,
            CARD_Y2 - 16
        ),
        radius=38,
        outline=(
            205,
            168,
            92,
            70
        ),
        width=2
    )

    draw_decorations(
        draw
    )

    # --------------------------------------------------------
    # Data
    # --------------------------------------------------------

    title = get_dua_field(
        dua,
        "title",
        "title_ur",
        "topic",
        "name",
        default="قرآنی دعا"
    )

    reference = get_dua_field(
        dua,
        "reference",
        "ref",
        "reference_text"
    )

    arabic = get_dua_field(
        dua,
        "arabic",
        "dua",
        "text"
    )

    context = get_dua_field(
        dua,
        "context",
        "story",
        "description",
        default=""
    )

    # --------------------------------------------------------
    # DUA TITLE
    # --------------------------------------------------------
    # Show the dua topic at the top of the video.
    # The old horizontal line crossing/under the title is intentionally removed.

    title_font = load_font(
        TITLE_FONT,
        52
    )

    display_title = title.strip()
    if not display_title.startswith("دعا برائے"):
        display_title = f"دعا برائے {display_title}"

    title_lines = wrap_text(
        draw,
        display_title,
        title_font,
        830,
        "rtl",
        "ur"
    )

    title_y = CARD_Y1 + 42
    title_bottom = draw_centered_lines(
        draw,
        title_lines,
        title_font,
        WIDTH // 2,
        title_y,
        68,
        GOLD,
        "rtl",
        "ur",
        gap=2
    )

    # No divider line is drawn here.

    # --------------------------------------------------------
    # ARABIC TEXT
    # --------------------------------------------------------

    arabic_top = max(245, title_bottom + 35)
    arabic_bottom = arabic_top + 355

    # Arabic middle box removed intentionally.
    # The Arabic text is rendered directly on the main card.

    arabic_font, arabic_lines, arabic_line_height, arabic_height = fit_text(
        draw,
        arabic,
        ARABIC_FONT,
        62,
        42,
        790,
        280,
        "rtl",
        "ar",
        3
    )

    arabic_y = (
        arabic_top
        + (
            (
                arabic_bottom
                - arabic_top
            )
            - arabic_height
        )
        / 2
    )

    draw_centered_lines(
        draw,
        arabic_lines,
        arabic_font,
        WIDTH // 2,
        int(arabic_y),
        arabic_line_height,
        DARK_TEXT,
        "rtl",
        "ar",
        gap=3
    )

    # --------------------------------------------------------
    # URDU TRANSLATION
    # --------------------------------------------------------

    urdu_top = arabic_bottom + 30
    urdu_bottom = urdu_top + 465

    # Urdu translation middle box removed intentionally.
    # The translation is rendered directly on the main card.

    label_font = load_font(
        TITLE_FONT,
        32
    )

    label = "اردو ترجمہ"

    label_box = draw.textbbox(
        (0, 0),
        label,
        font=label_font,
        direction="rtl",
        language="ur"
    )

    label_width = (
        label_box[2]
        - label_box[0]
    )

    draw.text(
        (
            WIDTH // 2
            - label_width / 2,
            urdu_top + 18
        ),
        label,
        font=label_font,
        fill=GOLD,
        direction="rtl",
        language="ur"
    )

    meaning_font, meaning_lines, meaning_line_height, meaning_height = fit_text(
        draw,
        translation,
        URDU_FONT,
        39,
        27,
        790,
        355,
        "rtl",
        "ur",
        2
    )

    meaning_y = (
        urdu_top
        + 78
        + (
            (
                urdu_bottom
                - urdu_top
                - 78
            )
            - meaning_height
        )
        / 2
    )

    draw_centered_lines(
        draw,
        meaning_lines,
        meaning_font,
        WIDTH // 2,
        int(meaning_y),
        meaning_line_height,
        DARK_TEXT,
        "rtl",
        "ur",
        gap=2
    )

    # --------------------------------------------------------
    # REFERENCE BADGE
    # --------------------------------------------------------

    ref_y = urdu_bottom + 28

    ref_font = load_font(
        ENGLISH_FONT,
        28
    )

    ref_text = (
        f"Quran • {reference}"
    )

    ref_box = draw.textbbox(
        (0, 0),
        ref_text,
        font=ref_font
    )

    ref_width = (
        ref_box[2]
        - ref_box[0]
        + 90
    )

    ref_height = 60

    ref_x1 = (
        WIDTH - ref_width
    ) // 2

    ref_x2 = (
        ref_x1
        + ref_width
    )

    draw.rounded_rectangle(
        (
            ref_x1,
            ref_y,
            ref_x2,
            ref_y + ref_height
        ),
        radius=30,
        fill=GREEN
    )

    draw.text(
        (
            WIDTH // 2,
            ref_y + ref_height / 2
        ),
        ref_text,
        font=ref_font,
        fill=WHITE,
        anchor="mm"
    )

    # --------------------------------------------------------
    # CONTEXT
    # --------------------------------------------------------

    if context:

        context_top = (
            ref_y
            + ref_height
            + 25
        )

        context_height = (
            HEIGHT
            - context_top
            - 155
        )

        context_font, context_lines, context_line_height, context_total = fit_text(
            draw,
            context,
            URDU_FONT,
            29,
            21,
            770,
            context_height,
            "rtl",
            "ur",
            1
        )

        draw_centered_lines(
            draw,
            context_lines,
            context_font,
            WIDTH // 2,
            context_top,
            context_line_height,
            MUTED_TEXT,
            "rtl",
            "ur",
            gap=1
        )

    # --------------------------------------------------------
    # Bottom decorative line
    # --------------------------------------------------------

    draw.line(
        (
            340,
            HEIGHT - 98,
            740,
            HEIGHT - 98
        ),
        fill=GOLD,
        width=2
    )

    image.save(
        output_path,
        "PNG"
    )

    print(
        f"Poster created: {output_path}"
    )

    return output_path


# ============================================================
# SOCIAL MEDIA
# ============================================================

def make_social_text(
    dua,
    translation,
    translation_key,
    translation_version,
    video_number
):

    title = get_dua_field(
        dua,
        "title",
        "title_ur",
        "topic",
        "name",
        default="قرآنی دعا"
    )

    reference = get_dua_field(
        dua,
        "reference",
        "ref",
        "reference_text"
    )

    arabic = get_dua_field(
        dua,
        "arabic",
        "dua",
        "text"
    )

    context = get_dua_field(
        dua,
        "context",
        "story",
        "description",
        default=""
    )

    youtube_title = (
        f"{title} | Quranic Dua "
        f"#{reference}"
    )

    youtube_description = f"""{title}

قرآن کریم کی یہ خوبصورت دعا یاد کریں اور اپنی روزمرہ زندگی میں پڑھیں۔

دعا:
{arabic}

اردو ترجمہ:
{translation}

حوالہ:
{reference}

پس منظر:
{context}

اللہ تعالیٰ ہمیں قرآن کریم سمجھنے اور اس پر عمل کرنے کی توفیق عطا فرمائے۔ آمین۔

قرآن کے اردو معنی کا ماخذ:
QuranEnc.com

Urdu Translation:
Muhammad Junagarhi

Translation Version:
{translation_version}

#Quran #QuranicDua #Dua #IslamicShorts #IslamicReminder #UrduIslamic #QuranReminder
"""

    youtube_hashtags = (
        "#Quran "
        "#QuranicDua "
        "#Dua "
        "#IslamicShorts "
        "#IslamicReminder "
        "#UrduIslamic "
        "#QuranReminder "
        "#IslamicVideo "
        "#Muslim"
    )

    youtube_tags = (
        "Quran, Quranic Dua, Dua, Islamic Dua, "
        "Quran Dua, Urdu Quran, Urdu Islamic Video, "
        "Islamic Reminder, Quran Reminder, Islamic Shorts, "
        "Muslim Reminder, Daily Dua, Quran Verses, "
        "Islamic Status, Urdu Islamic Shorts"
    )

    tiktok_caption = f"""{title}

{arabic}

اردو ترجمہ:
{translation}

حوالہ:
{reference}

قرآن کریم کی دعاؤں کو یاد کریں اور دوسروں تک بھی پہنچائیں۔

#Quran #Dua #QuranicDua #IslamicTok #IslamicReminder #UrduIslamic #Muslim #QuranReminder #IslamicVideo
"""

    tiktok_hashtags = (
        "#Quran "
        "#Dua "
        "#QuranicDua "
        "#IslamicTok "
        "#IslamicReminder "
        "#UrduIslamic "
        "#Muslim "
        "#QuranReminder "
        "#IslamicVideo "
        "#IslamicContent"
    )

    return f"""============================================================
ISLAMIC QURANIC DUA VIDEO {video_number}
============================================================

TITLE:
{title}

REFERENCE:
{reference}

ARABIC DUA:
{arabic}

URDU MEANING:
{translation}

CONTEXT:
{context}


============================================================
YOUTUBE
============================================================

TITLE:
{youtube_title}


DESCRIPTION:

{youtube_description}


HASHTAGS:

{youtube_hashtags}


TAGS:

{youtube_tags}


============================================================
TIKTOK
============================================================

CAPTION:

{tiktok_caption}


HASHTAGS:

{tiktok_hashtags}


============================================================
SOURCE
============================================================

Quran Translation Source:
QuranEnc.com

Translation:
Muhammad Junagarhi

Translation Key:
{translation_key}

Translation Version:
{translation_version}


============================================================
VIDEO
============================================================

Resolution:
1080 x 1920

Duration:
60 seconds

FPS:
24

Format:
MP4 / H.264

============================================================
"""


# ============================================================
# VIDEO
# ============================================================

def create_video(
    background,
    poster,
    output_video
):

    total_frames = (
        FPS
        * VIDEO_SECONDS
    )

    filter_complex = (
        "[0:v]"
        "scale=1080:1920:"
        "force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "eq=brightness=-0.08:saturation=0.82,"
        "zoompan="
        "z='min(zoom+0.00015,1.07)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        f"d={total_frames}:"
        "s=1080x1920:"
        "fps=24"
        "[bg];"

        "[bg][1:v]"
        "overlay=0:0:"
        "format=auto,"
        "format=yuv420p"
        "[v]"
    )

    command = [
        "ffmpeg",
        "-y",

        "-loop",
        "1",

        "-i",
        str(background),

        "-loop",
        "1",

        "-i",
        str(poster),

        "-stream_loop",
        "-1",

        "-i",
        str(AUDIO_FILE),

        "-filter_complex",
        filter_complex,

        "-map",
        "[v]",

        "-map",
        "2:a",

        "-t",
        str(VIDEO_SECONDS),

        "-r",
        str(FPS),

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "24",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-pix_fmt",
        "yuv420p",

        "-movflags",
        "+faststart",

        "-shortest",

        str(output_video)
    ]

    print("")
    print(
        f"Creating video: {output_video.name}"
    )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:

        print("")
        print(
            "FFmpeg STDOUT:"
        )

        print(
            result.stdout[-5000:]
        )

        print("")
        print(
            "FFmpeg STDERR:"
        )

        print(
            result.stderr[-10000:]
        )

        raise RuntimeError(
            "FFmpeg failed."
        )

    if not output_video.exists():

        raise RuntimeError(
            "FFmpeg completed but video "
            "file was not created."
        )

    size_mb = (
        output_video.stat().st_size
        / 1024
        / 1024
    )

    if size_mb < 0.05:

        raise RuntimeError(
            f"Video appears invalid: "
            f"{size_mb:.3f} MB"
        )

    print(
        f"Video created successfully: "
        f"{size_mb:.2f} MB"
    )


# ============================================================
# ZIP
# ============================================================

def create_zip(
    batch_dir,
    zip_path
):

    print("")
    print(
        "Creating ONE ZIP..."
    )

    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED
    ) as archive:

        for file in sorted(
            batch_dir.iterdir()
        ):

            if file.is_file():

                archive.write(
                    file,
                    arcname=file.name
                )

    if not zip_path.exists():

        raise RuntimeError(
            "ZIP creation failed."
        )

    size_mb = (
        zip_path.stat().st_size
        / 1024
        / 1024
    )

    print(
        f"ZIP created: "
        f"{size_mb:.2f} MB"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("ISLAMIC QURANIC DUA VIDEO AUTOMATION")
    print("=" * 70)

    # --------------------------------------------------------
    # Prepare
    # --------------------------------------------------------

    check_environment()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    WORK_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    clean_folder(
        OUTPUT_DIR
    )

    clean_folder(
        WORK_DIR
    )

    # --------------------------------------------------------
    # Load duas
    # --------------------------------------------------------

    duas = load_duas()

    selected_duas, old_used = choose_three_duas(
        duas
    )

    print("")
    print(
        "SELECTED 3 DIFFERENT DUAS"
    )

    for number, dua in enumerate(
        selected_duas,
        start=1
    ):

        print(
            f"{number}. "
            f"{get_dua_field(dua, 'title', 'name')}"
        )

        print(
            f"   {get_dua_field(dua, 'reference', 'ref')}"
        )

    # --------------------------------------------------------
    # QuranEnc translation discovery
    # --------------------------------------------------------

    print("")
    print(
        "=" * 70
    )

    print(
        "QURANENC TRANSLATION DISCOVERY"
    )

    translation_key, translation_version, translation_info = (
        discover_urdu_translation()
    )

    print(
        f"Final translation key: "
        f"{translation_key}"
    )

    print(
        f"Final translation version: "
        f"{translation_version}"
    )

    # --------------------------------------------------------
    # Batch folder
    # --------------------------------------------------------

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    batch_dir = (
        OUTPUT_DIR
        / f"batch_{timestamp}"
    )

    batch_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    new_used = list(
        old_used
    )

    # --------------------------------------------------------
    # Create 3 videos
    # --------------------------------------------------------

    for index, dua in enumerate(
        selected_duas,
        start=1
    ):

        print("")
        print("=" * 70)

        print(
            f"CREATING VIDEO {index}/{BATCH_SIZE}"
        )

        print("=" * 70)

        sura = int(
            get_dua_field(
                dua,
                "sura",
                "surah"
            )
        )

        ayah = int(
            get_dua_field(
                dua,
                "ayah",
                "aya",
                "verse"
            )
        )

        ayah_end = int(
            get_dua_field(
                dua,
                "ayah_end",
                "aya_end",
                default=ayah
            )
        )

        reference = get_dua_field(
            dua,
            "reference",
            "ref",
            "reference_text"
        )

        print(
            f"Reference: {reference}"
        )

        print(
            f"Quran: {sura}:{ayah}"
            + (
                f"-{ayah_end}"
                if ayah_end != ayah
                else ""
            )
        )

        # ----------------------------------------------------
        # Urdu translation
        # ----------------------------------------------------

        translation = fetch_quran_translation(
            translation_key,
            sura,
            ayah,
            ayah_end
        )

        print("")
        print(
            "Translation successfully obtained."
        )

        print(
            f"Translation length: "
            f"{len(translation)} characters"
        )

        # ----------------------------------------------------
        # Background
        # ----------------------------------------------------

        background = download_background(
            index
        )

        # ----------------------------------------------------
        # Poster
        # ----------------------------------------------------

        poster = (
            WORK_DIR
            / f"poster_{index}.png"
        )

        create_poster(
            dua,
            translation,
            poster
        )

        # ----------------------------------------------------
        # Video
        # ----------------------------------------------------

        video_path = (
            batch_dir
            / f"dua_{index:02d}.mp4"
        )

        create_video(
            background,
            poster,
            video_path
        )

        # ----------------------------------------------------
        # Social text
        # ----------------------------------------------------

        social_path = (
            batch_dir
            / f"dua_{index:02d}_social_media.txt"
        )

        social_text = make_social_text(
            dua,
            translation,
            translation_key,
            translation_version,
            index
        )

        social_path.write_text(
            social_text,
            encoding="utf-8"
        )

        # ----------------------------------------------------
        # Metadata JSON
        # ----------------------------------------------------

        metadata = {

            "video_number": index,

            "title": get_dua_field(
                dua,
                "title",
                "title_ur",
                "topic",
                "name"
            ),

            "reference": reference,

            "sura": sura,

            "ayah_start": ayah,

            "ayah_end": ayah_end,

            "arabic": get_dua_field(
                dua,
                "arabic",
                "dua",
                "text"
            ),

            "urdu_meaning": translation,

            "context": get_dua_field(
                dua,
                "context",
                "story",
                "description"
            ),

            "source": {
                "name": "QuranEnc.com",
                "translation_key": translation_key,
                "translation_version": translation_version
            },

            "video": {
                "width": WIDTH,
                "height": HEIGHT,
                "fps": FPS,
                "duration_seconds": VIDEO_SECONDS
            }
        }

        metadata_path = (
            batch_dir
            / f"dua_{index:02d}.json"
        )

        save_json(
            metadata_path,
            metadata
        )

        # ----------------------------------------------------
        # Mark used
        # ----------------------------------------------------

        identifier = dua_identifier(
            dua
        )

        if identifier not in new_used:

            new_used.append(
                identifier
            )

    # --------------------------------------------------------
    # Save used list only after ALL 3 succeed
    # --------------------------------------------------------

    save_json(
        USED_FILE,
        new_used
    )

    # --------------------------------------------------------
    # README
    # --------------------------------------------------------

    readme = f"""ISLAMIC QURANIC DUA VIDEO BATCH

Created:
{datetime.now().isoformat()}

Videos:
3

Resolution:
1080 x 1920

Duration:
60 seconds

FPS:
24

Source:
QuranEnc.com

Urdu Translation:
Muhammad Junagarhi

Translation Key:
{translation_key}

Translation Version:
{translation_version}

Each video includes:
- MP4 video
- YouTube title
- YouTube description
- YouTube hashtags
- YouTube tags
- TikTok caption
- TikTok hashtags
- JSON metadata

The video itself does not display source/version
information at the bottom.
"""

    (batch_dir / "README.txt").write_text(
        readme,
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Validate exactly 3 MP4
    # --------------------------------------------------------

    mp4_files = list(
        batch_dir.glob("*.mp4")
    )

    if len(mp4_files) != 3:

        raise RuntimeError(
            f"Expected exactly 3 videos, "
            f"found {len(mp4_files)}."
        )

    # --------------------------------------------------------
    # Validate social files
    # --------------------------------------------------------

    social_files = list(
        batch_dir.glob(
            "*_social_media.txt"
        )
    )

    if len(social_files) != 3:

        raise RuntimeError(
            f"Expected 3 social files, "
            f"found {len(social_files)}."
        )

    # --------------------------------------------------------
    # ONE ZIP
    # --------------------------------------------------------

    zip_path = (
        OUTPUT_DIR
        / f"Islamic-Dua-3-Videos-{timestamp}.zip"
    )

    create_zip(
        batch_dir,
        zip_path
    )

    # --------------------------------------------------------
    # Final output
    # --------------------------------------------------------

    print("")
    print("=" * 70)
    print("FINAL OUTPUT")
    print("=" * 70)

    print("")
    print(
        "Videos:"
    )

    for file in sorted(
        mp4_files
    ):

        print(
            f"  {file.name}"
        )

    print("")
    print(
        "Social files:"
    )

    for file in sorted(
        social_files
    ):

        print(
            f"  {file.name}"
        )

    print("")
    print(
        f"ONE ZIP:"
    )

    print(
        f"  {zip_path}"
    )

    print("")
    print("=" * 70)
    print("SUCCESS")
    print("3 UNIQUE VIDEOS CREATED")
    print("1 ZIP CREATED")
    print("=" * 70)


if __name__ == "__main__":

    try:

        main()

    except Exception as e:

        print("")
        print("=" * 70)
        print("BUILD FAILED")
        print("=" * 70)

        print(
            str(e)
        )

        print("")
        print(
            "The workflow stopped before "
            "creating/uploading incomplete videos."
        )

        raise
