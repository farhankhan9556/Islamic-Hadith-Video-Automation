import os
import re
import json
import random
import subprocess
from pathlib import Path
from datetime import datetime, timezone

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import arabic_reshaper
from bidi.algorithm import get_display


# ============================================================
# CONFIGURATION
# ============================================================

WIDTH = 1080
HEIGHT = 1920

VIDEO_DURATION = 75
FPS = 30

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
SUNNAH_API_KEY = os.getenv("SUNNAH_API_KEY")

SUNNAH_API_BASE = "https://api.sunnah.com/v1"
SUNNAH_WEB_BASE = "https://sunnah.com"

OUTPUT_DIR = Path("output")
WORK_DIR = Path("work")
AUDIO_FILE = Path("audio/islamic_background.mp3")
FONT_DIR = Path("fonts")
USED_FILE = Path("used_hadith.json")

OUTPUT_DIR.mkdir(exist_ok=True)
WORK_DIR.mkdir(exist_ok=True)

# We intentionally restrict the generator to these two collections.
COLLECTIONS = {
    "bukhari": "Sahih al-Bukhari",
    "muslim": "Sahih Muslim",
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
    "Kaaba",
]

REQUEST_TIMEOUT = 60


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(f"[INFO] {message}")


# ============================================================
# JSON / USED HADITH
# ============================================================

def load_used():
    if not USED_FILE.exists():
        return {}

    try:
        data = json.loads(
            USED_FILE.read_text(encoding="utf-8")
        )

        if isinstance(data, dict):
            return data

    except Exception as exc:
        log(f"Could not read used_hadith.json: {exc}")

    return {}


def save_used(data):
    USED_FILE.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


# ============================================================
# SUNNAH.COM API
# ============================================================

def sunnah_headers():
    if not SUNNAH_API_KEY:
        raise RuntimeError(
            "SUNNAH_API_KEY is missing. "
            "Add your Sunnah.com API key to GitHub Secrets."
        )

    return {
        "X-API-Key": SUNNAH_API_KEY,
        "Accept": "application/json",
        "User-Agent": "IslamicVideoGenerator/1.0"
    }


def get_valid_random_hadith():
    """
    Get a real Hadith reference from the official Sunnah.com API.

    We do NOT generate or invent a Hadith number.

    The API result gives us the canonical collection and
    Hadith number. The actual Urdu text is then obtained
    from the corresponding Sunnah.com webpage.
    """

    used = load_used()

    # Try several API pages and randomly choose from returned
    # verified/available records.
    for attempt in range(30):

        collection = random.choice(
            list(COLLECTIONS.keys())
        )

        # Get collection data through the official API.
        # The API allows up to 100 records per page.
        page_number = random.randint(1, 100)

        url = (
            f"{SUNNAH_API_BASE}/hadiths"
        )

        params = {
            "collection": collection,
            "limit": 100,
            "page": page_number,
        }

        log(
            f"Checking Sunnah.com API: "
            f"{collection}, page {page_number}"
        )

        response = requests.get(
            url,
            headers=sunnah_headers(),
            params=params,
            timeout=REQUEST_TIMEOUT
        )

        if response.status_code == 404:
            continue

        response.raise_for_status()

        data = response.json()

        records = data.get("data", [])

        if not records:
            continue

        random.shuffle(records)

        for record in records:

            record_collection = (
                record.get("collection")
                or collection
            )

            number = record.get("hadithNumber")

            if not number:
                continue

            key = (
                f"{record_collection}:"
                f"{number}"
            )

            if key in used:
                continue

            if record_collection not in COLLECTIONS:
                continue

            return {
                "collection": record_collection,
                "number": str(number),
            }

    raise RuntimeError(
        "Could not find an unused Hadith from the "
        "official Sunnah.com API."
    )


# ============================================================
# URDU EXTRACTION
# ============================================================

def is_urdu_text(text):
    """
    Conservative Urdu detection.

    We never translate anything.
    This only helps identify text already present on
    Sunnah.com after selecting Urdu.
    """

    if not text:
        return False

    text = re.sub(r"\s+", " ", text).strip()

    if len(text) < 30:
        return False

    # Characters strongly associated with Urdu.
    urdu_specific = set(
        "ٹڈڑںھےؤئۃگپچژے"
    )

    specific_count = sum(
        1 for char in text
        if char in urdu_specific
    )

    # Common Urdu words.
    common_words = [
        "ہے",
        "ہیں",
        "سے",
        "نے",
        "اور",
        "کے",
        "کی",
        "کا",
        "ایک",
        "جو",
        "یہ",
        "وہ",
        "میں",
        "پر",
        "کو",
        "تھا",
        "تھی",
        "تھے",
        "اللہ",
        "رسول",
        "فرمایا",
    ]

    common_count = sum(
        1 for word in common_words
        if word in text
    )

    return (
        specific_count >= 1
        or common_count >= 2
    )


def clean_hadith_text(text):
    """
    Clean only formatting/HTML artifacts.
    The actual words are NOT translated or rewritten.
    """

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    # Remove accidental UI labels.
    text = re.sub(
        r"^(Translation|ترجمہ)\s*:?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    return text.strip()


def extract_urdu_from_page(page, collection, number):
    """
    Extract the Urdu Hadith from the exact Sunnah.com page.

    Priority:
    1. Urdu/language-specific DOM elements.
    2. Hadith container around the exact reference.
    3. Conservative Urdu candidates.

    If the script cannot confidently find Urdu text,
    it FAILS instead of translating or guessing.
    """

    collection_name = COLLECTIONS[collection]

    reference_text = (
        f"{collection_name} {number}"
    )

    candidates = page.evaluate(
        """
        (referenceText) => {

            function normalize(value) {
                return (value || "")
                    .replace(/\\\\s+/g, " ")
                    .trim();
            }

            function collect(root) {

                const result = [];

                const selectors = [
                    '[lang="ur"]',
                    '[lang="ur-PK"]',
                    '[data-lang="ur"]',
                    '[data-language="ur"]',
                    '[class*="urdu"]',
                    '[id*="urdu"]'
                ];

                for (const selector of selectors) {

                    for (const element of root.querySelectorAll(selector)) {

                        const text = normalize(
                            element.innerText ||
                            element.textContent
                        );

                        if (text.length >= 30) {
                            result.push(text);
                        }
                    }
                }

                return result;
            }

            // First try explicit Urdu elements.
            let direct = collect(document);

            if (direct.length > 0) {
                return direct;
            }

            // Find the exact Hadith reference.
            const elements = Array.from(
                document.querySelectorAll(
                    "a, span, div, p, h1, h2, h3, h4"
                )
            );

            const referenceElement = elements.find(
                element =>
                    normalize(
                        element.innerText ||
                        element.textContent
                    ) === referenceText
            );

            if (!referenceElement) {
                return [];
            }

            let container = referenceElement;

            // Move upward until we reach the Hadith block.
            for (let i = 0; i < 8 && container; i++) {

                const descendants = Array.from(
                    container.querySelectorAll(
                        "p, div, span"
                    )
                );

                const texts = descendants
                    .map(element =>
                        normalize(
                            element.innerText ||
                            element.textContent
                        )
                    )
                    .filter(text => text.length >= 30);

                if (texts.length > 0) {
                    direct = direct.concat(texts);
                }

                container = container.parentElement;
            }

            return direct;
        }
        """,
        reference_text
    )

    # Python-side conservative filtering.
    filtered = []

    for text in candidates:

        text = clean_hadith_text(text)

        if not is_urdu_text(text):
            continue

        # Ignore obvious navigation/reference text.
        lower = text.lower()

        ignored = [
            "language",
            "reference",
            "in-book reference",
            "select collections",
            "search",
            "report error",
            "share",
            "copy",
        ]

        if any(item in lower for item in ignored):
            continue

        filtered.append(text)

    # Remove duplicates.
    filtered = list(dict.fromkeys(filtered))

    if not filtered:
        return None

    # Prefer medium/long Hadith-sized text.
    # Very huge containers are usually entire page sections.
    filtered.sort(
        key=lambda value: (
            0 if len(value) > 2500 else 1,
            abs(len(value) - 700)
        )
    )

    selected = filtered[0]

    # Safety check.
    if len(selected) < 40:
        return None

    return selected


def get_hadith_from_sunnah():
    """
    Complete source chain:

        Official Sunnah.com API
                ↓
        Valid collection + number
                ↓
        Exact Sunnah.com page
                ↓
        Urdu language selection
                ↓
        Exact Urdu text

    No AI translation.
    No generated Hadith.
    """

    selected = get_valid_random_hadith()

    collection = selected["collection"]
    number = selected["number"]

    url = (
        f"{SUNNAH_WEB_BASE}/"
        f"{collection}:{number}"
    )

    log(
        f"Selected Sunnah.com Hadith: {url}"
    )

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        context = browser.new_context(
            viewport={
                "width": 1440,
                "height": 1000
            },
            locale="ur-PK"
        )

        page = context.new_page()

        try:

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(2000)

            # Find the Urdu language control.
            urdu = page.get_by_text(
                "اردو",
                exact=True
            )

            if urdu.count() == 0:
                raise RuntimeError(
                    "Sunnah.com Urdu language control "
                    "was not found."
                )

            clicked = False

            for i in range(
                min(urdu.count(), 5)
            ):

                try:

                    control = urdu.nth(i)

                    if control.is_visible():

                        control.click(
                            timeout=10000
                        )

                        clicked = True
                        break

                except Exception:
                    continue

            if not clicked:
                raise RuntimeError(
                    "Could not select Urdu on Sunnah.com."
                )

            # Allow language content to load.
            page.wait_for_timeout(2500)

            # Wait until Urdu-like content exists.
            try:
                page.wait_for_function(
                    """
                    () => {
                        const text =
                            document.body.innerText || "";

                        return /[ٹڈڑںھےؤئۃگپچژے]/.test(text)
                            && text.length > 500;
                    }
                    """,
                    timeout=15000
                )
            except PlaywrightTimeoutError:
                pass

            urdu_text = extract_urdu_from_page(
                page,
                collection,
                number
            )

            if not urdu_text:

                # Save diagnostic screenshot for GitHub artifact.
                screenshot_path = (
                    WORK_DIR /
                    "sunnah_urdu_extraction_failed.png"
                )

                page.screenshot(
                    path=str(screenshot_path),
                    full_page=True
                )

                raise RuntimeError(
                    "Could not safely extract the Urdu "
                    "Hadith from Sunnah.com. "
                    "The workflow stopped rather than "
                    "guessing or translating the Hadith."
                )

        finally:
            browser.close()

    collection_name = COLLECTIONS[collection]

    reference = (
        f"{collection_name} {number}"
    )

    return {
        "collection": collection,
        "number": number,
        "text": urdu_text,
        "reference": reference,
        "url": url,
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

    log(
        f"Searching Pexels: {query}"
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
            "per_page": 40,
            "page": random.randint(1, 5),
        },
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    data = response.json()

    photos = data.get(
        "photos",
        []
    )

    if not photos:
        raise RuntimeError(
            "No Pexels photos found."
        )

    photo = random.choice(
        photos
    )

    image_url = (
        photo.get("src", {}).get("portrait")
        or photo.get("src", {}).get("large2x")
        or photo.get("src", {}).get("large")
        or photo.get("src", {}).get("original")
    )

    if not image_url:
        raise RuntimeError(
            "Pexels returned a photo without "
            "a usable image URL."
        )

    image_response = requests.get(
        image_url,
        timeout=REQUEST_TIMEOUT
    )

    image_response.raise_for_status()

    image_path = (
        WORK_DIR /
        "pexels.jpg"
    )

    image_path.write_bytes(
        image_response.content
    )

    return {
        "path": image_path,
        "photographer": photo.get(
            "photographer",
            "Pexels"
        ),
        "photographer_url": photo.get(
            "photographer_url",
            "https://www.pexels.com/"
        ),
        "pexels_url": photo.get(
            "url",
            "https://www.pexels.com/"
        ),
    }


# ============================================================
# FONT
# ============================================================

def find_font():

    possible = [
        FONT_DIR /
        "NotoNaskhArabic-Regular.ttf",

        FONT_DIR /
        "NotoNaskhArabic-Medium.ttf",

        FONT_DIR /
        "NotoNaskhArabic-Bold.ttf",

        Path(
            "/usr/share/fonts/truetype/noto/"
            "NotoNaskhArabic-Regular.ttf"
        ),

        Path(
            "/usr/share/fonts/opentype/noto/"
            "NotoNaskhArabic-Regular.ttf"
        ),
    ]

    for font in possible:

        if font.exists():
            log(
                f"Using font: {font}"
            )

            return str(font)

    raise RuntimeError(
        "Noto Naskh Arabic font not found."
    )


# ============================================================
# URDU TEXT SHAPING
# ============================================================

def shape_urdu(text):
    """
    Shape Urdu for correct RTL rendering.
    This does NOT translate or modify the meaning.
    """

    reshaped = arabic_reshaper.reshape(
        text
    )

    return get_display(
        reshaped
    )


# ============================================================
# IMAGE
# ============================================================

def fit_cover(image, width, height):

    image = image.convert("RGB")

    scale = max(
        width / image.width,
        height / image.height
    )

    new_size = (
        int(image.width * scale),
        int(image.height * scale)
    )

    image = image.resize(
        new_size,
        Image.Resampling.LANCZOS
    )

    left = (
        image.width - width
    ) // 2

    top = (
        image.height - height
    ) // 2

    return image.crop(
        (
            left,
            top,
            left + width,
            top + height
        )
    )


def create_background(photo_path):

    image = Image.open(
        photo_path
    ).convert("RGB")

    # Blurred background.
    bg = fit_cover(
        image,
        WIDTH,
        HEIGHT
    )

    bg = bg.filter(
        ImageFilter.GaussianBlur(25)
    )

    canvas = bg.copy()

    # Main image.
    main = fit_cover(
        image,
        WIDTH,
        HEIGHT
    )

    # Slight dark overlay.
    overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 70)
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
# TEXT OVERLAY
# ============================================================

def wrap_urdu_text(
    text,
    draw,
    font,
    max_width
):

    words = text.split()

    lines = []
    current = []

    for word in words:

        test_words = (
            current + [word]
        )

        test_text = shape_urdu(
            " ".join(test_words)
        )

        bbox = draw.textbbox(
            (0, 0),
            test_text,
            font=font
        )

        width = (
            bbox[2] - bbox[0]
        )

        if (
            width > max_width
            and current
        ):

            lines.append(
                " ".join(current)
            )

            current = [word]

        else:
            current = test_words

    if current:
        lines.append(
            " ".join(current)
        )

    return lines


def create_text_overlay(hadith):

    font_path = find_font()

    hadith_font = ImageFont.truetype(
        font_path,
        53
    )

    reference_font = ImageFont.truetype(
        font_path,
        38
    )

    overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0)
    )

    draw = ImageDraw.Draw(
        overlay
    )

    # Central panel.
    panel_x = 60
    panel_y = 250
    panel_w = WIDTH - 120
    panel_h = 1420

    draw.rounded_rectangle(
        (
            panel_x,
            panel_y,
            panel_x + panel_w,
            panel_y + panel_h
        ),
        radius=40,
        fill=(0, 0, 0, 155)
    )

    # Exact Hadith text.
    lines = wrap_urdu_text(
        hadith["text"],
        draw,
        hadith_font,
        WIDTH - 180
    )

    # Allow more lines rather than cutting the Hadith.
    if len(lines) > 17:

        # Reduce font size if needed.
        hadith_font = ImageFont.truetype(
            font_path,
            45
        )

        lines = wrap_urdu_text(
            hadith["text"],
            draw,
            hadith_font,
            WIDTH - 180
        )

    if len(lines) > 20:
        raise RuntimeError(
            "Hadith is too long to fit safely "
            "inside the video."
        )

    line_height = 88

    total_height = (
        len(lines) *
        line_height
    )

    start_y = (
        820 -
        total_height / 2
    )

    for index, original_line in enumerate(lines):

        line = shape_urdu(
            original_line
        )

        bbox = draw.textbbox(
            (0, 0),
            line,
            font=hadith_font
        )

        line_width = (
            bbox[2] - bbox[0]
        )

        x = (
            WIDTH -
            line_width
        ) / 2

        y = (
            start_y +
            index * line_height
        )

        draw.text(
            (x, y),
            line,
            font=hadith_font,
            fill=(255, 255, 255, 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0, 255)
        )

    # Exact source reference.
    reference_text = (
        "حوالہ: " +
        hadith["reference"]
    )

    reference_text = shape_urdu(
        reference_text
    )

    bbox = draw.textbbox(
        (0, 0),
        reference_text,
        font=reference_font
    )

    reference_width = (
        bbox[2] - bbox[0]
    )

    draw.text(
        (
            (WIDTH - reference_width) / 2,
            1460
        ),
        reference_text,
        font=reference_font,
        fill=(245, 245, 245, 255),
        stroke_width=2,
        stroke_fill=(0, 0, 0, 255)
    )

    return overlay


# ============================================================
# VIDEO
# ============================================================

def make_video(
    background,
    text_overlay,
    output_path
):

    bg_path = (
        WORK_DIR /
        "background.jpg"
    )

    text_path = (
        WORK_DIR /
        "text_overlay.png"
    )

    background.save(
        bg_path,
        "JPEG",
        quality=95
    )

    text_overlay.save(
        text_path
    )

    if not AUDIO_FILE.exists():
        raise RuntimeError(
            f"Audio file missing: {AUDIO_FILE}"
        )

    total_frames = (
        VIDEO_DURATION *
        FPS
    )

    filter_complex = (
        "[0:v]"
        "scale=1200:2133,"
        "zoompan="
        "z='min(zoom+0.00035,1.10)':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        f"d={total_frames}:"
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

    command = [
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

        "-movflags",
        "+faststart",

        str(output_path)
    ]

    log(
        "Creating 75-second video..."
    )

    subprocess.run(
        command,
        check=True
    )


# ============================================================
# METADATA
# ============================================================

def create_metadata(
    hadith,
    photo
):

    metadata_dir = (
        OUTPUT_DIR /
        "metadata"
    )

    metadata_dir.mkdir(
        exist_ok=True
    )

    reference = hadith["reference"]
    source_url = hadith["url"]

    photographer = photo[
        "photographer"
    ]

    photographer_url = photo[
        "photographer_url"
    ]

    pexels_url = photo[
        "pexels_url"
    ]

    youtube = f"""TITLE:
Hadith | {reference} | Urdu Islamic Reminder

DESCRIPTION:
Urdu Hadith from Sunnah.com.

Reference:
{reference}

Hadith source:
Sunnah.com
{source_url}

Photo:
Photo by {photographer} on Pexels
{photographer_url}
{pexels_url}

#Hadith #IslamicReminder #IslamicShorts #Urdu #Islam #Muslim
"""

    tiktok = f"""TITLE:
Urdu Hadith | {reference}

DESCRIPTION:
A Hadith from Sunnah.com in Urdu.

Reference:
{reference}

Source:
Sunnah.com
{source_url}

Photo:
Photo by {photographer} on Pexels
{pexels_url}

#Hadith #IslamicTikTok #IslamicReminder #UrduIslamic #Islam #Muslim
"""

    instagram = f"""TITLE:
Urdu Hadith | {reference}

DESCRIPTION:
A Hadith from Sunnah.com in Urdu.

Reference:
{reference}

Source:
Sunnah.com
{source_url}

Photo:
Photo by {photographer} on Pexels
{pexels_url}

#Hadith #IslamicReels #IslamicReminder #Urdu #Islam #Muslim
"""

    facebook = f"""TITLE:
Urdu Hadith | {reference}

DESCRIPTION:
A Hadith from Sunnah.com in Urdu.

Reference:
{reference}

Source:
Sunnah.com
{source_url}

Photo:
Photo by {photographer} on Pexels
{pexels_url}

#Hadith #IslamicReminder #Islam #Urdu #Muslim
"""

    files = {
        "youtube.txt": youtube,
        "tiktok.txt": tiktok,
        "instagram.txt": instagram,
        "facebook.txt": facebook,
    }

    for filename, content in files.items():

        (
            metadata_dir /
            filename
        ).write_text(
            content,
            encoding="utf-8"
        )


# ============================================================
# SAVE USED HADITH
# ============================================================

def save_hadith_record(
    hadith
):

    used = load_used()

    key = (
        f"{hadith['collection']}:"
        f"{hadith['number']}"
    )

    used[key] = {
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "reference": hadith[
            "reference"
        ],

        "url": hadith[
            "url"
        ],
    }

    save_used(
        used
    )


# ============================================================
# MAIN
# ============================================================

def main():

    log(
        "========================================"
    )

    log(
        "Islamic Hadith Video Generator"
    )

    log(
        "========================================"
    )

    # 1. Get exact Hadith from Sunnah.com.
    hadith = get_hadith_from_sunnah()

    log(
        f"Hadith: {hadith['reference']}"
    )

    log(
        f"Source: {hadith['url']}"
    )

    # 2. Get Pexels photo.
    photo = get_pexels_photo()

    log(
        f"Photo: {photo['photographer']}"
    )

    # 3. Create background.
    background = create_background(
        photo["path"]
    )

    # 4. Create Urdu Hadith overlay.
    overlay = create_text_overlay(
        hadith
    )

    # 5. Filename.
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

    # 7. Create social metadata.
    create_metadata(
        hadith,
        photo
    )

    # 8. Only after successful video creation,
    #    mark the Hadith as used.
    save_hadith_record(
        hadith
    )

    log(
        "========================================"
    )

    log(
        "VIDEO CREATED SUCCESSFULLY"
    )

    log(
        f"Video: {video_path}"
    )

    log(
        "Metadata: output/metadata/"
    )

    log(
        "========================================"
    )


if __name__ == "__main__":
    main()
