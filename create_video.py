import json
import os
import random
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests

from PIL import (
    Image,
    ImageDraw,
    ImageFont,
    ImageFilter,
    features
)


# ============================================================
# PROJECT PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_FILE = ROOT / "data" / "duas.json"

USED_FILE = ROOT / "used_duas.json"

OUTPUT_DIR = ROOT / "output"

WORK_DIR = ROOT / "work"

AUDIO_FILE = (
    ROOT /
    "audio" /
    "islamic_background.mp3"
)


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


TRANSLATION_KEY = (
    "urdu_junagarhi"
)


# ============================================================
# COLORS
# ============================================================

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


# ============================================================
# DIRECTORIES
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
# FONT
# ============================================================

def find_font():

    fonts = [

        Path(
            "/usr/share/fonts/truetype/noto/"
            "NotoNaskhArabic-Regular.ttf"
        ),

        Path(
            "/usr/share/fonts/opentype/noto/"
            "NotoNaskhArabic-Regular.ttf"
        ),

        ROOT /
        "fonts" /
        "NotoNaskhArabic-Regular.ttf"

    ]


    for font in fonts:

        if font.exists():

            print(
                "Using Arabic/Urdu font:"
            )

            print(
                font
            )

            return font


    raise RuntimeError(
        "Noto Naskh Arabic font "
        "was not found."
    )


FONT_FILE = find_font()


# ============================================================
# VERIFY RTL ENGINE
# ============================================================

if not features.check("raqm"):

    raise RuntimeError(
        "Pillow RAQM support is missing. "
        "Arabic/Urdu RTL rendering cannot continue."
    )


print(
    "Pillow RAQM RTL support: OK"
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

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# FONT
# ============================================================

def get_font(size):

    return ImageFont.truetype(
        str(FONT_FILE),
        size
    )


# ============================================================
# RTL TEXT WIDTH
# ============================================================

def rtl_width(
    draw,
    text,
    font,
    language="ur"
):

    text = clean_text(
        text
    )

    if not text:

        return 0

    box = draw.textbbox(
        (0, 0),
        text,
        font=font,
        direction="rtl",
        language=language
    )

    return (
        box[2] -
        box[0]
    )


# ============================================================
# RTL WRAPPING
#
# IMPORTANT:
# We keep the ORIGINAL logical text.
# Pillow + RAQM handles Arabic/Urdu shaping
# and right-to-left display.
# ============================================================

def wrap_rtl_text(
    draw,
    text,
    font,
    max_width,
    language="ur"
):

    text = clean_text(
        text
    )

    if not text:

        return []


    words = text.split()

    lines = []

    current = ""


    for word in words:

        candidate = (
            word
            if not current
            else
            current + " " + word
        )


        width = rtl_width(
            draw,
            candidate,
            font,
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


# ============================================================
# FIT RTL TEXT
# ============================================================

def fit_rtl_text(
    draw,
    text,
    max_width,
    max_height,
    max_size,
    min_size,
    language="ur"
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
            max_width,
            language
        )


        line_height = int(
            size * 1.45
        )


        total_height = (
            len(lines) *
            line_height
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
#
# DO NOT REVERSE TEXT.
# DO NOT USE PYTHON-BIDI.
# DO NOT USE ARABIC-RESHAPER.
# Pillow RAQM handles it.
# ============================================================

def draw_rtl(
    draw,
    xy,
    text,
    font,
    fill,
    language="ur",
    anchor="mm"
):

    text = clean_text(
        text
    )

    if not text:

        return


    draw.text(
        xy,
        text,
        font=font,
        fill=fill,
        anchor=anchor,
        direction="rtl",
        language=language,
        align="center"
    )


# ============================================================
# LOAD USED
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
# SAVE USED
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
# LOAD DUAS
# ============================================================

def load_duas():

    if not DATA_FILE.exists():

        raise RuntimeError(
            f"Missing:\n{DATA_FILE}"
        )


    try:

        data = json.loads(
            DATA_FILE.read_text(
                encoding="utf-8"
            )
        )

    except Exception as error:

        raise RuntimeError(
            f"Invalid duas.json:\n{error}"
        )


    if not isinstance(
        data,
        list
    ):

        raise RuntimeError(
            "duas.json must contain "
            "a JSON list."
        )


    if not data:

        raise RuntimeError(
            "duas.json is empty."
        )


    return data


# ============================================================
# HTTP GET
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
# QURANENC TRANSLATION
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
        f"QuranEnc: {sura}:{ayah}"
    )


    try:

        response = http_get(
            url,
            timeout=60
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

                return translation


    except Exception as error:

        print(
            "Ayah endpoint error:"
        )

        print(
            error
        )


    # ========================================================
    # SURAH FALLBACK
    # ========================================================

    print(
        f"Trying Surah fallback: {sura}"
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


        data = response.json()


        if isinstance(
            data,
            list
        ):

            verses = data

        elif isinstance(
            data,
            dict
        ):

            verses = (
                data.get("result")
                or
                data.get("data")
                or
                data.get("translations")
                or
                []
            )

        else:

            verses = []


        for verse in verses:

            if not isinstance(
                verse,
                dict
            ):

                continue


            try:

                verse_number = int(
                    verse.get(
                        "aya"
                    )
                )

            except Exception:

                continue


            if (
                verse_number
                !=
                int(ayah)
            ):

                continue


            translation = clean_text(
                verse.get(
                    "translation",
                    ""
                )
            )


            if translation:

                return translation


    except Exception as error:

        print(
            "Surah endpoint error:"
        )

        print(
            error
        )


    raise RuntimeError(
        f"No QuranEnc translation "
        f"returned for {sura}:{ayah}"
    )


# ============================================================
# COMPLETE QURAN TRANSLATION
# ============================================================

def fetch_quran_translation(
    dua
):

    translation_key = dua.get(
        "translation_key",
        TRANSLATION_KEY
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


    result = clean_text(
        " ".join(
            translations
        )
    )


    if not result:

        raise RuntimeError(
            "Empty QuranEnc translation."
        )


    return result


# ============================================================
# PEXELS BACKGROUND
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
                    "query":
                        query,

                    "orientation":
                        "portrait",

                    "size":
                        "large",

                    "per_page":
                        15
                },
                timeout=60
            )


            data = response.json()


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
                    or
                    src.get("large2x")
                    or
                    src.get("large")
                )


                if not image_url:

                    continue


                path = (
                    WORK_DIR /
                    "background.jpg"
                )


                try:

                    response = requests.get(
                        image_url,
                        timeout=60
                    )


                    response.raise_for_status()


                    path.write_bytes(
                        response.content
                    )


                    test = Image.open(
                        path
                    )


                    test.verify()


                    return path


                except Exception:

                    path.unlink(
                        missing_ok=True
                    )


        except Exception as error:

            print(
                "Pexels error:"
            )

            print(
                error
            )


    raise RuntimeError(
        "Could not download "
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


    image = image.filter(
        ImageFilter.GaussianBlur(
            radius=1.2
        )
    )


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
            70
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
    urdu_translation
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
    # CARD
    # ========================================================

    card = (
        55,
        60,
        WIDTH - 55,
        HEIGHT - 60
    )


    draw.rounded_rectangle(
        card,
        radius=42,
        fill=(
            250,
            249,
            241,
            245
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

    title_fit = fit_rtl_text(
        draw,
        dua["title"],
        800,
        110,
        50,
        30,
        "ur"
    )


    if not title_fit:

        raise RuntimeError(
            "Title cannot fit."
        )


    (
        title_font,
        title_lines,
        title_height
    ) = title_fit


    y = 155


    for line in title_lines:

        draw_rtl(
            draw,
            (
                center,
                y
            ),
            line,
            title_font,
            GOLD,
            "ur"
        )

        y += title_height


    # ========================================================
    # LINE
    # ========================================================

    draw.line(
        (
            150,
            260,
            WIDTH - 150,
            260
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

    arabic_fit = fit_rtl_text(
        draw,
        dua["arabic"],
        800,
        380,
        54,
        30,
        "ar"
    )


    if not arabic_fit:

        raise RuntimeError(
            "Arabic Dua cannot fit."
        )


    (
        arabic_font,
        arabic_lines,
        arabic_height
    ) = arabic_fit


    arabic_y = 335


    for line in arabic_lines:

        draw_rtl(
            draw,
            (
                center,
                arabic_y
            ),
            line,
            arabic_font,
            DARK,
            "ar"
        )

        arabic_y += arabic_height


    # ========================================================
    # URDU MEANING TITLE
    # ========================================================

    meaning_title_font = get_font(
        34
    )


    meaning_title_y = (
        arabic_y + 20
    )


    draw_rtl(
        draw,
        (
            center,
            meaning_title_y
        ),
        "اردو معنی",
        meaning_title_font,
        GOLD,
        "ur"
    )


    # ========================================================
    # URDU MEANING
    # ========================================================

    meaning_y = (
        meaning_title_y + 75
    )


    meaning_fit = fit_rtl_text(
        draw,
        urdu_translation,
        790,
        430,
        42,
        24,
        "ur"
    )


    if not meaning_fit:

        raise RuntimeError(
            "Urdu translation is too long "
            "for one screen."
        )


    (
        meaning_font,
        meaning_lines,
        meaning_height
    ) = meaning_fit


    for line in meaning_lines:

        draw_rtl(
            draw,
            (
                center,
                meaning_y
            ),
            line,
            meaning_font,
            DARK,
            "ur"
        )

        meaning_y += meaning_height


    # ========================================================
    # REFERENCE
    # ========================================================

    reference_y = 1180


    draw.line(
        (
            150,
            reference_y - 55,
            WIDTH - 150,
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
        32
    )


    reference_text = (
        "حوالہ: " +
        clean_text(
            dua["reference"]
        )
    )


    draw_rtl(
        draw,
        (
            center,
            reference_y
        ),
        reference_text,
        reference_font,
        GOLD,
        "ur"
    )


    # ========================================================
    # CONTEXT
    # ========================================================

    context = clean_text(
        dua.get(
            "context",
            ""
        )
    )


    if context:

        context_title_y = 1285


        context_title_font = get_font(
            32
        )


        draw_rtl(
            draw,
            (
                center,
                context_title_y
            ),
            "پس منظر",
            context_title_font,
            GOLD,
            "ur"
        )


        context_fit = fit_rtl_text(
            draw,
            context,
            770,
            270,
            29,
            20,
            "ur"
        )


        if not context_fit:

            raise RuntimeError(
                "Context is too long."
            )


        (
            context_font,
            context_lines,
            context_height
        ) = context_fit


        context_y = (
            context_title_y + 65
        )


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
                "ur"
            )

            context_y += context_height


    # ========================================================
    # SOURCE
    # ========================================================

    source_font = get_font(
        17
    )


    source_text = (
        "ماخذ: QuranEnc.com | "
        "اردو ترجمہ: محمد جوناگڑھی"
    )


    draw_rtl(
        draw,
        (
            center,
            HEIGHT - 105
        ),
        source_text,
        source_font,
        SOFT_GOLD,
        "ur"
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


    print(
        "Poster created:"
    )

    print(
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

    if not AUDIO_FILE.exists():

        raise RuntimeError(
            "Islamic background audio "
            "is missing."
        )


    command = [

        "ffmpeg",

        "-y",

        # Background
        "-loop",
        "1",

        "-i",
        str(background),

        # Poster
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
            "overlay=0:0"
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


    required = [

        "title",

        "arabic",

        "reference",

        "sura",

        "ayah",

        "source"

    ]


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


        valid = True


        for field in required:

            if not dua.get(
                field
            ):

                valid = False

                break


        if valid:

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
            "No valid Duas available."
        )


    selected = random.choice(
        available
    )


    print()
    print(
        "========================================"
    )

    print(
        "SELECTED DUA"
    )

    print(
        "========================================"
    )

    print(
        "ID:",
        selected["id"]
    )

    print(
        "Title:",
        selected["title"]
    )

    print(
        "Reference:",
        selected["reference"]
    )

    print(
        "========================================"
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
                TRANSLATION_KEY
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
    # API CHECK
    # ========================================================

    if not PEXELS_API_KEY:

        raise SystemExit(
            "ERROR: PEXELS_API_KEY is missing."
        )


    # ========================================================
    # FONT CHECK
    # ========================================================

    print(
        "Font:",
        FONT_FILE
    )


    # ========================================================
    # AUDIO CHECK
    # ========================================================

    if not AUDIO_FILE.exists():

        raise SystemExit(
            f"Audio missing:\n"
            f"{AUDIO_FILE}"
        )


    # ========================================================
    # DATA CHECK
    # ========================================================

    if not DATA_FILE.exists():

        raise SystemExit(
            f"Dua database missing:\n"
            f"{DATA_FILE}"
        )


    # ========================================================
    # CLEAN WORK
    # ========================================================

    if WORK_DIR.exists():

        shutil.rmtree(
            WORK_DIR
        )


    WORK_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


    # ========================================================
    # SELECT
    # ========================================================

    dua = select_dua()


    # ========================================================
    # TRANSLATION
    # ========================================================

    print()
    print(
        "Fetching exact QuranEnc Urdu translation..."
    )


    urdu_translation = (
        fetch_quran_translation(
            dua
        )
    )


    print(
        "Translation received."
    )


    # ========================================================
    # BACKGROUND
    # ========================================================

    print()
    print(
        "Downloading Islamic background..."
    )


    background = (
        download_background()
    )


    prepared_background = (
        prepare_background(
            background
        )
    )


    # ========================================================
    # POSTER
    # ========================================================

    print()
    print(
        "Creating Arabic/Urdu poster..."
    )


    poster = create_poster(
        dua,
        urdu_translation
    )


    # ========================================================
    # OUTPUT
    # ========================================================

    timestamp = int(
        time.time()
    )


    output_file = (
        OUTPUT_DIR /
        f"dua_{timestamp}.mp4"
    )


    # ========================================================
    # VIDEO
    # ========================================================

    print()
    print(
        "Creating video..."
    )


    create_video(
        prepared_background,
        poster,
        output_file
    )


    # ========================================================
    # METADATA
    # ========================================================

    save_metadata(
        dua,
        urdu_translation,
        output_file
    )


    # ========================================================
    # USED LIST
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
    # FINAL
    # ========================================================

    if not output_file.exists():

        raise RuntimeError(
            "Video was not generated."
        )


    size_mb = (
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
        "File:",
        output_file
    )

    print(
        "Size:",
        f"{size_mb:.2f} MB"
    )

    print(
        "Resolution:",
        f"{WIDTH}x{HEIGHT}"
    )

    print(
        "Duration:",
        f"{VIDEO_SECONDS} seconds"
    )

    print(
        "RTL engine:",
        "Pillow RAQM"
    )

    print(
        "Translation:",
        "QuranEnc / Muhammad Junagarhi"
    )

    print(
        "============================================"
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
