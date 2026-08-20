"""
Step 2: Measure OCR accuracy against known-correct answers (ground truth).

Why this matters: Step 1 just showed us OCR output and we eyeballed it.
That's fine for a first look, but from here on we need an actual NUMBER
to know whether OCR (or later, our parsing/matching code) is getting
better or worse when we change something.

How it works:
    1. We already know the "correct answer" for each sample image
       (stored in ground_truth.json) - we know this because I generated
       those images myself.
    2. This script runs OCR on each image, then checks whether each
       expected piece of information (medicine name, dosage, frequency,
       etc.) can be found in the OCR text - allowing for small OCR
       mistakes (fuzzy matching), not requiring an exact character match.
    3. It prints a report: what was found, what was missed, and an
       overall accuracy percentage.

Usage:
    python step2_test_accuracy.py
"""

import os
import json
import difflib
import re

GROUND_TRUTH_FILE = "ground_truth.json"


def normalize(text):
    """Lowercase and strip out punctuation/extra spaces so minor
    formatting differences don't count as mismatches."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fuzzy_contains(haystack, needle, threshold=0.75):
    """Check whether 'needle' appears somewhere inside 'haystack',
    allowing for minor OCR mistakes (not requiring an exact match).

    Returns (found: bool, best_score: float 0-1)
    """
    haystack = normalize(haystack)
    needle = normalize(needle)

    if not needle:
        return True, 1.0
    if needle in haystack:
        return True, 1.0

    n = len(needle)
    best = 0.0
    # slide a window roughly the size of 'needle' across the haystack
    for i in range(0, max(1, len(haystack) - n + 1)):
        window = haystack[i:i + n]
        ratio = difflib.SequenceMatcher(None, window, needle).ratio()
        if ratio > best:
            best = ratio
        if best == 1.0:
            break

    return best >= threshold, round(best, 2)


def get_reader():
    import easyocr
    print("Loading OCR model...")
    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    print("Model ready.\n")
    return reader


def run_ocr_text(reader, image_path):
    results = reader.readtext(image_path, detail=0, paragraph=True)
    return " ".join(results)


def score_prescription(ocr_text, expected):
    """Check each medicine's name, dosage, frequency, and timing
    individually - so we know exactly which pieces OCR struggles with."""
    total = 0
    passed = 0
    details = []

    for med in expected["medicines"]:
        for field in ["name", "dosage", "frequency", "timing"]:
            total += 1
            found, score = fuzzy_contains(ocr_text, med[field])
            if found:
                passed += 1
            details.append((f"{med['name']} -> {field} ('{med[field]}')", found, score))

    return passed, total, details


def score_strip(ocr_text, expected):
    total = 0
    passed = 0
    details = []

    for field in ["brand", "medicine_name", "dosage"]:
        total += 1
        found, score = fuzzy_contains(ocr_text, expected[field])
        if found:
            passed += 1
        details.append((f"{field} ('{expected[field]}')", found, score))

    return passed, total, details


def print_report(image_path, passed, total, details):
    pct = (passed / total * 100) if total else 0
    print("=" * 60)
    print(f"{image_path}  ->  {passed}/{total} fields matched ({pct:.0f}%)")
    print("=" * 60)
    for label, found, score in details:
        mark = "PASS" if found else "FAIL"
        print(f"  [{mark}] {label:45s} similarity={score}")
    print()


if __name__ == "__main__":
    if not os.path.exists(GROUND_TRUTH_FILE):
        print(f"Could not find {GROUND_TRUTH_FILE} - make sure it's in this folder.")
        raise SystemExit(1)

    with open(GROUND_TRUTH_FILE) as f:
        ground_truth = json.load(f)

    reader = get_reader()

    total_passed = 0
    total_fields = 0

    for image_path, expected in ground_truth.items():
        if not os.path.exists(image_path):
            print(f"Skipping {image_path} - file not found in this folder.\n")
            continue

        ocr_text = run_ocr_text(reader, image_path)

        if expected["type"] == "prescription":
            passed, total, details = score_prescription(ocr_text, expected)
        else:
            passed, total, details = score_strip(ocr_text, expected)

        print_report(image_path, passed, total, details)
        total_passed += passed
        total_fields += total

    overall_pct = (total_passed / total_fields * 100) if total_fields else 0
    print("#" * 60)
    print(f"OVERALL ACCURACY: {total_passed}/{total_fields} fields ({overall_pct:.0f}%)")
    print("#" * 60)