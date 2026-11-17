
import os
import re
import csv
import subprocess
from datetime import datetime
from PIL import Image, ImageOps
import img2pdf

# ==================================================
# CONFIGURATION
# ==================================================

INPUT_FOLDER = "screenshots"
OUTPUT_PDF = "combined_screenshots.pdf"
OUTPUT_CSV = "image_order.csv"

SUPPORTED_FORMATS = (
    ".jpg", ".jpeg", ".png",
    ".heic", ".tiff", ".bmp", ".webp"
)

# ==================================================
# TIMESTAMP EXTRACTION
# ==================================================

def get_filename_datetime(filename):
    """
    Extract timestamps from macOS screenshot filenames.

    Example:
    Screenshot 2026-11-14 at 10.30.12 AM.png
    """

    patterns = [
        (
            r"(\d{4}-\d{2}-\d{2}) at "
            r"(\d{1,2})\.(\d{2})\.(\d{2}) (AM|PM)",
            "%Y-%m-%d %I.%M.%S %p"
        ),
        (
            r"(\d{4}-\d{2}-\d{2}) at "
            r"(\d{1,2})\.(\d{2})\.(\d{2})",
            "%Y-%m-%d %H.%M.%S"
        )
    ]

    for pattern, fmt in patterns:
        match = re.search(pattern, filename, re.IGNORECASE)

        if match:
            try:
                return datetime.strptime(
                    " ".join(match.groups()),
                    fmt
                )
            except ValueError:
                pass

    return None


def get_exif_datetime(filepath):
    """
    Extract image timestamps using ExifTool.
    """

    tags = [
        "DateTimeOriginal",
        "CreateDate",
        "MediaCreateDate",
        "TrackCreateDate",
        "FileModifyDate"
    ]

    for tag in tags:

        try:
            result = subprocess.run(
                [
                    "exiftool",
                    "-s3",
                    f"-{tag}",
                    filepath
                ],
                capture_output=True,
                text=True,
                timeout=10
            )

            value = result.stdout.strip()

            if not value:
                continue

            formats = [
                "%Y:%m:%d %H:%M:%S%z",
                "%Y:%m:%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S"
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue

        except Exception:
            continue

    return None


def get_image_datetime(filepath):

    filename = os.path.basename(filepath)

    # 1. Try macOS screenshot filename
    timestamp = get_filename_datetime(filename)

    if timestamp:
        return timestamp, "Filename"

    # 2. Try EXIF metadata
    timestamp = get_exif_datetime(filepath)

    if timestamp:
        return timestamp, "EXIF"

    # 3. Fall back to filesystem modification time
    timestamp = datetime.fromtimestamp(
        os.path.getmtime(filepath)
    )

    return timestamp, "File Modified Time"


# ==================================================
# IMAGE COLLECTION
# ==================================================

def get_images(folder):

    images = []

    for filename in os.listdir(folder):

        filepath = os.path.join(folder, filename)

        if not os.path.isfile(filepath):
            continue

        if filename.lower().endswith(SUPPORTED_FORMATS):

            timestamp, source = get_image_datetime(filepath)

            images.append({
                "filename": filename,
                "filepath": filepath,
                "datetime": timestamp,
                "source": source
            })

    return images


# ==================================================
# CHRONOLOGICAL SORTING
# ==================================================

def normalize_datetime(dt):
    """
    Convert aware timestamps to local time and remove
    timezone information so all timestamps are comparable.

    Naive timestamps are assumed to be local time.
    """

    if dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)

    return dt


def sort_images(images):

    for image in images:
        image["datetime"] = normalize_datetime(
            image["datetime"]
        )

    return sorted(
        images,
        key=lambda image: image["datetime"]
    )


# ==================================================
# PDF GENERATION
# ==================================================

def generate_pdf(images, output_pdf):

    pdf_images = []
    temporary_files = []

    for image in images:

        filepath = image["filepath"]

        try:
            with Image.open(filepath) as img:

                # Apply orientation stored in image metadata
                img = ImageOps.exif_transpose(img)

                # JPEG and PNG can be embedded directly
                if img.format in ("JPEG", "PNG"):

                    pdf_images.append(filepath)

                else:

                    # Convert other formats to JPEG
                    converted = os.path.join(
                        INPUT_FOLDER,
                        "_temp_" + image["filename"] + ".jpg"
                    )

                    img.convert("RGB").save(
                        converted,
                        "JPEG",
                        quality=95
                    )

                    pdf_images.append(converted)
                    temporary_files.append(converted)

        except Exception as error:

            print(
                f"Skipping {image['filename']}: {error}"
            )

    if pdf_images:

        with open(output_pdf, "wb") as pdf_file:

            pdf_file.write(
                img2pdf.convert(pdf_images)
            )

        print(f"\nPDF successfully created: {output_pdf}")

    else:

        print("No valid images available for PDF.")

    # Remove temporary converted images
    for filepath in temporary_files:

        if os.path.exists(filepath):
            os.remove(filepath)


# ==================================================
# CSV REPORT
# ==================================================

def generate_csv(images, output_csv):

    with open(
        output_csv,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.writer(file)

        writer.writerow([
            "Order",
            "Filename",
            "Date",
            "Time",
            "Timestamp Source"
        ])

        for index, image in enumerate(images, start=1):

            writer.writerow([
                index,
                image["filename"],
                image["datetime"].date(),
                image["datetime"].time(),
                image["source"]
            ])

    print(f"CSV report created: {output_csv}")


# ==================================================
# MAIN
# ==================================================

def main():

    if not os.path.isdir(INPUT_FOLDER):

        print("Input folder does not exist!")
        return

    print("\nReading images...")

    images = get_images(INPUT_FOLDER)

    if not images:

        print("No supported images found!")
        return

    print(f"Found {len(images)} images.")

    print("\nSorting images chronologically...")

    images = sort_images(images)

    print("\n========== IMAGE ORDER ==========\n")

    for index, image in enumerate(images, start=1):

        print(
            f"{index:03d}. "
            f"{image['filename']} | "
            f"{image['datetime']} | "
            f"Source: {image['source']}"
        )

    print("\n=================================")

    print("\nGenerating PDF...")

    generate_pdf(images, OUTPUT_PDF)

    generate_csv(images, OUTPUT_CSV)

    print("\nAll tasks completed!")


if __name__ == "__main__":
    main()
