import json
import os
import random
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests
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
# VIDEO SETTINGS
# ============================================================

WIDTH = 1080
HEIGHT = 1920
FPS = 24
VIDEO_SECONDS = 60


# ============================================================
# API
# ============================================================

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()

PEXELS_URL = "https://api.pexels.com/v1/search"

QURANENC_URL = (
    "https://quranenc.com/api/v1/translation/aya"
)


# ============================================================
# DESIGN
# ============================================================

BACKGROUND_COLOR = (246, 245, 237)
CARD_COLOR = (250, 249, 241)

DARK = (35, 35, 35)
GOLD = (154, 116, 45)
SOFT_GOLD = (190, 160, 95)
LIGHT_BORDER = (218, 205, 170)


OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
WORK_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):
    if text is None:
        return ""

    text = str(text)

    text = text.replace("\ufeff", "")
    text = text.replace("\u200b", "")
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")

    # Remove HTML tags from QuranEnc response
    text = re.sub(r"<[^>]+>", " ", text)

    # Remove excessive spaces
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# USED DUA SYSTEM
# ============================================================

def load_used():

    if not USED_FILE.exists():
        return []

    try:
        data = json.loads(
            USED_FILE.read_text(encoding="utf-8")
        )

        if isinstance(data, list):
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
        raise FileNotFoundError(
            f"Missing Dua database: {DATA_FILE}"
        )

    data = json.loads(
        DATA_FILE.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(data, list):
        raise RuntimeError(
            "duas.json must contain a JSON list."
        )

    return data


# ============================================================
# FONT
# ============================================================

def get_font(size):

    if not FONT_FILE.exists():
        raise FileNotFoundError(
            f"Missing Urdu font: {FONT_FILE}"
        )

    return ImageFont.truetype(
        str(FONT_FILE),
        size
    )


# ============================================================
# RTL WRAPPING
# ============================================================

def wrap_rtl_text(
    draw,
    text,
    font,
    max_width,
    language="ur"
):

    words = text.split()

    lines = []
    current = ""

    for word in words:

        candidate = (
            word
            if not current
            else current + " " + word
        )

        try:

            box = draw.textbbox(
                (0, 0),
                candidate,
                font=font,
                direction="rtl",
                language=language
            )

        except Exception:

            box = draw.textbbox(
                (0, 0),
                candidate,
                font=font
            )

        width = box[2] - box[0]

        if width <= max_width:

            current = candidate

        else:

            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


# ============================================================
# FONT FITTING
# ============================================================

def fit_text(
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

        font = get_font(size)

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
            len(lines) * line_height
        )

        if total_height <= max_height:

            return (
                font,
                lines,
                line_height
            )

    return None


# ============================================================
# FETCH EXACT URDU TRANSLATION
# ============================================================

def fetch_quranenc_translation(dua):

    translation_key = dua.get(
        "translation_key",
        "urdu_junagarhi"
    )

    sura = int(dua["sura"])
    ayah = int(dua["ayah"])

    url = (
        f"{QURANENC_URL}/"
        f"{translation_key}/"
        f"{sura}/"
        f"{ayah}"
    )

    print(
        "Fetching QuranEnc translation:"
    )

    print(url)

    response = requests.get(
        url,
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    translation = clean_text(
        data.get("translation", "")
    )

    if not translation:

        raise RuntimeError(
            f"QuranEnc returned no translation "
            f"for {sura}:{ayah}"
        )

    return translation


# ============================================================
# PEXELS BACKGROUND
# ============================================================

def download_background():

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

    random.shuffle(queries)

    headers = {
        "Authorization": PEXELS_API_KEY
    }

    for query in queries:

        print(
            f"Searching Pexels: {query}"
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
            .get("photos", [])
        )

        if not photos:
            continue

        random.shuffle(photos)

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

            image_path = (
                WORK_DIR /
                "background.jpg"
            )

            try:

                r = requests.get(
                    url,
                    timeout=60
                )

                r.raise_for_status()

                image_path.write_bytes(
                    r.content
                )

                Image.open(
                    image_path
                ).verify()

                return image_path

            except Exception:

                image_path.unlink(
                    missing_ok=True
                )

    raise RuntimeError(
        "Could not download an Islamic "
        "background from Pexels."
    )


# ============================================================
# PREPARE BACKGROUND
# ============================================================

def prepare_background(
    image_path
):

    image = Image.open(
        image_path
    ).convert("RGB")

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
        new_width - WIDTH
    ) // 2

    top = (
        new_height - HEIGHT
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

    # Dark overlay so the card remains readable
    overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 70)
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
        "RGB",
        (WIDTH, HEIGHT),
        BACKGROUND_COLOR
    )

    draw = ImageDraw.Draw(image)

    center = WIDTH // 2

    # --------------------------------------------------------
    # MAIN CARD
    # --------------------------------------------------------

    card_x1 = 70
    card_y1 = 100

    card_x2 = WIDTH - 70
    card_y2 = HEIGHT - 100

    draw.rounded_rectangle(
        (
            card_x1,
            card_y1,
            card_x2,
            card_y2
        ),
        radius=35,
        fill=CARD_COLOR,
        outline=SOFT_GOLD,
        width=3
    )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title_font = get_font(52)

    title = clean_text(
        dua["title"]
    )

    draw.text(
        (center, 195),
        title,
        font=title_font,
        fill=GOLD,
        anchor="mm",
        direction="rtl",
        language="ur"
    )

    draw.line(
        (
            180,
            265,
            WIDTH - 180,
            265
        ),
        fill=SOFT_GOLD,
        width=2
    )

    # --------------------------------------------------------
    # ARABIC
    # --------------------------------------------------------

    arabic = clean_text(
        dua["arabic"]
    )

    arabic_font = get_font(52)

    arabic_lines = wrap_rtl_text(
        draw,
        arabic,
        arabic_font,
        800,
        language="ar"
    )

    y = 335

    for line in arabic_lines:

        draw.text(
            (center, y),
            line,
            font=arabic_font,
            fill=DARK,
            anchor="ma",
            direction="rtl",
            language="ar"
        )

        y += 80

    # --------------------------------------------------------
    # URDU MEANING TITLE
    # --------------------------------------------------------

    meaning_title_font = get_font(
        35
    )

    draw.text(
        (center, y + 25),
        "اردو معنی",
        font=meaning_title_font,
        fill=GOLD,
        anchor="ma",
        direction="rtl",
        language="ur"
    )

    y += 100

    # --------------------------------------------------------
    # URDU TRANSLATION
    # --------------------------------------------------------

    meaning = clean_text(
        urdu_translation
    )

    fitted = fit_text(
        draw,
        meaning,
        max_width=800,
        max_height=430,
        max_size=44,
        min_size=28,
        language="ur"
    )

    if not fitted:

        raise RuntimeError(
            "Urdu translation is too long "
            "for one screen."
        )

    meaning_font, lines, line_height = fitted

    for line in lines:

        draw.text(
            (center, y),
            line,
            font=meaning_font,
            fill=DARK,
            anchor="ma",
            direction="rtl",
            language="ur"
        )

        y += line_height

    # --------------------------------------------------------
    # REFERENCE
    # --------------------------------------------------------

    reference_y = 1225

    draw.line(
        (
            180,
            reference_y - 55,
            WIDTH - 180,
            reference_y - 55
        ),
        fill=SOFT_GOLD,
        width=2
    )

    reference_font = get_font(
        34
    )

    reference = (
        "حوالہ: " +
        clean_text(
            dua["reference"]
        )
    )

    draw.text(
        (center, reference_y),
        reference,
        font=reference_font,
        fill=GOLD,
        anchor="ma",
        direction="rtl",
        language="ur"
    )

    # --------------------------------------------------------
    # CONTEXT
    # --------------------------------------------------------

    context = clean_text(
        dua.get("context", "")
    )

    if context:

        context_title_font = get_font(
            34
        )

        draw.text(
            (center, 1325),
            "پس منظر",
            font=context_title_font,
            fill=GOLD,
            anchor="ma",
            direction="rtl",
            language="ur"
        )

        fitted_context = fit_text(
            draw,
            context,
            max_width=790,
            max_height=300,
            max_size=32,
            min_size=23,
            language="ur"
        )

        if not fitted_context:

            raise RuntimeError(
                "Context is too long "
                "for one screen."
            )

        context_font, context_lines, context_line_height = fitted_context

        y_context = 1390

        for line in context_lines:

            draw.text(
                (center, y_context),
                line,
                font=context_font,
                fill=DARK,
                anchor="ma",
                direction="rtl",
                language="ur"
            )

            y_context += context_line_height

    # --------------------------------------------------------
    # SOURCE
    # --------------------------------------------------------

    source_font = get_font(
        21
    )

    source = (
        "ماخذ: QuranEnc — "
        "اردو ترجمہ: محمد جوناگڑھی"
    )

    draw.text(
        (center, HEIGHT - 150),
        source,
        font=source_font,
        fill=SOFT_GOLD,
        anchor="ma",
        direction="rtl",
        language="ur"
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

        (
            "[0:v]"
            "scale=1160:2060,"
            "crop=1080:1920:"
            "x='40+35*sin(t/10)':"
            "y='70+35*cos(t/12)',"
            "format=yuv420p"
            "[bg];"

            "[1:v]"
            "format=rgba"
            "[poster];"

            "[bg][poster]"
            "overlay=0:0:format=auto"
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

    # Start a new cycle
    if not available:

        print(
            "All Duas have been used."
        )

        print(
            "Starting a new cycle."
        )

        used = set()

        available = duas

        save_used([])

    selected = random.choice(
        available
    )

    print(
        "=" * 60
    )

    print(
        "SELECTED:"
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
    output_file
):

    metadata = {

        "type": "quran_dua",

        "title": dua["title"],

        "arabic": dua["arabic"],

        "urdu": urdu_translation,

        "reference": dua["reference"],

        "sura": dua["sura"],

        "ayah": dua["ayah"],

        "context": dua.get(
            "context",
            ""
        ),

        "source": "QuranEnc",

        "translation": "Muhammad Junagarhi",

        "translation_key": dua.get(
            "translation_key",
            "urdu_junagarhi"
        ),

        "video": output_file.name
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
        "==========================================\n"
        " ISLAMIC DUA VIDEO AUTOMATION\n"
        "==========================================\n"
    )

    # --------------------------------------------------------
    # CHECK API KEY
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
            f"ERROR: Missing font:\n"
            f"{FONT_FILE}"
        )

    # --------------------------------------------------------
    # CHECK AUDIO
    # --------------------------------------------------------

    if not AUDIO_FILE.exists():

        raise SystemExit(
            f"ERROR: Missing audio:\n"
            f"{AUDIO_FILE}"
        )

    # --------------------------------------------------------
    # CHECK DATABASE
    # --------------------------------------------------------

    if not DATA_FILE.exists():

        raise SystemExit(
            f"ERROR: Missing database:\n"
            f"{DATA_FILE}"
        )

    # --------------------------------------------------------
    # CLEAN WORK DIRECTORY
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
    # SELECT DUA
    # --------------------------------------------------------

    dua = select_dua()

    # --------------------------------------------------------
    # GET EXACT URDU TRANSLATION
    # --------------------------------------------------------

    urdu_translation = (
        fetch_quranenc_translation(
            dua
        )
    )

    print(
        "\nUrdu translation received."
    )

    print(
        urdu_translation
    )

    # --------------------------------------------------------
    # DOWNLOAD BACKGROUND
    # --------------------------------------------------------

    background = (
        download_background()
    )

    # --------------------------------------------------------
    # PREPARE BACKGROUND
    # --------------------------------------------------------

    prepared_background = (
        prepare_background(
            background
        )
    )

    # --------------------------------------------------------
    # CREATE POSTER
    # --------------------------------------------------------

    poster = create_poster(
        dua,
        urdu_translation
    )

    # --------------------------------------------------------
    # OUTPUT NAME
    # --------------------------------------------------------

    timestamp = int(
        time.time()
    )

    output_file = (
        OUTPUT_DIR /
        f"dua_{timestamp}.mp4"
    )

    # --------------------------------------------------------
    # CREATE VIDEO
    # --------------------------------------------------------

    create_video(
        prepared_background,
        poster,
        output_file
    )

    # --------------------------------------------------------
    # SAVE METADATA
    # --------------------------------------------------------

    save_metadata(
        dua,
        urdu_translation,
        output_file
    )

    # --------------------------------------------------------
    # MARK AS USED
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
    # FINISHED
    # --------------------------------------------------------

    print(
        "\n"
        "=========================================="
    )

    print(
        " VIDEO CREATED SUCCESSFULLY"
    )

    print(
        "=========================================="
    )

    print(
        f"Video: {output_file}"
    )

    print(
        f"Metadata: {output_file.with_suffix('.json')}"
    )

    print(
        "==========================================\n"
    )


if __name__ == "__main__":
    main()
