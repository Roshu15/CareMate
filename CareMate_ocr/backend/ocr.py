"""Small OCR.space client used by the API and standalone scripts."""
import os


def extract_text(image_bytes, filename="prescription.jpg", content_type="image/jpeg"):
    api_key = os.getenv("OCR_SPACE_API_KEY")
    if not api_key:
        raise RuntimeError("Set OCR_SPACE_API_KEY in the environment")
    import requests
    response = requests.post(
        "https://api.ocr.space/parse/image", headers={"apikey": api_key},
        files={"file": (filename, image_bytes, content_type)},
        data={"language": "eng", "OCREngine": "3"}, timeout=45,
    )
    response.raise_for_status()
    result = response.json()
    if result.get("IsErroredOnProcessing"):
        raise RuntimeError(str(result.get("ErrorMessage", "OCR failed")))
    parsed = result.get("ParsedResults") or []
    return parsed[0].get("ParsedText", "") if parsed else ""


if __name__ == "__main__":
    from pathlib import Path
    image_path = Path(__file__).resolve().parents[1] / "prescription.jpg"
    print(extract_text(image_path.read_bytes(), image_path.name))
