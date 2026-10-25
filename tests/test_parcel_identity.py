"""Near-identical parcels must never be treated as the same parcel (plan C4, eval gate A).

These run the normaliser checks the Evidence Critic relies on (same_parcel, refs_match,
find_in_text) against the demo parcels and the real Gazette text, so they work before
the agents API exists. The Gazette tests skip if the parquet isn't there.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "data"))
import normalizer as n  # noqa: E402

NOTICES_954 = ["2024-05-17:5885", "2024-06-21:7770", "2024-10-04:12679", "2024-10-04:12777"]

NEIGHBOURS = [
    ("N/Wanga/Matungu/954", "N/Wanga/Matungu/955"),
    ("LR 12715/288", "L.R. No. 12715/289"),
    ("LR 12715/288", "LR 12715/2880"),
    ("LR 12715/288", "LR 112715/288"),
    ("Nairobi/Block 9/123", "Nairobi/Block 9/1230"),
    ("Nairobi/Block 9/123", "Nairobi/Block 91/123"),
    ("Kajiado/Kitengela/2830", "Kajiado/Kitengela/2829"),
]


@pytest.mark.parametrize("a,b", NEIGHBOURS)
def test_neighbours_are_different_parcels(a, b):
    assert n.normalise(a) is not None and n.normalise(b) is not None
    assert not n.same_parcel(a, b)


@pytest.mark.parametrize("a,b", NEIGHBOURS)
def test_neighbour_is_not_found_in_the_others_text(a, b):
    text = f"registered under title No. {b}, and whereas"
    assert n.find_in_text(b, text)  # sanity: the parcel that is there is found
    assert n.find_in_text(a, text) == []
    assert n.refs_match(a, [b]) == []


@pytest.mark.parametrize("same", ["LR 12715/288", "L.R. No. 12715/288", "L.R. 12715/288"])
def test_spellings_of_one_parcel_still_match(same):
    assert n.same_parcel("LR 12715/288", same)


@pytest.fixture(scope="module")
def notices():
    pq = pytest.importorskip("pyarrow.parquet")
    if not n.NOTICES_PARQUET.exists():
        pytest.skip("gazette_notices.parquet not present")
    rows = pq.read_table(n.NOTICES_PARQUET, columns=["notice_id", "parcel_refs", "raw_text"]).to_pylist()
    return {r["notice_id"]: r for r in rows}


@pytest.mark.parametrize("notice_id", NOTICES_954)
def test_954_notices_name_954_and_never_955(notices, notice_id):
    r = notices[notice_id]
    assert n.refs_match("N/Wanga/Matungu/954", r["parcel_refs"])
    assert n.find_in_text("N/Wanga/Matungu/954", r["raw_text"])
    assert n.refs_match("N/Wanga/Matungu/955", r["parcel_refs"]) == []
    assert n.find_in_text("N/Wanga/Matungu/955", r["raw_text"]) == []


def test_no_notice_in_the_extract_is_about_955(notices):
    hits = [i for i, r in notices.items() if n.refs_match("N/Wanga/Matungu/955", r["parcel_refs"])]
    assert hits == []
