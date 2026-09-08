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


ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
WORK_DIR = ROOT / "work"

AUDIO_FILE = ROOT / "audio" / "islamic_background.mp3"
FONT_FILE = ROOT / "fonts" / "NotoNastaliqUrdu-Regular.ttf"
USED_FILE = ROOT / "used_hadith.json"

WIDTH = 1080
HEIGHT = 1920
FPS = 30
DURATION = 75

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()

DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
WORK_DIR.mkdir(exist_ok=True)

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

PEXELS_QUERIES = [
    "mosque",
    "masjid",
    "Medina mosque",
    "mosque sunset",
    "Islamic architecture",
    "Kaaba",
    "beautiful mosque",
]


# ---------------------------------------------------------
# BASIC FUNCTIONS
# ---------------------------------------------------------

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
            f"Command failed with exit code {result.returncode}"
        )

    return result


def clean_text(text):
    if not text:
        return ""

    text = str(text)

    # Normalize Unicode.
    text = unicodedata.normalize("NFKC", text)

    # Convert ﷺ ligature to normal Arabic text.
    text = text.replace(
        "\ufdfa",
        "صلى الله عليه وسلم"
    )

    # Remove invisible BOM/zero-width space only.
    text = text.replace("\ufeff", "")
    text = text.replace("\u200b", "")

    # IMPORTANT:
    # Do NOT remove ZWNJ/ZWJ because Urdu shaping can need them.

    text = text.replace("\r", " ")
    text = text.replace("\n", " ")

    # Remove actual control characters.
    text = re.sub(
        r"[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]",
        "",
        text,
    )

    # Normalize spaces.
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ---------------------------------------------------------
# USED HADITH
# ---------------------------------------------------------

def load_used():
    if not USED_FILE.exists():
        return set()

    try:
        data = json.loads(
            USED_FILE.read_text(encoding="utf-8")
        )

        if isinstance(data, dict):
            return set(str(x) for x in data.keys())

        if isinstance(data, list):
            return set(str(x) for x in data)

    except Exception as exc:
        print("Warning reading used_hadith.json:", exc)

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


# ---------------------------------------------------------
# HADITH DATABASE
# ---------------------------------------------------------

def load_hadith_file(path):

    if not path.exists():
        raise RuntimeError(
            f"Missing Hadith database: {path}"
        )

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Invalid database format: {path}"
        )

    hadiths = data.get("hadiths")

    if not isinstance(hadiths, list):
        raise RuntimeError(
            f"'hadiths' list not found: {path}"
        )

    print(
        f"{path.name}: {len(hadiths)} Hadiths"
    )

    return hadiths


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


def is_urdu(text):

    if not text:
        return False

    arabic_block = re.findall(
        r"[\u0600-\u06FF]",
        text
    )

    return len(arabic_block) >= 10


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

            key = f"{collection}:{number}"

            if key in used:
                continue

            candidates.append({
                "key": key,
                "collection": collection,
                "collection_name": config["name"],
                "number": number,
                "text": text,
            })

    if not candidates:

        print(
            "No unused Hadith remains."
        )

        raise RuntimeError(
            "All Hadiths have already been used. "
            "Reset used_hadith.json if you want to start again."
        )

    selected = random.choice(candidates)

    print("=" * 70)
    print("SELECTED HADITH")
    print("=" * 70)

    print(
        "Collection:",
        selected["collection_name"]
    )

    print(
        "Number:",
        selected["number"]
    )

    print(
        "Text:",
        selected["text"]
    )

    print("=" * 70)

    return selected


# ---------------------------------------------------------
# PEXELS
# ---------------------------------------------------------

def search_pexels(query):

    if not PEXELS_API_KEY:
        raise RuntimeError(
            "PEXELS_API_KEY is missing."
        )

    response = requests.get(
        "https://api.pexels.com/v1/search",
        headers={
            "Authorization": PEXELS_API_KEY
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


def download_file(url, destination):

    for attempt in range(3):

        try:

            response = requests.get(
                url,
                timeout=90,
                headers={
                    "User-Agent": "Mozilla/5.0"
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

            Image.open(destination).verify()

            return destination

        except Exception as exc:

            print(
                "Image download failed:",
                exc
            )

            time.sleep(2)

    return None


def get_background_image():

    queries = list(PEXELS_QUERIES)

    random.shuffle(queries)

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

            photos = search_pexels(query)

            random.shuffle(photos)

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
                    destination
                )

                if result:
                    return result

        except Exception as exc:

            print(
                "Pexels error:",
                exc
            )

    raise RuntimeError(
        "Could not obtain Pexels image."
    )


def prepare_background(image_file):

    image = Image.open(
        image_file
    ).convert("RGB")

    target_ratio = (
        WIDTH / HEIGHT
    )

    source_ratio = (
        image.width / image.height
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
        (new_width, new_height),
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

    # Slight dark overlay.
    dark = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 75)
    )

    image = Image.alpha_composite(
        image.convert("RGBA"),
        dark
    )

    output = (
        WORK_DIR /
        "background.jpg"
    )

    image.convert("RGB").save(
        output,
        quality=95
    )

    return output


# ---------------------------------------------------------
# FONTS / URDU RENDERING
# ---------------------------------------------------------

def get_urdu_font(size):

    if not FONT_FILE.exists():

        raise RuntimeError(
            f"Font not found: {FONT_FILE}"
        )

    return ImageFont.truetype(
        str(FONT_FILE),
        size
    )


def get_english_font(size):

    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]

    for path in paths:

        if Path(path).exists():

            return ImageFont.truetype(
                path,
                size
            )

    raise RuntimeError(
        "English font not found."
    )


def raqm_available():

    try:
        return features.check("raqm")
    except Exception:
        return False


# ---------------------------------------------------------
# URDU MEASUREMENT
# ---------------------------------------------------------

def text_width(draw, text, font):

    if raqm_available():

        box = draw.textbbox(
            (0, 0),
            text,
            font=font,
            direction="rtl",
            language="ur"
        )

    else:

        box = draw.textbbox(
            (0, 0),
            text,
            font=font
        )

    return box[2] - box[0]


def text_height(draw, text, font):

    if raqm_available():

        box = draw.textbbox(
            (0, 0),
            text,
            font=font,
            direction="rtl",
            language="ur"
        )

    else:

        box = draw.textbbox(
            (0, 0),
            text,
            font=font
        )

    return box[3] - box[1]


def draw_urdu(
    draw,
    position,
    text,
    font,
    fill,
    anchor="mm"
):

    if raqm_available():

        draw.text(
            position,
            text,
            font=font,
            fill=fill,
            anchor=anchor,
            direction="rtl",
            language="ur"
        )

    else:

        # Emergency fallback.
        # RAQM should normally be available
        # because the workflow installs it.

        import arabic_reshaper
        from bidi.algorithm import get_display

        shaped = get_display(
            arabic_reshaper.reshape(text)
        )

        draw.text(
            position,
            shaped,
            font=font,
            fill=fill,
            anchor=anchor
        )


# ---------------------------------------------------------
# URDU WRAPPING
# ---------------------------------------------------------

def wrap_urdu(
    text,
    font,
    max_width
):

    text = clean_text(text)

    words = text.split()

    dummy = Image.new(
        "RGB",
        (10, 10)
    )

    draw = ImageDraw.Draw(dummy)

    lines = []

    current = ""

    for word in words:

        candidate = (
            word
            if not current
            else current + " " + word
        )

        width = text_width(
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


def make_pages(text):

    # Larger Nastaliq font.
    font = get_urdu_font(72)

    lines = wrap_urdu(
        text,
        font,
        870
    )

    # Maximum 3 lines per screen.
    # This makes the Urdu much easier to read.
    lines_per_page = 3

    pages = []

    for i in range(
        0,
        len(lines),
        lines_per_page
    ):

        pages.append(
            lines[
                i:i + lines_per_page
            ]
        )

    return pages


# ---------------------------------------------------------
# TEXT PAGE
# ---------------------------------------------------------

def create_text_page(
    lines,
    reference,
    destination
):

    canvas = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0)
    )

    draw = ImageDraw.Draw(
        canvas
    )

    urdu_font = get_urdu_font(72)
    reference_font = get_english_font(34)

    heights = []

    for line in lines:

        heights.append(
            text_height(
                draw,
                line,
                urdu_font
            )
        )

    line_gap = 28

    text_height_total = (
        sum(heights)
        +
        line_gap *
        max(0, len(lines) - 1)
    )

    ref_box = draw.textbbox(
        (0, 0),
        reference,
        font=reference_font
    )

    ref_height = (
        ref_box[3] -
        ref_box[1]
    )

    card_width = 980

    card_height = (
        text_height_total
        + 100
        + ref_height
        + 80
    )

    card_x = (
        WIDTH -
        card_width
    ) // 2

    card_y = (
        HEIGHT -
        card_height
    ) // 2

    # Move card slightly upward.
    card_y -= 70

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
        fill=(0, 0, 0, 215),
        outline=(255, 255, 255, 80),
        width=2
    )

    # -----------------------------------------------------
    # URDU
    # -----------------------------------------------------

    center_x = WIDTH // 2

    current_y = (
        card_y + 55
    )

    for index, line in enumerate(lines):

        line_h = heights[index]

        # Shadow.
        draw_urdu(
            draw,
            (
                center_x + 4,
                current_y
                + line_h // 2
                + 5
            ),
            line,
            urdu_font,
            (0, 0, 0, 255),
            anchor="mm"
        )

        # White Urdu.
        draw_urdu(
            draw,
            (
                center_x,
                current_y
                + line_h // 2
            ),
            line,
            urdu_font,
            (255, 255, 255, 255),
            anchor="mm"
        )

        current_y += (
            line_h +
            line_gap
        )

    # -----------------------------------------------------
    # REFERENCE SEPARATOR
    # -----------------------------------------------------

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
        fill=(255, 255, 255, 100),
        width=2
    )

    # -----------------------------------------------------
    # REFERENCE
    # -----------------------------------------------------

    reference_y = (
        separator_y + 38
    )

    ref_box = draw.textbbox(
        (0, 0),
        reference,
        font=reference_font
    )

    ref_width = (
        ref_box[2] -
        ref_box[0]
    )

    ref_x = (
        center_x -
        ref_width // 2
    )

    # Reference shadow.
    draw.text(
        (
            ref_x + 2,
            reference_y + 3
        ),
        reference,
        font=reference_font,
        fill=(0, 0, 0, 255)
    )

    # Reference.
    draw.text(
        (
            ref_x,
            reference_y
        ),
        reference,
        font=reference_font,
        fill=(255, 255, 255, 255)
    )

    canvas.save(
        destination,
        "PNG"
    )

    print(
        "Created:",
        destination
    )


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

    for index, page in enumerate(pages):

        file = (
            page_dir /
            f"page_{index:03d}.png"
        )

        create_text_page(
            page,
            reference,
            file
        )

        result.append(file)

    print(
        "Total text pages:",
        len(result)
    )

    return result


# ---------------------------------------------------------
# VIDEO
# ---------------------------------------------------------

def create_video(
    background,
    pages,
    output_file
):

    if not pages:
        raise RuntimeError(
            "No text pages."
        )

    page_duration = (
        DURATION /
        len(pages)
    )

    inputs = []

    # Background.
    inputs.extend([
        "-loop",
        "1",
        "-i",
        str(background)
    ])

    # Text pages.
    for page in pages:

        inputs.extend([
            "-loop",
            "1",
            "-t",
            f"{page_duration:.4f}",
            "-i",
            str(page)
        ])

    # Audio.
    inputs.extend([
        "-stream_loop",
        "-1",
        "-i",
        str(AUDIO_FILE)
    ])

    filters = []

    # -----------------------------------------------------
    # BACKGROUND
    # -----------------------------------------------------

    filters.append(
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
        "[background]"
    )

    # -----------------------------------------------------
    # TEXT PAGES
    # -----------------------------------------------------

    page_labels = []

    for index in range(
        len(pages)
    ):

        input_index = index + 1

        label = f"page{index}"

        page_labels.append(
            f"[{label}]"
        )

        filters.append(
            f"[{input_index}:v]"
            "format=rgba,"
            "fps=30,"
            "setpts=PTS-STARTPTS"
            f"[{label}]"
        )

    # Concatenate text pages.
    concat_inputs = "".join(
        page_labels
    )

    filters.append(
        concat_inputs
        + f"concat=n={len(pages)}:"
          "v=1:a=0,"
          "format=rgba"
        "[text]"
    )

    # Overlay text onto background.
    filters.append(
        "[background][text]"
        "overlay=0:0:"
        "format=auto,"
        "format=yuv420p"
        "[video]"
    )

    # Audio.
    audio_index = (
        len(pages) + 1
    )

    filters.append(
        f"[{audio_index}:a]"
        "atrim=duration=75,"
        "asetpts=PTS-STARTPTS"
        "[audio]"
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

        "-movflags",
        "+faststart",

        str(output_file)
    ]

    run_command(command)

    print(
        "VIDEO CREATED:",
        output_file
    )


# ---------------------------------------------------------
# METADATA
# ---------------------------------------------------------

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
            indent=2
        ),
        encoding="utf-8"
    )


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    print("=" * 70)
    print(
        "ISLAMIC HADITH VIDEO GENERATOR"
    )
    print("=" * 70)

    print(
        "Pillow RAQM available:",
        raqm_available()
    )

    if not raqm_available():

        raise RuntimeError(
            "Pillow RAQM is NOT available. "
            "GitHub workflow must install "
            "libraqm-dev, libfribidi-dev and "
            "libharfbuzz-dev BEFORE installing Pillow."
        )

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

    # Clean work directory.
    if WORK_DIR.exists():

        for item in WORK_DIR.iterdir():

            if item.is_dir():

                shutil.rmtree(item)

            else:

                item.unlink()

    WORK_DIR.mkdir(
        exist_ok=True
    )

    # Select Hadith.
    hadith = select_hadith()

    # Get image.
    original = get_background_image()

    background = prepare_background(
        original
    )

    # Create Urdu pages.
    pages = create_pages(
        hadith
    )

    # Output video.
    timestamp = int(
        time.time()
    )

    output_video = (
        OUTPUT_DIR /
        f"islamic_hadith_{timestamp}.mp4"
    )

    # Create video.
    create_video(
        background,
        pages,
        output_video
    )

    # Metadata.
    create_metadata(
        hadith
    )

    # Save used Hadith.
    used = load_used()

    used.add(
        hadith["key"]
    )

    save_used(
        used
    )

    print("=" * 70)
    print("SUCCESS")
    print(
        "Video:",
        output_video
    )
    print(
        "Reference:",
        hadith["collection_name"],
        hadith["number"]
    )
    print("=" * 70)


if __name__ == "__main__":
    main()
