"""Create editable default reminder times; the patient/caretaker should confirm them."""
DEFAULTS = {"1-0-0": ["08:00"], "0-1-0": ["13:00"], "0-0-1": ["20:00"],
            "1-0-1": ["08:00", "20:00"], "1-1-0": ["08:00", "13:00"],
            "0-1-1": ["13:00", "20:00"], "1-1-1": ["08:00", "13:00", "20:00"]}


def generate_schedule(medicine, dose, frequency, timing, duration):
    return {"medicine": medicine, "dose": dose, "timing": timing,
            "duration": duration, "reminder_times": DEFAULTS.get(frequency, [])}
