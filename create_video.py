import os
import json
import random
import time
import subprocess
from pathlib import Path

import requests

from PIL import (
    Image,
    ImageDraw,
    ImageFont
)

import arabic_reshaper

from bidi.algorithm import get_display


# ============================================================
# SETTINGS
# ============================================================

PEXELS_API_KEY = os.getenv(
    "PEXELS_API_KEY"
)

WIDTH = 1080
HEIGHT = 1920

VIDEO_SECONDS = 75

BASE_DIR = Path(
    __file__
).resolve().parent

DATA_DIR = (
    BASE_DIR / "data"
)

OUTPUT_DIR = (
    BASE_DIR / "output"
)

WORK_DIR = (
    BASE_DIR / "work"
)

AUDIO_FILE = (
    BASE_DIR
    / "audio"
    / "islamic_background.mp3"
)

FONT_FILE = (
    BASE_DIR
    / "fonts"
    / "NotoNaskhArabic-Regular.ttf"
)

USED_FILE = (
    BASE_DIR
    / "used_hadith.json"
)


OUTPUT_DIR.mkdir(
    exist_ok=True
)

WORK_DIR.mkdir(
    exist_ok=True
)


# ============================================================
# HADITH DATABASE
# ============================================================

DATABASES = {
    "bukhari": {
        "file":
            DATA_DIR / "urd-bukhari.json",

        "name":
            "Sahih al-Bukhari",
    },

    "muslim": {
        "file":
            DATA_DIR / "urd-muslim.json",

        "name":
            "Sahih Muslim",
    },
}


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

        if isinstance(
            data,
            dict
        ):

            return set(
                data.keys()
            )

        if isinstance(
            data,
            list
        ):

            return set(data)

    except Exception as e:

        print(
            "Could not read used_hadith.json:",
            e
        )

    return set()


def save_used(used):

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
# LOAD DATABASE
# ============================================================

def load_database(collection):

    info = DATABASES[
        collection
    ]

    filename = info["file"]

    if not filename.exists():

        raise FileNotFoundError(
            f"Missing Hadith database: {filename}"
        )

    print(
        f"Loading {info['name']}..."
    )

    data = json.loads(
        filename.read_text(
            encoding="utf-8"
        )
    )

    hadiths = data.get(
        "hadiths"
    )

    if not isinstance(
        hadiths,
        list
    ):

        raise RuntimeError(
            f"Invalid Hadith database: {filename}"
        )

    print(
        f"Loaded {len(hadiths)} Hadiths."
    )

    return hadiths


# ============================================================
# CLEAN HADITH TEXT
# ============================================================

def clean_hadith_text(text):

    if not text:

        return ""

    text = str(text)

    text = text.replace(
        "\u00a0",
        " "
    )

    text = text.replace(
        "\r",
        " "
    )

    text = text.replace(
        "\n",
        " "
    )

    text = " ".join(
        text.split()
    )

    return text.strip()


# ============================================================
# GET HADITH NUMBER
# ============================================================

def get_hadith_number(hadith):

    possible_keys = [
        "hadithnumber",
        "hadithNumber",
        "number",
        "id"
    ]

    for key in possible_keys:

        value = hadith.get(
            key
        )

        if value is not None:

            return str(value)

    return None


# ============================================================
# GET HADITH TEXT
# ============================================================

def get_hadith_text(hadith):

    possible_keys = [
        "text",
        "hadith",
        "body"
    ]

    for key in possible_keys:

        value = hadith.get(
            key
        )

        if isinstance(
            value,
            str
        ):

            value = clean_hadith_text(
                value
            )

            if len(value) >= 20:

                return value

    return None


# ============================================================
# SELECT HADITH
# ============================================================

def select_hadith():

    used = load_used()

    collections = list(
        DATABASES.keys()
    )

    random.shuffle(
        collections
    )

    for collection in collections:

        hadiths = load_database(
            collection
        )

        candidates = []

        for hadith in hadiths:

            number = (
                get_hadith_number(
                    hadith
                )
            )

            text = (
                get_hadith_text(
                    hadith
                )
            )

            if not number:
                continue

            if not text:
                continue

            key = (
                f"{collection}:{number}"
            )

            if key in used:
                continue

            candidates.append(
                (
                    hadith,
                    number,
                    text,
                    key
                )
            )

        if not candidates:

            print(
                f"No unused Hadiths left in {collection}."
            )

            continue

        hadith, number, text, key = (
            random.choice(
                candidates
            )
        )

        reference = (
            f"{DATABASES[collection]['name']} "
            f"{number}"
        )

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
            "Collection:",
            DATABASES[
                collection
            ]["name"]
        )

        print(
            "Number:",
            number
        )

        print(
            "Reference:",
            reference
        )

        print(
            "Text length:",
            len(text)
        )

        print(
            "=" * 60
        )

        return {
            "key": key,
            "collection": collection,
            "number": number,
            "reference": reference,
            "urdu": text
        }

    raise RuntimeError(
        "No unused Hadiths are available."
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
        "query":
            query,

        "orientation":
            "portrait",

        "size":
            "large",

        "per_page":
            15,

        "page":
            random.randint(
                1,
                3
            )
    }

    response = requests.get(
        "https://api.pexels.com/v1/search",
        headers=headers,
        params=params,
        timeout=60
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

    sources = photo.get(
        "src",
        {}
    )

    image_url = (
        sources.get(
            "portrait"
        )
        or
        sources.get(
            "large2x"
        )
        or
        sources.get(
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
        "path":
            image_path,

        "photographer":
            photo.get(
                "photographer",
                "Unknown"
            ),

        "photographer_url":
            photo.get(
                "photographer_url",
                ""
            ),

        "pexels_url":
            photo.get(
                "url",
                ""
            )
    }


# ============================================================
# URDU TEXT
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


def wrap_urdu_text(
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
            current
            + " "
            + word
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
            bbox[2]
            - bbox[0]
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
# CREATE IMAGE
# ============================================================

def create_text_image(
    background_path,
    hadith_text,
    reference
):

    image = Image.open(
        background_path
    ).convert(
        "RGB"
    )

    target_ratio = (
        WIDTH / HEIGHT
    )

    image_ratio = (
        image.width /
        image.height
    )

    # Crop to 9:16
    if image_ratio > target_ratio:

        new_width = int(
            image.height
            * target_ratio
        )

        left = (
            image.width
            - new_width
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
            image.width
            / target_ratio
        )

        top = (
            image.height
            - new_height
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

    # Dark overlay
    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, 115)
    )

    image = Image.alpha_composite(
        image.convert(
            "RGBA"
        ),
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

    lines = wrap_urdu_text(
        draw,
        hadith_text,
        font,
        880
    )

    # Keep text readable
    if len(lines) > 13:

        lines = lines[:13]

    line_spacing = 18

    line_heights = []

    for line in lines:

        shaped = shape_urdu(
            line
        )

        bbox = draw.textbbox(
            (0, 0),
            shaped,
            font=font
        )

        line_heights.append(
            bbox[3] -
            bbox[1]
        )

    total_height = (
        sum(line_heights)
        +
        (
            line_spacing
            *
            max(
                0,
                len(lines) - 1
            )
        )
    )

    start_y = (
        HEIGHT
        - total_height
    ) // 2

    # Don't put text too high
    start_y = max(
        250,
        start_y
    )

    y = start_y

    for line, height in zip(
        lines,
        line_heights
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
            bbox[2]
            - bbox[0]
        )

        x = (
            WIDTH
            - text_width
        ) // 2

        # Shadow
        draw.text(
            (
                x + 3,
                y + 3
            ),
            shaped,
            font=font,
            fill=(
                0,
                0,
                0,
                190
            )
        )

        # Text
        draw.text(
            (
                x,
                y
            ),
            shaped,
            font=font,
            fill=(
                255,
                255,
                255,
                255
            )
        )

        y += (
            height
            + line_spacing
        )

    # ========================================================
    # REFERENCE
    # ========================================================

    reference_text = (
        "حوالہ: "
        + reference
    )

    reference_text = (
        shape_urdu(
            reference_text
        )
    )

    bbox = draw.textbbox(
        (0, 0),
        reference_text,
        font=reference_font
    )

    reference_width = (
        bbox[2]
        - bbox[0]
    )

    reference_x = (
        WIDTH
        - reference_width
    ) // 2

    reference_y = (
        HEIGHT
        - 250
    )

    draw.text(
        (
            reference_x + 2,
            reference_y + 2
        ),
        reference_text,
        font=reference_font,
        fill=(
            0,
            0,
            0,
            190
        )
    )

    draw.text(
        (
            reference_x,
            reference_y
        ),
        reference_text,
        font=reference_font,
        fill=(
            255,
            255,
            255,
            255
        )
    )

    output = (
        WORK_DIR /
        "text_image.png"
    )

    image.convert(
        "RGB"
    ).save(
        output,
        quality=95
    )

    return output


# ============================================================
# CREATE VIDEO
# ============================================================

def create_video(
    image_path
):

    output = (
        OUTPUT_DIR
        /
        f"islamic_hadith_{int(time.time())}.mp4"
    )

    video_filter = (
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
        video_filter,

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

        str(output)
    ]

    print()
    print(
        "Creating video..."
    )

    subprocess.run(
        command,
        check=True
    )

    return output


# ============================================================
# METADATA
# ============================================================

def create_metadata(
    hadith,
    pexels
):

    reference = (
        hadith["reference"]
    )

    title = (
        f"{reference} | "
        "Beautiful Hadith Reminder"
    )

    description = (
        f"{reference}\n\n"
        "Daily Islamic Hadith Reminder.\n\n"
        f"Reference: {reference}\n\n"
        "Background photo by "
        f"{pexels['photographer']} "
        "via Pexels."
    )

    hashtags = (
        "#Hadith "
        "#Islam "
        "#IslamicReminder "
        "#Quran "
        "#Sunnah "
        "#Muslim "
        "#Urdu"
    )

    # YouTube
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

    # TikTok
    (
        OUTPUT_DIR /
        "tiktok_caption.txt"
    ).write_text(
        description
        + "\n\n"
        + hashtags,
        encoding="utf-8"
    )

    # Instagram
    (
        OUTPUT_DIR /
        "instagram_caption.txt"
    ).write_text(
        description
        + "\n\n"
        + hashtags,
        encoding="utf-8"
    )

    # Facebook
    (
        OUTPUT_DIR /
        "facebook_caption.txt"
    ).write_text(
        description
        + "\n\n"
        + hashtags,
        encoding="utf-8"
    )

    # Internal metadata
    metadata = {

        "collection":
            hadith[
                "collection"
            ],

        "reference":
            reference,

        "hadith_number":
            hadith[
                "number"
            ],

        "pexels_photographer":
            pexels[
                "photographer"
            ],

        "pexels_url":
            pexels[
                "pexels_url"
            ]
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

    print()
    print("=" * 60)
    print(
        "ISLAMIC HADITH VIDEO GENERATOR"
    )
    print("=" * 60)

    # --------------------------------------------------------
    # CHECK FILES
    # --------------------------------------------------------

    if not PEXELS_API_KEY:

        raise RuntimeError(
            "PEXELS_API_KEY is missing."
        )

    if not AUDIO_FILE.exists():

        raise FileNotFoundError(
            f"Missing audio: {AUDIO_FILE}"
        )

    if not FONT_FILE.exists():

        raise FileNotFoundError(
            f"Missing font: {FONT_FILE}"
        )

    # --------------------------------------------------------
    # SELECT HADITH
    # --------------------------------------------------------

    hadith = select_hadith()

    # --------------------------------------------------------
    # DOWNLOAD IMAGE
    # --------------------------------------------------------

    pexels = (
        download_pexels_image()
    )

    # --------------------------------------------------------
    # CREATE TEXT IMAGE
    # --------------------------------------------------------

    image = (
        create_text_image(
            pexels["path"],
            hadith["urdu"],
            hadith["reference"]
        )
    )

    # --------------------------------------------------------
    # CREATE VIDEO
    # --------------------------------------------------------

    video = (
        create_video(
            image
        )
    )

    # --------------------------------------------------------
    # CREATE METADATA
    # --------------------------------------------------------

    create_metadata(
        hadith,
        pexels
    )

    # --------------------------------------------------------
    # MARK HADITH AS USED
    # --------------------------------------------------------

    used = load_used()

    used.add(
        hadith["key"]
    )

    save_used(
        used
    )

    # --------------------------------------------------------
    # FINISHED
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print(
        "VIDEO CREATED SUCCESSFULLY"
    )
    print("=" * 60)

    print(
        "Video:",
        video
    )

    print(
        "Reference:",
        hadith["reference"]
    )

    print(
        "Pexels:",
        pexels[
            "photographer"
        ]
    )

    print("=" * 60)


if __name__ == "__main__":
    main()
