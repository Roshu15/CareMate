import requests
from datetime import datetime

from medicine_extractor import extract_medicines
from rxnorm import get_rxnorm_medicine
from schedule_generation import generate_schedule
from database import add_medicine


API_KEY = "K82343367488957"


def process_prescription(image_path):

    # Prescription start date
    start_date = datetime.now().strftime("%Y-%m-%d")

    # ---------------- OCR ----------------
    print("\n Reading prescription...")

    with open(image_path, "rb") as file:
        response = requests.post(
            "https://api.ocr.space/parse/image",
            headers={"apikey": API_KEY},
            files={"file": file},
            data={
                "language": "eng",
                "OCREngine": "3"
            }
        )

    result = response.json()

    if result.get("IsErroredOnProcessing"):
        print(" OCR failed")
        return

    extracted_text = result["ParsedResults"][0]["ParsedText"]

    print("\n========== OCR TEXT ==========")
    print(extracted_text)

    # ---------------- MEDICINE EXTRACTION ----------------
    print("\n Extracting medicines...")

    medicines = extract_medicines(extracted_text)

    if not medicines:
        print(" No medicines found.")
        return

    # ---------------- RXNORM + SCHEDULE + DATABASE ----------------
    print("\n========== MEDICINE DETAILS ==========")

    for medicine in medicines:

        name = medicine["medicine"]
        dose = medicine["dose"]
        frequency = medicine["frequency"]
        timing = medicine["timing"]
        duration = medicine["duration"]

        # RxNorm
        rxcui = get_rxnorm_medicine(name)

        # Generate schedule
        schedule = generate_schedule(
            name,
            dose,
            frequency,
            timing,
            duration
        )

        reminder_times = schedule["reminder_times"]

        print("\nMedicine:", name)
        print("Dose:", dose)
        print("Frequency:", frequency)
        print("Timing:", timing)
        print("Duration:", duration, "days")
        print("Start Date:", start_date)
        print("RxCUI:", rxcui)
        print("Reminder Times:", reminder_times)

        # Save to database
        add_medicine(
            name,
            dose,
            frequency,
            timing,
            duration,
            start_date,
            reminder_times,
            rxcui
        )

        print(" Saved to database")
        print("----------------------------------------")


# ---------------- RUN PROGRAM ----------------

if __name__ == "__main__":

    image_path = "prescription.jpg"

    process_prescription(image_path)