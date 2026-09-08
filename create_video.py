import json
import os
import random
import re
import subprocess
import time
from pathlib import Path

import requests
import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ============================================================
# SETTINGS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
WORK_DIR = ROOT / "work"
AUDIO_FILE = ROOT / "audio" / "islamic_background.mp3"
URDU_FONT = ROOT / "fonts" / "NotoNaskhArabic-Regular.ttf"
USED_FILE = ROOT / "used_hadith.json"

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30
VIDEO_SECONDS = 75

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "").strip()

OUTPUT_DIR.mkdir(exist_ok=True)
WORK_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)


# ============================================================
# DATABASES
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
    "islamic architecture",
    "mosque sunset",
    "quran",
    "kaaba",
    "medina mosque",
    "islamic background",
    "beautiful mosque",
]


# ============================================================
# BASIC HELPERS
# ============================================================

def run_command(command):
    print("Running:", " ".join(map(str, command)))

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


def clean_spaces(text):
    text = str(text or "")
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ============================================================
# USED HADITH
# ============================================================

def load_used_hadith():
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
        print("Could not read used_hadith.json:", exc)

    return set()


def save_used_hadith(used):
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
# HADITH DATABASE
# ============================================================

def load_database(path):
    if not path.exists():
        raise RuntimeError(
            f"Hadith database missing: {path}"
        )

    try:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        raise RuntimeError(
            f"Invalid JSON file: {path}\n{exc}"
        )

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Unexpected database format: {path}"
        )

    hadiths = data.get("hadiths")

    if not isinstance(hadiths, list):
        raise RuntimeError(
            f"'hadiths' list not found in {path}"
        )

    print(
        f"Loaded {len(hadiths)} Hadiths from "
        f"{path.name}"
    )

    return hadiths


def get_hadith_number(item):
    possible_keys = [
        "hadithnumber",
        "hadithNumber",
        "number",
        "id",
    ]

    for key in possible_keys:
        value = item.get(key)

        if value is not None:
            value = str(value).strip()

            if value:
                return value

    return None


def get_hadith_text(item):
    possible_keys = [
        "text",
        "hadith",
        "body",
        "hadithText",
    ]

    for key in possible_keys:
        value = item.get(key)

        if isinstance(value, str):
            value = clean_spaces(value)

            if value:
                return value

    return None


def looks_like_urdu(text):
    if not text:
        return False

    urdu_chars = re.findall(
        r"[\u0600-\u06FF\u0750-\u077F]",
        text,
    )

    return len(urdu_chars) >= 10


def select_hadith():
    used = load_used_hadith()

    candidates = []

    for collection_key, config in DATABASES.items():

        hadiths = load_database(
            config["file"]
        )

        for item in hadiths:

            number = get_hadith_number(item)
            text = get_hadith_text(item)

            if not number or not text:
                continue

            if not looks_like_urdu(text):
                continue

            unique_key = (
                f"{collection_key}:{number}"
            )

            if unique_key in used:
                continue

            candidates.append(
                {
                    "key": unique_key,
                    "collection": collection_key,
                    "collection_name": config["name"],
                    "number": number,
                    "text": text,
                }
            )

    if not candidates:

        print(
            "All available Hadiths have been used."
        )

        print(
            "Resetting used_hadith.json."
        )

        used = set()
        save_used_hadith(used)

        return select_hadith()

    selected = random.choice(candidates)

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

def pexels_request(query):
    if not PEXELS_API_KEY:
        raise RuntimeError(
            "PEXELS_API_KEY GitHub Secret is missing."
        )

    url = "https://api.pexels.com/v1/search"

    headers = {
        "Authorization": PEXELS_API_KEY
    }

    params = {
        "query": query,
        "orientation": "portrait",
        "size": "large",
        "per_page": 15,
    }

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=60,
    )

    response.raise_for_status()

    return response.json()


def download_image(url, destination):
    for attempt in range(3):

        try:

            print(
                f"Downloading image "
                f"(attempt {attempt + 1})..."
            )

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
                    "Downloaded image is too small."
                )

            Image.open(destination).verify()

            print(
                "Image downloaded:",
                destination,
            )

            return destination

        except Exception as exc:

            print(
                "Image download failed:",
                exc,
            )

            time.sleep(2)

    return None


def get_pexels_image(destination):
    queries = list(PEXELS_QUERIES)
    random.shuffle(queries)

    for query in queries:

        try:

            print(
                "Searching Pexels:",
                query,
            )

            data = pexels_request(query)

            photos = data.get(
                "photos",
                [],
            )

            random.shuffle(photos)

            for photo in photos:

                source = photo.get(
                    "src",
                    {},
                )

                image_url = (
                    source.get("large2x")
                    or source.get("large")
                    or source.get("original")
                )

                if not image_url:
                    continue

                result = download_image(
                    image_url,
                    destination,
                )

                if result:
                    return result

        except Exception as exc:

            print(
                "Pexels search failed:",
                exc,
            )

    raise RuntimeError(
        "Could not download an Islamic image from Pexels."
    )


# ============================================================
# IMAGE PREPARATION
# ============================================================

def prepare_background(input_file):
    image = Image.open(
        input_file
    ).convert("RGB")

    image_ratio = (
        image.width / image.height
    )

    target_ratio = (
        VIDEO_WIDTH / VIDEO_HEIGHT
    )

    if image_ratio > target_ratio:

        new_height = VIDEO_HEIGHT

        new_width = int(
            new_height * image_ratio
        )

    else:

        new_width = VIDEO_WIDTH

        new_height = int(
            new_width / image_ratio
        )

    image = image.resize(
        (new_width, new_height),
        Image.Resampling.LANCZOS,
    )

    left = (
        new_width - VIDEO_WIDTH
    ) // 2

    top = (
        new_height - VIDEO_HEIGHT
    ) // 2

    image = image.crop(
        (
            left,
            top,
            left + VIDEO_WIDTH,
            top + VIDEO_HEIGHT,
        )
    )

    # Darken image slightly.
    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 80),
    )

    image = Image.alpha_composite(
        image.convert("RGBA"),
        overlay,
    )

    output = (
        WORK_DIR /
        "background_prepared.jpg"
    )

    image.convert("RGB").save(
        output,
        quality=95,
    )

    return output


# ============================================================
# FONTS
# ============================================================

def get_urdu_font(size):
    if not URDU_FONT.exists():
        raise RuntimeError(
            f"Urdu font missing: {URDU_FONT}"
        )

    return ImageFont.truetype(
        str(URDU_FONT),
        size,
    )


def get_reference_font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]

    for path in candidates:

        if Path(path).exists():
            return ImageFont.truetype(
                path,
                size,
            )

    # Last fallback.
    return ImageFont.truetype(
        str(URDU_FONT),
        size,
    )


# ============================================================
# URDU TEXT RENDERING
# ============================================================

def shape_urdu(text):
    text = clean_spaces(text)

    reshaped = arabic_reshaper.reshape(
        text
    )

    return get_display(
        reshaped
    )


def text_width(draw, text, font):
    box = draw.textbbox(
        (0, 0),
        text,
        font=font,
    )

    return box[2] - box[0]


def wrap_urdu(text, font, max_width):
    """
    IMPORTANT:
    Wrap the original Urdu words first.
    Only shape each completed line afterward.
    """

    words = clean_spaces(text).split()

    lines = []
    current = ""

    test_image = Image.new(
        "RGB",
        (10, 10),
    )

    draw = ImageDraw.Draw(
        test_image
    )

    for word in words:

        candidate = (
            word
            if not current
            else current + " " + word
        )

        shaped = shape_urdu(
            candidate
        )

        if (
            text_width(
                draw,
                shaped,
                font,
            )
            <= max_width
        ):

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
# SPLIT HADITH INTO PAGES
# ============================================================

def split_hadith_into_pages(text):
    """
    Creates readable pages rather than shrinking
    the entire Hadith to tiny text.
    """

    font_size = 58

    font = get_urdu_font(
        font_size
    )

    raw_lines = wrap_urdu(
        text,
        font,
        850,
    )

    # 5 lines maximum per screen.
    max_lines = 5

    pages = []

    for index in range(
        0,
        len(raw_lines),
        max_lines,
    ):

        page = raw_lines[
            index:index + max_lines
        ]

        pages.append(page)

    return pages


# ============================================================
# CREATE TEXT OVERLAY
# ============================================================

def create_overlay(
    lines,
    reference,
    output_file,
):
    image = Image.new(
        "RGBA",
        (
            VIDEO_WIDTH,
            VIDEO_HEIGHT,
        ),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(
        image
    )

    # --------------------------------------------------------
    # Fonts
    # --------------------------------------------------------

    urdu_font = get_urdu_font(58)

    reference_font = get_reference_font(
        34
    )

    # --------------------------------------------------------
    # Prepare Urdu lines
    # --------------------------------------------------------

    shaped_lines = []

    for line in lines:

        shaped_lines.append(
            shape_urdu(line)
        )

    # --------------------------------------------------------
    # Calculate text block
    # --------------------------------------------------------

    line_spacing = 18

    line_heights = []

    for line in shaped_lines:

        box = draw.textbbox(
            (0, 0),
            line,
            font=urdu_font,
        )

        height = (
            box[3] - box[1]
        )

        line_heights.append(
            height
        )

    text_height = (
        sum(line_heights)
        + line_spacing *
        max(
            0,
            len(shaped_lines) - 1,
        )
    )

    reference_box = draw.textbbox(
        (0, 0),
        reference,
        font=reference_font,
    )

    reference_height = (
        reference_box[3]
        - reference_box[1]
    )

    reference_gap = 40

    card_padding_x = 55
    card_padding_top = 50
    card_padding_bottom = 42

    card_height = (
        card_padding_top
        + text_height
        + reference_gap
        + reference_height
        + card_padding_bottom
    )

    card_width = 960

    # --------------------------------------------------------
    # Card position
    # --------------------------------------------------------

    card_x1 = (
        VIDEO_WIDTH - card_width
    ) // 2

    card_x2 = (
        card_x1 + card_width
    )

    # Keep the card around the center/lower-middle.
    card_y1 = int(
        VIDEO_HEIGHT * 0.30
    )

    card_y2 = (
        card_y1 + card_height
    )

    # Prevent going below screen.
    if card_y2 > VIDEO_HEIGHT - 180:

        card_y2 = (
            VIDEO_HEIGHT - 180
        )

        card_y1 = (
            card_y2 - card_height
        )

    # --------------------------------------------------------
    # Main dark card
    # --------------------------------------------------------

    draw.rounded_rectangle(
        (
            card_x1,
            card_y1,
            card_x2,
            card_y2,
        ),
        radius=38,
        fill=(
            0,
            0,
            0,
            190,
        ),
        outline=(
            255,
            255,
            255,
            60,
        ),
        width=2,
    )

    # --------------------------------------------------------
    # Urdu text
    # --------------------------------------------------------

    current_y = (
        card_y1
        + card_padding_top
    )

    center_x = VIDEO_WIDTH // 2

    for index, line in enumerate(
        shaped_lines
    ):

        box = draw.textbbox(
            (0, 0),
            line,
            font=urdu_font,
        )

        line_width = (
            box[2] - box[0]
        )

        x = (
            center_x
            - line_width // 2
        )

        # Shadow.
        draw.text(
            (
                x + 3,
                current_y + 4,
            ),
            line,
            font=urdu_font,
            fill=(
                0,
                0,
                0,
                230,
            ),
        )

        # White Urdu text.
        draw.text(
            (
                x,
                current_y,
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

        current_y += (
            line_heights[index]
            + line_spacing
        )

    # --------------------------------------------------------
    # Separator
    # --------------------------------------------------------

    separator_y = (
        current_y + 5
    )

    draw.line(
        (
            card_x1 + 100,
            separator_y,
            card_x2 - 100,
            separator_y,
        ),
        fill=(
            255,
            255,
            255,
            80,
        ),
        width=2,
    )

    # --------------------------------------------------------
    # Reference
    # --------------------------------------------------------

    reference_y = (
        separator_y
        + reference_gap
    )

    reference_box = draw.textbbox(
        (0, 0),
        reference,
        font=reference_font,
    )

    reference_width = (
        reference_box[2]
        - reference_box[0]
    )

    reference_x = (
        center_x
        - reference_width // 2
    )

    # Reference shadow.
    draw.text(
        (
            reference_x + 2,
            reference_y + 3,
        ),
        reference,
        font=reference_font,
        fill=(
            0,
            0,
            0,
            230,
        ),
    )

    # Reference.
    draw.text(
        (
            reference_x,
            reference_y,
        ),
        reference,
        font=reference_font,
        fill=(
            235,
            235,
            235,
            255,
        ),
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    image.save(
        output_file,
        "PNG",
    )

    print(
        "Created overlay:",
        output_file,
    )


# ============================================================
# CREATE ALL OVERLAYS
# ============================================================

def create_overlays(
    hadith,
):
    pages = split_hadith_into_pages(
        hadith["text"]
    )

    reference = (
        f'{hadith["collection_name"]} '
        f'{hadith["number"]}'
    )

    overlay_dir = (
        WORK_DIR / "overlays"
    )

    overlay_dir.mkdir(
        exist_ok=True
    )

    overlay_files = []

    for index, page in enumerate(
        pages
    ):

        output_file = (
            overlay_dir /
            f"overlay_{index:03d}.png"
        )

        create_overlay(
            page,
            reference,
            output_file,
        )

        overlay_files.append(
            output_file
        )

    print(
        f"Created {len(overlay_files)} text pages."
    )

    return overlay_files


# ============================================================
# CREATE VIDEO
# ============================================================

def create_video(
    background,
    overlays,
    audio,
    output_file,
):
    if not overlays:
        raise RuntimeError(
            "No text overlays created."
        )

    # Each page gets equal time.
    page_duration = (
        VIDEO_SECONDS
        / len(overlays)
    )

    inputs = [
        "-loop",
        "1",
        "-i",
        str(background),
    ]

    for overlay in overlays:

        inputs.extend(
            [
                "-loop",
                "1",
                "-i",
                str(overlay),
            ]
        )

    # Audio.
    inputs.extend(
        [
            "-stream_loop",
            "-1",
            "-i",
            str(audio),
        ]
    )

    filters = []

    # Background with slow zoom.
    filters.append(
        "[0:v]"
        "scale=1080:1920,"
        "zoompan="
        "z='min(zoom+0.00035,1.08)':"
        "d=2250:"
        "s=1080x1920:"
        "fps=30,"
        "trim=duration=75,"
        "setpts=PTS-STARTPTS"
        "[bg]"
    )

    previous = "[bg]"

    # Add overlays sequentially.
    for index in range(
        len(overlays)
    ):

        overlay_input = (
            f"[{index + 1}:v]"
        )

        overlay_output = (
            f"[ov{index}]"
        )

        filters.append(
            f"{overlay_input}"
            f"format=rgba,"
            f"trim=duration={page_duration:.3f},"
            f"setpts=PTS-STARTPTS"
            f"{overlay_output}"
        )

    # First overlay.
    current = previous

    for index in range(
        len(overlays)
    ):

        output_label = (
            f"[mix{index}]"
        )

        filters.append(
            f"{current}"
            f"{'[ov' + str(index) + ']'}"
            f"overlay=0:0:"
            f"enable='between(t,"
            f"{index * page_duration:.3f},"
            f"{(index + 1) * page_duration:.3f})'"
            f"{output_label}"
        )

        current = output_label

    # Audio is the final input.
    audio_input = (
        f"[{len(overlays) + 1}:a]"
    )

    filters.append(
        f"{audio_input}"
        f"atrim=duration={VIDEO_SECONDS},"
        f"asetpts=PTS-STARTPTS"
        f"[aud]"
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
        "[aud]",

        "-t",
        str(VIDEO_SECONDS),

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

    print(
        "VIDEO CREATED:",
        output_file,
    )


# ============================================================
# METADATA
# ============================================================

def create_metadata(hadith):
    collection = hadith[
        "collection_name"
    ]

    number = hadith[
        "number"
    ]

    reference = (
        f"{collection} {number}"
    )

    title = (
        f"Beautiful Hadith | "
        f"{reference} | Islamic Reminder"
    )

    description = (
        "Islamic Hadith reminder.\n\n"
        f"Reference: {reference}\n\n"
        "May Allah guide us and help us "
        "follow the Sunnah. Ameen.\n\n"
        "#IslamicReminder "
        "#Hadith "
        "#Islam "
        "#Sunnah "
        "#Muslim "
        "#Quran "
        "#IslamicShorts"
    )

    tiktok_caption = (
        f"{reference}\n\n"
        "#Hadith #Islam #Sunnah "
        "#Muslim #IslamicReminder"
    )

    instagram_caption = (
        f"{reference}\n\n"
        "A beautiful Islamic reminder.\n\n"
        "#Hadith #Islam #Sunnah "
        "#Muslim #IslamicReminder "
        "#IslamicReels"
    )

    facebook_caption = (
        f"{reference}\n\n"
        "Islamic reminder for today.\n\n"
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
        tiktok_caption,
        encoding="utf-8",
    )

    (
        OUTPUT_DIR /
        "instagram_caption.txt"
    ).write_text(
        instagram_caption,
        encoding="utf-8",
    )

    (
        OUTPUT_DIR /
        "facebook_caption.txt"
    ).write_text(
        facebook_caption,
        encoding="utf-8",
    )

    metadata = {
        "title": title,
        "description": description,
        "reference": reference,
        "collection": collection,
        "hadith_number": number,
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
    print()

    # --------------------------------------------------------
    # Check required files.
    # --------------------------------------------------------

    if not PEXELS_API_KEY:
        raise RuntimeError(
            "PEXELS_API_KEY GitHub Secret is missing."
        )

    if not AUDIO_FILE.exists():
        raise RuntimeError(
            f"Background audio missing: {AUDIO_FILE}"
        )

    if not URDU_FONT.exists():
        raise RuntimeError(
            f"Urdu font missing: {URDU_FONT}"
        )

    # --------------------------------------------------------
    # Clean previous work.
    # --------------------------------------------------------

    for item in WORK_DIR.iterdir():

        try:

            if item.is_file():
                item.unlink()

            elif item.is_dir():

                import shutil

                shutil.rmtree(
                    item
                )

        except Exception as exc:

            print(
                "Could not clean:",
                item,
                exc,
            )

    # --------------------------------------------------------
    # Select Hadith.
    # --------------------------------------------------------

    hadith = select_hadith()

    # --------------------------------------------------------
    # Download Islamic image.
    # --------------------------------------------------------

    original_image = (
        WORK_DIR /
        "pexels_islamic.jpg"
    )

    get_pexels_image(
        original_image
    )

    # --------------------------------------------------------
    # Prepare image.
    # --------------------------------------------------------

    background = prepare_background(
        original_image
    )

    # --------------------------------------------------------
    # Create Urdu pages.
    # --------------------------------------------------------

    overlays = create_overlays(
        hadith
    )

    # --------------------------------------------------------
    # Output file.
    # --------------------------------------------------------

    timestamp = int(
        time.time()
    )

    output_video = (
        OUTPUT_DIR /
        f"islamic_hadith_{timestamp}.mp4"
    )

    # --------------------------------------------------------
    # Create video.
    # --------------------------------------------------------

    create_video(
        background,
        overlays,
        AUDIO_FILE,
        output_video,
    )

    # --------------------------------------------------------
    # Metadata.
    # --------------------------------------------------------

    create_metadata(
        hadith
    )

    # --------------------------------------------------------
    # Mark Hadith as used ONLY after video succeeds.
    # --------------------------------------------------------

    used = load_used_hadith()

    used.add(
        hadith["key"]
    )

    save_used_hadith(
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
        "Hadith:",
        hadith["collection_name"],
        hadith["number"],
    )
    print("=" * 70)


if __name__ == "__main__":
    main()
