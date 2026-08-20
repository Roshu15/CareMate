"""
Step 1 (v2): Test OCR using EasyOCR instead of Tesseract.

Why this version: Tesseract needs a separate program installed outside
Python (which was causing install errors). EasyOCR is pure Python -
'pip install easyocr' is the ONLY install step. No .exe, no PATH setup.

First run will download recognition models automatically (~a couple
hundred MB, one-time only, needs internet). Every run after that is
instant and works fully offline.

Usage:
    python step1_test_ocr_easyocr.py path/to/your/image.jpg     -> test ONE image
    python step1_test_ocr_easyocr.py                            -> test the 3 sample images
                                                                     if they're in this folder
"""

import sys
import os

DEFAULT_IMAGES = [
    "sample_prescription.jpg",
    "sample_strip1.jpg",
    "sample_strip2.jpg",
]


def get_reader():
    """Load EasyOCR once. First call downloads models if not cached yet."""
    import easyocr
    print("Loading OCR model (first run downloads it - may take a minute)...")
    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    print("Model ready.\n")
    return reader


def run_ocr(reader, image_path):
    if not os.path.exists(image_path):
        print(f"Skipping '{image_path}' - file not found in this folder.")
        return

    # detail=0 returns just the text (no bounding boxes/confidence scores)
    # paragraph=True merges nearby text into readable lines/paragraphs
    results = reader.readtext(image_path, detail=0, paragraph=True)

    print("=" * 50)
    print(f"OCR OUTPUT - {image_path}")
    print("=" * 50)
    for line in results:
        print(line)
    print()


if __name__ == "__main__":
    reader = get_reader()

    if len(sys.argv) == 2:
        run_ocr(reader, sys.argv[1])
    elif len(sys.argv) == 1:
        print("No image path given - testing default sample images in this folder:")
        print(", ".join(DEFAULT_IMAGES))
        print()
        found_any = False
        for path in DEFAULT_IMAGES:
            if os.path.exists(path):
                found_any = True
                run_ocr(reader, path)
        if not found_any:
            print("None of the default sample images were found in this folder.")
            print("Either place them here, or run:")
            print("  python step1_test_ocr_easyocr.py your_image.jpg")
    else:
        print("Usage:")
        print("  python step1_test_ocr_easyocr.py path/to/image.jpg   (test one image)")
        print("  python step1_test_ocr_easyocr.py                     (test default samples)")
        sys.exit(1)