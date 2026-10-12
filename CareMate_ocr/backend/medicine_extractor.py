"""Conservative extraction of common prescription formats from OCR text."""
import re
import difflib
from pathlib import Path

_DOSE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|μg|g|ml|mL|iu|units?|%)\b|\b\d+\s*[kK]\b", re.I)
_FREQUENCY = re.compile(r"\b[01]-[01]-[01]\b")
_DURATION = re.compile(r"\b(\d{1,3})\s*(?:days?|dys?)\b", re.I)
_DICTIONARY_PATH = Path(__file__).resolve().parents[2] / "medicinedictionary.txt"
try:
    _MEDICINE_NAMES = [line.strip() for line in _DICTIONARY_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
except OSError:
    _MEDICINE_NAMES = []


def _correct_name(raw_name):
    normalized = re.sub(r"[^a-z0-9]", "", raw_name.lower())
    dictionary = {re.sub(r"[^a-z0-9]", "", item.lower()): item for item in _MEDICINE_NAMES}
    if normalized in dictionary:
        return dictionary[normalized], 1.0, "exact_match"
    matches = difflib.get_close_matches(normalized, dictionary.keys(), n=1, cutoff=0.82)
    if not matches:
        return raw_name, None, "unmatched"
    best = matches[0]
    confidence = difflib.SequenceMatcher(None, normalized, best).ratio()
    return dictionary[best], round(confidence, 2), "suggested_correction"


def extract_medicines(text):
    medicines = []
    sections = [s.strip() for s in re.split(r"(?:^|\n)\s*\d+[.)]\s*", text) if s.strip()]
    if len(sections) <= 1:
        sections = [s.strip() for s in re.split(r"\n+", text) if s.strip()]
    for section in sections:
        dose_match = _DOSE.search(section)
        if not dose_match:
            continue
        dose = dose_match.group(0).strip()
        prefix = section[:dose_match.start()]
        prefix = re.sub(r"^\s*(?:tab(?:let)?|cap(?:sule)?|syrup|inj(?:ection)?)\.?\s*", "", prefix, flags=re.I)
        prefix = re.sub(r"^\s*\d+[.)]\s*", "", prefix)
        name = re.sub(r"[^A-Za-z0-9+ -]", " ", prefix).strip(" -:.")
        name = re.sub(r"\s+", " ", name)
        if not name or len(name) > 80:
            continue
        freq_match = _FREQUENCY.search(section)
        duration_match = _DURATION.search(section)
        timing_match = re.search(r"\b(before|after|with)\s+(?:the\s+)?(?:food|meal|breakfast|lunch|dinner)\b", section, re.I)
        corrected, confidence, name_status = _correct_name(name)
        medicines.append({
            "medicine": corrected, "raw_medicine": name, "name_confidence": confidence,
            "name_status": name_status, "dose": dose,
            "frequency": freq_match.group(0) if freq_match else "Unknown",
            "timing": timing_match.group(0).strip() if timing_match else "Not specified",
            "duration": int(duration_match.group(1)) if duration_match else 0,
            "needs_review": True,
        })
    return medicines
