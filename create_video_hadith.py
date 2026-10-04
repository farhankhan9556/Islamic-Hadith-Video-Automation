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

USED_FILE = PROJECT_DIR / "used_hadith.json"

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
        "Islamic-Hadith-Video-Automation/1.0 "
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

    print("Pillow RAQM:", features.check("raqm"))

    if not ARABIC_FONT:
        raise RuntimeError("Arabic font not found.")
    if not URDU_FONT:
        raise RuntimeError("Urdu font not found.")
    if not TITLE_FONT:
        raise RuntimeError("Title font not found.")
    if not ENGLISH_FONT:
        raise RuntimeError("English font not found.")
    if not AUDIO_FILE.exists():
        raise RuntimeError(f"Missing: {AUDIO_FILE}")
    if not PEXELS_API_KEY:
        raise RuntimeError("PEXELS_API_KEY GitHub Secret is missing.")
    if not SUNNAH_API_KEY:
        raise RuntimeError("SUNNAH_API_KEY GitHub Secret is missing.")
    if not HADITH_COLLECTIONS:
        raise RuntimeError("HADITH_COLLECTIONS is empty.")

    print("Arabic font:", ARABIC_FONT)
    print("Urdu font:", URDU_FONT)
    print("Title font:", TITLE_FONT)
    print("PEXELS_API_KEY: OK")
    print("SUNNAH_API_KEY: OK")
    print("Sunnah.com API:", SUNNAH_API_URL)
    print("Collections:", ", ".join(HADITH_COLLECTIONS))
    print("Environment check passed.")

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
# SUNNAH.COM API HELPERS
# ============================================================

# Official Sunnah.com API v1.
# Authentication is sent in the X-API-Key HTTP header.
SUNNAH_API_URL = os.getenv(
    "SUNNAH_API_URL",
    "https://api.sunnah.com/v1"
).strip().rstrip("/")

SUNNAH_API_KEY = os.getenv("SUNNAH_API_KEY", "").strip()

# Official collection names used by the Sunnah.com API.
HADITH_COLLECTIONS = [
    x.strip().lower()
    for x in os.getenv(
        "HADITH_COLLECTIONS",
        "bukhari,muslim"
    ).split(",")
    if x.strip()
]

# The API returns language-specific entries in hadith[].
ARABIC_LANGS = {
    x.strip().lower()
    for x in os.getenv("HADITH_ARABIC_LANGS", "ar,ara,arabic").split(",")
    if x.strip()
}

URDU_LANGS = {
    x.strip().lower()
    for x in os.getenv("HADITH_URDU_LANGS", "ur,urd,urdu").split(",")
    if x.strip()
}

# Maximum items allowed by the official API is 100.
API_PAGE_SIZE = 100
API_REQUEST_DELAY = float(os.getenv("SUNNAH_API_REQUEST_DELAY", "0.6"))
RANDOM_HADITH_ATTEMPTS = int(os.getenv("RANDOM_HADITH_ATTEMPTS", "20"))


def get_hadith_field(hadith, *names, default=""):
    if not isinstance(hadith, dict):
        return default

    for name in names:
        value = hadith.get(name)
        if value is not None:
            if isinstance(value, (dict, list)):
                continue
            value = str(value).strip()
            if value:
                return value
    return default


def clean_hadith_text(text):
    if text is None:
        return ""

    text = html.unescape(str(text))
    text = unicodedata.normalize("NFKC", text)

    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(
        r"[\u200B-\u200F\u202A-\u202E\u2060\uFEFF]",
        "",
        text,
    )
    text = text.replace("\u00AD", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def language_entry(entries, languages):
    """Return the first language-specific Hadith entry matching languages."""
    if not isinstance(entries, list):
        return None

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        lang = str(entry.get("lang", "")).strip().lower()
        if lang in languages and clean_hadith_text(entry.get("body", "")):
            return entry
    return None


def grade_text(item):
    grades = item.get("grades", []) if isinstance(item, dict) else []
    if not isinstance(grades, list):
        return ""

    values = []
    for grade in grades:
        if not isinstance(grade, dict):
            continue
        value = clean_hadith_text(grade.get("grade", ""))
        graded_by = clean_hadith_text(grade.get("graded_by", ""))
        if value and graded_by:
            values.append(f"{value} ({graded_by})")
        elif value:
            values.append(value)

    # Keep the API's published grading text exactly; only join multiple
    # published grade records for metadata/reference display.
    return " | ".join(dict.fromkeys(values))


def collection_display_name(collection):
    names = {
        "bukhari": "Sahih al-Bukhari",
        "muslim": "Sahih Muslim",
    }
    return names.get(collection.lower(), collection)


def hadith_identifier(hadith):
    collection = get_hadith_field(
        hadith, "collection", "bookSlug", default="unknown"
    ).lower()
    number = get_hadith_field(
        hadith, "hadithNumber", "hadith_number", "number", default="unknown"
    )
    urn = get_hadith_field(hadith, "urn", "id", "hadithId", default="")
    if urn:
        return f"{collection}|{number}|{urn}".strip().lower()
    return f"{collection}|{number}".strip().lower()


def normalize_sunnah_hadith(item, fallback_collection=""):
    """Convert an official Sunnah.com Hadith object to our video format."""
    if not isinstance(item, dict):
        return None

    entries = item.get("hadith", [])
    arabic_entry = language_entry(entries, ARABIC_LANGS)
    urdu_entry = language_entry(entries, URDU_LANGS)

    if not arabic_entry or not urdu_entry:
        return None

    collection = get_hadith_field(
        item, "collection", default=fallback_collection
    ).lower()
    number = get_hadith_field(item, "hadithNumber", default="")

    arabic = clean_hadith_text(arabic_entry.get("body", ""))
    urdu = clean_hadith_text(urdu_entry.get("body", ""))

    chapter_number = get_hadith_field(
        urdu_entry, "chapterNumber", default=""
    ) or get_hadith_field(arabic_entry, "chapterNumber", default="")
    chapter_title_urdu = clean_hadith_text(
        urdu_entry.get("chapterTitle", "")
    )
    chapter_title = clean_hadith_text(
        arabic_entry.get("chapterTitle", "")
    )

    grade = grade_text(item)
    book_name = collection_display_name(collection)

    # Use the canonical Sunnah.com collection + hadith number reference.
    reference = f"{book_name} • Hadith {number}" if number else book_name
    if grade:
        reference += f" • {grade}"

    context = ""
    if chapter_title_urdu:
        context = f"باب: {chapter_title_urdu}"
    elif chapter_title:
        context = f"Chapter: {chapter_title}"

    return {
        "id": get_hadith_field(item, "urn", default=""),
        "urn": get_hadith_field(urdu_entry, "urn", default="")
              or get_hadith_field(arabic_entry, "urn", default=""),
        "title": "حدیث شریف",
        "collection": collection,
        "bookSlug": collection,
        "book": book_name,
        "bookNumber": get_hadith_field(item, "bookNumber", default=""),
        "chapter": chapter_number,
        "chapterId": get_hadith_field(item, "chapterId", default=""),
        "chapterTitle": chapter_title,
        "chapterTitleUrdu": chapter_title_urdu,
        "hadithNumber": number,
        "grade": grade,
        "reference": reference,
        "arabic": arabic,
        "hadithUrdu": urdu,
        "context": context,
        "source_url": (
            f"https://sunnah.com/{collection}/{number}"
            if collection and number else ""
        ),
        "_raw": item,
    }


def sunnah_api_get(path, params=None, attempts=4, timeout=60):
    if not SUNNAH_API_KEY:
        raise RuntimeError(
            "SUNNAH_API_KEY GitHub Secret is missing. "
            "Add the secret under Settings > Secrets and variables > Actions."
        )

    url = f"{SUNNAH_API_URL}/{path.lstrip('/')}"
    last_error = None

    headers = {
        "X-API-Key": SUNNAH_API_KEY,
        "Accept": "application/json",
        "User-Agent": "Islamic-Hadith-Video-Automation/2.0 (GitHub Actions)",
    }

    for attempt in range(1, attempts + 1):
        print(f"Sunnah.com API request {attempt}/{attempts}: {url}")
        try:
            response = SESSION.get(
                url,
                params=params or {},
                headers=headers,
                timeout=timeout,
            )
            print("HTTP status:", response.status_code)

            if response.status_code == 429 or response.status_code >= 500:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 2.0 * attempt
                except ValueError:
                    delay = 2.0 * attempt
                time.sleep(max(delay, API_REQUEST_DELAY))
                continue

            if response.status_code in (401, 403):
                raise RuntimeError(
                    f"Sunnah.com API authentication failed (HTTP {response.status_code}). "
                    "Check SUNNAH_API_KEY and confirm your API access/languages."
                )

            response.raise_for_status()
            data = response.json()
            time.sleep(API_REQUEST_DELAY)
            return data

        except RuntimeError:
            raise
        except (requests.exceptions.RequestException, ValueError) as exc:
            last_error = exc
            print("Sunnah.com API error:", exc)
            if attempt < attempts:
                time.sleep(2 * attempt)

    raise RuntimeError(
        f"Sunnah.com API request failed after {attempts} attempts. "
        f"Last error: {last_error}"
    )


def extract_hadith_list(data):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    value = data.get("data")
    return value if isinstance(value, list) else []


def fetch_collection_total(collection):
    """Get the total API result count without downloading the collection."""
    data = sunnah_api_get(
        "/hadiths",
        params={
            "collection": collection,
            "limit": 1,
            "page": 1,
        },
    )
    total = data.get("total") if isinstance(data, dict) else None
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = 0

    if total <= 0:
        raise RuntimeError(
            f"Sunnah.com returned no usable total for collection '{collection}'."
        )
    print(f"Collection {collection}: {total} Hadith records available to query")
    return total


def fetch_hadith_by_number(collection, number):
    data = sunnah_api_get(
        f"/collections/{collection}/hadiths/{number}"
    )
    if not isinstance(data, dict):
        return None
    return normalize_sunnah_hadith(data, fallback_collection=collection)


def fetch_hadith_candidates():
    """
    Retrieve only a small number of individual Hadith records instead of
    downloading entire collections. This is much lighter on the official API.
    """
    if not HADITH_COLLECTIONS:
        raise RuntimeError("HADITH_COLLECTIONS is empty.")

    totals = {
        collection: fetch_collection_total(collection)
        for collection in HADITH_COLLECTIONS
    }

    candidates = []
    seen = set()
    attempts = 0

    while len(candidates) < max(BATCH_SIZE * 4, 12) and attempts < RANDOM_HADITH_ATTEMPTS:
        attempts += 1
        collection = random.choice(list(totals.keys()))
        number = random.randint(1, totals[collection])

        try:
            item = fetch_hadith_by_number(collection, number)
        except Exception as exc:
            print(f"Skipping {collection} #{number}: {exc}")
            continue

        if not item:
            print(
                f"Skipping {collection} #{number}: "
                "Arabic and/or Urdu language data was not returned."
            )
            continue

        identifier = hadith_identifier(item)
        if identifier in seen:
            continue

        seen.add(identifier)
        candidates.append(item)
        print(
            f"Usable Hadith {len(candidates)}: "
            f"{item['book']} #{item['hadithNumber']}"
        )

    if len(candidates) < BATCH_SIZE:
        raise RuntimeError(
            f"Only {len(candidates)} Hadiths with BOTH Arabic and Urdu were "
            f"found after {attempts} API lookups. "
            "Your Sunnah.com API key may not include Urdu data, or the "
            "selected collections may not expose Urdu for those records. "
            "No AI translation will be used."
        )

    print(f"Usable Hadiths available: {len(candidates)}")
    return candidates


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
        default="حدیث شریف"
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
        "hadithArabic",
        "text"
    )

    context = get_dua_field(
        dua,
        "context",
        "chapterTitleUrdu",
        "chapterTitle",
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

    display_title = title.strip() or "حدیث شریف"

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
        10
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
        gap=10
    )

    # --------------------------------------------------------
    # REFERENCE BADGE
    # --------------------------------------------------------

    ref_y = urdu_bottom + 28

    # English-only reference badge. This avoids Arabic/Urdu glyph
    # square/tofu problems while keeping the source easy to read.
    ref_font_path = find_font([
        "NotoSans-Regular.ttf",
        "DejaVuSans.ttf",
    ]) or ENGLISH_FONT

    ref_font = load_font(
        ref_font_path,
        27
    )

    ref_text = reference or "Hadith source"

    ref_box = draw.textbbox(
        (0, 0),
        ref_text,
        font=ref_font
    )

    ref_width = ref_box[2] - ref_box[0] + 90
    ref_width = min(ref_width, WIDTH - 180)
    ref_height = 60

    ref_x1 = (WIDTH - ref_width) // 2
    ref_x2 = ref_x1 + ref_width

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
            36,
            26,
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
            DARK_TEXT,
            "rtl",
            "ur",
            gap=5
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
    hadith,
    video_number
):

    title = get_dua_field(hadith, "title", default="حدیث شریف")
    reference = get_dua_field(hadith, "reference", default="Hadith source")
    arabic = get_dua_field(hadith, "arabic", default="")
    urdu = get_dua_field(hadith, "hadithUrdu", "urdu", default="")
    context = get_dua_field(hadith, "context", default="")
    grade = get_dua_field(hadith, "grade", default="")
    book = get_dua_field(hadith, "book", default="")
    number = get_dua_field(hadith, "hadithNumber", default="")

    youtube_title = (
        f"Hadith {number} | {book}" if number and book
        else "Hadith Sharif | Islamic Reminder"
    )

    youtube_description = f"""{title}

Arabic Hadith:
{arabic}

Urdu Hadith:
{urdu}

Reference:
{reference}

Book:
{book}

Hadith Number:
{number}

Grade:
{grade}

{context}

Source: Hadith API

This video uses the Hadith text and Urdu text returned by the configured API. No AI translation or paraphrasing is used.

#Hadith #IslamicShorts #HadithReminder #IslamicReminder #Sunnah #Muslim
"""

    youtube_hashtags = (
        "#Hadith #IslamicShorts #HadithReminder "
        "#IslamicReminder #Sunnah #Muslim #IslamicVideo"
    )

    youtube_tags = (
        "Hadith, Hadith Sharif, Islamic Hadith, Hadith Urdu, "
        "Hadith Arabic, Sahih Hadith, Sunnah, Islamic Reminder, "
        "Hadith Reminder, Islamic Shorts, Muslim, Islam, Sunnah Hadith"
    )

    tiktok_caption = f"""{title}

{urdu}

Reference: {reference}

#Hadith #Sunnah #IslamicTok #IslamicReminder #Muslim #HadithReminder
"""

    tiktok_hashtags = (
        "#Hadith #Sunnah #IslamicTok #IslamicReminder "
        "#Muslim #HadithReminder #IslamicContent"
    )

    return f"""============================================================
ISLAMIC HADITH VIDEO {video_number}
============================================================

TITLE:
{title}

REFERENCE:
{reference}

BOOK:
{book}

HADITH NUMBER:
{number}

GRADE:
{grade}

ARABIC HADITH:
{arabic}

URDU HADITH:
{urdu}

CONTEXT / CHAPTER:
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

Source:
Sunnah.com Official API

API Endpoint:
{SUNNAH_API_URL}


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
    print("ISLAMIC HADITH VIDEO AUTOMATION")
    print("=" * 70)

    check_environment()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    clean_folder(OUTPUT_DIR)
    clean_folder(WORK_DIR)

    # --------------------------------------------------------
    # Fetch Hadiths from API
    # --------------------------------------------------------

    hadiths = fetch_hadith_candidates()
    selected_hadiths, old_used = choose_three_hadiths(hadiths)

    print("")
    print("SELECTED 3 DIFFERENT HADITHS")

    for number, hadith in enumerate(selected_hadiths, start=1):
        print(
            f"{number}. "
            f"{get_dua_field(hadith, 'book')} "
            f"#{get_dua_field(hadith, 'hadithNumber')}"
        )
        print(f"   {get_dua_field(hadith, 'reference')}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    batch_dir = OUTPUT_DIR / f"batch_{timestamp}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    new_used = list(old_used)

    # --------------------------------------------------------
    # Create 3 videos
    # --------------------------------------------------------

    for index, hadith in enumerate(selected_hadiths, start=1):

        print("")
        print("=" * 70)
        print(f"CREATING VIDEO {index}/{BATCH_SIZE}")
        print("=" * 70)

        reference = get_dua_field(
            hadith,
            "reference",
            default="Hadith source"
        )

        print(f"Reference: {reference}")
        print(f"Book: {get_dua_field(hadith, 'book')}")
        print(f"Hadith number: {get_dua_field(hadith, 'hadithNumber')}")
        print(f"Grade: {get_dua_field(hadith, 'grade')}")

        arabic = get_dua_field(hadith, "arabic")
        urdu = get_dua_field(hadith, "hadithUrdu")

        if not arabic or not urdu:
            raise RuntimeError(
                "Selected Hadith is missing Arabic or Urdu text."
            )

        # ----------------------------------------------------
        # Background
        # ----------------------------------------------------

        background = download_background(index)

        # ----------------------------------------------------
        # Poster
        # ----------------------------------------------------

        poster = WORK_DIR / f"poster_{index}.png"

        create_poster(
            hadith,
            urdu,
            poster
        )

        # ----------------------------------------------------
        # Video
        # ----------------------------------------------------

        video_path = batch_dir / f"hadith_{index:02d}.mp4"

        create_video(
            background,
            poster,
            video_path
        )

        # ----------------------------------------------------
        # Social metadata
        # ----------------------------------------------------

        social_path = (
            batch_dir / f"hadith_{index:02d}_social_media.txt"
        )

        social_text = make_social_text(
            hadith,
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
            "title": get_dua_field(hadith, "title", default="حدیث شریف"),
            "reference": reference,
            "book": get_dua_field(hadith, "book"),
            "book_slug": get_dua_field(hadith, "bookSlug"),
            "hadith_number": get_dua_field(hadith, "hadithNumber"),
            "chapter": get_dua_field(hadith, "chapter"),
            "chapter_title": get_dua_field(hadith, "chapterTitle"),
            "chapter_title_urdu": get_dua_field(hadith, "chapterTitleUrdu"),
            "grade": get_dua_field(hadith, "grade"),
            "arabic": arabic,
            "urdu": urdu,
            "context": get_dua_field(hadith, "context"),
            "source": {
                "name": "Sunnah.com Official API",
                "endpoint": SUNNAH_API_URL,
            },
            "video": {
                "width": WIDTH,
                "height": HEIGHT,
                "fps": FPS,
                "duration_seconds": VIDEO_SECONDS,
            }
        }

        metadata_path = batch_dir / f"hadith_{index:02d}.json"
        save_json(metadata_path, metadata)

        # ----------------------------------------------------
        # Mark used
        # ----------------------------------------------------

        identifier = hadith_identifier(hadith)
        if identifier not in new_used:
            new_used.append(identifier)

    # Save only after all 3 videos succeeded.
    save_json(USED_FILE, new_used)

    readme = f"""ISLAMIC HADITH VIDEO BATCH

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
Sunnah.com Official API

API Endpoint:
{SUNNAH_API_URL}

Collections:
{', '.join(HADITH_COLLECTIONS)}

Status filter:
Not used — collection-based selection.

Each video includes:
- MP4 video
- YouTube title
- YouTube description
- YouTube hashtags
- YouTube tags
- TikTok caption
- TikTok hashtags
- JSON metadata

No AI translation or AI paraphrasing is used.
The Arabic and Urdu Hadith text comes directly from the API response.
"""

    (batch_dir / "README.txt").write_text(
        readme,
        encoding="utf-8"
    )

    mp4_files = list(batch_dir.glob("*.mp4"))
    if len(mp4_files) != 3:
        raise RuntimeError(
            f"Expected exactly 3 videos, found {len(mp4_files)}."
        )

    social_files = list(batch_dir.glob("*_social_media.txt"))
    if len(social_files) != 3:
        raise RuntimeError(
            f"Expected 3 social files, found {len(social_files)}."
        )

    zip_path = (
        OUTPUT_DIR / f"Islamic-Hadith-3-Videos-{timestamp}.zip"
    )

    create_zip(batch_dir, zip_path)

    print("")
    print("=" * 70)
    print("FINAL OUTPUT")
    print("=" * 70)
    print("Videos:")
    for file in sorted(mp4_files):
        print(f"  {file.name}")
    print("Social files:")
    for file in sorted(social_files):
        print(f"  {file.name}")
    print("ONE ZIP:")
    print(f"  {zip_path}")
    print("")
    print("=" * 70)
    print("SUCCESS")
    print("3 UNIQUE HADITH VIDEOS CREATED")
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