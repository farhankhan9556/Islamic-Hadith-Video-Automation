import json
import os
import random
import re
import subprocess
import time
import unicodedata
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, features


# =========================
# SETTINGS
# =========================

ROOT = Path(__file__).parent

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

MAX_FONT = 78
MIN_FONT = 38

PEXELS_KEY = os.getenv("PEXELS_API_KEY", "").strip()


# =========================
# FOLDERS
# =========================

DATA.mkdir(exist_ok=True)
OUTPUT.mkdir(exist_ok=True)
WORK.mkdir(exist_ok=True)


# =========================
# DATABASES
# =========================

DATABASES = {
    "bukhari": (
        DATA / "urd-bukhari.json",
        "Sahih al-Bukhari"
    ),
    "muslim": (
        DATA / "urd-muslim.json",
        "Sahih Muslim"
    ),
}


# =========================
# TEXT CLEAN
# =========================

def clean_text(text):

    text = str(text)

    text = unicodedata.normalize(
        "NFKC",
        text
    )

    # Replace special ﷺ character
    text = text.replace(
        "\ufdfa",
        "صلى الله عليه وسلم"
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

    text = re.sub(
        r"[\u0000-\u001F\u007F-\u009F]",
        "",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =========================
# USED HADITH
# =========================

def load_used():

    if not USED.exists():
        return set()

    try:

        data = json.loads(
            USED.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(data, dict):
            return set(data.keys())

        if isinstance(data, list):
            return set(
                str(x) for x in data
            )

    except Exception:
        pass

    return set()


def save_used(used):

    data = {
        x: True
        for x in sorted(used)
    }

    USED.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# =========================
# LOAD HADITH
# =========================

def load_database(path):

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    return data["hadiths"]


def get_number(item):

    for key in [
        "hadithnumber",
        "hadithNumber",
        "number",
        "id"
    ]:

        if item.get(key) is not None:

            return str(
                item[key]
            ).strip()

    return None


def get_text(item):

    for key in [
        "text",
        "hadith",
        "body",
        "hadithText"
    ]:

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


# =========================
# CHECK URDU
# =========================

def is_urdu(text):

    chars = re.findall(
        r"[\u0600-\u06FF]",
        text
    )

    return len(chars) >= 10


# =========================
# SELECT HADITH
# =========================

def select_hadith():

    used = load_used()

    candidates = []

    for collection, (file, name) in DATABASES.items():

        records = load_database(
            file
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

            text = get_text(
                item
            )

            if not number or not text:
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

                "collection": name,

                "number": number,

                "text": text
            })

    if not candidates:

        raise RuntimeError(
            "No unused Hadith available."
        )

    hadith = random.choice(
        candidates
    )

    print()
    print("SELECTED HADITH")
    print("-------------------------")
    print(
        hadith["collection"]
    )
    print(
        hadith["number"]
    )
    print(
        hadith["text"]
    )
    print("-------------------------")

    return hadith


# =========================
# FONT
# =========================

def get_font(size):

    if not FONT.exists():

        raise RuntimeError(
            "NotoNastaliqUrdu-Regular.ttf "
            "not found."
        )

    return ImageFont.truetype(
        str(FONT),
        size
    )


def get_ref_font(size):

    path = (
        "/usr/share/fonts/truetype/"
        "dejavu/DejaVuSans.ttf"
    )

    return ImageFont.truetype(
        path,
        size
    )


# =========================
# URDU WRAP
# =========================

def wrap_text(
    draw,
    text,
    font,
    width
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

        box = draw.textbbox(
            (0, 0),
            test,
            font=font,
            direction="rtl",
            language="ur"
        )

        text_width = (
            box[2] - box[0]
        )

        if text_width <= width:

            current = test

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


# =========================
# FIND BEST FONT SIZE
# =========================

def find_font_size(
    text
):

    test_image = Image.new(
        "RGB",
        (WIDTH, HEIGHT)
    )

    draw = ImageDraw.Draw(
        test_image
    )

    # Area available for Hadith
    max_width = 880
    max_height = 700

    for size in range(
        MAX_FONT,
        MIN_FONT - 1,
        -2
    ):

        font = get_font(
            size
        )

        lines = wrap_text(
            draw,
            text,
            font,
            max_width
        )

        heights = []

        for line in lines:

            box = draw.textbbox(
                (0, 0),
                line,
                font=font,
                direction="rtl",
                language="ur"
            )

            heights.append(
                box[3] - box[1]
            )

        total_height = (
            sum(heights)
            +
            20 *
            max(
                0,
                len(lines) - 1
            )
        )

        if total_height <= max_height:

            return size, lines

    # Very long Hadith.
    # Use smallest readable size.
    font = get_font(
        MIN_FONT
    )

    lines = wrap_text(
        draw,
        text,
        font,
        max_width
    )

    return MIN_FONT, lines


# =========================
# CREATE HADITH SCREEN
# =========================

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

    font_size, lines = find_font_size(
        hadith["text"]
    )

    font = get_font(
        font_size
    )

    heading_font = get_font(
        42
    )

    ref_font = get_ref_font(
        30
    )

    # Heading
    heading = (
        "نبی کریم ﷺ نے فرمایا:"
    )

    reference = (
        f'{hadith["collection"]} '
        f'{hadith["number"]}'
    )

    # Calculate Hadith height
    heights = []

    for line in lines:

        box = draw.textbbox(
            (0, 0),
            line,
            font=font,
            direction="rtl",
            language="ur"
        )

        heights.append(
            box[3] - box[1]
        )

    text_height = (
        sum(heights)
        +
        20 *
        max(
            0,
            len(lines) - 1
        )
    )

    heading_box = draw.textbbox(
        (0, 0),
        heading,
        font=heading_font,
        direction="rtl",
        language="ur"
    )

    heading_height = (
        heading_box[3]
        -
        heading_box[1]
    )

    ref_box = draw.textbbox(
        (0, 0),
        reference,
        font=ref_font
    )

    ref_height = (
        ref_box[3]
        -
        ref_box[1]
    )

    # Card
    card_width = 980

    card_height = (
        heading_height
        + 45
        + text_height
        + 55
        + 2
        + 30
        + ref_height
        + 45
    )

    # Keep card inside screen
    card_height = min(
        card_height,
        1050
    )

    card_x = (
        WIDTH -
        card_width
    ) // 2

    card_y = (
        HEIGHT -
        card_height
    ) // 2

    card_y -= 40

    # Card
    draw.rounded_rectangle(
        (
            card_x,
            card_y,
            card_x + card_width,
            card_y + card_height
        ),
        radius=45,
        fill=(
            0,
            0,
            0,
            220
        ),
        outline=(
            255,
            255,
            255,
            80
        ),
        width=2
    )

    center = WIDTH // 2

    # Heading
    heading_y = (
        card_y + 55
    )

    draw.text(
        (
            center,
            heading_y
        ),
        heading,
        font=heading_font,
        fill=(
            255,
            255,
            255,
            255
        ),
        anchor="ma",
        direction="rtl",
        language="ur"
    )

    # Hadith
    current_y = (
        card_y
        + 55
        + heading_height
        + 35
    )

    for i, line in enumerate(lines):

        line_height = heights[i]

        y = (
            current_y
            + line_height / 2
        )

        # Shadow
        draw.text(
            (
                center + 3,
                y + 4
            ),
            line,
            font=font,
            fill=(
                0,
                0,
                0,
                255
            ),
            anchor="mm",
            direction="rtl",
            language="ur"
        )

        # Text
        draw.text(
            (
                center,
                y
            ),
            line,
            font=font,
            fill=(
                255,
                255,
                255,
                255
            ),
            anchor="mm",
            direction="rtl",
            language="ur"
        )

        current_y += (
            line_height + 20
        )

    # Separator
    separator_y = (
        current_y + 10
    )

    draw.line(
        (
            card_x + 100,
            separator_y,
            card_x + card_width - 100,
            separator_y
        ),
        fill=(
            255,
            255,
            255,
            100
        ),
        width=2
    )

    # Reference
    reference_y = (
        separator_y + 25
    )

    draw.text(
        (
            center,
            reference_y
        ),
        reference,
        font=ref_font,
        fill=(
            255,
            255,
            255,
            255
        ),
        anchor="ma"
    )

    output = (
        WORK /
        "hadith_screen.png"
    )

    image.save(
        output,
        "PNG"
    )

    print(
        "Font size used:",
        font_size
    )

    print(
        "Hadith lines:",
        len(lines)
    )

    return output


# =========================
# PEXELS IMAGE
# =========================

def get_image():

    if not PEXELS_KEY:

        raise RuntimeError(
            "PEXELS_API_KEY is missing."
        )

    queries = [
        "mosque",
        "masjid",
        "Medina mosque",
        "Mecca mosque",
        "Kaaba",
        "Islamic architecture"
    ]

    random.shuffle(
        queries
    )

    for query in queries:

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
                "per_page": 10
            },
            timeout=60
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

            src = photo.get(
                "src",
                {}
            )

            url = (
                src.get("large2x")
                or src.get("large")
                or src.get("original")
            )

            if not url:
                continue

            try:

                r = requests.get(
                    url,
                    timeout=60
                )

                r.raise_for_status()

                file = (
                    WORK /
                    "background.jpg"
                )

                file.write_bytes(
                    r.content
                )

                Image.open(
                    file
                ).verify()

                return file

            except Exception:
                continue

    raise RuntimeError(
        "Could not download Pexels image."
    )


# =========================
# PREPARE BACKGROUND
# =========================

def prepare_background(
    source
):

    image = Image.open(
        source
    ).convert("RGB")

    ratio = (
        WIDTH /
        HEIGHT
    )

    source_ratio = (
        image.width /
        image.height
    )

    if source_ratio > ratio:

        new_height = HEIGHT

        new_width = int(
            HEIGHT *
            source_ratio
        )

    else:

        new_width = WIDTH

        new_height = int(
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

    # Darken background
    overlay = Image.new(
        "RGBA",
        image.size,
        (
            0,
            0,
            0,
            65
        )
    )

    image = Image.alpha_composite(
        image.convert("RGBA"),
        overlay
    )

    output = (
        WORK /
        "background.jpg"
    )

    image.convert(
        "RGB"
    ).save(
        output,
        quality=90
    )

    return output


# =========================
# CREATE VIDEO
# =========================

def create_video(
    background,
    screen,
    output
):

    print(
        "Creating video..."
    )

    filter_complex = (

        "[0:v]"
        "scale=1080:1920,"
        "trim=duration=75,"
        "setpts=PTS-STARTPTS"
        "[bg];"

        "[1:v]"
        "format=rgba,"
        "trim=duration=75,"
        "setpts=PTS-STARTPTS"
        "[card];"

        "[bg][card]"
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

        # Hadith screen
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
        "75",

        "-c:v",
        "libx264",

        # FAST
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


# =========================
# METADATA
# =========================

def create_metadata(
    hadith
):

    reference = (
        f'{hadith["collection"]} '
        f'{hadith["number"]}'
    )

    title = (
        "Islamic Hadith Reminder | "
        f"{reference}"
    )

    description = (
        "Islamic Hadith Reminder\n\n"
        f"Reference: {reference}\n\n"
        "May Allah guide us to follow "
        "the teachings of Islam. Ameen.\n\n"
        "#Hadith #Islam #Sunnah "
        "#Muslim #IslamicReminder"
    )

    files = {

        "youtube_title.txt":
            title,

        "youtube_description.txt":
            description,

        "tiktok_caption.txt":
            f"{reference}\n\n"
            "#Hadith #Islam #Sunnah #Muslim",

        "instagram_caption.txt":
            f"{reference}\n\n"
            "#Hadith #Islam #Sunnah #Muslim",

        "facebook_caption.txt":
            f"{reference}\n\n"
            "#Hadith #Islam #Sunnah"
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


# =========================
# MAIN
# =========================

def main():

    print(
        "Starting Islamic Hadith Video..."
    )

    if not features.check("raqm"):

        raise RuntimeError(
            "Pillow RAQM is not available."
        )

    if not PEXELS_KEY:

        raise RuntimeError(
            "PEXELS_API_KEY is missing."
        )

    if not AUDIO.exists():

        raise RuntimeError(
            "Background audio missing."
        )

    if not FONT.exists():

        raise RuntimeError(
            "Noto Nastaliq Urdu font missing."
        )

    # Clean work folder
    for item in WORK.iterdir():

        if item.is_dir():

            shutil.rmtree(
                item
            )

        else:

            item.unlink()

    # Select Hadith
    hadith = select_hadith()

    # Get image
    image = get_image()

    # Prepare image
    background = prepare_background(
        image
    )

    # Create Hadith screen
    screen = create_screen(
        hadith
    )

    # Output
    filename = (
        "islamic_hadith_"
        + str(int(time.time()))
        + ".mp4"
    )

    video = (
        OUTPUT /
        filename
    )

    # Create video
    create_video(
        background,
        screen,
        video
    )

    # Metadata
    create_metadata(
        hadith
    )

    # Save used Hadith
    used = load_used()

    used.add(
        hadith["key"]
    )

    save_used(
        used
    )

    print()
    print(
        "================================"
    )
    print(
        "SUCCESS"
    )
    print(
        "================================"
    )
    print(
        "Reference:",
        hadith["collection"],
        hadith["number"]
    )
    print(
        "Complete Hadith displayed once."
    )
    print(
        "Video:",
        video
    )


if __name__ == "__main__":
    main()
