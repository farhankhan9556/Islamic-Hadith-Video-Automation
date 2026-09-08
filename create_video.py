import os
import re
import json
import random
import textwrap
import subprocess
from pathlib import Path
from datetime import datetime

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from playwright.sync_api import sync_playwright


# ============================================================
# CONFIGURATION
# ============================================================

WIDTH = 1080
HEIGHT = 1920

VIDEO_DURATION = 75
FPS = 30

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

OUTPUT_DIR = Path("output")
IMAGE_DIR = Path("work")
AUDIO_FILE = Path("audio/islamic_background.mp3")
FONT_DIR = Path("fonts")

USED_FILE = Path("used_hadith.json")

OUTPUT_DIR.mkdir(exist_ok=True)
IMAGE_DIR.mkdir(exist_ok=True)

# Only use these two collections initially.
COLLECTIONS = {
    "bukhari": {
        "name": "Sahih al-Bukhari",
        "max_hadith": 7563
    },
    "muslim": {
        "name": "Sahih Muslim",
        "max_hadith": 7500
    }
}

PEXELS_SEARCH_TERMS = [
    "mosque",
    "Islamic mosque",
    "Islamic architecture",
    "Quran mosque",
    "masjid",
    "Muslim prayer",
    "Islamic sunset",
    "Islamic night",
    "mosque interior",
    "Kaaba"
]


# ============================================================
# HELPERS
# ============================================================

def log(message):
    print(f"[INFO] {message}")


def clean_text(text):
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_used():
    if not USED_FILE.exists():
        return {}

    try:
        return json.loads(USED_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_used(data):
    USED_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ============================================================
# HADITH
# ============================================================

def get_random_hadith_url():
    used = load_used()

    for _ in range(30):

        collection = random.choice(list(COLLECTIONS.keys()))
        number = random.randint(
            1,
            COLLECTIONS[collection]["max_hadith"]
        )

        key = f"{collection}:{number}"

        if key not in used:
            return collection, number

    raise RuntimeError("Could not find an unused Hadith.")


def extract_urdu_text(body_text, collection, number):
    """
    Try to identify the Urdu translation from the Sunnah.com
    Urdu page.

    We deliberately do NOT translate the Hadith ourselves.
    """

    lines = [
        clean_text(x)
        for x in body_text.splitlines()
        if clean_text(x)
    ]

    # Urdu-specific characters commonly appearing in Urdu.
    urdu_chars = set(
        "ٹڈڑںھےؤئۃﷺگپچژک"
    )

    candidates = []

    for line in lines:

        if len(line) < 25:
            continue

        # Skip obvious navigation/reference lines.
        lower = line.lower()

        if "reference" in lower:
            continue

        if "in-book reference" in lower:
            continue

        if "sahih al-bukhari" in lower:
            continue

        if "sahih muslim" in lower:
            continue

        if "language" in lower:
            continue

        # Count Urdu-specific characters.
        score = sum(
            1 for ch in line
            if ch in urdu_chars
        )

        if score >= 1:
            candidates.append(line)

    if not candidates:
        return None

    # Longest candidate is normally the Hadith translation.
    candidates.sort(key=len, reverse=True)

    return candidates[0]


def get_hadith_from_sunnah():
    collection, number = get_random_hadith_url()

    url = f"https://sunnah.com/{collection}:{number}"

    log(f"Opening Sunnah.com: {url}")

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            viewport={
                "width": 1440,
                "height": 1000
            }
        )

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(1500)

        # Select Urdu.
        try:
            page.get_by_text(
                "اردو",
                exact=True
            ).click(timeout=10000)

            page.wait_for_timeout(1500)

        except Exception as e:
            log(f"Urdu button click failed: {e}")

        body = page.locator("body").inner_text()

        browser.close()

    urdu = extract_urdu_text(
        body,
        collection,
        number
    )

    if not urdu:
        raise RuntimeError(
            "Could not extract Urdu Hadith from Sunnah.com"
        )

    collection_name = COLLECTIONS[collection]["name"]

    reference = (
        f"{collection_name}، حدیث {number}"
    )

    return {
        "collection": collection,
        "number": number,
        "text": urdu,
        "reference": reference,
        "url": url
    }


# ============================================================
# PEXELS
# ============================================================

def get_pexels_photo():
    if not PEXELS_API_KEY:
        raise RuntimeError(
            "PEXELS_API_KEY is missing."
        )

    query = random.choice(
        PEXELS_SEARCH_TERMS
    )

    log(f"Searching Pexels: {query}")

    headers = {
        "Authorization": PEXELS_API_KEY
    }

    params = {
        "query": query,
        "orientation": "portrait",
        "size": "large",
        "per_page": 30,
        "page": random.randint(1, 5)
    }

    response = requests.get(
        "https://api.pexels.com/v1/search",
        headers=headers,
        params=params,
        timeout=60
    )

    response.raise_for_status()

    data = response.json()

    photos = data.get("photos", [])

    if not photos:
        raise RuntimeError(
            "No Pexels photos found."
        )

    photo = random.choice(photos)

    image_url = (
        photo["src"].get("original")
        or photo["src"].get("large2x")
        or photo["src"].get("large")
    )

    image_data = requests.get(
        image_url,
        timeout=60
    )

    image_data.raise_for_status()

    image_path = IMAGE_DIR / "pexels.jpg"

    image_path.write_bytes(
        image_data.content
    )

    return {
        "path": image_path,
        "photographer": photo.get(
            "photographer",
            "Pexels"
        ),
        "pexels_url": photo.get(
            "url",
            "https://www.pexels.com/"
        )
    }


# ============================================================
# FONT
# ============================================================

def find_font():
    possible = [
        FONT_DIR / "NotoNaskhArabic-Regular.ttf",
        FONT_DIR / "NotoNaskhArabic-Medium.ttf",
        FONT_DIR / "NotoNaskhArabic-Bold.ttf",
        Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoNaskhArabic-Regular.ttf"),
    ]

    for font in possible:
        if font.exists():
            return str(font)

    raise RuntimeError(
        "Noto Naskh Arabic font not found."
    )


# ============================================================
# IMAGE PREPARATION
# ============================================================

def create_background(photo_path):
    """
    Creates a 1080x1920 background.
    """

    image = Image.open(photo_path).convert("RGB")

    # Create blurred background.
    bg = image.copy()

    bg.thumbnail(
        (WIDTH, HEIGHT)
    )

    canvas = Image.new(
        "RGB",
        (WIDTH, HEIGHT)
    )

    # Cover background.
    scale = max(
        WIDTH / bg.width,
        HEIGHT / bg.height
    )

    new_size = (
        int(bg.width * scale),
        int(bg.height * scale)
    )

    bg = bg.resize(
        new_size,
        Image.Resampling.LANCZOS
    )

    left = (
        bg.width - WIDTH
    ) // 2

    top = (
        bg.height - HEIGHT
    ) // 2

    bg = bg.crop(
        (
            left,
            top,
            left + WIDTH,
            top + HEIGHT
        )
    )

    bg = bg.filter(
        ImageFilter.GaussianBlur(20)
    )

    canvas.paste(bg, (0, 0))

    # Main image.
    main = image.copy()

    scale = max(
        WIDTH / main.width,
        HEIGHT / main.height
    )

    new_size = (
        int(main.width * scale),
        int(main.height * scale)
    )

    main = main.resize(
        new_size,
        Image.Resampling.LANCZOS
    )

    left = (
        main.width - WIDTH
    ) // 2

    top = (
        main.height - HEIGHT
    ) // 2

    main = main.crop(
        (
            left,
            top,
            left + WIDTH,
            top + HEIGHT
        )
    )

    # Darken slightly.
    overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 80)
    )

    main = Image.alpha_composite(
        main.convert("RGBA"),
        overlay
    )

    canvas.paste(
        main.convert("RGB"),
        (0, 0)
    )

    return canvas


# ============================================================
# TEXT IMAGE
# ============================================================

def create_text_overlay(hadith):
    """
    Creates transparent text overlay.
    """

    font_path = find_font()

    title_font = ImageFont.truetype(
        font_path,
        55
    )

    hadith_font = ImageFont.truetype(
        font_path,
        53
    )

    ref_font = ImageFont.truetype(
        font_path,
        40
    )

    overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0)
    )

    draw = ImageDraw.Draw(
        overlay
    )

    # Semi-transparent central panel.
    panel_x = 70
    panel_y = 310
    panel_w = WIDTH - 140
    panel_h = 1300

    draw.rounded_rectangle(
        (
            panel_x,
            panel_y,
            panel_x + panel_w,
            panel_y + panel_h
        ),
        radius=35,
        fill=(0, 0, 0, 145)
    )

    # Heading.
    heading = "رسول اللہ ﷺ نے فرمایا"

    heading_box = draw.textbbox(
        (0, 0),
        heading,
        font=title_font
    )

    heading_w = (
        heading_box[2] - heading_box[0]
    )

    draw.text(
        (
            (WIDTH - heading_w) / 2,
            390
        ),
        heading,
        font=title_font,
        fill=(255, 255, 255, 255),
        stroke_width=2,
        stroke_fill=(0, 0, 0, 255)
    )

    # Hadith wrapping.
    words = hadith["text"].split()

    lines = []
    current = ""

    # Urdu needs right-to-left layout.
    for word in words:

        test = (
            current + " " + word
        ).strip()

        if len(test) > 38:
            lines.append(current)
            current = word
        else:
            current = test

    if current:
        lines.append(current)

    # Maximum lines.
    lines = lines[:14]

    line_height = 82

    total_height = (
        len(lines) * line_height
    )

    start_y = (
        760 - total_height / 2
    )

    for i, line in enumerate(lines):

        bbox = draw.textbbox(
            (0, 0),
            line,
            font=hadith_font
        )

        line_w = (
            bbox[2] - bbox[0]
        )

        x = (
            WIDTH - line_w
        ) / 2

        y = (
            start_y +
            i * line_height
        )

        draw.text(
            (x, y),
            line,
            font=hadith_font,
            fill=(255, 255, 255, 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0, 255)
        )

    # Reference.
    reference = (
        "حوالہ: " +
        hadith["reference"]
    )

    bbox = draw.textbbox(
        (0, 0),
        reference,
        font=ref_font
    )

    ref_w = (
        bbox[2] - bbox[0]
    )

    draw.text(
        (
            (WIDTH - ref_w) / 2,
            1380
        ),
        reference,
        font=ref_font,
        fill=(240, 240, 240, 255),
        stroke_width=2,
        stroke_fill=(0, 0, 0, 255)
    )

    return overlay


# ============================================================
# VIDEO
# ============================================================

def make_video(background, text_overlay, output_path):
    bg_path = IMAGE_DIR / "background.jpg"
    text_path = IMAGE_DIR / "text_overlay.png"

    background.save(
        bg_path,
        quality=95
    )

    text_overlay.save(
        text_path
    )

    if not AUDIO_FILE.exists():
        raise RuntimeError(
            f"Audio file missing: {AUDIO_FILE}"
        )

    # Convert transparent overlay to a video
    # and create a slow zoom on the background.
    filter_complex = (
        "[0:v]"
        "scale=1200:2133,"
        "zoompan="
        "z='min(zoom+0.00035,1.10)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        f"d={VIDEO_DURATION * FPS}:"
        f"s={WIDTH}x{HEIGHT}:"
        f"fps={FPS}"
        "[bg];"

        "[1:v]"
        f"scale={WIDTH}:{HEIGHT}"
        "[txt];"

        "[bg][txt]"
        "overlay=0:0"
        "[v]"
    )

    cmd = [
        "ffmpeg",
        "-y",

        "-loop",
        "1",
        "-i",
        str(bg_path),

        "-loop",
        "1",
        "-i",
        str(text_path),

        "-stream_loop",
        "-1",
        "-i",
        str(AUDIO_FILE),

        "-filter_complex",
        filter_complex,

        "-map",
        "[v]",
        "-map",
        "2:a",

        "-t",
        str(VIDEO_DURATION),

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

        "-shortest",

        str(output_path)
    ]

    log("Creating video...")

    subprocess.run(
        cmd,
        check=True
    )


# ============================================================
# SOCIAL MEDIA METADATA
# ============================================================

def create_metadata(hadith, photo):
    output_metadata = OUTPUT_DIR / "metadata"

    output_metadata.mkdir(
        exist_ok=True
    )

    ref = hadith["reference"]

    source = hadith["url"]

    photographer = photo["photographer"]

    photo_url = photo["pexels_url"]

    youtube = f"""TITLE:
رسول اللہ ﷺ نے فرمایا | خوبصورت حدیث | Islamic Reminder

DESCRIPTION:
رسول اللہ ﷺ کی ایک خوبصورت حدیث۔

حوالہ:
{ref}

Hadith source:
Sunnah.com
{source}

Photo:
{photographer} / Pexels
{photo_url}

#IslamicShorts #Hadith #IslamicReminder #Islam #Urdu #Muslim
"""

    tiktok = f"""TITLE:
رسول اللہ ﷺ کی خوبصورت حدیث ❤️

DESCRIPTION:
رسول اللہ ﷺ کی ایک خوبصورت حدیث اور ہمارے لیے اہم نصیحت۔

حوالہ:
{ref}

Source:
Sunnah.com

#IslamicTikTok #Hadith #IslamicReminder #Islam #UrduIslamic #Muslim
"""

    instagram = f"""TITLE:
رسول اللہ ﷺ نے فرمایا ❤️

DESCRIPTION:
رسول اللہ ﷺ کی خوبصورت حدیث۔

حوالہ:
{ref}

Source:
Sunnah.com
{source}

Photo:
{photographer} / Pexels

#Islam #Hadith #IslamicReminder #IslamicReels #Urdu #Muslim #IslamicVideo
"""

    facebook = f"""TITLE:
رسول اللہ ﷺ کی خوبصورت حدیث

DESCRIPTION:
رسول اللہ ﷺ کی ایک خوبصورت حدیث جو ہمارے لیے اہم سبق رکھتی ہے۔

حوالہ:
{ref}

Source:
Sunnah.com
{source}

Photo:
{photographer} / Pexels
{photo_url}

#IslamicReminder #Hadith #Islam #Urdu #IslamicVideo #Muslim
"""

    files = {
        "youtube.txt": youtube,
        "tiktok.txt": tiktok,
        "instagram.txt": instagram,
        "facebook.txt": facebook
    }

    for filename, content in files.items():

        (
            output_metadata / filename
        ).write_text(
            content,
            encoding="utf-8"
        )


# ============================================================
# SAVE HADITH INFORMATION
# ============================================================

def save_hadith_record(hadith):
    used = load_used()

    key = (
        f"{hadith['collection']}:"
        f"{hadith['number']}"
    )

    used[key] = {
        "date": datetime.utcnow().isoformat(),
        "reference": hadith["reference"],
        "url": hadith["url"]
    }

    save_used(used)


# ============================================================
# MAIN
# ============================================================

def main():

    log("====================================")
    log("Islamic Hadith Video Generator")
    log("====================================")

    # 1. Get Hadith.
    hadith = get_hadith_from_sunnah()

    log(
        f"Hadith selected: "
        f"{hadith['reference']}"
    )

    log(
        f"Source: {hadith['url']}"
    )

    # 2. Get Pexels photo.
    photo = get_pexels_photo()

    log(
        f"Photo: "
        f"{photo['photographer']}"
    )

    # 3. Prepare background.
    background = create_background(
        photo["path"]
    )

    # 4. Prepare Urdu text.
    overlay = create_text_overlay(
        hadith
    )

    # 5. Create filename.
    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    video_path = (
        OUTPUT_DIR /
        f"islamic_hadith_{timestamp}.mp4"
    )

    # 6. Create video.
    make_video(
        background,
        overlay,
        video_path
    )

    # 7. Social metadata.
    create_metadata(
        hadith,
        photo
    )

    # 8. Remember Hadith.
    save_hadith_record(
        hadith
    )

    log("====================================")
    log("VIDEO CREATED SUCCESSFULLY")
    log(f"Video: {video_path}")
    log("Metadata: output/metadata/")
    log("====================================")


if __name__ == "__main__":
    main()
