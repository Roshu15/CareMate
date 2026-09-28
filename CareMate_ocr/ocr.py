import requests

API_KEY = "K82343367488957"
IMAGE = "prescription.jpg"

with open(IMAGE, "rb") as file:
    response = requests.post(
        "https://api.ocr.space/parse/image",
        headers={"apikey": API_KEY},
        files={"file": file},
        data={"language": "eng", "OCREngine": "3"}
    )

result = response.json()

print(result["ParsedResults"][0]["ParsedText"])