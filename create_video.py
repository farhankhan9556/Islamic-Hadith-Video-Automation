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
from PIL import Image, ImageDraw, ImageFont


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
WORK_DIR = ROOT / "work"

AUDIO_FILE = ROOT / "audio" / "islamic_background.mp3"
FONT_FILE = ROOT / "fonts" / "NotoNaskhArabic-Regular.ttf"
USED_FILE = ROOT / "used_hadith.json"

WIDTH = 1080
HEIGHT = 1920
FPS = 30
DURATION = 75

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()

DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
WORK_DIR.mkdir(exist_ok=True)


# ============================================================
# HADITH DATABASES
# ============================================================

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


# ============================================================
# PEXELS SEARCH TERMS
# ============================================================

PEXELS_QUERIES = [
    "mosque",
    "masjid",
    "medina mosque",
    "mosque sunset",
    "islamic architecture",
    "kaaba",
    "quran",
    "beautiful mosque",
]


# ============================================================
# COMMAND HELPER
# ============================================================

def run_command(command):
    print("\nRUNNING:")
    print(" ".join(str(x) for x in command))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError(
            f"FFmpeg command failed: {result.returncode}"
        )

    return result


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = str(text)

    # Remove line breaks.
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")

    # Remove zero-width/control characters.
    text = re.sub(
        r"[\u0000-\u001F\u007F-\u009F]",
        "",
        text,
    )

    # Remove common problematic invisible Unicode marks.
    text = text.replace("\u200b", "")
    text = text.replace("\u200c", "")
    text = text.replace("\u200d", "")
    text = text.replace("\ufeff", "")

    # Normalize spaces.
    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# USED HADITH
# ============================================================

def load_used():
    if not USED_FILE.exists():
        return set()

    try:
        data = json.loads(
            USED_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(data, dict):
            return set(
                str(x)
                for x in data.keys()
            )

        if isinstance(data, list):
            return set(
                str(x)
                for x in data
            )

    except Exception as exc:
        print(
            "Warning: could not read used_hadith.json:",
            exc,
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
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# LOAD HADITH DATABASE
# ============================================================

def load_hadith_file(path):

    if not path.exists():
        raise RuntimeError(
            f"Missing Hadith database: {path}"
        )

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Invalid Hadith database format: {path}"
        )

    hadiths = data.get("hadiths")

    if not isinstance(hadiths, list):
        raise RuntimeError(
            f"'hadiths' list not found in {path}"
        )

    print(
        f"{path.name}: {len(hadiths)} records"
    )

    return hadiths


# ============================================================
# GET HADITH NUMBER
# ============================================================

def get_number(item):

    for key in [
        "hadithnumber",
        "hadithNumber",
        "number",
        "id",
    ]:

        value = item.get(key)

        if value is not None:

            value = str(value).strip()

            if value:
                return value

    return None


# ============================================================
# GET HADITH TEXT
# ============================================================

def get_text(item):

    for key in [
        "text",
        "hadith",
        "body",
        "hadithText",
    ]:

        value = item.get(key)

        if isinstance(value, str):

            value = clean_text(value)

            if value:
                return value

    return None


# ============================================================
# CHECK URDU
# ============================================================

def is_urdu(text):

    if not text:
        return False

    arabic_chars = re.findall(
        r"[\u0600-\u06FF]",
        text,
    )

    return len(arabic_chars) >= 10


# ============================================================
# SELECT HADITH
# ============================================================

def select_hadith():

    used = load_used()

    candidates = []

    for collection, config in DATABASES.items():

        records = load_hadith_file(
            config["file"]
        )

        for item in records:

            if not isinstance(item, dict):
                continue

            number = get_number(item)
            text = get_text(item)

            if not number:
                continue

            if not text:
                continue

            if not is_urdu(text):
                continue

            key = (
                f"{collection}:{number}"
            )

            if key in used:
                continue

            candidates.append(
                {
                    "key": key,
                    "collection": collection,
                    "collection_name":
                        config["name"],
                    "number": number,
                    "text": text,
                }
            )

    if not candidates:

        print(
            "No unused Hadith remains."
        )

        print(
            "Resetting used_hadith.json."
        )

        save_used(set())

        return select_hadith()

    selected = random.choice(
        candidates
    )

    print()
    print("=" * 70)
    print("SELECTED HADITH")
    print("=" * 70)

    print(
        "Collection:",
        selected["collection_name"],
    )

    print(
        "Number:",
        selected["number"],
    )

    print(
        "Text:",
        selected["text"],
    )

    print("=" * 70)

    return selected


# ============================================================
# PEXELS
# ============================================================

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

    return response.json().get(
        "photos",
        []
    )


def download_file(
    url,
    destination,
):

    for attempt in range(3):

        try:

            response = requests.get(
                url,
                timeout=90,
                headers={
                    "User-Agent":
                        "Mozilla/5.0"
                },
            )

            response.raise_for_status()

            destination.write_bytes(
                response.content
            )

            if destination.stat().st_size < 10000:
                raise RuntimeError(
                    "Image is too small."
                )

            Image.open(
                destination
            ).verify()

            return destination

        except Exception as exc:

            print(
                "Image download failed:",
                exc,
            )

            time.sleep(2)

    return None


def get_background_image():

    queries = list(
        PEXELS_QUERIES
    )

    random.shuffle(queries)

    destination = (
        WORK_DIR /
        "pexels_background.jpg"
    )

    for query in queries:

        print(
            "Pexels search:",
            query,
        )

        try:

            photos = search_pexels(
                query
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

                result = download_file(
                    url,
                    destination,
                )

                if result:
                    print(
                        "Background image ready."
                    )

                    return result

        except Exception as exc:

            print(
                "Pexels error:",
                exc,
            )

    raise RuntimeError(
        "Could not obtain a Pexels image."
    )


# ============================================================
# PREPARE BACKGROUND
# ============================================================

def prepare_background(
    image_file
):

    image = Image.open(
        image_file
    ).convert("RGB")

    target_ratio = (
        WIDTH / HEIGHT
    )

    source_ratio = (
        image.width /
        image.height
    )

    if source_ratio > target_ratio:

        new_height = HEIGHT

        new_width = int(
            HEIGHT * source_ratio
        )

    else:

        new_width = WIDTH

        new_height = int(
            WIDTH / source_ratio
        )

    image = image.resize(
        (
            new_width,
            new_height,
        ),
        Image.Resampling.LANCZOS,
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
            top + HEIGHT,
        )
    )

    # Darken background slightly.
    dark = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 65),
    )

    image = Image.alpha_composite(
        image.convert("RGBA"),
        dark,
    )

    output = (
        WORK_DIR /
        "background.jpg"
    )

    image.convert(
        "RGB"
    ).save(
        output,
        quality=95,
    )

    return output


# ============================================================
# FONT
# ============================================================

def get_urdu_font(size):

    if not FONT_FILE.exists():
        raise RuntimeError(
            f"Font not found: {FONT_FILE}"
        )

    return ImageFont.truetype(
        str(FONT_FILE),
        size,
    )


def get_english_font(size):

    system_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]

    for path in system_fonts:

        if Path(path).exists():

            return ImageFont.truetype(
                path,
                size,
            )

    return ImageFont.truetype(
        str(FONT_FILE),
        size,
    )


# ============================================================
# URDU SHAPING
# ============================================================

def shape_urdu(text):

    text = clean_text(text)

    reshaped = (
        arabic_reshaper.reshape(
            text
        )
    )

    return get_display(
        reshaped
    )


# ============================================================
# WIDTH
# ============================================================

def get_text_width(
    draw,
    text,
    font,
):

    box = draw.textbbox(
        (0, 0),
        text,
        font=font,
    )

    return (
        box[2] - box[0]
    )


# ============================================================
# WRAP URDU
# ============================================================

def wrap_urdu(
    text,
    font,
    max_width,
):

    words = clean_text(
        text
    ).split()

    dummy = Image.new(
        "RGB",
        (10, 10),
    )

    draw = ImageDraw.Draw(
        dummy
    )

    lines = []
    current = ""

    for word in words:

        candidate = (
            word
            if not current
            else current + " " + word
        )

        shaped = shape_urdu(
            candidate
        )

        width = get_text_width(
            draw,
            shaped,
            font,
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
# SPLIT INTO PAGES
# ============================================================

def make_pages(text):

    # Larger font than previous version.
    font = get_urdu_font(64)

    lines = wrap_urdu(
        text,
        font,
        850,
    )

    # Only 4 lines per page.
    # This keeps the text large.
    lines_per_page = 4

    pages = []

    for i in range(
        0,
        len(lines),
        lines_per_page,
    ):

        pages.append(
            lines[
                i:i + lines_per_page
            ]
        )

    return pages


# ============================================================
# CREATE SINGLE TEXT PNG
# ============================================================

def create_text_page(
    lines,
    reference,
    destination,
):

    canvas = Image.new(
        "RGBA",
        (
            WIDTH,
            HEIGHT,
        ),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(
        canvas
    )

    # --------------------------------------------------------
    # Fonts
    # --------------------------------------------------------

    urdu_font = get_urdu_font(
        64
    )

    reference_font = get_english_font(
        32
    )

    # --------------------------------------------------------
    # Shape lines
    # --------------------------------------------------------

    shaped_lines = [
        shape_urdu(line)
        for line in lines
    ]

    # --------------------------------------------------------
    # Measurements
    # --------------------------------------------------------

    line_gap = 22

    heights = []

    for line in shaped_lines:

        box = draw.textbbox(
            (0, 0),
            line,
            font=urdu_font,
        )

        heights.append(
            box[3] - box[1]
        )

    text_height = (
        sum(heights)
        +
        line_gap *
        max(
            0,
            len(heights) - 1,
        )
    )

    ref_box = draw.textbbox(
        (0, 0),
        reference,
        font=reference_font,
    )

    ref_height = (
        ref_box[3] -
        ref_box[1]
    )

    # --------------------------------------------------------
    # Card dimensions
    # --------------------------------------------------------

    card_width = 960

    card_height = (
        text_height
        + 80
        + ref_height
        + 60
    )

    card_x = (
        WIDTH -
        card_width
    ) // 2

    # Center the card vertically.
    card_y = (
        HEIGHT -
        card_height
    ) // 2

    # Slightly move upward.
    card_y -= 50

    # --------------------------------------------------------
    # Card
    # --------------------------------------------------------

    draw.rounded_rectangle(
        (
            card_x,
            card_y,
            card_x + card_width,
            card_y + card_height,
        ),
        radius=42,
        fill=(
            0,
            0,
            0,
            205,
        ),
        outline=(
            255,
            255,
            255,
            70,
        ),
        width=2,
    )

    # --------------------------------------------------------
    # Urdu
    # --------------------------------------------------------

    y = (
        card_y + 45
    )

    center = WIDTH // 2

    for index, line in enumerate(
        shaped_lines
    ):

        box = draw.textbbox(
            (0, 0),
            line,
            font=urdu_font,
        )

        line_width = (
            box[2] -
            box[0]
        )

        x = (
            center -
            line_width // 2
        )

        # Strong black shadow.
        draw.text(
            (
                x + 4,
                y + 5,
            ),
            line,
            font=urdu_font,
            fill=(
                0,
                0,
                0,
                255,
            ),
        )

        # White text.
        draw.text(
            (
                x,
                y,
            ),
            line,
            font=urdu_font,
            fill=(
                255,
                255,
                255,
                255,
            ),
        )

        y += (
            heights[index]
            + line_gap
        )

    # --------------------------------------------------------
    # Separator
    # --------------------------------------------------------

    separator_y = (
        y + 12
    )

    draw.line(
        (
            card_x + 100,
            separator_y,
            card_x + card_width - 100,
            separator_y,
        ),
        fill=(
            255,
            255,
            255,
            90,
        ),
        width=2,
    )

    # --------------------------------------------------------
    # Reference
    # --------------------------------------------------------

    reference_y = (
        separator_y + 30
    )

    ref_box = draw.textbbox(
        (0, 0),
        reference,
        font=reference_font,
    )

    ref_width = (
        ref_box[2] -
        ref_box[0]
    )

    ref_x = (
        center -
        ref_width // 2
    )

    draw.text(
        (
            ref_x + 2,
            reference_y + 3,
        ),
        reference,
        font=reference_font,
        fill=(
            0,
            0,
            0,
            255,
        ),
    )

    draw.text(
        (
            ref_x,
            reference_y,
        ),
        reference,
        font=reference_font,
        fill=(
            255,
            255,
            255,
            255,
        ),
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    canvas.save(
        destination,
        "PNG",
    )

    print(
        "Created:",
        destination,
    )


# ============================================================
# CREATE TEXT PAGES
# ============================================================

def create_pages(hadith):

    page_dir = (
        WORK_DIR /
        "pages"
    )

    page_dir.mkdir(
        exist_ok=True
    )

    pages = make_pages(
        hadith["text"]
    )

    reference = (
        f'{hadith["collection_name"]} '
        f'{hadith["number"]}'
    )

    result = []

    for index, page in enumerate(
        pages
    ):

        file = (
            page_dir /
            f"page_{index:03d}.png"
        )

        create_text_page(
            page,
            reference,
            file,
        )

        result.append(file)

    print(
        "Total text pages:",
        len(result),
    )

    return result


# ============================================================
# CREATE VIDEO
# ============================================================

def create_video(
    background,
    pages,
    output_file,
):

    if not pages:
        raise RuntimeError(
            "No text pages."
        )

    # Duration per page.
    page_duration = (
        DURATION /
        len(pages)
    )

    inputs = []

    # Background image.
    inputs.extend(
        [
            "-loop",
            "1",
            "-i",
            str(background),
        ]
    )

    # Text pages.
    for page in pages:

        inputs.extend(
            [
                "-loop",
                "1",
                "-i",
                str(page),
            ]
        )

    # Background audio.
    inputs.extend(
        [
            "-stream_loop",
            "-1",
            "-i",
            str(AUDIO_FILE),
        ]
    )

    filters = []

    # --------------------------------------------------------
    # Background
    # --------------------------------------------------------

    filters.append(
        "[0:v]"
        "scale=1080:1920:"
        "force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "zoompan="
        "z='min(zoom+0.00025,1.08)':"
        "d=2250:"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        "s=1080x1920:"
        "fps=30,"
        "trim=duration=75,"
        "setpts=PTS-STARTPTS"
        "[background]"
    )

    # --------------------------------------------------------
    # Text pages
    # --------------------------------------------------------

    for index, page in enumerate(
        pages
    ):

        input_index = index + 1

        filters.append(
            f"[{input_index}:v]"
            f"format=rgba,"
            f"trim=duration={page_duration:.4f},"
            f"setpts=PTS-STARTPTS"
            f"[page{index}]"
        )

    # --------------------------------------------------------
    # Overlay pages sequentially
    # --------------------------------------------------------

    current = "[background]"

    for index in range(
        len(pages)
    ):

        output_label = (
            f"[video{index}]"
        )

        filters.append(
            f"{current}"
            f"[page{index}]"
            f"overlay=0:0:"
            f"enable='between(t,"
            f"{index * page_duration:.4f},"
            f"{(index + 1) * page_duration:.4f})'"
            f"{output_label}"
        )

        current = output_label

    # --------------------------------------------------------
    # Audio
    # --------------------------------------------------------

    audio_index = (
        len(pages) + 1
    )

    filters.append(
        f"[{audio_index}:a]"
        f"atrim=duration=75,"
        f"asetpts=PTS-STARTPTS"
        f"[audio]"
    )

    filter_complex = ";".join(
        filters
    )

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",

        *inputs,

        "-filter_complex",
        filter_complex,

        "-map",
        current,

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

        "-movflags",
        "+faststart",

        str(output_file),
    ]

    run_command(
        command
    )

    print()
    print(
        "VIDEO CREATED:"
    )
    print(
        output_file
    )


# ============================================================
# METADATA
# ============================================================

def create_metadata(hadith):

    reference = (
        f'{hadith["collection_name"]} '
        f'{hadith["number"]}'
    )

    title = (
        f"Islamic Hadith Reminder | "
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
        encoding="utf-8",
    )

    (
        OUTPUT_DIR /
        "youtube_description.txt"
    ).write_text(
        description,
        encoding="utf-8",
    )

    (
        OUTPUT_DIR /
        "tiktok_caption.txt"
    ).write_text(
        tiktok,
        encoding="utf-8",
    )

    (
        OUTPUT_DIR /
        "instagram_caption.txt"
    ).write_text(
        instagram,
        encoding="utf-8",
    )

    (
        OUTPUT_DIR /
        "facebook_caption.txt"
    ).write_text(
        facebook,
        encoding="utf-8",
    )

    metadata = {
        "title": title,
        "description": description,
        "reference": reference,
        "collection": hadith[
            "collection_name"
        ],
        "hadith_number": hadith[
            "number"
        ],
    }

    (
        OUTPUT_DIR /
        "metadata.json"
    ).write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("ISLAMIC HADITH VIDEO GENERATOR")
    print("=" * 70)

    # --------------------------------------------------------
    # Check files
    # --------------------------------------------------------

    if not PEXELS_API_KEY:
        raise RuntimeError(
            "PEXELS_API_KEY is not configured."
        )

    if not AUDIO_FILE.exists():
        raise RuntimeError(
            f"Missing audio: {AUDIO_FILE}"
        )

    if not FONT_FILE.exists():
        raise RuntimeError(
            f"Missing Urdu font: {FONT_FILE}"
        )

    # --------------------------------------------------------
    # Clean work folder
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Select Hadith
    # --------------------------------------------------------

    hadith = select_hadith()

    # --------------------------------------------------------
    # Get image
    # --------------------------------------------------------

    original = (
        get_background_image()
    )

    background = (
        prepare_background(
            original
        )
    )

    # --------------------------------------------------------
    # Create text pages
    # --------------------------------------------------------

    pages = create_pages(
        hadith
    )

    # --------------------------------------------------------
    # Video filename
    # --------------------------------------------------------

    timestamp = int(
        time.time()
    )

    output_video = (
        OUTPUT_DIR /
        f"islamic_hadith_{timestamp}.mp4"
    )

    # --------------------------------------------------------
    # Create video
    # --------------------------------------------------------

    create_video(
        background,
        pages,
        output_video,
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

    print()
    print("=" * 70)
    print("SUCCESS")
    print("=" * 70)
    print(
        "Video:",
        output_video,
    )
    print(
        "Reference:",
        hadith["collection_name"],
        hadith["number"],
    )
    print("=" * 70)


if __name__ == "__main__":
    main()
