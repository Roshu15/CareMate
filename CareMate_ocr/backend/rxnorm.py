import requests


def get_rxnorm_medicine(medicine_name):

    url = "https://rxnav.nlm.nih.gov/REST/rxcui.json"

    params = {
        "name": medicine_name
    }

    response = requests.get(url, params=params, timeout=8)

    if response.status_code != 200:
        return None

    data = response.json()

    rxcui_list = data.get("idGroup", {}).get("rxnormId")

    if not rxcui_list:
        return None

    return rxcui_list[0]


if __name__ == "__main__":
    for medicine in ("Paracetamol", "Amlodipine", "Vitamin D3", "Metformin"):
        print(medicine, get_rxnorm_medicine(medicine))
