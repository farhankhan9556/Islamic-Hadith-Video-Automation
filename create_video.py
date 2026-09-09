import json
import os
import random
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_FILE = ROOT / "data" / "duas.json"
USED_FILE = ROOT / "used_duas.json"

OUTPUT_DIR = ROOT / "output"
WORK_DIR = ROOT / "work"

FONT_FILE = ROOT / "fonts" / "NotoNastaliqUrdu-Regular.ttf"
AUDIO_FILE = ROOT / "audio" / "islamic_background.mp3"


# ============================================================
# VIDEO
# ============================================================

WIDTH = 1080
HEIGHT = 1920

FPS = 24
VIDEO_SECONDS = 60


# ============================================================
# API
# ============================================================

PEXELS_API_KEY = os.getenv(
    "PEXELS_API_KEY",
    ""
).strip()

PEXELS_URL = (
    "https://api.pexels.com/v1/search"
)

QURANENC_URL = (
    "https://quranenc.com/api/v1/translation/aya"
)


# ============================================================
# DESIGN
# ============================================================

BACKGROUND_COLOR = (
    246,
    245,
    237
)

CARD_COLOR = (
    250,
    249,
    241
)

DARK = (
    35,
    35,
    35
)

GOLD = (
    154,
    116,
    45
)

SOFT_GOLD = (
    190,
    160,
    95
)


OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

WORK_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):

    if text is None:
        return ""

    text = str(text)

    text = text.replace(
        "\ufeff",
        ""
    )

    text = text.replace(
        "\u200b",
        ""
    )

    text = text.replace(
        "\r",
        " "
    )

    text = text.replace(
        "\n",
        " "
    )

    # Remove HTML
    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    # Remove excessive spaces
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# RTL TEXT
# ============================================================

def rtl_text(text):

    text = clean_text(text)

    if not text:
        return ""

    reshaped = arabic_reshaper.reshape(
        text
    )

    return get_display(
        reshaped
    )


# ============================================================
# USED DUA
# ============================================================

def load_used():

    if not USED_FILE.exists():
        return []

    try:

        data = json.loads(
            USED_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(
            data,
            list
        ):
            return data

    except Exception:
        pass

    return []


def save_used(used):

    USED_FILE.write_text(
        json.dumps(
            used,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# ============================================================
# LOAD DATABASE
# ============================================================

def load_duas():

    if not DATA_FILE.exists():

        raise RuntimeError(
            f"Missing file: {DATA_FILE}"
        )

    data = json.loads(
        DATA_FILE.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        data,
        list
    ):

        raise RuntimeError(
            "duas.json must be a JSON list."
        )

    if not data:

        raise RuntimeError(
            "duas.json is empty."
        )

    return data


# ============================================================
# FONT
# ============================================================

def get_font(size):

    if not FONT_FILE.exists():

        raise RuntimeError(
            f"Font not found: {FONT_FILE}"
        )

    return ImageFont.truetype(
        str(FONT_FILE),
        size
    )


# ============================================================
# WRAP RTL
# ============================================================

def wrap_rtl_text(
    draw,
    text,
    font,
    max_width
):

    text = clean_text(
        text
    )

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

        display_candidate = rtl_text(
            candidate
        )

        box = draw.textbbox(
            (0, 0),
            display_candidate,
            font=font
        )

        width = (
            box[2] - box[0]
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


# ============================================================
# FIT TEXT
# ============================================================

def fit_text(
    draw,
    text,
    max_width,
    max_height,
    max_size,
    min_size
):

    for size in range(
        max_size,
        min_size - 1,
        -2
    ):

        font = get_font(
            size
        )

        lines = wrap_rtl_text(
            draw,
            text,
            font,
            max_width
        )

        line_height = int(
            size * 1.45
        )

        total_height = (
            len(lines)
            * line_height
        )

        if total_height <= max_height:

            return (
                font,
                lines,
                line_height
            )

    return None


# ============================================================
# DRAW RTL
# ============================================================

def draw_rtl(
    draw,
    xy,
    text,
    font,
    fill,
    anchor="ma"
):

    display_text = rtl_text(
        text
    )

    draw.text(
        xy,
        display_text,
        font=font,
        fill=fill,
        anchor=anchor
    )


# ============================================================
# FETCH QURANENC
# ============================================================

def fetch_single_translation(
    translation_key,
    sura,
    ayah
):

    url = (
        f"{QURANENC_URL}/"
        f"{translation_key}/"
        f"{sura}/"
        f"{ayah}"
    )

    print(
        f"QuranEnc: {sura}:{ayah}"
    )

    response = requests.get(
        url,
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    translation = clean_text(
        data.get(
            "translation",
            ""
        )
    )

    if not translation:

        raise RuntimeError(
            f"No QuranEnc translation "
            f"returned for {sura}:{ayah}"
        )

    return translation


def fetch_quran_translation(
    dua
):

    translation_key = dua.get(
        "translation_key",
        "urdu_junagarhi"
    )

    sura = int(
        dua["sura"]
    )

    start_ayah = int(
        dua["ayah"]
    )

    end_ayah = int(
        dua.get(
            "ayah_end",
            start_ayah
        )
    )

    translations = []

    for ayah in range(
        start_ayah,
        end_ayah + 1
    ):

        translation = (
            fetch_single_translation(
                translation_key,
                sura,
                ayah
            )
        )

        translations.append(
            translation
        )

    # Keep the source translation text,
    # only joining consecutive requested ayat.
    return " ".join(
        translations
    )


# ============================================================
# DOWNLOAD PEXELS IMAGE
# ============================================================

def download_background():

    if not PEXELS_API_KEY:

        raise RuntimeError(
            "PEXELS_API_KEY is missing."
        )

    queries = [
        "beautiful mosque",
        "Islamic architecture",
        "Medina mosque",
        "Kaaba",
        "mosque sunset",
        "Islamic pattern",
        "mosque interior",
        "mosque night"
    ]

    random.shuffle(
        queries
    )

    headers = {
        "Authorization":
        PEXELS_API_KEY
    }

    for query in queries:

        print(
            f"Pexels search: {query}"
        )

        response = requests.get(
            PEXELS_URL,
            headers=headers,
            params={
                "query": query,
                "orientation": "portrait",
                "size": "large",
                "per_page": 15
            },
            timeout=60
        )

        response.raise_for_status()

        photos = (
            response.json()
            .get(
                "photos",
                []
            )
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

            url = (
                src.get("portrait")
                or src.get("large2x")
                or src.get("large")
            )

            if not url:
                continue

            path = (
                WORK_DIR /
                "background.jpg"
            )

            try:

                r = requests.get(
                    url,
                    timeout=60
                )

                r.raise_for_status()

                path.write_bytes(
                    r.content
                )

                test_image = Image.open(
                    path
                )

                test_image.verify()

                return path

            except Exception:

                path.unlink(
                    missing_ok=True
                )

    raise RuntimeError(
        "Could not download a Pexels background."
    )


# ============================================================
# PREPARE BACKGROUND
# ============================================================

def prepare_background(
    image_path
):

    image = Image.open(
        image_path
    ).convert(
        "RGB"
    )

    image_ratio = (
        image.width /
        image.height
    )

    target_ratio = (
        WIDTH /
        HEIGHT
    )

    if image_ratio > target_ratio:

        new_height = HEIGHT

        new_width = int(
            new_height *
            image_ratio
        )

    else:

        new_width = WIDTH

        new_height = int(
            new_width /
            image_ratio
        )

    image = image.resize(
        (
            new_width,
            new_height
        ),
        Image.Resampling.LANCZOS
    )

    left = (
        new_width -
        WIDTH
    ) // 2

    top = (
        new_height -
        HEIGHT
    ) // 2

    image = image.crop(
        (
            left,
            top,
            left + WIDTH,
            top + HEIGHT
        )
    )

    image = image.filter(
        ImageFilter.GaussianBlur(
            radius=1.2
        )
    )

    # Darken background
    overlay = Image.new(
        "RGBA",
        (
            WIDTH,
            HEIGHT
        ),
        (
            0,
            0,
            0,
            75
        )
    )

    image = Image.alpha_composite(
        image.convert("RGBA"),
        overlay
    )

    output = (
        WORK_DIR /
        "background_prepared.jpg"
    )

    image.convert(
        "RGB"
    ).save(
        output,
        quality=95
    )

    return output


# ============================================================
# CREATE TRANSPARENT POSTER
# ============================================================

def create_poster(
    dua,
    urdu_translation
):

    # IMPORTANT:
    # Transparent outside the card so
    # the Islamic background remains visible.
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

    draw = ImageDraw.Draw(
        image
    )

    center = WIDTH // 2

    # --------------------------------------------------------
    # CARD
    # --------------------------------------------------------

    card_x1 = 65
    card_y1 = 75

    card_x2 = WIDTH - 65
    card_y2 = HEIGHT - 75

    draw.rounded_rectangle(
        (
            card_x1,
            card_y1,
            card_x2,
            card_y2
        ),
        radius=40,
        fill=(
            250,
            249,
            241,
            242
        ),
        outline=(
            SOFT_GOLD[0],
            SOFT_GOLD[1],
            SOFT_GOLD[2],
            255
        ),
        width=4
    )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title_font = get_font(
        52
    )

    draw_rtl(
        draw,
        (
            center,
            175
        ),
        dua["title"],
        title_font,
        GOLD,
        "mm"
    )

    draw.line(
        (
            170,
            255,
            WIDTH - 170,
            255
        ),
        fill=(
            SOFT_GOLD[0],
            SOFT_GOLD[1],
            SOFT_GOLD[2],
            255
        ),
        width=2
    )

    # --------------------------------------------------------
    # ARABIC
    # --------------------------------------------------------

    arabic = clean_text(
        dua["arabic"]
    )

    arabic_font = get_font(
        52
    )

    arabic_lines = wrap_rtl_text(
        draw,
        arabic,
        arabic_font,
        800
    )

    y = 320

    for line in arabic_lines:

        draw_rtl(
            draw,
            (
                center,
                y
            ),
            line,
            arabic_font,
            DARK,
            "ma"
        )

        y += 80

    # --------------------------------------------------------
    # MEANING TITLE
    # --------------------------------------------------------

    meaning_title_font = get_font(
        35
    )

    draw_rtl(
        draw,
        (
            center,
            y + 15
        ),
        "اردو معنی",
        meaning_title_font,
        GOLD,
        "ma"
    )

    y += 85

    # --------------------------------------------------------
    # URDU TRANSLATION
    # --------------------------------------------------------

    fitted = fit_text(
        draw,
        urdu_translation,
        max_width=790,
        max_height=430,
        max_size=43,
        min_size=26
    )

    if not fitted:

        raise RuntimeError(
            "Urdu translation cannot fit "
            "on one screen."
        )

    meaning_font, lines, line_height = fitted

    for line in lines:

        draw_rtl(
            draw,
            (
                center,
                y
            ),
            line,
            meaning_font,
            DARK,
            "ma"
        )

        y += line_height

    # --------------------------------------------------------
    # REFERENCE
    # --------------------------------------------------------

    reference_y = 1200

    draw.line(
        (
            170,
            reference_y - 55,
            WIDTH - 170,
            reference_y - 55
        ),
        fill=(
            SOFT_GOLD[0],
            SOFT_GOLD[1],
            SOFT_GOLD[2],
            255
        ),
        width=2
    )

    reference_font = get_font(
        34
    )

    draw_rtl(
        draw,
        (
            center,
            reference_y
        ),
        "حوالہ: " +
        dua["reference"],
        reference_font,
        GOLD,
        "ma"
    )

    # --------------------------------------------------------
    # CONTEXT
    # --------------------------------------------------------

    context = clean_text(
        dua.get(
            "context",
            ""
        )
    )

    if context:

        context_title_font = get_font(
            34
        )

        draw_rtl(
            draw,
            (
                center,
                1305
            ),
            "پس منظر",
            context_title_font,
            GOLD,
            "ma"
        )

        fitted_context = fit_text(
            draw,
            context,
            max_width=780,
            max_height=300,
            max_size=31,
            min_size=22
        )

        if not fitted_context:

            raise RuntimeError(
                "Context is too long "
                "for one screen."
            )

        context_font, context_lines, context_line_height = fitted_context

        context_y = 1370

        for line in context_lines:

            draw_rtl(
                draw,
                (
                    center,
                    context_y
                ),
                line,
                context_font,
                DARK,
                "ma"
            )

            context_y += context_line_height

    # --------------------------------------------------------
    # SOURCE
    # --------------------------------------------------------

    source_font = get_font(
        20
    )

    source_text = (
        "ماخذ: QuranEnc.com — "
        "اردو ترجمہ: محمد جوناگڑھی"
    )

    draw_rtl(
        draw,
        (
            center,
            HEIGHT - 125
        ),
        source_text,
        source_font,
        SOFT_GOLD,
        "ma"
    )

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    poster = (
        WORK_DIR /
        "poster.png"
    )

    image.save(
        poster
    )

    return poster


# ============================================================
# CREATE VIDEO
# ============================================================

def create_video(
    background,
    poster,
    output_file
):

    command = [

        "ffmpeg",
        "-y",

        # Background
        "-loop",
        "1",
        "-i",
        str(background),

        # Transparent poster
        "-loop",
        "1",
        "-i",
        str(poster),

        # Audio
        "-stream_loop",
        "-1",
        "-i",
        str(AUDIO_FILE),

        "-filter_complex",

        (
            "[0:v]"
            "scale=1160:2060,"
            "crop=1080:1920:"
            "x='40+35*sin(t/10)':"
            "y='70+35*cos(t/12)'"
            "[bg];"

            "[1:v]"
            "format=rgba"
            "[poster];"

            "[bg][poster]"
            "overlay=0:0:"
            "format=auto"
            "[v]"
        ),

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
        "medium",

        "-crf",
        "20",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-pix_fmt",
        "yuv420p",

        "-movflags",
        "+faststart",

        str(output_file)
    ]

    print(
        "Running FFmpeg..."
    )

    subprocess.run(
        command,
        check=True
    )


# ============================================================
# SELECT DUA
# ============================================================

def select_dua():

    duas = load_duas()

    used = set(
        load_used()
    )

    available = []

    for dua in duas:

        if not isinstance(
            dua,
            dict
        ):
            continue

        dua_id = dua.get(
            "id"
        )

        if not dua_id:
            continue

        if dua_id in used:
            continue

        required = [
            "title",
            "arabic",
            "reference",
            "sura",
            "ayah",
            "source"
        ]

        if not all(
            dua.get(field)
            for field in required
        ):
            continue

        available.append(
            dua
        )

    if not available:

        print(
            "All Duas used."
        )

        print(
            "Starting new cycle."
        )

        save_used([])

        available = duas

    selected = random.choice(
        available
    )

    print(
        "=" * 60
    )

    print(
        "SELECTED DUA:",
        selected["title"]
    )

    print(
        "REFERENCE:",
        selected["reference"]
    )

    print(
        "SOURCE:",
        selected["source"]
    )

    print(
        "=" * 60
    )

    return selected


# ============================================================
# SAVE METADATA
# ============================================================

def save_metadata(
    dua,
    urdu_translation,
    output_file
):

    metadata = {

        "type":
        "quran_dua",

        "title":
        dua["title"],

        "arabic":
        dua["arabic"],

        "urdu":
        urdu_translation,

        "reference":
        dua["reference"],

        "sura":
        dua["sura"],

        "ayah":
        dua["ayah"],

        "ayah_end":
        dua.get(
            "ayah_end",
            dua["ayah"]
        ),

        "context":
        dua.get(
            "context",
            ""
        ),

        "source":
        "QuranEnc.com",

        "translation":
        "Muhammad Junagarhi",

        "translation_key":
        dua.get(
            "translation_key",
            "urdu_junagarhi"
        ),

        "video":
        output_file.name
    }

    metadata_file = (
        output_file.with_suffix(
            ".json"
        )
    )

    metadata_file.write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "\n"
        "============================================\n"
        " ISLAMIC DUA VIDEO AUTOMATION\n"
        "============================================\n"
    )

    # --------------------------------------------------------
    # CHECK PEXELS
    # --------------------------------------------------------

    if not PEXELS_API_KEY:

        raise SystemExit(
            "ERROR: PEXELS_API_KEY is missing."
        )

    # --------------------------------------------------------
    # CHECK FONT
    # --------------------------------------------------------

    if not FONT_FILE.exists():

        raise SystemExit(
            f"ERROR: Font missing:\n"
            f"{FONT_FILE}"
        )

    # --------------------------------------------------------
    # CHECK AUDIO
    # --------------------------------------------------------

    if not AUDIO_FILE.exists():

        raise SystemExit(
            f"ERROR: Audio missing:\n"
            f"{AUDIO_FILE}"
        )

    # --------------------------------------------------------
    # CHECK DATABASE
    # --------------------------------------------------------

    if not DATA_FILE.exists():

        raise SystemExit(
            f"ERROR: Dua database missing:\n"
            f"{DATA_FILE}"
        )

    # --------------------------------------------------------
    # CLEAN WORK
    # --------------------------------------------------------

    if WORK_DIR.exists():

        shutil.rmtree(
            WORK_DIR
        )

    WORK_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # SELECT
    # --------------------------------------------------------

    dua = select_dua()

    # --------------------------------------------------------
    # QURANENC
    # --------------------------------------------------------

    urdu_translation = (
        fetch_quran_translation(
            dua
        )
    )

    print(
        "\nExact Urdu translation received."
    )

    # --------------------------------------------------------
    # BACKGROUND
    # --------------------------------------------------------

    background = (
        download_background()
    )

    prepared_background = (
        prepare_background(
            background
        )
    )

    # --------------------------------------------------------
    # POSTER
    # --------------------------------------------------------

    poster = create_poster(
        dua,
        urdu_translation
    )

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    timestamp = int(
        time.time()
    )

    output_file = (
        OUTPUT_DIR /
        f"dua_{timestamp}.mp4"
    )

    # --------------------------------------------------------
    # VIDEO
    # --------------------------------------------------------

    create_video(
        prepared_background,
        poster,
        output_file
    )

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    save_metadata(
        dua,
        urdu_translation,
        output_file
    )

    # --------------------------------------------------------
    # MARK USED
    # --------------------------------------------------------

    used = load_used()

    if dua["id"] not in used:

        used.append(
            dua["id"]
        )

    save_used(
        used
    )

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    print(
        "\n"
        "============================================"
    )

    print(
        "VIDEO CREATED SUCCESSFULLY"
    )

    print(
        "============================================"
    )

    print(
        f"VIDEO: {output_file}"
    )

    print(
        f"METADATA: "
        f"{output_file.with_suffix('.json')}"
    )

    print(
        "============================================"
    )


if __name__ == "__main__":
    main()
