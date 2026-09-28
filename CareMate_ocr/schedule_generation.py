def generate_schedule(medicine, dose, frequency, timing, duration):

    time_slots = {
        "1-0-0": ["08:00 AM"],
        "0-1-0": ["01:00 PM"],
        "0-0-1": ["08:00 PM"],
        "1-0-1": ["08:00 AM", "08:00 PM"],
        "1-1-0": ["08:00 AM", "01:00 PM"],
        "0-1-1": ["01:00 PM", "08:00 PM"],
        "1-1-1": ["08:00 AM", "01:00 PM", "08:00 PM"]
    }

    times = time_slots.get(frequency, [])

    return {
        "medicine": medicine,
        "dose": dose,
        "timing": timing,
        "duration": duration,
        "reminder_times": times
    }


medicines = [
    ("Paracetamol", "500mg", "1-0-1", "After food", 5),
    ("Amlodipine", "5mg", "1-0-0", "Before breakfast", 30),
    ("Vitamin D3", "60K", "0-0-1", "After dinner", 10),
    ("Metformin", "500mg", "1-0-1", "After food", 30)
]


for medicine in medicines:

    schedule = generate_schedule(*medicine)

    