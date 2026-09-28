import requests


def get_rxnorm_medicine(medicine_name):

    url = "https://rxnav.nlm.nih.gov/REST/rxcui.json"

    params = {
        "name": medicine_name
    }

    response = requests.get(url, params=params)

    if response.status_code != 200:
        return None

    data = response.json()

    rxcui_list = data.get("idGroup", {}).get("rxnormId")

    if not rxcui_list:
        return None

    return rxcui_list[0]


# Medicines extracted from prescription
medicines = [
    "Paracetamol",
    "Amlodipine",
    "Vitamin D3",
    "Metformin"
]

for medicine in medicines:

    rxcui = get_rxnorm_medicine(medicine)

    