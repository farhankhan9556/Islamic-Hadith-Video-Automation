import os
import re
import json
import html
import random
import shutil
import zipfile
import subprocess
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

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()

PEXELS_URL = "https://api.pexels.com/v1/search"

QURANENC_TRANSLATION_KEY = "urdu_junagarhi"
QURANENC_API = "https://quranenc.com/api/v1"

PROJECT_DIR = Path(__file__).resolve().parent

DATA_FILE = PROJECT_DIR / "data" / "duas.json"
USED_FILE = PROJECT_DIR / "used_duas.json"

FONT_DIR = PROJECT_DIR / "fonts"
AUDIO_FILE = PROJECT_DIR / "audio" / "islamic_background.mp3"

OUTPUT_DIR = PROJECT_DIR / "output"
WORK_DIR = PROJECT_DIR / "work"


# ============================================================
# COLORS
# ============================================================

BG_OVERLAY = (8, 12, 18, 115)

CARD = (247, 242, 228, 238)
CARD_INNER = (255, 250, 238, 40)

GOLD = (198, 157, 72, 255)
GOLD_LIGHT = (232, 205, 137, 255)

DARK_TEXT = (36, 30, 24, 255)
MUTED_TEXT = (88, 76, 62, 255)

WHITE = (255, 255, 255, 255)

GREEN = (44, 93, 71, 255)


# ============================================================
# FONT LOCATOR
# ============================================================

def find_font(names):
    candidates = []

    for name in names:
        candidates.extend([
            FONT_DIR / name,
            Path("/usr/share/fonts/truetype/noto") / name,
            Path("/usr/share/fonts/opentype/noto") / name,
        ])

    for path in candidates:
        if path.exists():
            return str(path)

    # Try fc-match on Ubuntu
    for family in names:
        try:
            result = subprocess.run(
                ["fc-match", "-f", "%{file}", family],
                capture_output=True,
                text=True,
                check=False,
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
    "NotoNastaliqUrdu-Bold.ttf",
    "NotoNaskhArabic-Regular.ttf",
])

TITLE_FONT = find_font([
    "NotoNastaliqUrdu-Regular.ttf",
    "NotoNaskhArabic-Regular.ttf",
])

ENGLISH_FONT = find_font([
    "NotoSans-Regular.ttf",
])


# ============================================================
# CHECKS
# ============================================================

def check_environment():

    print("Checking environment...")

    if not features.check("raqm"):
        raise RuntimeError(
            "Pillow RAQM support is not available. "
            "Install libraqm-dev/libfribidi-dev and rebuild Pillow."
        )

    if not ARABIC_FONT:
        raise RuntimeError("Arabic font not found.")

    if not URDU_FONT:
        raise RuntimeError("Urdu font not found.")

    if not TITLE_FONT:
        raise RuntimeError("Title font not found.")

    if not DATA_FILE.exists():
        raise RuntimeError(f"Missing file: {DATA_FILE}")

    if not AUDIO_FILE.exists():
        raise RuntimeError(f"Missing audio: {AUDIO_FILE}")

    if not PEXELS_API_KEY:
        raise RuntimeError(
            "PEXELS_API_KEY GitHub Secret is missing."
        )

    print(f"Arabic font: {ARABIC_FONT}")
    print(f"Urdu font:   {URDU_FONT}")
    print(f"RAQM:        {features.check('raqm')}")


# ============================================================
# GENERAL HELPERS
# ============================================================

def load_json(path, default):
    if not path.exists():
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def clean_output_folder():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for item in OUTPUT_DIR.iterdir():

        if item.is_dir():
            shutil.rmtree(item)

        else:
            item.unlink()


def clean_work_folder():
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)

    WORK_DIR.mkdir(parents=True, exist_ok=True)


def safe_filename(text):
    text = str(text)

    text = re.sub(
        r'[<>:"/\\|?*\x00-\x1F]',
        "_",
        text
    )

    text = re.sub(r"\s+", "_", text)

    return text[:100]


# ============================================================
# QURANENC
# ============================================================

def get_quranenc_version():

    url = f"{QURANENC_API}/translations/list/ur"

    try:

        response = requests.get(
            url,
            params={"localization": "ur"},
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        if isinstance(data, list):

            for item in data:

                if item.get("key") == QURANENC_TRANSLATION_KEY:

                    return item.get(
                        "version",
                        "Version not returned by API"
                    )

    except Exception as e:

        print(
            "Warning: Could not retrieve QuranEnc version:",
            e
        )

    return "Version not returned by API"


def clean_quranenc_translation(text):

    """
    Removes HTML/footnote formatting that can appear in
    QuranEnc translations.

    Examples removed:

        <sup>[1]</sup>
        [1]
        ［1］
        ^{[1]}
        ¹ ² ³

    This prevents the little footnote markers from becoming
    square boxes when rendered by Pillow.
    """

    if not text:
        return ""

    text = html.unescape(str(text))

    # --------------------------------------------------------
    # Remove HTML tags
    # --------------------------------------------------------

    # Specifically remove superscript footnotes first
    text = re.sub(
        r"<sup[^>]*>\s*[\[\［]?\s*[0-9٠-٩]+\s*[\]\］]?\s*</sup>",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"<sup[^>]*>\s*\^\s*\{\s*[\[]?\s*[0-9٠-٩]+\s*[\]]?\s*\}\s*</sup>",
        "",
        text,
        flags=re.IGNORECASE
    )

    # Remove remaining HTML
    text = re.sub(
        r"<[^>]+>",
        "",
        text
    )

    # --------------------------------------------------------
    # Remove QuranEnc web-style footnote markers
    # --------------------------------------------------------

    # ^{[1]}
    text = re.sub(
        r"\^\s*\{\s*[\[\［]\s*[0-9٠-٩]+\s*[\]\］]\s*\}",
        "",
        text
    )

    # ^{1}
    text = re.sub(
        r"\^\s*\{\s*[0-9٠-٩]+\s*\}",
        "",
        text
    )

    # [1]
    text = re.sub(
        r"[\[\［]\s*[0-9٠-٩]+\s*[\]\］]",
        "",
        text
    )

    # ﴿1﴾
    text = re.sub(
        r"﴿\s*[0-9٠-٩]+\s*﴾",
        "",
        text
    )

    # (1) when used as a standalone footnote marker
    text = re.sub(
        r"(?<!\d)\(\s*[0-9٠-٩]+\s*\)(?!\d)",
        "",
        text
    )

    # Superscript Unicode digits
    text = re.sub(
        r"[\u00B9\u00B2\u00B3\u2070-\u2079]",
        "",
        text
    )

    # --------------------------------------------------------
    # Remove stray formatting symbols left by footnotes
    # --------------------------------------------------------

    text = text.replace("^{", "")
    text = text.replace("}", "")

    # Invisible formatting characters
    text = re.sub(
        r"[\u200b\u200c\u200d\u2060\ufeff]",
        "",
        text
    )

    # Soft hyphen
    text = text.replace("\u00ad", "")

    # Normalize whitespace
    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    # Clean spaces before punctuation
    text = re.sub(
        r"\s+([،۔,.;:!?؟])",
        r"\1",
        text
    )

    # --------------------------------------------------------
    # Final safety check
    # --------------------------------------------------------

    forbidden = [
        "□",
        "�",
        "^{[",
        "<sup",
        "</sup>",
    ]

    for bad in forbidden:

        if bad in text:

            raise RuntimeError(
                f"Unclean QuranEnc marker remained: {bad!r}"
            )

    return text


def fetch_single_translation(sura, ayah):

    url = (
        f"{QURANENC_API}/translation/aya/"
        f"{QURANENC_TRANSLATION_KEY}/"
        f"{sura}/{ayah}"
    )

    response = requests.get(
        url,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    translation = data.get("translation", "")

    return clean_quranenc_translation(
        translation
    )


def fetch_quran_translation(
    sura,
    ayah,
    ayah_end=None
):

    if not ayah_end:
        ayah_end = ayah

    translations = []

    for current_ayah in range(
        int(ayah),
        int(ayah_end) + 1
    ):

        print(
            f"Fetching QuranEnc "
            f"{sura}:{current_ayah}"
        )

        translation = fetch_single_translation(
            sura,
            current_ayah
        )

        if translation:
            translations.append(
                translation
            )

    result = " ".join(translations)

    result = clean_quranenc_translation(result)

    if not result:
        raise RuntimeError(
            f"Empty QuranEnc translation for "
            f"{sura}:{ayah}-{ayah_end}"
        )

    return result


# ============================================================
# DUA DATA
# ============================================================

def get_dua_field(dua, *names, default=""):

    for name in names:

        value = dua.get(name)

        if value is not None and str(value).strip():

            return value

    return default


def dua_identifier(dua):

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

    if len(data) < BATCH_SIZE:

        raise RuntimeError(
            f"You need at least {BATCH_SIZE} "
            f"different duas in data/duas.json."
        )

    return data


def choose_three_duas(duas):

    used = load_json(
        USED_FILE,
        []
    )

    if not isinstance(used, list):
        used = []

    used_set = set(
        str(x).strip()
        for x in used
    )

    # --------------------------------------------------------
    # First preference: never-used duas
    # --------------------------------------------------------

    unused = []

    for dua in duas:

        identifier = dua_identifier(dua)

        if identifier not in used_set:

            unused.append(dua)

    # --------------------------------------------------------
    # If enough unused duas exist, choose from them
    # --------------------------------------------------------

    if len(unused) >= BATCH_SIZE:

        selected = random.sample(
            unused,
            BATCH_SIZE
        )

    else:

        # We have reached the end of the list.
        # Start a new cycle, but still guarantee 3
        # different videos in this batch.

        print(
            "All available duas have been used. "
            "Starting a new cycle."
        )

        selected = random.sample(
            duas,
            BATCH_SIZE
        )

        # Reset used list for the new cycle
        used = []

    return selected, used


# ============================================================
# PEXELS BACKGROUND
# ============================================================

BACKGROUND_SEARCHES = [
    "mosque architecture night",
    "islamic architecture",
    "mosque sunset",
    "islamic geometric pattern",
    "beautiful mosque",
    "ramadan mosque",
    "mosque interior",
    "islamic art background",
]


def download_background(index):

    query = random.choice(
        BACKGROUND_SEARCHES
    )

    headers = {
        "Authorization": PEXELS_API_KEY
    }

    params = {
        "query": query,
        "orientation": "portrait",
        "size": "large",
        "per_page": 20,
        "page": random.randint(1, 5),
    }

    print(
        f"Pexels background search: {query}"
    )

    response = requests.get(
        PEXELS_URL,
        headers=headers,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    photos = data.get(
        "photos",
        []
    )

    if not photos:

        raise RuntimeError(
            "Pexels returned no background images."
        )

    # Shuffle to reduce repetition
    random.shuffle(photos)

    photo = photos[0]

    src = photo.get("src", {})

    image_url = (
        src.get("portrait")
        or src.get("large2x")
        or src.get("large")
    )

    if not image_url:

        raise RuntimeError(
            "Pexels photo has no usable image URL."
        )

    output = (
        WORK_DIR /
        f"background_{index}.jpg"
    )

    image_response = requests.get(
        image_url,
        timeout=60
    )

    image_response.raise_for_status()

    with open(output, "wb") as f:
        f.write(image_response.content)

    return output


# ============================================================
# IMAGE HELPERS
# ============================================================

def load_font(path, size):

    return ImageFont.truetype(
        path,
        size
    )


def text_width(draw, text, font, direction="rtl", language="ur"):

    bbox = draw.textbbox(
        (0, 0),
        text,
        font=font,
        direction=direction,
        language=language
    )

    return bbox[2] - bbox[0]


def wrap_text(
    draw,
    text,
    font,
    max_width,
    direction="rtl",
    language="ur"
):

    words = text.split()

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
                lines.append(current)

            # If one word itself is too long,
            # keep it rather than deleting content.
            current = word

    if current:
        lines.append(current)

    return lines


def fit_text_lines(
    draw,
    text,
    font_path,
    start_size,
    min_size,
    max_width,
    max_height,
    direction,
    language,
    spacing
):

    size = start_size

    while size >= min_size:

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
            size * 1.55
        )

        total_height = (
            len(lines) * line_height
            + max(0, len(lines) - 1) * spacing
        )

        if total_height <= max_height:

            return (
                font,
                lines,
                line_height,
                total_height
            )

        size -= 2

    # Final fallback at minimum size
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
        min_size * 1.55
    )

    total_height = (
        len(lines) * line_height
        + max(0, len(lines) - 1) * spacing
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
    spacing=0
):

    y = top_y

    for line in lines:

        bbox = draw.textbbox(
            (0, 0),
            line,
            font=font,
            direction=direction,
            language=language
        )

        width = (
            bbox[2] - bbox[0]
        )

        x = center_x - width / 2

        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
            direction=direction,
            language=language
        )

        y += line_height + spacing

    return y


# ============================================================
# DECORATIONS
# ============================================================

def draw_corner_geometry(draw):

    # Top-left
    for offset in range(0, 80, 18):

        draw.line(
            [
                (80 + offset, 90),
                (160 + offset, 90),
            ],
            fill=GOLD,
            width=2
        )

    # Top-right
    for offset in range(0, 80, 18):

        draw.line(
            [
                (920 - offset, 90),
                (1000 - offset, 90),
            ],
            fill=GOLD,
            width=2
        )

    # Decorative diamond
    cx = WIDTH // 2
    cy = 82

    points = [
        (cx, cy - 20),
        (cx + 20, cy),
        (cx, cy + 20),
        (cx - 20, cy),
    ]

    draw.polygon(
        points,
        outline=GOLD,
        width=2
    )

    draw.ellipse(
        (
            cx - 5,
            cy - 5,
            cx + 5,
            cy + 5
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
        (WIDTH, HEIGHT),
        (0, 0, 0, 0)
    )

    # --------------------------------------------------------
    # Shadow layer
    # --------------------------------------------------------

    shadow = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0)
    )

    shadow_draw = ImageDraw.Draw(
        shadow
    )

    card_x1 = 70
    card_y1 = 145
    card_x2 = WIDTH - 70
    card_y2 = HEIGHT - 125

    shadow_draw.rounded_rectangle(
        (
            card_x1 + 10,
            card_y1 + 15,
            card_x2 + 10,
            card_y2 + 15
        ),
        radius=48,
        fill=(0, 0, 0, 150)
    )

    shadow = shadow.filter(
        ImageFilter.GaussianBlur(18)
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
            card_x1,
            card_y1,
            card_x2,
            card_y2
        ),
        radius=48,
        fill=CARD,
        outline=GOLD,
        width=4
    )

    # Inner border
    draw.rounded_rectangle(
        (
            card_x1 + 15,
            card_y1 + 15,
            card_x2 - 15,
            card_y2 - 15
        ),
        radius=38,
        outline=(198, 157, 72, 80),
        width=2
    )

    draw_corner_geometry(
        draw
    )

    # --------------------------------------------------------
    # Values
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

    context = get_dua_field(
        dua,
        "context",
        "story",
        "description",
        default=""
    )

    arabic = get_dua_field(
        dua,
        "arabic",
        "dua",
        "text"
    )

    # --------------------------------------------------------
    # Title
    # --------------------------------------------------------

    title_font = load_font(
        TITLE_FONT,
        62
    )

    title_lines = wrap_text(
        draw,
        str(title),
        title_font,
        850,
        direction="rtl",
        language="ur"
    )

    y = 205

    y = draw_centered_lines(
        draw,
        title_lines,
        title_font,
        WIDTH // 2,
        y,
        85,
        GOLD,
        "rtl",
        "ur",
        spacing=4
    )

    # Divider
    divider_y = y + 20

    draw.line(
        (
            225,
            divider_y,
            855,
            divider_y
        ),
        fill=GOLD,
        width=3
    )

    # --------------------------------------------------------
    # Arabic panel
    # --------------------------------------------------------

    arabic_box_top = divider_y + 45
    arabic_box_bottom = arabic_box_top + 390

    draw.rounded_rectangle(
        (
            105,
            arabic_box_top,
            975,
            arabic_box_bottom
        ),
        radius=35,
        fill=(255, 255, 255, 85),
        outline=(198, 157, 72, 90),
        width=2
    )

    arabic_font, arabic_lines, arabic_line_height, arabic_total = fit_text_lines(
        draw,
        str(arabic),
        ARABIC_FONT,
        start_size=62,
        min_size=42,
        max_width=790,
        max_height=315,
        direction="rtl",
        language="ar",
        spacing=2
    )

    arabic_start = (
        arabic_box_top
        + (
            (arabic_box_bottom - arabic_box_top)
            - arabic_total
        ) / 2
    )

    draw_centered_lines(
        draw,
        arabic_lines,
        arabic_font,
        WIDTH // 2,
        int(arabic_start),
        arabic_line_height,
        DARK_TEXT,
        "rtl",
        "ar",
        spacing=2
    )

    # --------------------------------------------------------
    # Urdu meaning
    # --------------------------------------------------------

    urdu_box_top = arabic_box_bottom + 35
    urdu_box_bottom = urdu_box_top + 470

    draw.rounded_rectangle(
        (
            105,
            urdu_box_top,
            975,
            urdu_box_bottom
        ),
        radius=35,
        fill=(255, 255, 255, 55),
        outline=(198, 157, 72, 70),
        width=2
    )

    meaning_label_font = load_font(
        TITLE_FONT,
        34
    )

    label = "اردو ترجمہ"

    bbox = draw.textbbox(
        (0, 0),
        label,
        font=meaning_label_font,
        direction="rtl",
        language="ur"
    )

    label_width = (
        bbox[2] - bbox[0]
    )

    draw.text(
        (
            WIDTH // 2 - label_width / 2,
            urdu_box_top + 22
        ),
        label,
        font=meaning_label_font,
        fill=GOLD,
        direction="rtl",
        language="ur"
    )

    meaning_font, meaning_lines, meaning_line_height, meaning_total = fit_text_lines(
        draw,
        translation,
        URDU_FONT,
        start_size=40,
        min_size=28,
        max_width=790,
        max_height=355,
        direction="rtl",
        language="ur",
        spacing=2
    )

    meaning_start = (
        urdu_box_top
        + 85
        + (
            (urdu_box_bottom - urdu_box_top - 85)
            - meaning_total
        ) / 2
    )

    draw_centered_lines(
        draw,
        meaning_lines,
        meaning_font,
        WIDTH // 2,
        int(meaning_start),
        meaning_line_height,
        DARK_TEXT,
        "rtl",
        "ur",
        spacing=2
    )

    # --------------------------------------------------------
    # Reference badge
    # --------------------------------------------------------

    ref_y = urdu_box_bottom + 32

    ref_font = load_font(
        ENGLISH_FONT,
        32
    )

    ref_text = (
        f"Quran {reference}"
        if reference
        else "Quran"
    )

    ref_bbox = draw.textbbox(
        (0, 0),
        ref_text,
        font=ref_font
    )

    ref_width = (
        ref_bbox[2] - ref_bbox[0]
        + 80
    )

    ref_height = 62

    ref_x1 = (
        WIDTH - ref_width
    ) // 2

    ref_x2 = ref_x1 + ref_width

    draw.rounded_rectangle(
        (
            ref_x1,
            ref_y,
            ref_x2,
            ref_y + ref_height
        ),
        radius=31,
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
    # Context
    # --------------------------------------------------------

    if context:

        context_top = ref_y + ref_height + 30
        context_bottom = HEIGHT - 165

        context_font, context_lines, context_line_height, context_total = fit_text_lines(
            draw,
            str(context),
            URDU_FONT,
            start_size=31,
            min_size=23,
            max_width=770,
            max_height=context_bottom - context_top - 30,
            direction="rtl",
            language="ur",
            spacing=1
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
            spacing=1
        )

    # --------------------------------------------------------
    # Bottom decorative line
    # --------------------------------------------------------

    draw.line(
        (
            320,
            HEIGHT - 105,
            760,
            HEIGHT - 105
        ),
        fill=GOLD,
        width=2
    )

    image.save(
        output_path,
        "PNG"
    )

    return output_path


# ============================================================
# SOCIAL MEDIA TEXT
# ============================================================

def make_social_text(
    dua,
    translation,
    quranenc_version,
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

    title_en = get_dua_field(
        dua,
        "title_en",
        "english_title",
        default=""
    )

    reference = get_dua_field(
        dua,
        "reference",
        "ref",
        "reference_text"
    )

    context = get_dua_field(
        dua,
        "context",
        "story",
        "description",
        default=""
    )

    arabic = get_dua_field(
        dua,
        "arabic",
        "dua",
        "text"
    )

    # --------------------------------------------------------
    # YouTube
    # --------------------------------------------------------

    if title_en:

        youtube_title = (
            f"{title} | {title_en} | "
            f"Quranic Dua #{reference}"
        )

    else:

        youtube_title = (
            f"{title} | قرآن کی خوبصورت دعا "
            f"#{reference}"
        )

    youtube_description = f"""ایک خوبصورت قرآنی دعا یاد کریں اور اسے اپنی روزمرہ زندگی میں پڑھیں۔

دعا:
{arabic}

اردو ترجمہ:
{translation}

حوالہ:
سورۃ/آیت {reference}

پس منظر:
{context}

یہ ویڈیو قرآن کریم کے معنی کے مستند اردو ترجمہ کی بنیاد پر تیار کی گئی ہے۔

Translation Source:
QuranEnc.com

Urdu Translation:
Muhammad Junagarhi

QuranEnc Translation Version:
{quranenc_version}

اللہ تعالیٰ ہمیں قرآن کریم سمجھنے اور اس پر عمل کرنے کی توفیق عطا فرمائے۔ آمین۔

#Quran #QuranicDua #Dua #IslamicShorts #IslamicReminder #UrduIslamic #QuranReminder
"""

    youtube_hashtags = (
        "#Quran #QuranicDua #Dua "
        "#IslamicShorts #IslamicReminder "
        "#UrduIslamic #QuranReminder "
        "#IslamicVideo #Muslim"
    )

    youtube_tags = (
        "Quran, Quranic Dua, Dua, Islamic Dua, "
        "Quran Dua, Urdu Quran, Urdu Islamic Video, "
        "Islamic Reminder, Quran Reminder, Islamic Shorts, "
        "Muslim Reminder, Daily Dua, Quran Verses, "
        "Islamic Status, Urdu Islamic Shorts"
    )

    # --------------------------------------------------------
    # TikTok
    # --------------------------------------------------------

    tiktok_caption = f"""{title}

{arabic}

اردو ترجمہ:
{translation}

حوالہ: {reference}

قرآن کریم کی دعاؤں کو یاد کریں اور دوسروں تک بھی پہنچائیں۔

#Quran #Dua #QuranicDua #IslamicTok #IslamicReminder #UrduIslamic #Muslim #QuranReminder #IslamicVideo
"""

    tiktok_hashtags = (
        "#Quran #Dua #QuranicDua "
        "#IslamicTok #IslamicReminder "
        "#UrduIslamic #Muslim "
        "#QuranReminder #IslamicVideo "
        "#IslamicContent"
    )

    # --------------------------------------------------------
    # TXT
    # --------------------------------------------------------

    return f"""============================================================
ISLAMIC QURANIC DUA VIDEO {video_number}
============================================================

TITLE
{title}

REFERENCE
{reference}

ARABIC DUA
{arabic}

URDU MEANING
{translation}

CONTEXT / STORY
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
SOURCE INFORMATION
============================================================

Quran Translation Source:
QuranEnc.com

Urdu Translation:
Muhammad Junagarhi

Translation Key:
{QURANENC_TRANSLATION_KEY}

Translation Version:
{quranenc_version}

The Quranic meaning is retrieved from the QuranEnc API.

============================================================
VIDEO
============================================================

Resolution:
1080 x 1920

Duration:
60 seconds

Format:
MP4 / H.264

============================================================
"""


# ============================================================
# VIDEO CREATION
# ============================================================

def create_video(
    background,
    poster,
    output_video
):

    frames = FPS * VIDEO_SECONDS

    filter_complex = (
        "[0:v]"
        "scale=1080:1920:"
        "force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "eq=brightness=-0.08:saturation=0.82,"
        "zoompan="
        "z='min(zoom+0.00018,1.08)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        f"d={frames}:"
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

        str(output_video),
    ]

    print(
        "Creating video:",
        output_video
    )

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:

        print(result.stdout)
        print(result.stderr)

        raise RuntimeError(
            f"FFmpeg failed for {output_video}"
        )

    if not output_video.exists():

        raise RuntimeError(
            f"Video was not created: {output_video}"
        )

    if output_video.stat().st_size < 10000:

        raise RuntimeError(
            f"Video file appears invalid: {output_video}"
        )

    print(
        f"Video created: "
        f"{output_video.stat().st_size / 1024 / 1024:.2f} MB"
    )


# ============================================================
# ZIP
# ============================================================

def create_zip(batch_dir, zip_path):

    print(
        "Creating single ZIP:"
    )

    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED
    ) as zip_file:

        for file in sorted(
            batch_dir.iterdir()
        ):

            if file.is_file():

                zip_file.write(
                    file,
                    arcname=file.name
                )

    if not zip_path.exists():

        raise RuntimeError(
            "ZIP file was not created."
        )

    print(
        f"ZIP created: "
        f"{zip_path.stat().st_size / 1024 / 1024:.2f} MB"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("ISLAMIC QURANIC DUA VIDEO AUTOMATION")
    print("=" * 70)
    print("")

    check_environment()

    clean_output_folder()
    clean_work_folder()

    duas = load_duas()

    selected_duas, old_used = choose_three_duas(
        duas
    )

    print("")
    print(
        f"Selected {len(selected_duas)} different duas."
    )

    quranenc_version = (
        get_quranenc_version()
    )

    print(
        "QuranEnc version:",
        quranenc_version
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    batch_dir = (
        OUTPUT_DIR /
        f"batch_{timestamp}"
    )

    batch_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    new_used = list(old_used)

    created_videos = []

    # ========================================================
    # CREATE 3 VIDEOS
    # ========================================================

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

        reference = get_dua_field(
            dua,
            "reference",
            "ref",
            "reference_text"
        )

        sura = get_dua_field(
            dua,
            "sura",
            "surah"
        )

        ayah = get_dua_field(
            dua,
            "ayah",
            "aya",
            "verse"
        )

        ayah_end = get_dua_field(
            dua,
            "ayah_end",
            "aya_end",
            default=ayah
        )

        if not sura or not ayah:

            raise RuntimeError(
                f"Dua {index} is missing "
                f"sura/ayah information: {dua}"
            )

        # ----------------------------------------------------
        # Fetch exact QuranEnc Urdu meaning
        # ----------------------------------------------------

        translation = fetch_quran_translation(
            int(sura),
            int(ayah),
            int(ayah_end)
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
            WORK_DIR /
            f"poster_{index}.png"
        )

        create_poster(
            dua,
            translation,
            poster
        )

        # ----------------------------------------------------
        # Video
        # ----------------------------------------------------

        video_name = (
            f"dua_{index:02d}.mp4"
        )

        video_path = (
            batch_dir /
            video_name
        )

        create_video(
            background,
            poster,
            video_path
        )

        # ----------------------------------------------------
        # Social metadata TXT
        # ----------------------------------------------------

        text_name = (
            f"dua_{index:02d}_social_media.txt"
        )

        text_path = (
            batch_dir /
            text_name
        )

        social_text = make_social_text(
            dua,
            translation,
            quranenc_version,
            index
        )

        with open(
            text_path,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                social_text
            )

        # ----------------------------------------------------
        # Individual metadata JSON
        # ----------------------------------------------------

        metadata = {
            "video_number": index,
            "reference": reference,
            "sura": int(sura),
            "ayah_start": int(ayah),
            "ayah_end": int(ayah_end),
            "title": get_dua_field(
                dua,
                "title",
                "title_ur",
                "topic",
                "name"
            ),
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
            "quranenc": {
                "source": "QuranEnc.com",
                "translation_key": QURANENC_TRANSLATION_KEY,
                "version": quranenc_version
            },
            "video": {
                "width": WIDTH,
                "height": HEIGHT,
                "fps": FPS,
                "duration_seconds": VIDEO_SECONDS
            }
        }

        json_path = (
            batch_dir /
            f"dua_{index:02d}.json"
        )

        save_json(
            json_path,
            metadata
        )

        created_videos.append(
            video_path
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

        print(
            f"Finished video {index}: "
            f"{video_name}"
        )

    # ========================================================
    # SAVE USED LIST
    # ========================================================

    save_json(
        USED_FILE,
        new_used
    )

    # ========================================================
    # BATCH README
    # ========================================================

    readme_path = (
        batch_dir /
        "README.txt"
    )

    with open(
        readme_path,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            f"""ISLAMIC QURANIC DUA VIDEO BATCH

Created:
{datetime.now().isoformat()}

Videos:
3

Each video contains:
- MP4 video
- Social media TXT file
- Metadata JSON file

Social media TXT files contain:
- YouTube title
- YouTube description
- YouTube hashtags
- YouTube tags
- TikTok caption
- TikTok hashtags

Quran Translation:
QuranEnc.com

Urdu Translation:
Muhammad Junagarhi

Translation Key:
{QURANENC_TRANSLATION_KEY}

Translation Version:
{quranenc_version}

Video:
1080x1920
60 seconds
24 FPS

The video itself does not display the source/version
text at the bottom.
"""
        )

    # ========================================================
    # CREATE ONE ZIP ONLY
    # ========================================================

    zip_path = (
        OUTPUT_DIR /
        f"Islamic-Dua-3-Videos-{timestamp}.zip"
    )

    create_zip(
        batch_dir,
        zip_path
    )

    # ========================================================
    # VALIDATION
    # ========================================================

    print("")
    print("=" * 70)
    print("FINAL VALIDATION")
    print("=" * 70)

    mp4_files = list(
        batch_dir.glob("*.mp4")
    )

    txt_files = list(
        batch_dir.glob("*.txt")
    )

    json_files = list(
        batch_dir.glob("*.json")
    )

    print(
        f"MP4 files:  {len(mp4_files)}"
    )

    print(
        f"TXT files:  {len(txt_files)}"
    )

    print(
        f"JSON files: {len(json_files)}"
    )

    if len(mp4_files) != 3:

        raise RuntimeError(
            "ERROR: Expected exactly 3 videos."
        )

    if len(txt_files) < 4:

        raise RuntimeError(
            "ERROR: Social TXT files were not created correctly."
        )

    if not zip_path.exists():

        raise RuntimeError(
            "ERROR: ZIP was not created."
        )

    print("")
    print("OUTPUT FILES:")

    for file in sorted(
        batch_dir.iterdir()
    ):

        print(
            f"  {file.name}"
        )

    print("")
    print(
        f"FINAL ZIP: {zip_path}"
    )

    print("")
    print("=" * 70)
    print("SUCCESS - 3 UNIQUE VIDEOS CREATED")
    print("=" * 70)


if __name__ == "__main__":
    main()
