"""Builds data/extracts/synthetic_registry.csv.

This is a FAKE land registry. It stands in for an Ardhisasa search result,
which we can't get during the hackathon. Every row has synthetic=true and
every owner name is made up. It says nothing about who really owns a parcel.

parcel_id uses the same IDs as data/normalizer.py (e.g. RL:NAIROBI/BLOCK 9/123),
so registry rows join to Gazette parcel refs on the same key.

Rows set up on purpose for eval/cases.yaml:
  - RL:NAIROBI/BLOCK 9/123, title serial 5253012, inside the cancelled range
    5253001-5253367 (case 1, STOP)
  - RL:N/WANGA/MATUNGU/954, has 2024 Gazette notices (cases 1b and 2)
  - RL:N/WANGA/MATUNGU/955, its neighbour with no notices (gate A)
  - RL:KAJIADO/KITENGELA/2830, no notices in 2022-2024 (case 3)
  - LR:12715/288 and LR:12715/289, near-identical numbers (web mock, gate A)

Filler rows never reuse a parcel that appears in the Gazette extract, so a
random row can't accidentally pick up real notices.

Run:  python data/scripts/make_synthetic_registry.py
"""
import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATA))
import normalizer  # noqa: E402

OUT = DATA / "extracts" / "synthetic_registry.csv"

FIRST = ["Wanjiru", "Otieno", "Kamau", "Achieng", "Mutua", "Chebet", "Njoroge", "Akinyi",
         "Kiprop", "Wambui", "Ochieng", "Muthoni", "Kibet", "Nyambura", "Omondi", "Jepkosgei"]
LAST = ["Testowner", "Sampleson", "Demoyo", "Fakerson", "Placeholder", "Mockery"]

# (how a buyer might type the section, district)
SECTIONS = [
    ("Nairobi/Block 9", "Nairobi"),
    ("Kajiado/Kitengela", "Kajiado"),
    ("Kiambu/Ruiru East", "Kiambu"),
    ("Nakuru/Municipality Block 4", "Nakuru"),
    ("Machakos/Mavoko", "Machakos"),
]

FIXED = [
    ("Nairobi/Block 9/123", "Nairobi", "5253012", "serial in cancelled range 5253001-5253367 (case 1)"),
    ("N/Wanga/Matungu/954", "Kakamega", None, "has 2024 Gazette notices (cases 1b and 2)"),
    ("N/Wanga/Matungu/955", "Kakamega", None, "neighbour of 954, no notices (gate A)"),
    ("Kajiado/Kitengela/2830", "Kajiado", None, "no notices in 2022-2024 (case 3)"),
    ("LR 12715/288", "Nairobi", None, "near-identical neighbour of 12715/289 (web mock, gate A)"),
    ("LR 12715/289", "Nairobi", None, "near-identical neighbour of 12715/288 (web mock, gate A)"),
]

random.seed(2026)  # same output every run


def owner():
    return f"{random.choice(FIRST)} {random.choice(LAST)}"


def serial():
    # well outside the cancelled range unless a row asks for it
    return str(random.randint(5300000, 5399999))


def registered_on():
    return date(2008, 1, 1) + timedelta(days=random.randint(0, 6000))


def gazette_parcels() -> set[str]:
    """Every parcel ID mentioned in the Gazette extract (empty if the parquet isn't there)."""
    try:
        import pyarrow.parquet as pq
        refs = pq.read_table(normalizer.NOTICES_PARQUET, columns=["parcel_refs"]).column("parcel_refs").to_pylist()
    except (FileNotFoundError, ImportError) as err:
        print(f"warning: can't read the notices ({err}), filler rows aren't checked against them")
        return set()
    keys = set()
    for row in refs:
        for ref in row or []:
            keys.update(p.key for p in normalizer.normalise_all(ref))
    return keys


def main():
    in_gazette = gazette_parcels()
    rows, seen = [], set()

    def add(parcel_input, district, title_serial, note):
        pid = normalizer.normalise(parcel_input)
        if pid is None:
            raise ValueError(f"normaliser can't read {parcel_input!r}")
        if pid.key in seen:
            return False
        seen.add(pid.key)
        rows.append(dict(
            parcel_id=pid.key,
            parcel_input=parcel_input,
            district=district,
            title_serial=title_serial or serial(),
            registered_owner=owner(),
            tenure=random.choice(["Freehold", "Leasehold (99 yrs)"]),
            area_ha=round(random.uniform(0.04, 2.0), 3),
            registered_on=registered_on().isoformat(),
            encumbrance=random.choice(["", "", "", "Charge to (fictional) Demo Bank"]),
            synthetic="true",
            note=note,
        ))
        return True

    for parcel_input, district, title_serial, note in FIXED:
        add(parcel_input, district, title_serial, note)

    for section, district in SECTIONS:
        made = 0
        while made < 5:
            parcel_input = f"{section}/{random.randint(100, 9999)}"
            if normalizer.normalise(parcel_input).key in in_gazette:
                continue  # a real parcel with notices, leave it out
            made += add(parcel_input, district, None, "")

    cols = ["parcel_id", "parcel_input", "district", "title_serial", "registered_owner", "tenure",
            "area_ha", "registered_on", "encumbrance", "synthetic", "note"]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT}")


if __name__ == "__main__":
    main()
