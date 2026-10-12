from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.medicine_extractor import extract_medicines
from backend.rxnorm import get_rxnorm_medicine
from backend.schedule_generation import generate_schedule
from backend.database import add_medicine
from backend.ocr import extract_text


def process_prescription(image_path):

    # Prescription start date
    start_date = datetime.now().strftime("%Y-%m-%d")

    # ---------------- OCR ----------------
    print("\n Reading prescription...")

    with open(image_path, "rb") as file:
        extracted_text = extract_text(file.read(), image_path)

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

    image_path = PROJECT_ROOT / "prescription.jpg"

    process_prescription(image_path)
