"""
Step 2: Correct OCR's medicine-name guesses using a real dictionary.

The idea: instead of trusting whatever OCR read (which might be
"Paracetmol", "Paracetarnol", "PARACETAMOI", etc.), we compare it
against a list of REAL medicine names and snap it to the closest match
- but only if we're confident enough. If nothing matches well, we
say so honestly instead of guessing.

Usage:
    python step2b_medicine_correction.py
    -> runs a demo showing correction on realistic OCR mistakes
"""

import difflib
import re

DICTIONARY_FILE = "medicines_dictionary.txt"


def load_dictionary(path):
    with open(path) as f:
        return [line.strip() for line in f if line.strip()]


def normalize(text):
    """Lowercase, strip punctuation, so 'PARACETAMOI.' and 'paracetamol'
    are compared fairly."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return text.strip()


def correct_medicine_name(raw_name, dictionary, threshold=0.72):
    """
    Try to match a possibly-garbled OCR string against the real
    medicine dictionary.

    Returns a dict with:
        - input: what OCR gave us
        - corrected: our best guess at the real name (or None)
        - confidence: how close the match was (0-1)
        - status: "corrected" / "exact_match" / "no_confident_match"
    """
    normalized_input = normalize(raw_name)
    normalized_dict = {normalize(name): name for name in dictionary}

    # Exact match first (fast path, no correction needed)
    if normalized_input in normalized_dict:
        return {
            "input": raw_name,
            "corrected": normalized_dict[normalized_input],
            "confidence": 1.0,
            "status": "exact_match",
        }

    # Fuzzy match against every dictionary entry
    matches = difflib.get_close_matches(
        normalized_input, normalized_dict.keys(), n=1, cutoff=threshold
    )

    if matches:
        best = matches[0]
        score = difflib.SequenceMatcher(None, normalized_input, best).ratio()
        return {
            "input": raw_name,
            "corrected": normalized_dict[best],
            "confidence": round(score, 2),
            "status": "corrected",
        }

    # Nothing confident enough - be honest, don't guess
    return {
        "input": raw_name,
        "corrected": None,
        "confidence": 0.0,
        "status": "no_confident_match",
    }


if __name__ == "__main__":
    dictionary = load_dictionary(DICTIONARY_FILE)
    print(f"Loaded {len(dictionary)} known medicine names.\n")

    # Realistic OCR mistakes - the kind we've actually seen in testing,
    # plus a few more we're likely to hit with real photos.
    test_cases = [
        "Paracetmol",           # missing letter
        "PARACETAMOI",          # L misread as I
        "Amlodipin",            # missing final e
        "AMLOKIND",             # brand name, correct
        "Crocln",               # i misread as l
        "Metfrmin",             # missing letter
        "Azithromycln",         # i misread as l
        "Xyzstuffnotamedicine", # should fail - not a real medicine
    ]

    for raw in test_cases:
        result = correct_medicine_name(raw, dictionary)
        if result["status"] == "no_confident_match":
            print(f"  '{raw}'  ->  NO CONFIDENT MATCH (needs manual check)")
        else:
            print(f"  '{raw}'  ->  '{result['corrected']}'  "
                  f"(confidence: {result['confidence']}, {result['status']})")