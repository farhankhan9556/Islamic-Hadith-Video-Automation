import os
import re
import json
import random
import time
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

import arabic_reshaper
from bidi.algorithm import get_display


# ============================================================
# SETTINGS
# ============================================================

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

WIDTH = 1080
HEIGHT = 1920
VIDEO_SECONDS = 75

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
WORK_DIR = BASE_DIR / "work"

AUDIO_FILE = BASE_DIR / "audio" / "islamic_background.mp3"
FONT_FILE = BASE_DIR / "fonts" / "NotoNaskhArabic-Regular.ttf"
USED_FILE = BASE_DIR / "used_hadith.json"

OUTPUT_DIR.mkdir(exist_ok=True)
WORK_DIR.mkdir(exist_ok=True)

# Only these two collections
COLLECTIONS = {
    "bukhari": {
        "name": "Sahih al-Bukhari",
        "max_number": 7563,
    },
    "muslim": {
        "name": "Sahih Muslim",
        "max_number": 7500,
    },
}


# ============================================================
# USED HADITH
# ============================================================

def load_used_hadith():
    if not USED_FILE.exists():
        return set()

    try:
        data = json.loads(USED_FILE.read_text(encoding="utf-8"))

        if isinstance(data, list):
            return set(data)

        if isinstance(data, dict):
            return set(data.keys())

    except Exception:
        pass

    return set()


def save_used_hadith(used):
    data = {item: True for item in sorted(used)}

    USED_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ============================================================
# SUNNAH.COM
# ============================================================

def get_random_hadith_page():
    """
    Selects a random individual Hadith page from Bukhari or Muslim.

    No API key is used.
    """

    used = load_used_hadith()

    collections = list(COLLECTIONS.keys())
    random.shuffle(collections)

    for collection in collections:

        max_number = COLLECTIONS[collection]["max_number"]

        for attempt in range(30):

            number = random.randint(1, max_number)

            key = f"{collection}:{number}"

            if key in used:
                continue

            url = f"https://sunnah.com/{collection}:{number}"

            print(f"Trying Hadith: {url}")

            try:
                with sync_playwright() as p:

                    browser = p.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-setuid-sandbox"
                        ]
                    )

                    page = browser.new_page(
                        viewport={
                            "width": 1400,
                            "height": 1200
                        }
                    )

                    page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=60000
                    )

                    page.wait_for_timeout(2500)

                    # Check that the page is actually a Hadith page
                    body_text = page.locator("body").inner_text(
                        timeout=15000
                    )

                    if "Reference" not in body_text:
                        browser.close()
                        continue

                    # Click Urdu language
                    try:
                        urdu_button = page.get_by_text(
                            "اردو",
                            exact=True
                        ).first

                        if urdu_button.count() > 0:
                            urdu_button.click(timeout=10000)
                            page.wait_for_timeout(2500)

                    except Exception:
                        pass

                    # Get full page text after Urdu selection
                    text = page.locator("body").inner_text(
                        timeout=15000
                    )

                    browser.close()

                    reference = extract_reference(text)

                    if not reference:
                        continue

                    urdu_text = extract_urdu_hadith(text)

                    if not urdu_text:
                        continue

                    print("Reference:", reference)
                    print("Urdu Hadith found.")

                    return {
                        "key": key,
                        "collection": collection,
                        "number": number,
                        "reference": reference,
                        "url": url,
                        "urdu": urdu_text,
                    }

            except Exception as e:
                print("Sunnah error:", e)

            time.sleep(1)

    raise RuntimeError(
        "Could not find a new Hadith from Sunnah.com."
    )


def extract_reference(text):
    """
    Finds the official reference displayed by Sunnah.com.
    Example:
    Sahih al-Bukhari 54
    Sahih Muslim 2564
    """

    patterns = [
        r"Reference\s*:\s*(Sahih al-Bukhari\s+\d+)",
        r"Reference\s*:\s*(Sahih Muslim\s+\d+)",
        r"(Sahih al-Bukhari\s+\d+)",
        r"(Sahih Muslim\s+\d+)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:
            return match.group(1).strip()

    return None


def is_urdu_text(text):
    if not text:
        return False

    # Urdu/Arabic Unicode range
    arabic_chars = re.findall(
        r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]",
        text
    )

    if len(arabic_chars) < 20:
        return False

    # Urdu-specific characters
    urdu_chars = re.findall(
        r"[ٹڈڑںھہۃےی]",
        text
    )

    return len(urdu_chars) >= 1


def clean_hadith_text(text):
    text = re.sub(r"\s+", " ", text)
    text = text.strip()

    # Remove obvious UI labels
    remove_patterns = [
        r"^اردو$",
        r"^English$",
        r"^Bangla$",
        r"^Share$",
        r"^Copy$",
        r"^Report Error$",
    ]

    for pattern in remove_patterns:
        text = re.sub(
            pattern,
            "",
            text,
            flags=re.IGNORECASE
        )

    text = re.sub(r"\s+", " ", text).strip()

    return text


def extract_urdu_hadith(text):
    """
    Extract Urdu text conservatively.

    We look for blocks containing Urdu characters and reject
    navigation/UI content.
    """

    lines = [
        clean_hadith_text(line)
        for line in text.splitlines()
    ]

    candidates = []

    for line in lines:

        if len(line) < 30:
            continue

        if len(line) > 2500:
            continue

        if not is_urdu_text(line):
            continue

        # Reject obvious navigation/UI
        lower = line.lower()

        blocked = [
            "reference",
            "in-book reference",
            "report error",
            "sunnah.com",
            "english",
            "bangla",
            "search",
            "home",
            "share",
            "copy",
        ]

        if any(word in lower for word in blocked):
            continue

        candidates.append(line)

    if not candidates:
        return None

    # Usually the Hadith body is one of the longest Urdu blocks.
    candidates.sort(
        key=lambda x: len(x),
        reverse=True
    )

    return candidates[0]


# ============================================================
# PEXELS
# ============================================================

def download_pexels_image():
    if not PEXELS_API_KEY:
        raise RuntimeError(
            "PEXELS_API_KEY is missing."
        )

    queries = [
        "mosque",
        "masjid",
        "quran",
        "islamic architecture",
        "mosque sunset",
        "islamic background",
        "kaaba",
        "medina mosque",
    ]

    query = random.choice(queries)

    print("Pexels search:", query)

    headers = {
        "Authorization": PEXELS_API_KEY
    }

    params = {
        "query": query,
        "orientation": "portrait",
        "size": "large",
        "per_page": 15,
        "page": random.randint(1, 3),
    }

    response = requests.get(
        "https://api.pexels.com/v1/search",
        headers=headers,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    photos = data.get("photos", [])

    if not photos:
        raise RuntimeError(
            "No Pexels image found."
        )

    photo = random.choice(photos)

    image_url = (
        photo.get("src", {}).get("portrait")
        or photo.get("src", {}).get("large2x")
        or photo.get("src", {}).get("large")
    )

    if not image_url:
        raise RuntimeError(
            "Pexels did not return an image URL."
        )

    image_response = requests.get(
        image_url,
        timeout=60
    )

    image_response.raise_for_status()

    image_path = WORK_DIR / "background.jpg"

    image_path.write_bytes(
        image_response.content
    )

    return {
        "path": image_path,
        "photographer": photo.get(
            "photographer",
            "Unknown"
        ),
        "photographer_url": photo.get(
            "photographer_url",
            ""
        ),
        "pexels_url": photo.get(
            "url",
            ""
        ),
    }


# ============================================================
# URDU TEXT SHAPING
# ============================================================

def shape_urdu(text):
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


def wrap_rtl_text(
    draw,
    text,
    font,
    max_width
):
    """
    Wrap Urdu text while respecting RTL display.
    """

    words = text.split()

    lines = []
    current = ""

    for word in words:

        test = (
            current + " " + word
        ).strip()

        shaped = shape_urdu(test)

        bbox = draw.textbbox(
            (0, 0),
            shaped,
            font=font
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = test
        else:

            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


# ============================================================
# CREATE IMAGE
# ============================================================

def create_text_image(
    background_path,
    hadith_text,
    reference
):
    image = Image.open(
        background_path
    ).convert("RGB")

    # Cover the full vertical canvas
    image_ratio = image.width / image.height
    target_ratio = WIDTH / HEIGHT

    if image_ratio > target_ratio:
        # Crop width
        new_width = int(
            image.height * target_ratio
        )

        left = (
            image.width - new_width
        ) // 2

        image = image.crop(
            (
                left,
                0,
                left + new_width,
                image.height
            )
        )

    else:
        # Crop height
        new_height = int(
            image.width / target_ratio
        )

        top = (
            image.height - new_height
        ) // 2

        image = image.crop(
            (
                0,
                top,
                image.width,
                top + new_height
            )
        )

    image = image.resize(
        (WIDTH, HEIGHT),
        Image.Resampling.LANCZOS
    )

    # Dark overlay
    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 105)
    )

    image = Image.alpha_composite(
        image.convert("RGBA"),
        overlay
    )

    draw = ImageDraw.Draw(image)

    font_size = 60
    reference_size = 42

    font = ImageFont.truetype(
        str(FONT_FILE),
        font_size
    )

    reference_font = ImageFont.truetype(
        str(FONT_FILE),
        reference_size
    )

    max_text_width = 880

    lines = wrap_rtl_text(
        draw,
        hadith_text,
        font,
        max_text_width
    )

    # Limit extreme text length
    if len(lines) > 12:
        lines = lines[:12]

    # Calculate total height
    line_spacing = 20

    heights = []

    for line in lines:

        shaped = shape_urdu(line)

        bbox = draw.textbbox(
            (0, 0),
            shaped,
            font=font
        )

        heights.append(
            bbox[3] - bbox[1]
        )

    total_height = (
        sum(heights)
        + line_spacing * max(
            0,
            len(lines) - 1
        )
        + 150
    )

    start_y = max(
        250,
        (HEIGHT - total_height) // 2
    )

    # Hadith text
    y = start_y

    for line, line_height in zip(
        lines,
        heights
    ):

        shaped = shape_urdu(line)

        bbox = draw.textbbox(
            (0, 0),
            shaped,
            font=font
        )

        text_width = bbox[2] - bbox[0]

        x = (
            WIDTH - text_width
        ) // 2

        # Shadow
        draw.text(
            (x + 3, y + 3),
            shaped,
            font=font,
            fill=(0, 0, 0, 180)
        )

        draw.text(
            (x, y),
            shaped,
            font=font,
            fill=(255, 255, 255, 255)
        )

        y += line_height + line_spacing

    # Reference
    ref_text = shape_urdu(
        "حوالہ: " + reference
    )

    bbox = draw.textbbox(
        (0, 0),
        ref_text,
        font=reference_font
    )

    ref_width = (
        bbox[2] - bbox[0]
    )

    ref_x = (
        WIDTH - ref_width
    ) // 2

    ref_y = HEIGHT - 260

    draw.text(
        (
            ref_x + 2,
            ref_y + 2
        ),
        ref_text,
        font=reference_font,
        fill=(0, 0, 0, 180)
    )

    draw.text(
        (ref_x, ref_y),
        ref_text,
        font=reference_font,
        fill=(255, 255, 255, 255)
    )

    image_path = WORK_DIR / "text_image.png"

    image.convert("RGB").save(
        image_path,
        quality=95
    )

    return image_path


# ============================================================
# VIDEO
# ============================================================

def create_video(image_path):
    output_path = (
        OUTPUT_DIR
        / f"islamic_hadith_{int(time.time())}.mp4"
    )

    # Slow zoom effect
    vf = (
        "scale=1080:1920,"
        "zoompan="
        "z='min(zoom+0.00035,1.12)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        "d=1:"
        "s=1080x1920:"
        "fps=30,"
        "format=yuv420p"
    )

    command = [
        "ffmpeg",
        "-y",

        "-loop",
        "1",

        "-i",
        str(image_path),

        "-stream_loop",
        "-1",

        "-i",
        str(AUDIO_FILE),

        "-vf",
        vf,

        "-t",
        str(VIDEO_SECONDS),

        "-map",
        "0:v:0",

        "-map",
        "1:a:0",

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "23",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-shortest",

        "-movflags",
        "+faststart",

        str(output_path)
    ]

    print("Creating video...")

    subprocess.run(
        command,
        check=True
    )

    return output_path


# ============================================================
# METADATA
# ============================================================

def create_metadata(
    hadith,
    pexels
):
    base_name = (
        OUTPUT_DIR
        / f"hadith_{int(time.time())}"
    )

    title = (
        f"{hadith['reference']} | "
        f"Beautiful Hadith Reminder"
    )

    description = (
        f"{hadith['reference']}\n\n"
        "Daily Islamic Hadith Reminder.\n\n"
        "Hadith source: Sunnah.com\n"
        f"Reference: {hadith['reference']}\n\n"
        "Background photo by "
        f"{pexels['photographer']} "
        "via Pexels."
    )

    hashtags = (
        "#Hadith #Islam #IslamicReminder "
        "#Quran #Sunnah #Muslim #Urdu"
    )

    # YouTube
    (OUTPUT_DIR / "youtube_title.txt").write_text(
        title,
        encoding="utf-8"
    )

    (OUTPUT_DIR / "youtube_description.txt").write_text(
        description,
        encoding="utf-8"
    )

    # TikTok
    (OUTPUT_DIR / "tiktok_caption.txt").write_text(
        description + "\n\n" + hashtags,
        encoding="utf-8"
    )

    # Instagram
    (OUTPUT_DIR / "instagram_caption.txt").write_text(
        description + "\n\n" + hashtags,
        encoding="utf-8"
    )

    # Facebook
    (OUTPUT_DIR / "facebook_caption.txt").write_text(
        description + "\n\n" + hashtags,
        encoding="utf-8"
    )

    # Internal record
    metadata = {
        "reference": hadith["reference"],
        "collection": hadith["collection"],
        "number": hadith["number"],
        "sunnah_url": hadith["url"],
        "pexels_photographer": pexels[
            "photographer"
        ],
        "pexels_url": pexels[
            "pexels_url"
        ],
    }

    (OUTPUT_DIR / "metadata.json").write_text(
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

    print("=" * 60)
    print("ISLAMIC HADITH VIDEO GENERATOR")
    print("=" * 60)

    # Check files
    if not AUDIO_FILE.exists():
        raise FileNotFoundError(
            f"Missing audio file: {AUDIO_FILE}"
        )

    if not FONT_FILE.exists():
        raise FileNotFoundError(
            f"Missing font file: {FONT_FILE}"
        )

    # Get Hadith
    hadith = get_random_hadith_page()

    print()
    print("Selected:")
    print(hadith["reference"])
    print()

    # Download background
    pexels = download_pexels_image()

    # Create text image
    image_path = create_text_image(
        pexels["path"],
        hadith["urdu"],
        hadith["reference"]
    )

    # Create video
    video_path = create_video(
        image_path
    )

    # Metadata
    create_metadata(
        hadith,
        pexels
    )

    # IMPORTANT:
    # Only mark Hadith as used after video succeeds.
    used = load_used_hadith()

    used.add(
        hadith["key"]
    )

    save_used_hadith(
        used
    )

    print()
    print("=" * 60)
    print("VIDEO CREATED SUCCESSFULLY")
    print("=" * 60)
    print("Video:", video_path)
    print("Reference:", hadith["reference"])
    print("Pexels photographer:", pexels["photographer"])
    print("=" * 60)


if __name__ == "__main__":
    main()
