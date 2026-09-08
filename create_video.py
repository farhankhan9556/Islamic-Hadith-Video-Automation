import json
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


# =========================================================
# PROJECT PATHS
# =========================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
WORK_DIR = ROOT / "work"

AUDIO_FILE = ROOT / "audio" / "islamic_background.mp3"
FONT_FILE = ROOT / "fonts" / "NotoNastaliqUrdu-Regular.ttf"
USED_FILE = ROOT / "used_hadith.json"


# =========================================================
# VIDEO SETTINGS
# =========================================================

WIDTH = 1080
HEIGHT = 1920
FPS = 30
DURATION = 75

# Urdu settings
URDU_FONT_SIZE = 72
MAX_URDU_LINES = 3
MAX_TEXT_WIDTH = 880

# Do not use extremely long Hadiths.
# This is only a selection filter.
# The Hadith itself is NEVER shortened.
MAX_HADITH_CHARACTERS = 260


# =========================================================
# ENVIRONMENT
# =========================================================

PEXELS_API_KEY = os.getenv(
    "PEXELS_API_KEY",
    ""
).strip()


# =========================================================
# CREATE DIRECTORIES
# =========================================================

DATA_DIR.mkdir(
    exist_ok=True
)

OUTPUT_DIR.mkdir(
    exist_ok=True
)

WORK_DIR.mkdir(
    exist_ok=True
)


# =========================================================
# HADITH DATABASES
# =========================================================

DATABASES = {
    "bukhari": {
        "file": DATA_DIR / "urd-bukhari.json",
        "name": "Sahih al-Bukhari",
    },

    "muslim": {
        "file": DATA_DIR / "urd-muslim.json",
        "name": "Sahih Muslim",
    },
}


# =========================================================
# PEXELS SEARCH TERMS
# =========================================================

PEXELS_QUERIES = [
    "mosque",
    "masjid",
    "Medina mosque",
    "mosque sunset",
    "Islamic architecture",
    "Kaaba",
    "beautiful mosque",
]


# =========================================================
# RUN COMMAND
# =========================================================

def run_command(command):

    print()
    print("=" * 70)
    print("RUNNING COMMAND")
    print("=" * 70)

    print(
        " ".join(
            str(x)
            for x in command
        )
    )

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:

        print()
        print("=" * 70)
        print("COMMAND ERROR")
        print("=" * 70)

        print(result.stderr)

        raise RuntimeError(
            "Command failed with exit code "
            f"{result.returncode}"
        )

    return result


# =========================================================
# CLEAN TEXT
# =========================================================

def clean_text(text):

    if not text:
        return ""

    text = str(text)

    # Unicode normalization
    text = unicodedata.normalize(
        "NFKC",
        text
    )

    # Replace ﷺ ligature with normal Arabic text.
    # This avoids missing-glyph squares.
    text = text.replace(
        "\ufdfa",
        "صلى الله عليه وسلم"
    )

    # Remove BOM and zero-width space.
    text = text.replace(
        "\ufeff",
        ""
    )

    text = text.replace(
        "\u200b",
        ""
    )

    # IMPORTANT:
    # Keep ZWNJ / ZWJ.
    # Urdu shaping can require them.

    text = text.replace(
        "\r",
        " "
    )

    text = text.replace(
        "\n",
        " "
    )

    # Remove unwanted control characters.
    text = re.sub(
        r"[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]",
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


# =========================================================
# USED HADITH
# =========================================================

def load_used():

    if not USED_FILE.exists():
        return set()

    try:

        data = json.loads(
            USED_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(
            data,
            dict
        ):

            return set(
                str(x)
                for x in data.keys()
            )

        if isinstance(
            data,
            list
        ):

            return set(
                str(x)
                for x in data
            )

    except Exception as error:

        print(
            "Warning: Could not read used_hadith.json:",
            error
        )

    return set()


def save_used(used):

    data = {
        key: True
        for key in sorted(used)
    }

    USED_FILE.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# =========================================================
# LOAD HADITH DATABASE
# =========================================================

def load_hadith_file(path):

    if not path.exists():

        raise RuntimeError(
            f"Hadith database missing:\n{path}"
        )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    if not isinstance(
        data,
        dict
    ):

        raise RuntimeError(
            f"Invalid Hadith database:\n{path}"
        )

    hadiths = data.get(
        "hadiths"
    )

    if not isinstance(
        hadiths,
        list
    ):

        raise RuntimeError(
            f"'hadiths' list not found:\n{path}"
        )

    print(
        f"{path.name}: {len(hadiths)} records"
    )

    return hadiths


# =========================================================
# GET HADITH NUMBER
# =========================================================

def get_number(item):

    possible_keys = [
        "hadithnumber",
        "hadithNumber",
        "number",
        "id",
    ]

    for key in possible_keys:

        value = item.get(key)

        if value is not None:

            value = str(
                value
            ).strip()

            if value:
                return value

    return None


# =========================================================
# GET HADITH TEXT
# =========================================================

def get_text(item):

    possible_keys = [
        "text",
        "hadith",
        "body",
        "hadithText",
    ]

    for key in possible_keys:

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


# =========================================================
# CHECK URDU / ARABIC SCRIPT
# =========================================================

def is_urdu(text):

    if not text:
        return False

    arabic_block = re.findall(
        r"[\u0600-\u06FF]",
        text
    )

    return len(
        arabic_block
    ) >= 10


# =========================================================
# RAQM CHECK
# =========================================================

def raqm_available():

    try:

        return features.check(
            "raqm"
        )

    except Exception:

        return False


# =========================================================
# FONT
# =========================================================

def get_urdu_font(size):

    if not FONT_FILE.exists():

        raise RuntimeError(
            "Noto Nastaliq Urdu font not found:\n"
            f"{FONT_FILE}"
        )

    return ImageFont.truetype(
        str(FONT_FILE),
        size
    )


def get_english_font(size):

    font_paths = [

        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",

        "/usr/share/fonts/truetype/liberation2/"
        "LiberationSans-Regular.ttf",
    ]

    for path in font_paths:

        if Path(path).exists():

            return ImageFont.truetype(
                path,
                size
            )

    raise RuntimeError(
        "English reference font was not found."
    )


# =========================================================
# URDU TEXT WIDTH
# =========================================================

def get_urdu_width(
    draw,
    text,
    font
):

    box = draw.textbbox(
        (0, 0),
        text,
        font=font,
        direction="rtl",
        language="ur"
    )

    return (
        box[2] -
        box[0]
    )


# =========================================================
# URDU TEXT HEIGHT
# =========================================================

def get_urdu_height(
    draw,
    text,
    font
):

    box = draw.textbbox(
        (0, 0),
        text,
        font=font,
        direction="rtl",
        language="ur"
    )

    return (
        box[3] -
        box[1]
    )


# =========================================================
# DRAW URDU
# =========================================================

def draw_urdu(
    draw,
    position,
    text,
    font,
    fill,
    anchor="mm"
):

    draw.text(
        position,
        text,
        font=font,
        fill=fill,
        anchor=anchor,
        direction="rtl",
        language="ur"
    )


# =========================================================
# WRAP URDU
# =========================================================

def wrap_urdu(
    text,
    font,
    max_width
):

    text = clean_text(
        text
    )

    words = text.split()

    dummy = Image.new(
        "RGB",
        (10, 10)
    )

    draw = ImageDraw.Draw(
        dummy
    )

    lines = []

    current = ""

    for word in words:

        if not current:

            candidate = word

        else:

            candidate = (
                current
                + " "
                + word
            )

        width = get_urdu_width(
            draw,
            candidate,
            font
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


# =========================================================
# CHECK WHETHER HADITH FITS ONE SCREEN
# =========================================================

def hadith_fits_one_screen(text):

    font = get_urdu_font(
        URDU_FONT_SIZE
    )

    lines = wrap_urdu(
        text,
        font,
        MAX_TEXT_WIDTH
    )

    if len(lines) > MAX_URDU_LINES:

        return False

    if len(text) > MAX_HADITH_CHARACTERS:

        return False

    return True


# =========================================================
# SELECT SHORT HADITH
# =========================================================

def select_hadith():

    used = load_used()

    candidates = []

    print()
    print("=" * 70)
    print("SEARCHING FOR SHORT UNUSED HADITH")
    print("=" * 70)

    for collection, config in DATABASES.items():

        records = load_hadith_file(
            config["file"]
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

            if not number:
                continue

            if not text:
                continue

            if not is_urdu(
                text
            ):
                continue

            key = (
                f"{collection}:{number}"
            )

            if key in used:
                continue

            # Only short Hadiths.
            if not hadith_fits_one_screen(
                text
            ):
                continue

            candidates.append({

                "key": key,

                "collection": collection,

                "collection_name":
                    config["name"],

                "number": number,

                "text": text,
            })

    if not candidates:

        raise RuntimeError(
            "No unused short Hadith remains.\n"
            "The program will NOT cut or modify a long Hadith.\n"
            "If you want to start again, clear used_hadith.json."
        )

    selected = random.choice(
        candidates
    )

    print()
    print("=" * 70)
    print("SELECTED HADITH")
    print("=" * 70)

    print(
        "Collection:",
        selected[
            "collection_name"
        ]
    )

    print(
        "Number:",
        selected[
            "number"
        ]
    )

    print(
        "Characters:",
        len(
            selected["text"]
        )
    )

    print(
        "Text:",
        selected["text"]
    )

    print("=" * 70)

    return selected


# =========================================================
# PEXELS SEARCH
# =========================================================

def search_pexels(query):

    if not PEXELS_API_KEY:

        raise RuntimeError(
            "PEXELS_API_KEY is missing."
        )

    response = requests.get(
        "https://api.pexels.com/v1/search",

        headers={
            "Authorization":
                PEXELS_API_KEY
        },

        params={
            "query": query,
            "orientation": "portrait",
            "size": "large",
            "per_page": 15,
        },

        timeout=60,
    )

    response.raise_for_status()

    data = response.json()

    return data.get(
        "photos",
        []
    )


# =========================================================
# DOWNLOAD IMAGE
# =========================================================

def download_file(
    url,
    destination
):

    for attempt in range(3):

        try:

            response = requests.get(
                url,
                timeout=90,
                headers={
                    "User-Agent":
                        "Mozilla/5.0"
                }
            )

            response.raise_for_status()

            destination.write_bytes(
                response.content
            )

            if destination.stat().st_size < 10000:

                raise RuntimeError(
                    "Downloaded image is too small."
                )

            with Image.open(
                destination
            ) as image:

                image.verify()

            return destination

        except Exception as error:

            print(
                f"Image download attempt {attempt + 1} failed:",
                error
            )

            time.sleep(2)

    return None


# =========================================================
# GET BACKGROUND IMAGE
# =========================================================

def get_background_image():

    queries = list(
        PEXELS_QUERIES
    )

    random.shuffle(
        queries
    )

    destination = (
        WORK_DIR /
        "pexels_background.jpg"
    )

    for query in queries:

        print(
            "Pexels search:",
            query
        )

        try:

            photos = search_pexels(
                query
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
                    source.get(
                        "large2x"
                    )
                    or source.get(
                        "large"
                    )
                    or source.get(
                        "original"
                    )
                )

                if not url:
                    continue

                result = download_file(
                    url,
                    destination
                )

                if result:

                    print(
                        "Background image downloaded."
                    )

                    return result

        except Exception as error:

            print(
                "Pexels error:",
                error
            )

    raise RuntimeError(
        "Could not download a Pexels Islamic image."
    )


# =========================================================
# PREPARE BACKGROUND
# =========================================================

def prepare_background(
    image_file
):

    image = Image.open(
        image_file
    ).convert("RGB")

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

    # Slight darkening for readable text.
    dark_overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 70)
    )

    image = Image.alpha_composite(
        image.convert("RGBA"),
        dark_overlay
    )

    output = (
        WORK_DIR /
        "background.jpg"
    )

    image.convert(
        "RGB"
    ).save(
        output,
        quality=95
    )

    return output


# =========================================================
# CREATE SINGLE HADITH SCREEN
# =========================================================

def create_hadith_screen(
    hadith,
    destination
):

    canvas = Image.new(
        "RGBA",
        (
            WIDTH,
            HEIGHT
        ),
        (0, 0, 0, 0)
    )

    draw = ImageDraw.Draw(
        canvas
    )

    urdu_font = get_urdu_font(
        URDU_FONT_SIZE
    )

    reference_font = get_english_font(
        34
    )

    text = clean_text(
        hadith["text"]
    )

    reference = (
        f'{hadith["collection_name"]} '
        f'{hadith["number"]}'
    )

    lines = wrap_urdu(
        text,
        urdu_font,
        MAX_TEXT_WIDTH
    )

    # Safety check.
    if len(lines) > MAX_URDU_LINES:

        raise RuntimeError(
            "Selected Hadith does not fit "
            "within the maximum 3 lines."
        )

    # -----------------------------------------------------
    # CALCULATE TEXT SIZE
    # -----------------------------------------------------

    line_heights = []

    for line in lines:

        line_heights.append(
            get_urdu_height(
                draw,
                line,
                urdu_font
            )
        )

    line_gap = 28

    total_text_height = (
        sum(line_heights)
        +
        line_gap *
        (
            len(lines) - 1
        )
    )

    reference_box = draw.textbbox(
        (0, 0),
        reference,
        font=reference_font
    )

    reference_height = (
        reference_box[3]
        -
        reference_box[1]
    )

    # -----------------------------------------------------
    # CARD SIZE
    # -----------------------------------------------------

    card_width = 980

    card_height = (
        total_text_height
        + 100
        + reference_height
        + 85
    )

    card_x = (
        WIDTH -
        card_width
    ) // 2

    card_y = (
        HEIGHT -
        card_height
    ) // 2

    # Slightly above center.
    card_y -= 60

    # -----------------------------------------------------
    # CARD
    # -----------------------------------------------------

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
            215
        ),

        outline=(
            255,
            255,
            255,
            80
        ),

        width=2
    )

    # -----------------------------------------------------
    # URDU TEXT
    # -----------------------------------------------------

    center_x = (
        WIDTH // 2
    )

    current_y = (
        card_y + 55
    )

    for index, line in enumerate(
        lines
    ):

        line_height = (
            line_heights[index]
        )

        text_y = (
            current_y
            +
            line_height // 2
        )

        # Shadow
        draw_urdu(
            draw,

            (
                center_x + 4,
                text_y + 5
            ),

            line,

            urdu_font,

            (
                0,
                0,
                0,
                255
            ),

            anchor="mm"
        )

        # Main white text
        draw_urdu(
            draw,

            (
                center_x,
                text_y
            ),

            line,

            urdu_font,

            (
                255,
                255,
                255,
                255
            ),

            anchor="mm"
        )

        current_y += (
            line_height
            +
            line_gap
        )

    # -----------------------------------------------------
    # SEPARATOR
    # -----------------------------------------------------

    separator_y = (
        current_y + 8
    )

    draw.line(
        (
            card_x + 100,
            separator_y,

            card_x +
            card_width -
            100,

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

    # -----------------------------------------------------
    # REFERENCE
    # -----------------------------------------------------

    reference_y = (
        separator_y + 35
    )

    reference_box = draw.textbbox(
        (0, 0),
        reference,
        font=reference_font
    )

    reference_width = (
        reference_box[2]
        -
        reference_box[0]
    )

    reference_x = (
        center_x
        -
        reference_width // 2
    )

    # Reference shadow
    draw.text(
        (
            reference_x + 2,
            reference_y + 3
        ),

        reference,

        font=reference_font,

        fill=(
            0,
            0,
            0,
            255
        )
    )

    # Reference
    draw.text(
        (
            reference_x,
            reference_y
        ),

        reference,

        font=reference_font,

        fill=(
            255,
            255,
            255,
            255
        )
    )

    canvas.save(
        destination,
        "PNG"
    )

    print(
        "Hadith screen created:",
        destination
    )

    print(
        "Lines:",
        len(lines)
    )


# =========================================================
# CREATE VIDEO
# =========================================================

def create_video(
    background,
    hadith_screen,
    output_file
):

    # One Hadith screen for the ENTIRE video.
    #
    # No page changes.
    # No scrolling.
    # No second screen.
    # The complete Hadith stays visible.

    command = [

        "ffmpeg",

        "-y",

        "-hide_banner",

        # -------------------------------------------------
        # BACKGROUND IMAGE
        # -------------------------------------------------

        "-loop",
        "1",

        "-i",
        str(background),

        # -------------------------------------------------
        # HADITH SCREEN
        # -------------------------------------------------

        "-loop",
        "1",

        "-i",
        str(hadith_screen),

        # -------------------------------------------------
        # AUDIO
        # -------------------------------------------------

        "-stream_loop",
        "-1",

        "-i",
        str(AUDIO_FILE),

        # -------------------------------------------------
        # FILTER
        # -------------------------------------------------

        "-filter_complex",

        (
            "[0:v]"
            "scale=1080:1920:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "zoompan="
            "z='min(zoom+0.00025,1.08)':"
            "d=1:"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            "s=1080x1920:"
            "fps=30,"
            "trim=duration=75,"
            "setpts=PTS-STARTPTS"
            "[bg];"

            "[1:v]"
            "scale=1080:1920:"
            "force_original_aspect_ratio=disable,"
            "format=rgba,"
            "trim=duration=75,"
            "setpts=PTS-STARTPTS"
            "[text];"

            "[bg][text]"
            "overlay=0:0:"
            "shortest=1"
            "[video];"

            "[2:a]"
            "atrim=duration=75,"
            "asetpts=PTS-STARTPTS"
            "[audio]"
        ),

        # -------------------------------------------------
        # OUTPUT
        # -------------------------------------------------

        "-map",
        "[video]",

        "-map",
        "[audio]",

        "-t",
        "75",

        "-c:v",
        "libx264",

        "-preset",
        "medium",

        "-crf",
        "20",

        "-pix_fmt",
        "yuv420p",

        "-c:a",
        "aac",

        "-b:a",
        "192k",

        "-ar",
        "44100",

        "-movflags",
        "+faststart",

        str(output_file)
    ]

    run_command(
        command
    )

    print()
    print("=" * 70)
    print("VIDEO CREATED SUCCESSFULLY")
    print("=" * 70)

    print(
        output_file
    )


# =========================================================
# CREATE SOCIAL MEDIA METADATA
# =========================================================

def create_metadata(
    hadith
):

    reference = (
        f'{hadith["collection_name"]} '
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
        "#Muslim #IslamicReminder "
        "#IslamicShorts"
    )

    tiktok = (
        f"{reference}\n\n"
        "#Hadith #Islam #Sunnah "
        "#Muslim #IslamicReminder"
    )

    instagram = (
        f"{reference}\n\n"
        "Islamic reminder.\n\n"
        "#Hadith #Islam #Sunnah "
        "#Muslim #IslamicReels"
    )

    facebook = (
        f"{reference}\n\n"
        "Islamic Hadith Reminder.\n\n"
        "#Hadith #Islam #Sunnah"
    )

    (
        OUTPUT_DIR /
        "youtube_title.txt"
    ).write_text(
        title,
        encoding="utf-8"
    )

    (
        OUTPUT_DIR /
        "youtube_description.txt"
    ).write_text(
        description,
        encoding="utf-8"
    )

    (
        OUTPUT_DIR /
        "tiktok_caption.txt"
    ).write_text(
        tiktok,
        encoding="utf-8"
    )

    (
        OUTPUT_DIR /
        "instagram_caption.txt"
    ).write_text(
        instagram,
        encoding="utf-8"
    )

    (
        OUTPUT_DIR /
        "facebook_caption.txt"
    ).write_text(
        facebook,
        encoding="utf-8"
    )

    metadata = {

        "title": title,

        "description": description,

        "reference": reference,

        "collection":
            hadith[
                "collection_name"
            ],

        "hadith_number":
            hadith[
                "number"
            ],

        "hadith_text":
            hadith[
                "text"
            ],
    }

    (
        OUTPUT_DIR /
        "metadata.json"
    ).write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# =========================================================
# MAIN
# =========================================================

def main():

    print()
    print("=" * 70)
    print("ISLAMIC HADITH VIDEO GENERATOR")
    print("=" * 70)

    # -----------------------------------------------------
    # CHECK RAQM
    # -----------------------------------------------------

    print(
        "Pillow RAQM available:",
        raqm_available()
    )

    if not raqm_available():

        raise RuntimeError(
            "Pillow RAQM is NOT available.\n"
            "Make sure the GitHub workflow installs:\n"
            "libraqm-dev\n"
            "libfribidi-dev\n"
            "libharfbuzz-dev"
        )

    # -----------------------------------------------------
    # CHECK PEXELS
    # -----------------------------------------------------

    if not PEXELS_API_KEY:

        raise RuntimeError(
            "PEXELS_API_KEY is not configured."
        )

    # -----------------------------------------------------
    # CHECK AUDIO
    # -----------------------------------------------------

    if not AUDIO_FILE.exists():

        raise RuntimeError(
            "Background audio not found:\n"
            f"{AUDIO_FILE}"
        )

    # -----------------------------------------------------
    # CHECK FONT
    # -----------------------------------------------------

    if not FONT_FILE.exists():

        raise RuntimeError(
            "Noto Nastaliq Urdu font not found:\n"
            f"{FONT_FILE}"
        )

    # -----------------------------------------------------
    # CLEAN WORK DIRECTORY
    # -----------------------------------------------------

    if WORK_DIR.exists():

        for item in WORK_DIR.iterdir():

            if item.is_dir():

                shutil.rmtree(
                    item
                )

            else:

                item.unlink()

    WORK_DIR.mkdir(
        exist_ok=True
    )

    # -----------------------------------------------------
    # SELECT SHORT HADITH
    # -----------------------------------------------------

    hadith = select_hadith()

    # -----------------------------------------------------
    # DOWNLOAD PEXELS IMAGE
    # -----------------------------------------------------

    original_image = (
        get_background_image()
    )

    background = (
        prepare_background(
            original_image
        )
    )

    # -----------------------------------------------------
    # CREATE ONE HADITH SCREEN
    # -----------------------------------------------------

    hadith_screen = (
        WORK_DIR /
        "hadith_screen.png"
    )

    create_hadith_screen(
        hadith,
        hadith_screen
    )

    # -----------------------------------------------------
    # OUTPUT VIDEO
    # -----------------------------------------------------

    timestamp = int(
        time.time()
    )

    output_video = (
        OUTPUT_DIR /
        f"islamic_hadith_{timestamp}.mp4"
    )

    # -----------------------------------------------------
    # CREATE VIDEO
    # -----------------------------------------------------

    create_video(
        background,
        hadith_screen,
        output_video
    )

    # -----------------------------------------------------
    # METADATA
    # -----------------------------------------------------

    create_metadata(
        hadith
    )

    # -----------------------------------------------------
    # SAVE USED HADITH
    # -----------------------------------------------------

    used = load_used()

    used.add(
        hadith["key"]
    )

    save_used(
        used
    )

    # -----------------------------------------------------
    # SUCCESS
    # -----------------------------------------------------

    print()
    print("=" * 70)
    print("SUCCESS")
    print("=" * 70)

    print(
        "Video:",
        output_video
    )

    print(
        "Reference:",
        hadith["collection_name"],
        hadith["number"]
    )

    print(
        "Hadith lines: maximum",
        MAX_URDU_LINES
    )

    print(
        "Complete Hadith displayed once."
    )

    print("=" * 70)


# =========================================================
# START
# =========================================================

if __name__ == "__main__":
    main()
    
