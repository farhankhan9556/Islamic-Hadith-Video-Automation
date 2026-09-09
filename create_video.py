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
# PROJECT PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_FILE = ROOT / "data" / "duas.json"
USED_FILE = ROOT / "used_duas.json"

OUTPUT_DIR = ROOT / "output"
WORK_DIR = ROOT / "work"

FONT_FILE = ROOT / "fonts" / "NotoNastaliqUrdu-Regular.ttf"
AUDIO_FILE = ROOT / "audio" / "islamic_background.mp3"


# ============================================================
# VIDEO SETTINGS
# ============================================================

WIDTH = 1080
HEIGHT = 1920

FPS = 24
VIDEO_SECONDS = 60


# ============================================================
# API SETTINGS
# ============================================================

PEXELS_API_KEY = os.getenv(
    "PEXELS_API_KEY",
    ""
).strip()

PEXELS_URL = (
    "https://api.pexels.com/v1/search"
)

QURANENC_AYA_URL = (
    "https://quranenc.com/api/v1/translation/aya"
)

QURANENC_SURA_URL = (
    "https://quranenc.com/api/v1/translation/sura"
)

QURANENC_TRANSLATIONS_URL = (
    "https://quranenc.com/api/v1/translations/list"
)


# ============================================================
# DESIGN COLORS
# ============================================================

DARK = (35, 35, 35)

GOLD = (154, 116, 45)

SOFT_GOLD = (190, 160, 95)


# ============================================================
# CREATE DIRECTORIES
# ============================================================

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

    # Remove HTML tags
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
# ARABIC / URDU RTL SUPPORT
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
# LOAD USED DUA LIST
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


# ============================================================
# SAVE USED DUA LIST
# ============================================================

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
# LOAD DUA DATABASE
# ============================================================

def load_duas():

    if not DATA_FILE.exists():

        raise RuntimeError(
            f"Missing Dua database:\n"
            f"{DATA_FILE}"
        )

    try:

        data = json.loads(
            DATA_FILE.read_text(
                encoding="utf-8"
            )
        )

    except Exception as error:

        raise RuntimeError(
            f"Could not read duas.json:\n"
            f"{error}"
        )

    if not isinstance(
        data,
        list
    ):

        raise RuntimeError(
            "duas.json must contain a JSON list."
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
            f"Font not found:\n"
            f"{FONT_FILE}"
        )

    return ImageFont.truetype(
        str(FONT_FILE),
        size
    )


# ============================================================
# RTL TEXT WRAPPING
# ============================================================

def wrap_rtl_text(
    draw,
    text,
    font,
    max_width
):

    text = clean_text(text)

    if not text:
        return []

    words = text.split()

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

        text_width = (
            box[2] - box[0]
        )

        if text_width <= max_width:

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
# AUTO FONT FIT
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
# HTTP REQUEST HELPER
# ============================================================

def http_get(
    url,
    headers=None,
    params=None,
    timeout=60
):

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=timeout
    )

    response.raise_for_status()

    return response


# ============================================================
# GET QURANENC TRANSLATION VERSION
# ============================================================

def get_translation_version(
    translation_key
):

    try:

        response = http_get(
            QURANENC_TRANSLATIONS_URL,
            params={
                "localization": "en"
            },
            timeout=60
        )

        data = response.json()

        if isinstance(
            data,
            list
        ):

            for item in data:

                if not isinstance(
                    item,
                    dict
                ):
                    continue

                if item.get("key") == translation_key:

                    version = clean_text(
                        item.get(
                            "version",
                            ""
                        )
                    )

                    if version:
                        return version

    except Exception as error:

        print(
            "Could not retrieve "
            f"QuranEnc version: {error}"
        )

    return "latest"


# ============================================================
# QURANENC SINGLE AYAH
# ============================================================

def fetch_single_translation(
    translation_key,
    sura,
    ayah
):

    url = (
        f"{QURANENC_AYA_URL}/"
        f"{translation_key}/"
        f"{sura}/"
        f"{ayah}"
    )

    print(
        f"QuranEnc single ayah: "
        f"{sura}:{ayah}"
    )

    try:

        response = http_get(
            url,
            timeout=60
        )

        print(
            "QuranEnc single status:",
            response.status_code
        )

        data = response.json()

        if isinstance(
            data,
            dict
        ):

            translation = clean_text(
                data.get(
                    "translation",
                    ""
                )
            )

            if translation:

                print(
                    f"Single ayah translation "
                    f"found: {sura}:{ayah}"
                )

                return translation

        print(
            "Single-ayah endpoint returned "
            "no usable translation."
        )

    except Exception as error:

        print(
            "Single-ayah request failed:"
        )

        print(
            str(error)
        )


    # ========================================================
    # FALLBACK: FULL SURAH
    # ========================================================

    print(
        f"Trying full Surah fallback "
        f"for {sura}:{ayah}"
    )

    sura_url = (
        f"{QURANENC_SURA_URL}/"
        f"{translation_key}/"
        f"{sura}"
    )

    try:

        response = http_get(
            sura_url,
            timeout=60
        )

        print(
            "QuranEnc Surah status:",
            response.status_code
        )

        data = response.json()

        # According to QuranEnc API,
        # this endpoint returns a JSON array.
        if isinstance(
            data,
            list
        ):

            verses = data

        elif isinstance(
            data,
            dict
        ):

            # Extra protection in case
            # API wraps the array.
            verses = (
                data.get("result")
                or data.get("data")
                or data.get("translations")
                or []
            )

        else:

            verses = []

        print(
            f"Surah response contains "
            f"{len(verses)} items."
        )

        for verse in verses:

            if not isinstance(
                verse,
                dict
            ):
                continue

            try:

                verse_ayah = int(
                    verse.get("aya")
                )

            except Exception:

                continue

            if verse_ayah != int(
                ayah
            ):

                continue

            translation = clean_text(
                verse.get(
                    "translation",
                    ""
                )
            )

            if translation:

                print(
                    f"FULL SURAH fallback "
                    f"found translation for "
                    f"{sura}:{ayah}"
                )

                return translation

        raise RuntimeError(
            f"QuranEnc full Surah response "
            f"did not contain translation "
            f"for {sura}:{ayah}"
        )

    except Exception as error:

        raise RuntimeError(
            f"QuranEnc translation failed "
            f"for {sura}:{ayah}\n"
            f"Error: {error}"
        )


# ============================================================
# FETCH COMPLETE QURAN TRANSLATION
# ============================================================

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

    if end_ayah < start_ayah:

        raise RuntimeError(
            "ayah_end cannot be smaller "
            "than ayah."
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

    final_translation = clean_text(
        " ".join(
            translations
        )
    )

    if not final_translation:

        raise RuntimeError(
            f"Empty QuranEnc translation "
            f"for {sura}:{start_ayah}"
        )

    return final_translation


# ============================================================
# DOWNLOAD PEXELS BACKGROUND
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

        "mosque night",

        "Islamic background",

        "mosque sunrise"

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

        try:

            response = http_get(
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

            data = response.json()

            photos = data.get(
                "photos",
                []
            )

            if not photos:

                print(
                    "No photos found."
                )

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

                background_file = (
                    WORK_DIR /
                    "background.jpg"
                )

                try:

                    image_response = (
                        requests.get(
                            image_url,
                            timeout=60
                        )
                    )

                    image_response.raise_for_status()

                    background_file.write_bytes(
                        image_response.content
                    )

                    test_image = Image.open(
                        background_file
                    )

                    test_image.verify()

                    print(
                        "Background downloaded."
                    )

                    return background_file

                except Exception as error:

                    print(
                        "Background image failed:"
                    )

                    print(
                        str(error)
                    )

                    background_file.unlink(
                        missing_ok=True
                    )

        except Exception as error:

            print(
                f"Pexels query failed: "
                f"{error}"
            )

    raise RuntimeError(
        "Could not download any "
        "Pexels background."
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

    # Slight blur so text remains readable.
    image = image.filter(
        ImageFilter.GaussianBlur(
            radius=1.2
        )
    )

    # Dark overlay.
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
# CREATE POSTER
# ============================================================

def create_poster(
    dua,
    urdu_translation,
    translation_version
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

    draw = ImageDraw.Draw(
        image
    )

    center = WIDTH // 2


    # ========================================================
    # MAIN CARD
    # ========================================================

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


    # ========================================================
    # TITLE
    # ========================================================

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


    # ========================================================
    # TITLE LINE
    # ========================================================

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


    # ========================================================
    # ARABIC DUA
    # ========================================================

    arabic = clean_text(
        dua["arabic"]
    )

    arabic_fitted = fit_text(
        draw,
        arabic,
        max_width=800,
        max_height=390,
        max_size=54,
        min_size=34
    )

    if not arabic_fitted:

        raise RuntimeError(
            "Arabic Dua cannot fit "
            "on one screen."
        )

    (
        arabic_font,
        arabic_lines,
        arabic_line_height
    ) = arabic_fitted

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

        y += arabic_line_height


    # ========================================================
    # URDU MEANING TITLE
    # ========================================================

    meaning_title_font = get_font(
        35
    )

    draw_rtl(
        draw,
        (
            center,
            y + 20
        ),
        "اردو معنی",
        meaning_title_font,
        GOLD,
        "ma"
    )

    y += 90


    # ========================================================
    # URDU TRANSLATION
    # ========================================================

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
            "Urdu translation is too long "
            "to fit on one screen."
        )

    (
        meaning_font,
        meaning_lines,
        meaning_line_height
    ) = fitted

    for line in meaning_lines:

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

        y += meaning_line_height


    # ========================================================
    # REFERENCE
    # ========================================================

    reference_y = 1195

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


    # ========================================================
    # CONTEXT / STORY
    # ========================================================

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
                1300
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

        (
            context_font,
            context_lines,
            context_line_height
        ) = fitted_context

        context_y = 1365

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

            context_y += (
                context_line_height
            )


    # ========================================================
    # SOURCE / VERSION
    # ========================================================

    source_font = get_font(
        19
    )

    source_text = (
        "ماخذ: QuranEnc.com | "
        "اردو ترجمہ: محمد جوناگڑھی | "
        f"Version: {translation_version}"
    )

    # Keep source line inside width.
    source_fit = fit_text(
        draw,
        source_text,
        max_width=800,
        max_height=70,
        max_size=19,
        min_size=14
    )

    if source_fit:

        (
            source_font,
            source_lines,
            source_line_height
        ) = source_fit

        source_y = (
            HEIGHT -
            125
        )

        for line in source_lines:

            draw_rtl(
                draw,
                (
                    center,
                    source_y
                ),
                line,
                source_font,
                SOFT_GOLD,
                "ma"
            )

            source_y += (
                source_line_height
            )


    # ========================================================
    # SAVE POSTER
    # ========================================================

    poster = (
        WORK_DIR /
        "poster.png"
    )

    image.save(
        poster
    )

    return poster


# ============================================================
# CREATE VIDEO USING FFMPEG
# ============================================================

def create_video(
    background,
    poster,
    output_file
):

    if not AUDIO_FILE.exists():

        raise RuntimeError(
            f"Audio file not found:\n"
            f"{AUDIO_FILE}"
        )

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

        # Audio loop
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
            "shortest=1"
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
        "Starting FFmpeg..."
    )

    print(
        "Output:",
        output_file
    )

    subprocess.run(
        command,
        check=True
    )


# ============================================================
# SELECT UNUSED DUA
# ============================================================

def select_dua():

    duas = load_duas()

    used = set(
        load_used()
    )

    available = []

    required_fields = [
        "title",
        "arabic",
        "reference",
        "sura",
        "ayah",
        "source"
    ]

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

        valid = True

        for field in required_fields:

            if not dua.get(
                field
            ):

                valid = False

                break

        if not valid:
            continue

        available.append(
            dua
        )


    # ========================================================
    # RESET AFTER ALL DUAS ARE USED
    # ========================================================

    if not available:

        print(
            "All Duas have been used."
        )

        print(
            "Starting a new Dua cycle."
        )

        save_used(
            []
        )

        available = [
            dua
            for dua in duas
            if isinstance(
                dua,
                dict
            )
        ]


    if not available:

        raise RuntimeError(
            "No valid Duas found "
            "in duas.json."
        )


    # Random selection
    selected = random.choice(
        available
    )


    print(
        "=" * 60
    )

    print(
        "SELECTED DUA:"
    )

    print(
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
    translation_version,
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

        "translation_version":
            translation_version,

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
# CLEAN WORK DIRECTORY
# ============================================================

def clean_work_directory():

    if WORK_DIR.exists():

        shutil.rmtree(
            WORK_DIR
        )

    WORK_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "============================================"
    )
    print(
        "      ISLAMIC DUA VIDEO AUTOMATION"
    )
    print(
        "============================================"
    )
    print()


    # ========================================================
    # BASIC CHECKS
    # ========================================================

    if not PEXELS_API_KEY:

        raise SystemExit(
            "ERROR: PEXELS_API_KEY "
            "GitHub Secret is missing."
        )


    if not FONT_FILE.exists():

        raise SystemExit(
            f"ERROR: Font missing:\n"
            f"{FONT_FILE}"
        )


    if not AUDIO_FILE.exists():

        raise SystemExit(
            f"ERROR: Audio missing:\n"
            f"{AUDIO_FILE}"
        )


    if not DATA_FILE.exists():

        raise SystemExit(
            f"ERROR: Dua database missing:\n"
            f"{DATA_FILE}"
        )


    # ========================================================
    # CLEAN WORK FOLDER
    # ========================================================

    clean_work_directory()


    # ========================================================
    # SELECT DUA
    # ========================================================

    dua = select_dua()


    # ========================================================
    # TRANSLATION KEY
    # ========================================================

    translation_key = dua.get(
        "translation_key",
        "urdu_junagarhi"
    )

    print()
    print(
        "Translation key:",
        translation_key
    )


    # ========================================================
    # GET TRANSLATION VERSION
    # ========================================================

    translation_version = (
        get_translation_version(
            translation_key
        )
    )

    print(
        "QuranEnc translation version:",
        translation_version
    )


    # ========================================================
    # GET EXACT URDU TRANSLATION
    # ========================================================

    print()
    print(
        "Fetching exact Urdu translation..."
    )

    urdu_translation = (
        fetch_quran_translation(
            dua
        )
    )

    print()
    print(
        "Exact Urdu translation received."
    )


    # ========================================================
    # DOWNLOAD BACKGROUND
    # ========================================================

    print()
    print(
        "Downloading Islamic background..."
    )

    background = (
        download_background()
    )


    # ========================================================
    # PREPARE BACKGROUND
    # ========================================================

    prepared_background = (
        prepare_background(
            background
        )
    )


    # ========================================================
    # CREATE POSTER
    # ========================================================

    print()
    print(
        "Creating Islamic poster..."
    )

    poster = create_poster(
        dua,
        urdu_translation,
        translation_version
    )


    # ========================================================
    # OUTPUT FILE
    # ========================================================

    timestamp = int(
        time.time()
    )

    output_file = (
        OUTPUT_DIR /
        f"dua_{timestamp}.mp4"
    )


    # ========================================================
    # CREATE VIDEO
    # ========================================================

    print()
    print(
        "Creating 60-second video..."
    )

    create_video(
        prepared_background,
        poster,
        output_file
    )


    # ========================================================
    # SAVE METADATA
    # ========================================================

    save_metadata(
        dua,
        urdu_translation,
        translation_version,
        output_file
    )


    # ========================================================
    # UPDATE USED DUA LIST
    # ========================================================

    used = load_used()

    if dua["id"] not in used:

        used.append(
            dua["id"]
        )

    save_used(
        used
    )


    # ========================================================
    # FINAL CHECK
    # ========================================================

    if not output_file.exists():

        raise RuntimeError(
            "FFmpeg finished but the "
            "video file was not created."
        )


    file_size_mb = (
        output_file.stat().st_size
        /
        (1024 * 1024)
    )


    print()
    print(
        "============================================"
    )

    print(
        "       VIDEO CREATED SUCCESSFULLY"
    )

    print(
        "============================================"
    )

    print(
        "Video:",
        output_file
    )

    print(
        "Size:",
        f"{file_size_mb:.2f} MB"
    )

    print(
        "Duration:",
        f"{VIDEO_SECONDS} seconds"
    )

    print(
        "Resolution:",
        f"{WIDTH}x{HEIGHT}"
    )

    print(
        "FPS:",
        FPS
    )

    print(
        "Reference:",
        dua["reference"]
    )

    print(
        "Translation:",
        "Muhammad Junagarhi"
    )

    print(
        "QuranEnc Version:",
        translation_version
    )

    print(
        "============================================"
    )

    print()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
