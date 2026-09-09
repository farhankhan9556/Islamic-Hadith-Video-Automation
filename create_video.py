import json
import math
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

PEXELS_API_KEY = os.getenv(
    "PEXELS_API_KEY",
    ""
).strip()

PEXELS_URL = (
    "https://api.pexels.com/v1/search"
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


# ============================================================
# FILE PREPARATION
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
# USED DUA DATABASE
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
# LOAD DUA LIBRARY
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
# URDU FONT
# ============================================================

def get_font(size):

    return ImageFont.truetype(
        str(FONT_FILE),
        size
    )


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_rtl_text(
    draw,
    text,
    font,
    max_width
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

        box = draw.textbbox(
            (0, 0),
            candidate,
            font=font,
            direction="rtl",
            language="ur"
        )

        width = box[2] - box[0]

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
    min_size,
    spacing
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
# DOWNLOAD BACKGROUND
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
        "Islamic architecture night"
    ]

    random.shuffle(
        queries
    )

    headers = {
        "Authorization":
            PEXELS_API_KEY
    }

    for query in queries:

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

        photos = response.json().get(
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

            r = requests.get(
                url,
                timeout=60
            )

            r.raise_for_status()

            image_path.write_bytes(
                r.content
            )

            try:

                Image.open(
                    image_path
                ).verify()

                return image_path

            except Exception:

                image_path.unlink(
                    missing_ok=True
                )

    raise RuntimeError(
        "Could not download an Islamic background."
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

    # Slight blur for readable text.
    image = image.filter(
        ImageFilter.GaussianBlur(
            radius=1.2
        )
    )

    # Dark translucent overlay.
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
# CREATE DUA POSTER
# ============================================================

def create_poster(dua):

    image = Image.new(
        "RGB",
        (
            WIDTH,
            HEIGHT
        ),
        BACKGROUND_COLOR
    )

    draw = ImageDraw.Draw(
        image
    )

    # Outer card.
    card_x1 = 70
    card_y1 = 120
    card_x2 = WIDTH - 70
    card_y2 = HEIGHT - 120

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

    center = WIDTH // 2

    # ========================================================
    # TITLE
    # ========================================================

    title_font = get_font(
        52
    )

    title = clean_text(
        dua["title"]
    )

    draw.text(
        (
            center,
            210
        ),
        title,
        font=title_font,
        fill=GOLD,
        anchor="mm",
        direction="rtl",
        language="ur"
    )

    # Decorative line.
    draw.line(
        (
            180,
            275,
            WIDTH - 180,
            275
        ),
        fill=SOFT_GOLD,
        width=2
    )

    # ========================================================
    # ARABIC DUA
    # ========================================================

    arabic_font = get_font(
        55
    )

    arabic = clean_text(
        dua["arabic"]
    )

    arabic_lines = wrap_rtl_text(
        draw,
        arabic,
        arabic_font,
        780
    )

    y = 350

    for line in arabic_lines:

        draw.text(
            (
                center,
                y
            ),
            line,
            font=arabic_font,
            fill=DARK,
            anchor="ma",
            direction="rtl",
            language="ar"
        )

        y += 82

    # ========================================================
    # URDU MEANING
    # ========================================================

    meaning_title_font = get_font(
        35
    )

    draw.text(
        (
            center,
            y + 25
        ),
        "اردو معنی",
        font=meaning_title_font,
        fill=GOLD,
        anchor="ma",
        direction="rtl",
        language="ur"
    )

    y += 105

    meaning = clean_text(
        dua["urdu"]
    )

    fitted = fit_text(
        draw,
        meaning,
        max_width=800,
        max_height=380,
        max_size=45,
        min_size=30,
        spacing=1.45
    )

    if not fitted:

        raise RuntimeError(
            "Urdu meaning is too long "
            "for one screen."
        )

    meaning_font, lines, line_height = fitted

    for line in lines:

        draw.text(
            (
                center,
                y
            ),
            line,
            font=meaning_font,
            fill=DARK,
            anchor="ma",
            direction="rtl",
            language="ur"
        )

        y += line_height

    # ========================================================
    # REFERENCE
    # ========================================================

    draw.line(
        (
            180,
            1270,
            WIDTH - 180,
            1270
        ),
        fill=SOFT_GOLD,
        width=2
    )

    reference_font = get_font(
        34
    )

    reference = (
        "حوالہ: "
        +
        clean_text(
            dua["reference"]
        )
    )

    draw.text(
        (
            center,
            1335
        ),
        reference,
        font=reference_font,
        fill=GOLD,
        anchor="ma",
        direction="rtl",
        language="ur"
    )

    # ========================================================
    # STORY / CONTEXT
    # ========================================================

    story_title_font = get_font(
        34
    )

    draw.text(
        (
            center,
            1435
        ),
        "پس منظر / واقعہ",
        font=story_title_font,
        fill=GOLD,
        anchor="ma",
        direction="rtl",
        language="ur"
    )

    story = clean_text(
        dua["story"]
    )

    fitted_story = fit_text(
        draw,
        story,
        max_width=780,
        max_height=300,
        max_size=34,
        min_size=24,
        spacing=1.35
    )

    if not fitted_story:

        raise RuntimeError(
            "Story is too long "
            "for one screen."
        )

    story_font, story_lines, story_line_height = fitted_story

    y = 1500

    for line in story_lines:

        draw.text(
            (
                center,
                y
            ),
            line,
            font=story_font,
            fill=DARK,
            anchor="ma",
            direction="rtl",
            language="ur"
        )

        y += story_line_height

    # ========================================================
    # SOURCE
    # ========================================================

    source_font = get_font(
        22
    )

    source = (
        "ماخذ: "
        +
        clean_text(
            dua.get(
                "source",
                ""
            )
        )
    )

    draw.text(
        (
            center,
            HEIGHT - 170
        ),
        source,
        font=source_font,
        fill=SOFT_GOLD,
        anchor="ma",
        direction="rtl",
        language="ur"
    )

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
            "urdu",
            "reference",
            "story",
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

        # Start a new cycle only after
        # every Dua has been used.
        print(
            "All Duas used. "
            "Starting a new cycle."
        )

        used = set()

        available = duas

        save_used([])

    selected = random.choice(
        available
    )

    print()
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
        selected["reference"]
    )

    print(
        selected["source"]
    )

    print(
        "=" * 60
    )

    return selected


# ============================================================
# METADATA
# ============================================================

def save_metadata(
    dua,
    output_file
):

    metadata = {

        "type": "dua",

        "title":
            dua["title"],

        "arabic":
            dua["arabic"],

        "urdu":
            dua["urdu"],

        "reference":
            dua["reference"],

        "story":
            dua["story"],

        "source":
            dua["source"],

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

    if not PEXELS_API_KEY:

        raise SystemExit(
            "ERROR: PEXELS_API_KEY is missing."
        )

    if not FONT_FILE.exists():

        raise SystemExit(
            f"Missing font: {FONT_FILE}"
        )

    if not AUDIO_FILE.exists():

        raise SystemExit(
            f"Missing audio: {AUDIO_FILE}"
        )

    if not DATA_FILE.exists():

        raise SystemExit(
            f"Missing Dua database: {DATA_FILE}"
        )

    # Clean working directory.
    if WORK_DIR.exists():

        shutil.rmtree(
            WORK_DIR
        )

    WORK_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    dua = select_dua()

    background = download_background()

    prepared_background = prepare_background(
        background
    )

    poster = create_poster(
        dua
    )

    timestamp = int(
        time.time()
    )

    output_file = (
        OUTPUT_DIR /
        f"dua_{timestamp}.mp4"
    )

    create_video(
        prepared_background,
        poster,
        output_file
    )

    save_metadata(
        dua,
        output_file
    )

    used = load_used()

    if dua["id"] not in used:

        used.append(
            dua["id"]
        )

    save_used(
        used
    )

    print()
    print(
        "=" * 60
    )

    print(
        "VIDEO CREATED SUCCESSFULLY"
    )

    print(
        output_file
    )

    print(
        "=" * 60
    )


if __name__ == "__main__":
    main()
