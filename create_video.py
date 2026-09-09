import json
import math
import os
import random
import re
import shutil
import subprocess
import time
import unicodedata
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, features


# ============================================================
# SETTINGS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA = ROOT / "data"
OUTPUT = ROOT / "output"
WORK = ROOT / "work"

FONT = ROOT / "fonts" / "NotoNastaliqUrdu-Regular.ttf"
AUDIO = ROOT / "audio" / "islamic_background.mp3"
USED = ROOT / "used_hadith.json"

WIDTH = 1080
HEIGHT = 1920

FPS = 24
DURATION = 75

MAX_FONT = 88
MIN_FONT = 38

TEXT_WIDTH = 900
TEXT_HEIGHT = 900

PEXELS_KEY = os.getenv(
    "PEXELS_API_KEY",
    ""
).strip()


# ============================================================
# DATABASES
# ============================================================

DATABASES = {

    "bukhari": (
        DATA / "urd-bukhari.json",
        "Sahih al-Bukhari",
        "صحیح بخاری"
    ),

    "muslim": (
        DATA / "urd-muslim.json",
        "Sahih Muslim",
        "صحیح مسلم"
    )

}


# ============================================================
# CREATE FOLDERS
# ============================================================

DATA.mkdir(
    exist_ok=True
)

OUTPUT.mkdir(
    exist_ok=True
)

WORK.mkdir(
    exist_ok=True
)


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(value):

    text = unicodedata.normalize(
        "NFC",
        str(value or "")
    )

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

    # Remove HTML tags only.
    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    # Remove control characters.
    text = re.sub(
        r"[\x00-\x1F\x7F-\x9F]",
        "",
        text
    )

    # Normalize spaces.
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# USED HADITH
# ============================================================

def load_used():

    if not USED.exists():
        return set()

    try:

        data = json.loads(
            USED.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(
            data,
            dict
        ):

            return {
                str(key)
                for key in data.keys()
            }

        if isinstance(
            data,
            list
        ):

            return {
                str(value)
                for value in data
            }

    except Exception:

        pass

    return set()


def save_used(used):

    data = {
        key: True
        for key in sorted(used)
    }

    USED.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# ============================================================
# LOAD DATABASE
# ============================================================

def load_records(path):

    if not path.exists():

        raise RuntimeError(
            f"Hadith database missing: {path}"
        )

    data = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if isinstance(
        data,
        dict
    ):

        records = data.get(
            "hadiths",
            []
        )

    else:

        records = data

    if isinstance(
        records,
        dict
    ):

        records = records.get(
            "data",
            []
        )

    if not isinstance(
        records,
        list
    ):

        raise RuntimeError(
            f"Invalid Hadith database format: {path}"
        )

    return records


# ============================================================
# GET HADITH NUMBER
# ============================================================

def get_number(item):

    for key in (
        "hadithNumber",
        "hadithnumber",
        "number",
        "id"
    ):

        value = item.get(key)

        if value not in (
            None,
            ""
        ):

            return str(
                value
            ).strip()

    return None


# ============================================================
# GET URDU HADITH
# ============================================================

def get_urdu(item):

    for key in (
        "hadithUrdu",
        "urdu",
        "textUrdu",
        "translationUrdu"
    ):

        value = item.get(key)

        if isinstance(
            value,
            str
        ):

            value = clean_text(
                value
            )

            if value:

                return value

    return None


# ============================================================
# CHECK URDU
# ============================================================

def is_urdu(text):

    characters = re.findall(
        r"[\u0600-\u06FF]",
        text
    )

    return len(
        characters
    ) >= 10


# ============================================================
# FONT
# ============================================================

def urdu_font(size):

    if not FONT.exists():

        raise RuntimeError(
            f"Urdu font missing: {FONT}"
        )

    return ImageFont.truetype(
        str(FONT),
        size
    )


def latin_font(
    size,
    bold=False
):

    if bold:

        name = "DejaVuSans-Bold.ttf"

    else:

        name = "DejaVuSans.ttf"

    path = (
        "/usr/share/fonts/truetype/"
        "dejavu/"
        + name
    )

    return ImageFont.truetype(
        path,
        size
    )


# ============================================================
# TEXT BBOX
# ============================================================

def text_bbox(
    draw,
    text,
    font
):

    return draw.textbbox(
        (0, 0),
        text,
        font=font,
        direction="rtl",
        language="ur"
    )


# ============================================================
# URDU WRAP
# ============================================================

def wrap_text(
    draw,
    text,
    font,
    max_width
):

    words = text.split()

    lines = []

    current = ""

    for word in words:

        test = (
            word
            if not current
            else current + " " + word
        )

        box = text_bbox(
            draw,
            test,
            font
        )

        width = (
            box[2] -
            box[0]
        )

        if width <= max_width:

            current = test

        else:

            if current:

                lines.append(
                    current
                )

            word_box = text_bbox(
                draw,
                word,
                font
            )

            word_width = (
                word_box[2] -
                word_box[0]
            )

            # Never split a word.
            if word_width > max_width:

                return None

            current = word

    if current:

        lines.append(
            current
        )

    return lines


# ============================================================
# FIND FONT SIZE
# ============================================================

def fit_text(text):

    canvas = Image.new(
        "RGB",
        (
            WIDTH,
            HEIGHT
        )
    )

    draw = ImageDraw.Draw(
        canvas
    )

    for size in range(
        MAX_FONT,
        MIN_FONT - 1,
        -2
    ):

        font = urdu_font(
            size
        )

        lines = wrap_text(
            draw,
            text,
            font,
            TEXT_WIDTH
        )

        if not lines:
            continue

        heights = []

        for line in lines:

            box = text_bbox(
                draw,
                line,
                font
            )

            height = (
                box[3] -
                box[1]
            )

            heights.append(
                height
            )

        total_height = (
            sum(heights)
            +
            18 *
            max(
                0,
                len(lines) - 1
            )
        )

        if total_height <= TEXT_HEIGHT:

            return (
                size,
                lines,
                heights
            )

    # Important:
    # Do NOT force an oversized Hadith into the screen.
    return None


# ============================================================
# SELECT HADITH
# ============================================================

def select_hadith():

    used = load_used()

    candidates = []

    for collection, (
        path,
        english_name,
        urdu_name
    ) in DATABASES.items():

        records = load_records(
            path
        )

        for item in records:

            if not isinstance(
                item,
                dict
            ):

                continue

            number = get_number(
                item
            )

            text = get_urdu(
                item
            )

            if not number:
                continue

            if not text:
                continue

            if not is_urdu(text):
                continue

            key = (
                collection
                + ":"
                + number
            )

            if key in used:
                continue

            candidates.append({
                "key": key,
                "collection": english_name,
                "collection_urdu": urdu_name,
                "number": number,
                "text": text
            })

    if not candidates:

        raise RuntimeError(
            "No unused Hadith available."
        )

    random.shuffle(
        candidates
    )

    # Find one that completely fits.
    for hadith in candidates:

        fitted = fit_text(
            hadith["text"]
        )

        if fitted:

            (
                hadith["font_size"],
                hadith["lines"],
                hadith["heights"]
            ) = fitted

            print()
            print(
                "=" * 60
            )
            print(
                "SELECTED HADITH"
            )
            print(
                "=" * 60
            )

            print(
                hadith["collection"]
            )

            print(
                "Hadith No.:",
                hadith["number"]
            )

            print(
                hadith["text"]
            )

            print(
                "Font size:",
                hadith["font_size"]
            )

            print(
                "Lines:",
                len(
                    hadith["lines"]
                )
            )

            print(
                "=" * 60
            )

            return hadith

    raise RuntimeError(
        "No unused Hadith can fit completely "
        "on one screen at the minimum font size."
    )


# ============================================================
# CREATE POSTER SCREEN
# ============================================================

def create_screen(
    hadith
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

    # Light Islamic poster panel.
    panel = (
        65,
        245,
        1015,
        1665
    )

    draw.rounded_rectangle(
        panel,
        radius=46,
        fill=(
            250,
            247,
            238,
            238
        ),
        outline=(
            177,
            132,
            50,
            230
        ),
        width=4
    )

    gold = (
        164,
        118,
        39,
        255
    )

    dark = (
        30,
        29,
        25,
        255
    )

    center = WIDTH // 2

    # --------------------------------------------------------
    # Decorative lines
    # --------------------------------------------------------

    draw.line(
        (
            145,
            335,
            935,
            335
        ),
        fill=gold,
        width=3
    )

    draw.line(
        (
            145,
            1565,
            935,
            1565
        ),
        fill=gold,
        width=3
    )

    for y in (
        335,
        1565
    ):

        draw.polygon(
            [
                (
                    center,
                    y - 12
                ),
                (
                    center + 12,
                    y
                ),
                (
                    center,
                    y + 12
                ),
                (
                    center - 12,
                    y
                )
            ],
            fill=gold
        )

    # --------------------------------------------------------
    # Fonts
    # --------------------------------------------------------

    title_font = urdu_font(
        40
    )

    collection_font = urdu_font(
        46
    )

    hadith_font = urdu_font(
        hadith["font_size"]
    )

    ref_font = latin_font(
        28,
        bold=True
    )

    bottom_font = urdu_font(
        30
    )

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    draw.text(
        (
            center,
            285
        ),
        "حدیثِ مبارک",
        font=title_font,
        fill=gold,
        anchor="mm",
        direction="rtl",
        language="ur"
    )

    draw.text(
        (
            center,
            390
        ),
        hadith["collection_urdu"],
        font=collection_font,
        fill=dark,
        anchor="mm",
        direction="rtl",
        language="ur"
    )

    # --------------------------------------------------------
    # Complete Hadith
    # --------------------------------------------------------

    current_y = 475

    line_gap = 18

    for line, height in zip(
        hadith["lines"],
        hadith["heights"]
    ):

        draw.text(
            (
                center,
                current_y + height / 2
            ),
            line,
            font=hadith_font,
            fill=dark,
            anchor="mm",
            direction="rtl",
            language="ur"
        )

        current_y += (
            height +
            line_gap
        )

    # --------------------------------------------------------
    # Reference
    # --------------------------------------------------------

    reference = (
        f"Hadith No. {hadith['number']}"
    )

    draw.text(
        (
            center,
            1615
        ),
        reference,
        font=ref_font,
        fill=gold,
        anchor="mm"
    )

    draw.text(
        (
            center,
            1688
        ),
        "نبی کریم صلی اللہ علیہ وسلم نے فرمایا",
        font=bottom_font,
        fill=dark,
        anchor="mm",
        direction="rtl",
        language="ur"
    )

    output = (
        WORK /
        "hadith_screen.png"
    )

    image.save(
        output
    )

    return output


# ============================================================
# PEXELS IMAGE
# ============================================================

def get_image():

    if not PEXELS_KEY:

        raise RuntimeError(
            "PEXELS_API_KEY is missing."
        )

    queries = [
        "Islamic architecture",
        "mosque interior",
        "Medina mosque",
        "mosque sunset",
        "Kaaba",
        "Islamic pattern"
    ]

    random.shuffle(
        queries
    )

    last_error = None

    for query in queries:

        try:

            response = requests.get(
                "https://api.pexels.com/v1/search",
                headers={
                    "Authorization":
                        PEXELS_KEY
                },
                params={
                    "query": query,
                    "orientation": "portrait",
                    "size": "large",
                    "per_page": 15
                },
                timeout=45
            )

            response.raise_for_status()

            photos = response.json().get(
                "photos",
                []
            )

            random.shuffle(
                photos
            )

            for photo in photos:

                source = photo.get(
                    "src",
                    {}
                )

                url = (
                    source.get("large2x")
                    or source.get("large")
                    or source.get("original")
                )

                if not url:
                    continue

                try:

                    image_response = requests.get(
                        url,
                        timeout=45
                    )

                    image_response.raise_for_status()

                    path = (
                        WORK /
                        "background_source.jpg"
                    )

                    path.write_bytes(
                        image_response.content
                    )

                    with Image.open(
                        path
                    ) as check:

                        check.verify()

                    return path

                except Exception as error:

                    last_error = error

        except Exception as error:

            last_error = error

    raise RuntimeError(
        f"Could not download Pexels image: {last_error}"
    )


# ============================================================
# PREPARE BACKGROUND
# ============================================================

def prepare_background(
    source
):

    image = Image.open(
        source
    ).convert(
        "RGB"
    )

    target_ratio = (
        WIDTH /
        HEIGHT
    )

    source_ratio = (
        image.width /
        image.height
    )

    if source_ratio > target_ratio:

        new_height = HEIGHT

        new_width = math.ceil(
            HEIGHT *
            source_ratio
        )

    else:

        new_width = WIDTH

        new_height = math.ceil(
            WIDTH /
            source_ratio
        )

    image = image.resize(
        (
            new_width,
            new_height
        ),
        Image.Resampling.LANCZOS
    )

    left = max(
        0,
        (
            new_width -
            WIDTH
        ) // 2
    )

    top = max(
        0,
        (
            new_height -
            HEIGHT
        ) // 2
    )

    image = image.crop(
        (
            left,
            top,
            left + WIDTH,
            top + HEIGHT
        )
    )

    # Slight light overlay.
    overlay = Image.new(
        "RGBA",
        image.size,
        (
            255,
            255,
            255,
            28
        )
    )

    image = Image.alpha_composite(
        image.convert("RGBA"),
        overlay
    )

    image = image.convert(
        "RGB"
    )

    output = (
        WORK /
        "background.jpg"
    )

    image.save(
        output,
        quality=92
    )

    return output


# ============================================================
# CREATE VIDEO
# ============================================================

def create_video(
    background,
    screen,
    output
):

    print(
        "Creating video..."
    )

    # Slow background movement.
    # Text stays completely static.
    filter_complex = (

        "[0:v]"
        "scale=1160:2060,"
        "crop=1080:1920:"
        "x='40+40*sin(t/10)':"
        "y='70+40*cos(t/12)',"
        "eq=saturation=0.88:"
        "brightness=0.03,"
        "trim=duration=75,"
        "setpts=PTS-STARTPTS"
        "[bg];"

        "[1:v]"
        "format=rgba,"
        "trim=duration=75,"
        "setpts=PTS-STARTPTS"
        "[poster];"

        "[bg][poster]"
        "overlay=0:0:"
        "eof_action=repeat"
        "[video];"

        "[2:a]"
        "atrim=duration=75,"
        "asetpts=PTS-STARTPTS"
        "[audio]"
    )

    command = [

        "ffmpeg",

        "-y",

        "-hide_banner",

        "-loglevel",
        "warning",

        # Background
        "-loop",
        "1",

        "-i",
        str(background),

        # Poster
        "-loop",
        "1",

        "-i",
        str(screen),

        # Audio
        "-stream_loop",
        "-1",

        "-i",
        str(AUDIO),

        "-filter_complex",
        filter_complex,

        "-map",
        "[video]",

        "-map",
        "[audio]",

        "-t",
        str(DURATION),

        "-r",
        str(FPS),

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "23",

        "-pix_fmt",
        "yuv420p",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-movflags",
        "+faststart",

        str(output)
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:

        print(
            result.stderr
        )

        raise RuntimeError(
            "FFmpeg failed."
        )

    print(
        "VIDEO CREATED:"
    )

    print(
        output
    )


# ============================================================
# METADATA
# ============================================================

def create_metadata(
    hadith
):

    reference = (
        f"{hadith['collection']} "
        f"— Hadith No. "
        f"{hadith['number']}"
    )

    title = (
        "Islamic Hadith Reminder | "
        f"{reference}"
    )

    description = (
        "Islamic Hadith Reminder\n\n"
        f"{reference}\n\n"
        f"{hadith['text']}\n\n"
        "#Hadith "
        "#SahihBukhari "
        "#SahihMuslim "
        "#Islam "
        "#Sunnah "
        "#IslamicReminder"
    )

    files = {

        "youtube_title.txt":
            title,

        "youtube_description.txt":
            description,

        "tiktok_caption.txt":
            f"{reference}\n\n"
            "#Hadith #Islam #Sunnah "
            "#Muslim #IslamicReminder",

        "instagram_caption.txt":
            f"{reference}\n\n"
            "#Hadith #Islam #Sunnah "
            "#Muslim #IslamicReminder",

        "facebook_caption.txt":
            f"{reference}\n\n"
            "#Hadith #Islam #Sunnah "
            "#Muslim #IslamicReminder"
    }

    for filename, text in files.items():

        (
            OUTPUT /
            filename
        ).write_text(
            text,
            encoding="utf-8"
        )

    metadata = {

        "title": title,

        "reference": reference,

        "collection":
            hadith["collection"],

        "collection_urdu":
            hadith["collection_urdu"],

        "hadith_number":
            hadith["number"],

        "hadith_text":
            hadith["text"]
    }

    (
        OUTPUT /
        "metadata.json"
    ).write_text(
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
        "=" * 70
    )
    print(
        "ISLAMIC HADITH VIDEO GENERATOR"
    )
    print(
        "=" * 70
    )

    # --------------------------------------------------------
    # Basic checks
    # --------------------------------------------------------

    if not features.check(
        "raqm"
    ):

        raise RuntimeError(
            "Pillow RAQM is not available."
        )

    if not PEXELS_KEY:

        raise RuntimeError(
            "PEXELS_API_KEY is missing."
        )

    if not AUDIO.exists():

        raise RuntimeError(
            f"Background audio missing: {AUDIO}"
        )

    if not FONT.exists():

        raise RuntimeError(
            f"Urdu font missing: {FONT}"
        )

    # --------------------------------------------------------
    # Clean work directory
    # --------------------------------------------------------

    for item in WORK.iterdir():

        if item.is_dir():

            shutil.rmtree(
                item
            )

        else:

            item.unlink()

    # --------------------------------------------------------
    # Select Hadith
    # --------------------------------------------------------

    hadith = select_hadith()

    # --------------------------------------------------------
    # Background
    # --------------------------------------------------------

    source_image = get_image()

    background = prepare_background(
        source_image
    )

    # --------------------------------------------------------
    # Poster
    # --------------------------------------------------------

    screen = create_screen(
        hadith
    )

    # --------------------------------------------------------
    # Video filename
    # --------------------------------------------------------

    filename = (
        "islamic_hadith_"
        + str(
            int(
                time.time()
            )
        )
        + ".mp4"
    )

    video = (
        OUTPUT /
        filename
    )

    # --------------------------------------------------------
    # Create video
    # --------------------------------------------------------

    create_video(
        background,
        screen,
        video
    )

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    create_metadata(
        hadith
    )

    # --------------------------------------------------------
    # Save used Hadith
    # --------------------------------------------------------

    used = load_used()

    used.add(
        hadith["key"]
    )

    save_used(
        used
    )

    # --------------------------------------------------------
    # Success
    # --------------------------------------------------------

    print()
    print(
        "=" * 70
    )
    print(
        "SUCCESS"
    )
    print(
        "=" * 70
    )

    print(
        "Collection:",
        hadith["collection"]
    )

    print(
        "Hadith:",
        hadith["number"]
    )

    print(
        "Video:",
        video
    )

    print(
        "Complete Hadith displayed on ONE screen."
    )

    print(
        "No Hadith was truncated or paraphrased."
    )


if __name__ == "__main__":

    main()
