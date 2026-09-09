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
# PROJECT
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_FILE = ROOT / "data" / "duas.json"
USED_FILE = ROOT / "used_duas.json"

OUTPUT_DIR = ROOT / "output"
WORK_DIR = ROOT / "work"

AUDIO_FILE = ROOT / "audio" / "islamic_background.mp3"


# ============================================================
# VIDEO SETTINGS
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

QURANENC_AYA_URL = (
    "https://quranenc.com/api/v1/translation/aya"
)

QURANENC_SURA_URL = (
    "https://quranenc.com/api/v1/translation/sura"
)


# ============================================================
# QURANENC TRANSLATION
# ============================================================

TRANSLATION_KEY = "urdu_junagarhi"


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

    possible_fonts = [

        # GitHub Ubuntu runner
        Path(
            "/usr/share/fonts/truetype/noto/"
            "NotoNaskhArabic-Regular.ttf"
        ),

        # Other common Linux location
        Path(
            "/usr/share/fonts/opentype/noto/"
            "NotoNaskhArabic-Regular.ttf"
        ),

        # Repository fallback
        ROOT /
        "fonts" /
        "NotoNaskhArabic-Regular.ttf",

        # Old repository font fallback
        ROOT /
        "fonts" /
        "NotoNastaliqUrdu-Regular.ttf"
    ]

    for font_path in possible_fonts:

        if font_path.exists():

            print(
                "Using font:"
            )

            print(
                font_path
            )

            return font_path

    # Last-resort search
    search_locations = [

        Path(
            "/usr/share/fonts"
        ),

        ROOT /
        "fonts"
    ]

    for location in search_locations:

        if not location.exists():
            continue

        matches = list(
            location.rglob(
                "*.ttf"
            )
        )

        for font_path in matches:

            name = (
                font_path.name.lower()
            )

            if (
                "naskh" in name
                and
                "arabic" in name
            ):

                print(
                    "Using discovered font:"
                )

                print(
                    font_path
                )

                return font_path

    raise RuntimeError(
        "Arabic/Urdu font was not found."
    )


FONT_FILE = find_font()


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
# RTL
# ============================================================

def rtl_text(text):

    text = clean_text(
        text
    )

    if not text:
        return ""

    reshaped = (
        arabic_reshaper.reshape(
            text
        )
    )

    return get_display(
        reshaped
    )


# ============================================================
# FONT
# ============================================================

def get_font(size):

    return ImageFont.truetype(
        str(FONT_FILE),
        size
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
# LOAD DUAS
# ============================================================

def load_duas():

    if not DATA_FILE.exists():

        raise RuntimeError(
            f"Missing file:\n{DATA_FILE}"
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
            "duas.json must be a JSON list."
        )

    if not data:

        raise RuntimeError(
            "duas.json is empty."
        )

    return data


# ============================================================
# RTL WRAP
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

        display_candidate = (
            rtl_text(
                candidate
            )
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
# HTTP
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
        f"QuranEnc Ayah API: "
        f"{sura}:{ayah}"
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

                print(
                    f"Translation found "
                    f"for {sura}:{ayah}"
                )

                return translation

        print(
            "No translation from "
            "single Ayah endpoint."
        )

    except Exception as error:

        print(
            "Single Ayah API failed:"
        )

        print(
            str(error)
        )


    # ========================================================
    # FULL SURAH FALLBACK
    # ========================================================

    print(
        f"Trying full Surah "
        f"fallback: {sura}"
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

        print(
            "Surah verses received:",
            len(verses)
        )

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

                print(
                    f"Surah fallback "
                    f"found {sura}:{ayah}"
                )

                return translation

        raise RuntimeError(
            f"Translation for "
            f"{sura}:{ayah} was not "
            f"found in Surah response."
        )

    except Exception as error:

        raise RuntimeError(
            f"QuranEnc failed for "
            f"{sura}:{ayah}\n"
            f"{error}"
        )


# ============================================================
# COMPLETE TRANSLATION
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
            "Empty Urdu translation."
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
                    "query": query,
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
                    src.get(
                        "portrait"
                    )
                    or
                    src.get(
                        "large2x"
                    )
                    or
                    src.get(
                        "large"
                    )
                )

                if not image_url:

                    continue

                output = (
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

                    output.write_bytes(
                        image_response.content
                    )

                    test_image = (
                        Image.open(
                            output
                        )
                    )

                    test_image.verify()

                    print(
                        "Background downloaded."
                    )

                    return output

                except Exception:

                    output.unlink(
                        missing_ok=True
                    )

        except Exception as error:

            print(
                "Pexels request failed:"
            )

            print(
                str(error)
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

    dark_overlay = Image.new(
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
        image.convert(
            "RGBA"
        ),
        dark_overlay
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

    card_x1 = 55
    card_y1 = 60

    card_x2 = WIDTH - 55
    card_y2 = HEIGHT - 60

    draw.rounded_rectangle(
        (
            card_x1,
            card_y1,
            card_x2,
            card_y2
        ),
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

    title_fit = fit_text(
        draw,
        dua["title"],
        max_width=800,
        max_height=100,
        max_size=50,
        min_size=32
    )

    if not title_fit:

        raise RuntimeError(
            "Title does not fit."
        )

    (
        title_font,
        title_lines,
        title_line_height
    ) = title_fit

    title_y = 165

    for line in title_lines:

        draw_rtl(
            draw,
            (
                center,
                title_y
            ),
            line,
            title_font,
            GOLD,
            "ma"
        )

        title_y += (
            title_line_height
        )


    # ========================================================
    # LINE
    # ========================================================

    draw.line(
        (
            150,
            265,
            WIDTH - 150,
            265
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
    # ARABIC
    # ========================================================

    arabic_fit = fit_text(
        draw,
        dua["arabic"],
        max_width=800,
        max_height=380,
        max_size=54,
        min_size=32
    )

    if not arabic_fit:

        raise RuntimeError(
            "Arabic Dua does not fit."
        )

    (
        arabic_font,
        arabic_lines,
        arabic_line_height
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
            "ma"
        )

        arabic_y += (
            arabic_line_height
        )


    # ========================================================
    # MEANING TITLE
    # ========================================================

    meaning_title_font = get_font(
        34
    )

    meaning_title_y = (
        arabic_y + 15
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
        "ma"
    )


    # ========================================================
    # MEANING
    # ========================================================

    meaning_y = (
        meaning_title_y + 75
    )

    meaning_fit = fit_text(
        draw,
        urdu_translation,
        max_width=790,
        max_height=420,
        max_size=42,
        min_size=24
    )

    if not meaning_fit:

        raise RuntimeError(
            "Urdu translation does not "
            "fit on one screen."
        )

    (
        meaning_font,
        meaning_lines,
        meaning_line_height
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
            "ma"
        )

        meaning_y += (
            meaning_line_height
        )


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
            "ma"
        )

        context_fit = fit_text(
            draw,
            context,
            max_width=770,
            max_height=270,
            max_size=29,
            min_size=20
        )

        if not context_fit:

            raise RuntimeError(
                "Context does not fit."
            )

        (
            context_font,
            context_lines,
            context_line_height
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
                "ma"
            )

            context_y += (
                context_line_height
            )


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
        "ma"
    )


    # ========================================================
    # SAVE
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
            f"Audio file missing:\n"
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

        if valid:

            available.append(
                dua
            )


    # ========================================================
    # RESET CYCLE
    # ========================================================

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
            "No valid Duas found."
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
        "Title:",
        selected["title"]
    )

    print(
        "Reference:",
        selected["reference"]
    )

    print(
        "Sura:",
        selected["sura"]
    )

    print(
        "Ayah:",
        selected["ayah"]
    )

    if selected.get(
        "ayah_end"
    ):

        print(
            "Ayah End:",
            selected["ayah_end"]
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

    print(
        "Metadata saved:"
    )

    print(
        metadata_file
    )


# ============================================================
# CLEAN WORK
# ============================================================

def clean_work():

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
    # CHECK API
    # ========================================================

    if not PEXELS_API_KEY:

        raise SystemExit(
            "ERROR: PEXELS_API_KEY is missing."
        )


    # ========================================================
    # CHECK FONT
    # ========================================================

    if not FONT_FILE.exists():

        raise SystemExit(
            "ERROR: Arabic/Urdu font missing."
        )

    print(
        "Font:",
        FONT_FILE
    )


    # ========================================================
    # CHECK AUDIO
    # ========================================================

    if not AUDIO_FILE.exists():

        raise SystemExit(
            f"ERROR: Audio missing:\n"
            f"{AUDIO_FILE}"
        )


    # ========================================================
    # CHECK DATA
    # ========================================================

    if not DATA_FILE.exists():

        raise SystemExit(
            f"ERROR: Dua database missing:\n"
            f"{DATA_FILE}"
        )


    # ========================================================
    # CLEAN WORK
    # ========================================================

    clean_work()


    # ========================================================
    # SELECT
    # ========================================================

    dua = select_dua()


    # ========================================================
    # TRANSLATION
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
        "Urdu translation received."
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


    # ========================================================
    # PREPARE
    # ========================================================

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
        "Creating poster..."
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
        "Creating 60-second video..."
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
            "Video was not created."
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
        "============================================"
    )

    print()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()
