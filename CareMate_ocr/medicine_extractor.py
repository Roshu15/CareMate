import re


def extract_medicines(text):

    medicines = []

    # Split prescription into numbered medicine sections
    sections = re.split(r'\n(?=\d+\.)', text)

    for section in sections:

        # Medicine name and dose
        medicine_match = re.search(
            r'\d+\.\s*(?:Tab\.|Cap\.|Syrup\.|Inj\.)?\s*'
            r'([A-Za-z0-9\s]+?)\s+(\d+\s*(?:mg|g|ml|mcg|IU|K))',
            section,
            re.IGNORECASE
        )

        if not medicine_match:
            continue

        medicine_name = medicine_match.group(1).strip()
        dose = medicine_match.group(2).strip()

        # Frequency
        frequency_match = re.search(
            r'(\d-\d-\d)',
            section
        )

        frequency = frequency_match.group(1) if frequency_match else "Unknown"

        # Timing
        timing_match = re.search(
            r'\((.*?)\)',
            section
        )

        timing = timing_match.group(1).strip() if timing_match else "Not specified"

        # Duration
        duration_match = re.search(
            r'(\d+)\s*days?',
            section,
            re.IGNORECASE
        )

        duration = int(duration_match.group(1)) if duration_match else 0

        medicines.append({
            "medicine": medicine_name,
            "dose": dose,
            "frequency": frequency,
            "timing": timing,
            "duration": duration
        })

    return medicines