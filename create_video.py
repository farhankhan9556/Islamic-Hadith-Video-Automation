import os
import re
import json
import random
import time
import subprocess
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

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


# ============================================================
# COLLECTIONS
# ============================================================

COLLECTIONS = {
    "bukhari": {
        "name": "Sahih al-Bukhari",
        "max_number": 7563
    },
    "muslim": {
        "name": "Sahih Muslim",
        "max_number": 7500
    }
}


# ============================================================
# USED HADITH
# ============================================================

def load_used_hadith():

    if not USED_FILE.exists():
        return set()

    try:

        data = json.loads(
            USED_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(data, list):
            return set(data)

        if isinstance(data, dict):
            return set(data.keys())

    except Exception as e:

        print("Could not read used_hadith.json:", e)

    return set()


def save_used_hadith(used):

    data = {
        item: True
        for item in sorted(used)
    }

    USED_FILE.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# ============================================================
# CLEAN TEXT
# ============================================================

def clean_text(text):

    if not text:
        return ""

    text = text.replace(
        "\u00a0",
        " "
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# EXTRACT REFERENCE
# ============================================================

def extract_reference(page, collection, number):

    # Sunnah.com official reference table
    try:

        reference_cell = page.locator(
            ".hadith_reference tr:first-child td:nth-child(2)"
        ).first

        if reference_cell.count() > 0:

            reference = clean_text(
                reference_cell.inner_text(
                    timeout=10000
                )
            )

            # Usually begins with ":"
            reference = reference.lstrip(
                ":"
            ).strip()

            if (
                "Sahih al-Bukhari" in reference
                or "Sahih Muslim" in reference
            ):
                return reference

    except Exception as e:

        print(
            "Reference element extraction failed:",
            e
        )


    # Fallback: exact reference based on URL
    if collection == "bukhari":

        return f"Sahih al-Bukhari {number}"

    return f"Sahih Muslim {number}"


# ============================================================
# EXTRACT URDU HADITH
# ============================================================

def extract_urdu_hadith(page):

    try:

        # Sunnah.com uses this exact class
        locator = page.locator(
            ".urdu_hadith_full"
        )

        count = locator.count()

        print(
            "Urdu containers found:",
            count
        )

        if count == 0:
            return None

        texts = []

        for i in range(count):

            try:

                element = locator.nth(i)

                if not element.is_visible():
                    continue

                text = element.inner_text(
                    timeout=10000
                )

                text = clean_text(text)

                if len(text) >= 20:

                    texts.append(text)

            except Exception:
                continue

        if not texts:
            return None

        # The actual Hadith is normally the longest
        texts.sort(
            key=len,
            reverse=True
        )

        return texts[0]

    except Exception as e:

        print(
            "Urdu extraction error:",
            e
        )

        return None


# ============================================================
# FIND HADITH
# ============================================================

def get_random_hadith_page():

    used = load_used_hadith()

    collections = list(
        COLLECTIONS.keys()
    )

    random.shuffle(
        collections
    )

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )

        # IMPORTANT:
        # Tell Sunnah.com that we want Urdu
        context = browser.new_context(
            locale="ur-PK"
        )

        # Sunnah.com's own language preference cookie
        context.add_cookies([
            {
                "name": "langprefs13",
                "value": '"urdu"',
                "domain": "sunnah.com",
                "path": "/"
            }
        ])

        page = context.new_page()

        for collection in collections:

            max_number = COLLECTIONS[
                collection
            ]["max_number"]

            attempts = 0

            while attempts < 50:

                attempts += 1

                number = random.randint(
                    1,
                    max_number
                )

                key = (
                    f"{collection}:{number}"
                )

                if key in used:
                    continue

                url = (
                    f"https://sunnah.com/"
                    f"{collection}:{number}"
                )

                print(
                    f"Trying Hadith: {url}"
                )

                try:

                    response = page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=60000
                    )

                    # Skip obvious invalid pages
                    if response:

                        status = response.status

                        print(
                            "HTTP status:",
                            status
                        )

                        if status >= 400:
                            continue

                    # Give Sunnah.com JS time to load
                    page.wait_for_timeout(
                        2500
                    )

                    # Wait for Hadith container
                    try:

                        page.locator(
                            ".actualHadithContainer"
                        ).first.wait_for(
                            state="visible",
                            timeout=15000
                        )

                    except Exception:

                        print(
                            "Hadith container not found."
                        )

                        continue

                    # Wait for Urdu AJAX content
                    try:

                        page.locator(
                            ".urdu_hadith_full"
                        ).first.wait_for(
                            state="visible",
                            timeout=20000
                        )

                    except PlaywrightTimeoutError:

                        print(
                            "Urdu text did not load."
                        )

                        # Try clicking Urdu as fallback
                        try:

                            urdu = page.get_by_text(
                                "اردو",
                                exact=True
                            ).first

                            if urdu.count() > 0:

                                urdu.click(
                                    timeout=10000
                                )

                                page.wait_for_timeout(
                                    4000
                                )

                        except Exception:
                            pass

                    # Extract Urdu
                    urdu_text = (
                        extract_urdu_hadith(
                            page
                        )
                    )

                    if not urdu_text:

                        print(
                            "No Urdu Hadith found."
                        )

                        continue

                    # Extract reference
                    reference = extract_reference(
                        page,
                        collection,
                        number
                    )

                    print(
                        "SUCCESS:"
                    )

                    print(
                        "Reference:",
                        reference
                    )

                    print(
                        "Urdu length:",
                        len(urdu_text)
                    )

                    return {
                        "key": key,
                        "collection": collection,
                        "number": number,
                        "reference": reference,
                        "url": url,
                        "urdu": urdu_text
                    }

                except Exception as e:

                    print(
                        "Page error:",
                        e
                    )

                time.sleep(1)

        browser.close()

    raise RuntimeError(
        "Could not find a new Urdu Hadith from Sunnah.com."
    )


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
        "medina mosque"
    ]

    query = random.choice(
        queries
    )

    print(
        "Pexels search:",
        query
    )

    headers = {
        "Authorization":
        PEXELS_API_KEY
    }

    params = {
        "query": query,
        "orientation": "portrait",
        "size": "large",
        "per_page": 15,
        "page": random.randint(1, 3)
    }

    response = requests.get(
        "https://api.pexels.com/v1/search",
        headers=headers,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    photos = data.get(
        "photos",
        []
    )

    if not photos:

        raise RuntimeError(
            "No Pexels image found."
        )

    photo = random.choice(
        photos
    )

    image_url = (
        photo.get("src", {}).get(
            "portrait"
        )
        or
        photo.get("src", {}).get(
            "large2x"
        )
        or
        photo.get("src", {}).get(
            "large"
        )
    )

    if not image_url:

        raise RuntimeError(
            "Pexels image URL missing."
        )

    image_response = requests.get(
        image_url,
        timeout=60
    )

    image_response.raise_for_status()

    image_path = (
        WORK_DIR /
        "background.jpg"
    )

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
        )
    }


# ============================================================
# URDU SHAPING
# ============================================================

def shape_urdu(text):

    reshaped = (
        arabic_reshaper.reshape(
            text
        )
    )

    return get_display(
        reshaped
    )


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

        test = (
            current + " " + word
        ).strip()

        shaped = shape_urdu(
            test
        )

        bbox = draw.textbbox(
            (0, 0),
            shaped,
            font=font
        )

        width = (
            bbox[2] - bbox[0]
        )

        if width <= max_width:

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


# ============================================================
# CREATE TEXT IMAGE
# ============================================================

def create_text_image(
    background_path,
    hadith_text,
    reference
):

    image = Image.open(
        background_path
    ).convert("RGB")

    image_ratio = (
        image.width /
        image.height
    )

    target_ratio = (
        WIDTH / HEIGHT
    )

    if image_ratio > target_ratio:

        new_width = int(
            image.height *
            target_ratio
        )

        left = (
            image.width -
            new_width
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

        new_height = int(
            image.width /
            target_ratio
        )

        top = (
            image.height -
            new_height
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
        (
            WIDTH,
            HEIGHT
        ),
        Image.Resampling.LANCZOS
    )

    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 110)
    )

    image = Image.alpha_composite(
        image.convert("RGBA"),
        overlay
    )

    draw = ImageDraw.Draw(
        image
    )

    font = ImageFont.truetype(
        str(FONT_FILE),
        60
    )

    reference_font = (
        ImageFont.truetype(
            str(FONT_FILE),
            42
        )
    )

    lines = wrap_rtl_text(
        draw,
        hadith_text,
        font,
        880
    )

    # Keep video readable
    if len(lines) > 12:
        lines = lines[:12]

    line_spacing = 20

    heights = []

    for line in lines:

        shaped = shape_urdu(
            line
        )

        bbox = draw.textbbox(
            (0, 0),
            shaped,
            font=font
        )

        heights.append(
            bbox[3] -
            bbox[1]
        )

    total_height = (
        sum(heights)
        +
        line_spacing *
        max(
            0,
            len(lines) - 1
        )
        +
        150
    )

    y = max(
        250,
        (HEIGHT - total_height) // 2
    )

    for line, line_height in zip(
        lines,
        heights
    ):

        shaped = shape_urdu(
            line
        )

        bbox = draw.textbbox(
            (0, 0),
            shaped,
            font=font
        )

        text_width = (
            bbox[2] -
            bbox[0]
        )

        x = (
            WIDTH -
            text_width
        ) // 2

        draw.text(
            (
                x + 3,
                y + 3
            ),
            shaped,
            font=font,
            fill=(0, 0, 0, 180)
        )

        draw.text(
            (
                x,
                y
            ),
            shaped,
            font=font,
            fill=(255, 255, 255, 255)
        )

        y += (
            line_height +
            line_spacing
        )

    # Reference
    ref_text = shape_urdu(
        "حوالہ: " +
        reference
    )

    bbox = draw.textbbox(
        (0, 0),
        ref_text,
        font=reference_font
    )

    ref_width = (
        bbox[2] -
        bbox[0]
    )

    ref_x = (
        WIDTH -
        ref_width
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
        (
            ref_x,
            ref_y
        ),
        ref_text,
        font=reference_font,
        fill=(255, 255, 255, 255)
    )

    image_path = (
        WORK_DIR /
        "text_image.png"
    )

    image.convert(
        "RGB"
    ).save(
        image_path,
        quality=95
    )

    return image_path


# ============================================================
# CREATE VIDEO
# ============================================================

def create_video(
    image_path
):

    output_path = (
        OUTPUT_DIR /
        f"islamic_hadith_{int(time.time())}.mp4"
    )

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

    print(
        "Creating video..."
    )

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

    title = (
        f"{hadith['reference']} | "
        "Beautiful Hadith Reminder"
    )

    description = (
        f"{hadith['reference']}\n\n"
        "Daily Islamic Hadith Reminder.\n\n"
        "Source: Sunnah.com\n"
        f"Reference: {hadith['reference']}\n\n"
        "Background photo by "
        f"{pexels['photographer']} "
        "via Pexels."
    )

    hashtags = (
        "#Hadith #Islam #IslamicReminder "
        "#Quran #Sunnah #Muslim #Urdu"
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
        description +
        "\n\n" +
        hashtags,
        encoding="utf-8"
    )

    (
        OUTPUT_DIR /
        "instagram_caption.txt"
    ).write_text(
        description +
        "\n\n" +
        hashtags,
        encoding="utf-8"
    )

    (
        OUTPUT_DIR /
        "facebook_caption.txt"
    ).write_text(
        description +
        "\n\n" +
        hashtags,
        encoding="utf-8"
    )

    metadata = {
        "reference":
            hadith["reference"],

        "collection":
            hadith["collection"],

        "number":
            hadith["number"],

        # Kept internally only.
        # NOT displayed in video.
        "source_url":
            hadith["url"],

        "pexels_photographer":
            pexels["photographer"],

        "pexels_url":
            pexels["pexels_url"]
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


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print(
        "ISLAMIC HADITH VIDEO GENERATOR"
    )
    print("=" * 60)

    if not AUDIO_FILE.exists():

        raise FileNotFoundError(
            f"Missing audio file: "
            f"{AUDIO_FILE}"
        )

    if not FONT_FILE.exists():

        raise FileNotFoundError(
            f"Missing font file: "
            f"{FONT_FILE}"
        )

    # --------------------------------------------------------
    # HADITH
    # --------------------------------------------------------

    hadith = get_random_hadith_page()

    print()
    print(
        "Selected Hadith:"
    )

    print(
        hadith["reference"]
    )

    print(
        "Text length:",
        len(hadith["urdu"])
    )

    print()

    # --------------------------------------------------------
    # PEXELS
    # --------------------------------------------------------

    pexels = (
        download_pexels_image()
    )

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    image_path = (
        create_text_image(
            pexels["path"],
            hadith["urdu"],
            hadith["reference"]
        )
    )

    # --------------------------------------------------------
    # VIDEO
    # --------------------------------------------------------

    video_path = (
        create_video(
            image_path
        )
    )

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    create_metadata(
        hadith,
        pexels
    )

    # --------------------------------------------------------
    # MARK USED ONLY AFTER SUCCESS
    # --------------------------------------------------------

    used = load_used_hadith()

    used.add(
        hadith["key"]
    )

    save_used_hadith(
        used
    )

    print()
    print("=" * 60)
    print(
        "VIDEO CREATED SUCCESSFULLY"
    )
    print("=" * 60)

    print(
        "Video:",
        video_path
    )

    print(
        "Reference:",
        hadith["reference"]
    )

    print(
        "Pexels:",
        pexels["photographer"]
    )

    print("=" * 60)


if __name__ == "__main__":
    main()
