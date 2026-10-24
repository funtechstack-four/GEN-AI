"""Checks for data/normalizer.py, using parcel refs copied from gazette_notices.parquet and the I/O matrix
in spec-gh-8-parcel-id-normaliser.md."""
import pathlib
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "data"))
import normalizer  # noqa: E402
from normalizer import (  # noqa: E402
    NOTICES_PARQUET, ParcelId, check_serial, find_in_text, normalise, normalise_all, refs_match,
    same_parcel, text_pattern, variants,
)


def key(text):
    p = normalise(text)
    return p.key if p else None


# --- I/O matrix -------------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("LR 209/3466", "LR:209/3466"),
    ("L.R. No. 209/3466", "LR:209/3466"),
    ("L.R.No.209/3466", "LR:209/3466"),
    ("L R No 209/3466", "LR:209/3466"),
    ("I.R. 13537/208", "IR:13537/208"),
    ("IR. 13537/208", "IR:13537/208"),
    ("C.R. No. 1234", "CR:1234"),
    ("Nairobi/Block 82/288", "RL:NAIROBI/BLOCK 82/288"),
    ("Nairobi Block 82/288", "RL:NAIROBI/BLOCK 82/288"),
    ("L.R. No. Nairobi Block 82/288", "RL:NAIROBI/BLOCK 82/288"),
    ("Narok/CIS Mara/Nairagie\nEnkare/939", "RL:NAROK/CISMARA/NAIRAGIEENKARE/939"),
    ("Narok/CIS Mara/Nairagie Enkare/939", "RL:NAROK/CISMARA/NAIRAGIEENKARE/939"),
    ("209/3466", "LR:209/3466"),
    ("", None),
    ("hello", None),
    ("806", None),
])
def test_io_matrix(text, expected):
    assert key(text) == expected


def test_schemes_never_collide():
    assert key("I.R. 13537/208") != key("L.R. 13537/208")
    assert key("C.R. No. 1234") != key("L.R. No. 1234")
    assert not same_parcel("I.R. 13537/208", "13537/208")


def test_neighbours_are_different_parcels():
    assert key("Nairobi/Block 82/288") != key("Nairobi/Block 82/289")
    text = "under title Nos. Nairobi/Block 82/289, Nairobi/Block 82/2880 and Nairobi/Block 82/2288, and"
    assert find_in_text("Nairobi/Block 82/288", text) == []
    assert len(find_in_text("Nairobi/Block 82/288", "under title No. Nairobi/Block 82/288, and")) == 1


@pytest.mark.parametrize("serial", ["5253001", "No. 5,253,367", 5253100, "5253 200"])
def test_cancelled_serial(serial):
    r = check_serial(serial)
    assert r.valid and r.cancelled
    assert r.gazette_notice_no == "12436" and r.issue_date == "2024-09-27"
    assert r.source_url.startswith("https://") and "#page=" in r.source_url


@pytest.mark.parametrize("serial", ["5253000", "5253368", 5253000])
def test_live_serial(serial):
    r = check_serial(serial)
    assert r.valid and not r.cancelled


@pytest.mark.parametrize("serial", ["abc", "", None, -5, "5253001x"])
def test_bad_serial(serial):
    r = check_serial(serial)
    assert not r.valid and not r.cancelled


def test_serial_lookup_is_fast_after_first_load():
    check_serial("5253001")
    t = time.perf_counter()
    r = check_serial("5253100")
    assert r.cancelled and time.perf_counter() - t < 0.05


def test_missing_csv_returns_invalid(monkeypatch, tmp_path):
    monkeypatch.setattr(normalizer, "CANCELLED_CSV", tmp_path / "nope.csv")
    r = check_serial("5253001")
    assert not r.valid and not r.cancelled and r.reason


# --- real refs from gazette_notices.parquet ------------------------------------------------------

@pytest.mark.parametrize("ref, expected", [
    ("Nairobi Block 93/228", "RL:NAIROBI/BLOCK 93/228"),
    ("L.R. No. 330/298", "LR:330/298"),
    ("L.R. No. 209/2490/45", "LR:209/2490/45"),
    ("28428/54", "LR:28428/54"),
    ("Kijabe/ Kijabe Block 1/2954", "RL:KIJABE/KIJABE/BLOCK 1/2954"),
    ("Loc. 4/Kiranga/670", "RL:LOC4/KIRANGA/670"),
    ("K wale/Funzi Island/299", "RL:KWALE/FUNZIISLAND/299"),
    ("N o . K isumu/Kogony/2826", "RL:KISUMU/KOGONY/2826"),
    ("Pioneer/Ngeria Block 1 (EATEC)/10521", "RL:PIONEER/NGERIA/BLOCK 1/10521"),
    ("Pioneer/Ngeria Block 1(Eatec)/7426", "RL:PIONEER/NGERIA/BLOCK 1/7426"),
    ("Ndumberi/Tinganga/T.257", "RL:NDUMBERI/TINGANGA/T257"),
    ("Ruiru/Ruiru East Block 4/T. 1890", "RL:RUIRU/RUIRUEAST/BLOCK 4/T1890"),
    ("Mombasa/Block XL/28", "RL:MOMBASA/BLOCK XL/28"),
    ("Subukia/Subukia block13/200", "RL:SUBUKIA/SUBUKIA/BLOCK 13/200"),
    ("Makuyu/Kimorori/Block.3/5996", "RL:MAKUYU/KIMORORI/BLOCK 3/5996"),
    ("Makuyu/Makuyu Block. 1/7263", "RL:MAKUYU/MAKUYU/BLOCK 1/7263"),
    ("Kisumu/Manyatta �A�/2035", "RL:KISUMU/MANYATTAA/2035"),
    ("Kisumu/Kanyakwar “B”/2836", "RL:KISUMU/KANYAKWARB/2836"),
    ("E. Bukusu/N. Sang’alo/2388", "RL:EBUKUSU/NSANGALO/2388"),
    ("Kajiado/Kaputiei-North/5223", "RL:KAJIADO/KAPUTIEINORTH/5223"),
    ("C. Kasipul/Sino/1569", "RL:CKASIPUL/SINO/1569"),
    ("C.R. 15975/1", "CR:15975/1"),
    ("I.R. 13537/207", "IR:13537/207"),
    ("IR 10777/1", "IR:10777/1"),
    ("Flat No. 6 on LR. No. 1870/IV/148", "LR:1870/IV/148"),
    ("L.R. 2/308 (Orig No. 2/222", "LR:2/308"),
    ("L.R. No. 15081/35 (Original No. 15081/5/32", "LR:15081/35"),
    ("Plot No. Bububu ‘A’ Settlement Scheme/319", "RL:BUBUBUASETTLEMENTSCHEME/319"),
    ("Mombasa/Block XXI/265A", "RL:MOMBASA/BLOCK XXI/265A"),
    ("Kwale/Diani Beach Block/1609/2", "RL:KWALE/DIANIBEACHBLOCK/1609/2"),
    ("25980", None),
])
def test_real_refs(ref, expected):
    assert key(ref) == expected


def test_table_row_does_not_crash():
    row = ("New Parcel No. Area (Ha.) Dagoretti/Ruthimitu/835 Nairobi Block 128/835 0.1962 "
           "Dagoretti/Ruthimitu/839 Nairobi Block 128/839 0.2")
    keys = [p.key for p in normalise_all(row)]
    assert "RL:NAIROBI/BLOCK 128/835" in keys and "RL:DAGORETTI/RUTHIMITU/839" in keys
    assert normalise(row) is not None


# --- hard rules from review loop 1 ----------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "title No. West Nairobi/Block 82/288, and",
    "title No. Kiambu/Nairobi/Block 82/288, and",
    "title No. Kiambu/Block 82/288, and",
])
def test_section_must_start_the_hit(text):
    assert find_in_text("Nairobi/Block 82/288", text) == []


@pytest.mark.parametrize("text", [
    "known as Nairobi Block 93/228, situate",
    "known as Nairobi\nBlock 93/228, situate",
    "under title No. Nairobi/Block 93/228, and",
    "Nairobi Block 93/228",
])
def test_section_hit_after_lead_in(text):
    assert len(find_in_text("Nairobi/Block 93/228", text)) == 1


@pytest.mark.parametrize("text", [
    "known as Nairobi Block 209/3466, situate",
    "known as Nairobi Block-209/3466",
    "known as I.R. 209/3466, situate",
    "known as I.R.  No.  209/3466, situate",
    "known as C.R.\nNos. 209/3466, situate",
    "known as IR No 209/3466",
    "known as 1209/3466 and 209/34661 and 209/3466/1",
])
def test_lr_text_rejects_other_contexts(text):
    assert find_in_text("LR 209/3466", text) == []


@pytest.mark.parametrize("text", [
    "known as L.R. No. 209/3466, situate",
    "known as L.R.No.209/3466, situate",
    "known as LR 209/3466, situate",
    "registered as title No. 209/3466 and",
    "L.R. No.\n209/3466",
])
def test_lr_text_hits(text):
    assert len(find_in_text("L.R. No. 209/3466", text)) == 1


def test_sectionless_lr_needs_prefix():
    assert find_in_text("L.R. No. 1234", "holding 1234 shares, plot 1234") == []
    assert find_in_text("L.R. No. 1234", "known as L.R. No. 1234/5") == []
    assert len(find_in_text("L.R. No. 1234", "known as L.R. No. 1234, situate")) == 1


@pytest.mark.parametrize("junk", [
    "a/" * 1000, "Nairobi Block " * 150, "1/" * 1000, "(" * 2000, "L.R. " * 400, "x" * 2000,
    "'A'" * 700, "Kisumu/Manyatta 'A' " * 100,
])
def test_normalise_is_linear(junk):
    t = time.perf_counter()
    normalise(junk)
    normalise_all(junk)
    assert time.perf_counter() - t < 0.05


@pytest.mark.parametrize("text", [
    "Kisumu/Manyatta 'A'/2035", "Kisumu/Manyatta (A)/2035", 'Kisumu/Manyatta "A"/2035',
    "Kisumu/Manyatta �A�/2035", "Kisumu/Manyatta A/2035", "Kisumu/Manyatta ‘A’/2035",
])
def test_letter_suffix_is_part_of_name(text):
    assert key(text) == "RL:KISUMU/MANYATTAA/2035"


def test_letter_suffix_keeps_sections_apart():
    assert key("Kisumu/Manyatta 'A'/2035") != key("Kisumu/Shinoyi 'A'/2035")
    assert key("Kisumu/Manyatta 'A'/2035") != key("Kisumu/Manyatta/2035")
    assert find_in_text("Kisumu/Manyatta/2035", "title Kisumu/Manyatta (A)/2035, and") == []
    assert len(find_in_text("Kisumu/Manyatta 'A'/2035", "title Kisumu/Manyatta ‘A’/2035, and")) == 1


def test_multichar_parentheticals_dropped():
    assert key("Pioneer/Ngeria Block 1 (EATEC/10521") == "RL:PIONEER/NGERIA/BLOCK 1/10521"
    hit = find_in_text("Pioneer/Ngeria Block 1/10521", "title Pioneer/Ngeria Block 1 (EATEC)/10521 and")
    assert len(hit) == 1


@pytest.mark.parametrize("text", [
    "Nairobi/Block-82/288", "Nairobi/Block 82/288", "Nairobi/Block82/288", "Nairobi/BLOCK. 82/288",
])
def test_block_spellings(text):
    assert key(text) == "RL:NAIROBI/BLOCK 82/288"


@pytest.mark.parametrize("text, expected", [
    ("Original I.R. 13537/208", "IR:13537/208"),
    ("Grant I.R. 13537/208", "IR:13537/208"),
    ("Flat No. 6 on LR. No. 1870/IV/148", "LR:1870/IV/148"),
    ("Nairobi/Block 82/288/", "RL:NAIROBI/BLOCK 82/288"),
    ("C.R. No. pending, L.R. 209/1", "LR:209/1"),
])
def test_prefix_position(text, expected):
    assert key(text) == expected


def test_multi_parcel_refs():
    ref = "Plot Nos. Mombasa/Block XLVIII/134 and Mombasa/Block XLVII/110"
    assert [p.key for p in normalise_all(ref)] == ["RL:MOMBASA/BLOCK XLVIII/134", "RL:MOMBASA/BLOCK XLVII/110"]
    assert refs_match("Mombasa/Block XLVII/110", [ref, "Mombasa/Block XLVII/1100"]) == [ref]
    assert [p.key for p in normalise_all("L.R. Nos. 12716/517 and 12715/148")] == ["LR:12716/517", "LR:12715/148"]


# --- hard rules from review loop 2 ----------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("I.R. Nos. 13537/207 and 13537/208", ["IR:13537/207", "IR:13537/208"]),
    ("I.R. Nos. 13537/207, 13537/208 & 13537/209", ["IR:13537/207", "IR:13537/208", "IR:13537/209"]),
    ("I.R. Grant No. 13537/208", ["IR:13537/208"]),
    ("C.R. Nos. 15975/1 and 15975/2", ["CR:15975/1", "CR:15975/2"]),
    ("13537/207 and I.R. 13537/208", ["LR:13537/207", "IR:13537/208"]),
    ("I.R. No. 13537/207; 13537/208", ["IR:13537/207", "LR:13537/208"]),
    ("C.R. No. 1234; 209/1", ["CR:1234", "LR:209/1"]),
    ("I.R. No. 13537/207. The land 13537/208", ["IR:13537/207", "LR:13537/208"]),
    ("C.R. No. 15975/1. The land 15975/2", ["CR:15975/1", "LR:15975/2"]),
    ("10712 Grant IR 19109 and L.R. No. 2754/2", ["IR:19109", "LR:2754/2"]),
])
def test_prefix_scope_covers_its_list(text, expected):
    assert [p.key for p in normalise_all(text)] == expected


@pytest.mark.parametrize("text, expected", [
    ("L.R. Nos. 1234 and 5678", ["LR:1234", "LR:5678"]),
    ("C.R. Nos. 1234 and 1235", ["CR:1234", "CR:1235"]),
    ("C.R. No. 1234 and L.R. 209/1", ["CR:1234", "LR:209/1"]),
    ("Nairobi/Block 82/288 and 289", ["RL:NAIROBI/BLOCK 82/288", "RL:NAIROBI/BLOCK 82/289"]),
    ("Nairobi/Block 82/288, 289 and 290",
     ["RL:NAIROBI/BLOCK 82/288", "RL:NAIROBI/BLOCK 82/289", "RL:NAIROBI/BLOCK 82/290"]),
    ("Nairobi/Block 82/288, 289, and 290",
     ["RL:NAIROBI/BLOCK 82/288", "RL:NAIROBI/BLOCK 82/289", "RL:NAIROBI/BLOCK 82/290"]),
    ("L.R. Nos. 12716/517 and 12715/148", ["LR:12716/517", "LR:12715/148"]),
    # strings from gazette_notices.parquet
    ("L.R. Nos. 1853 and 1850/1", ["LR:1853", "LR:1850/1"]),
    ("L.R. No. 2899. registered as C.R. 16546/1", ["LR:2899", "CR:16546/1"]),
    ("Siaya/Olwa/1530 and 1529 shall be cancelled and the original land Siaya/Olwa/929",
     ["RL:SIAYA/OLWA/1530", "RL:SIAYA/OLWA/1529", "RL:SIAYA/OLWA/929"]),
    ("L.R. No. 10225 (original Nos. 464/12 and 9684/1", ["LR:10225"]),
    ("213310 (L.R. No. 12581/24", ["LR:12581/24"]),
])
def test_lists_of_numbers(text, expected):
    assert [p.key for p in normalise_all(text)] == expected


def test_refs_match_finds_list_members():
    ref = "Nairobi/Block 82/288 and 289"
    assert refs_match("Nairobi/Block 82/289", [ref]) == [ref]
    assert refs_match("I.R. 13537/208", ["I.R. Nos. 13537/207 and 13537/208"]) == ["I.R. Nos. 13537/207 and 13537/208"]
    assert refs_match("LR 13537/208", ["I.R. Nos. 13537/207 and 13537/208"]) == []


@pytest.mark.parametrize("parcel, text, n", [
    ("I.R. 13537/208", "known as I.R. 13537/208, situate", 1),
    ("I.R. 13537/208", "known as I.R.\nGrant No. 13537/208, situate", 1),
    ("I.R. 13537/208", "under I.R. Nos. 13537/207 and 13537/208, and", 1),
    ("C.R. 15975/1", "known as C.R. 15975/1, situate", 1),
    ("C.R. No. 1234", "under C.R. Nos. 1233 and 1234, and", 1),
    ("L.R. No. 5678", "under L.R. Nos. 1234 and 5678, and", 1),
    # cross-scheme negatives
    ("LR 13537/208", "under I.R. Nos. 13537/207 and 13537/208, and", 0),
    ("LR 1234", "under C.R. Nos. 1233 and\n1234, and", 0),
    ("LR 209/3466", "I.R. Nos. 1/2, 3/4, and 209/3466", 0),
    ("I.R. 209/3466", "I.R. Nos. 1/2, 3/4, and 209/3466", 1),
    ("I.R. 13537/208", "known as L.R. No. 13537/208, situate", 0),
    ("I.R. 13537/208", "known as 13537/208, situate", 0),
    ("I.R. 13537/208", "known as C.R. 13537/208, situate", 0),
    ("C.R. 15975/1", "known as I.R. 15975/1, situate", 0),
    ("C.R. No. 1234", "known as I.R. No. 1234, situate", 0),
    ("C.R. No. 1234", "holding 1234 shares", 0),
])
def test_ir_cr_text_search(parcel, text, n):
    assert len(find_in_text(parcel, text)) == n


@pytest.mark.parametrize("parcel, text", [
    ("L.R. No. 1870", "Flat No. 6 on L.R. No. 1870/IV/148"),
    ("L.R. No. 1870", "known as L.R. No. 1870 / 4"),
    ("LR 209/3466", "known as L.R. No. 209/3466/A"),
    ("Nairobi/Block 82/288", "title Nairobi/Block 82/288/XI"),
])
def test_number_end(parcel, text):
    assert find_in_text(parcel, text) == []


@pytest.mark.parametrize("text, n", [
    ("title West-Nairobi/Block 82/288, and", 0),
    ("title WEST NAIROBI/BLOCK 82/288, and", 0),
    ("title West Nairobi Block 82/288, and", 0),
    ("the said Nairobi/Block 82/288, and", 1),
    ("transferred from Nairobi/Block 82/288 to", 1),
    ("Area (Ha.) 0.1962 Nairobi Block 82/288 0.2", 1),
    ("Kiambu/Block 1/5, Nairobi/Block 82/288", 1),
])
def test_word_before_section_hit(text, n):
    assert len(find_in_text("Nairobi/Block 82/288", text)) == n


def test_input_cap_never_splits_a_number():
    text = "y" * (normalizer.MAX_INPUT - 6) + " LR 209/3466"
    assert text[:normalizer.MAX_INPUT].endswith("LR 20")
    assert normalise(text) is None
    assert normalise("y" * 100 + " LR 209/3466").key == "LR:209/3466"


@pytest.mark.parametrize("serial", ["Serial No: 5253001", "No: 5253001", "No. 5253001", "#5253001",
                                    "serial no. 5253001", "Title No: 5,253,001"])
def test_serial_labels(serial):
    r = check_serial(serial)
    assert r.valid and r.cancelled and r.serial == 5253001


def test_serial_evidence_fields():
    r = check_serial("5253001")
    assert r.status == "reported lost; deemed cancelled"
    assert r.quote == "5253001--5253367"
    assert r.notice_title == "LOSS OF TITLE DEEDS"
    assert r.gazette_no == "147" and r.notice_date == "2024-09-26"


@pytest.mark.parametrize("a, b, expected", [
    ("LR 209/3466", "L.R.No.209/3466", True),
    ("Nairobi/Block 82/288", "L.R. No. Nairobi Block 82/288", True),
    ("Narok/CIS Mara/Nairagie\nEnkare/939", "Narok/CIS Mara/Nairagie Enkare/939", True),
    ("hello", "hello", False),
    ("", "806", False),
    ("I.R. 13537/208", "L.R. 13537/208", False),
])
def test_same_parcel(a, b, expected):
    assert same_parcel(a, b) is expected


@pytest.mark.parametrize("junk", [
    "L.R. Nos. 1 and " * 300, "Nairobi/Block 1/1" + ", 1" * 1500, "(" + "1/" * 1000,
    "I.R. " * 400 + "1/2", "1 and 2/" * 300, ";. A" * 600,
])
def test_list_parsing_is_linear(junk):
    t = time.perf_counter()
    normalise_all(junk)
    assert time.perf_counter() - t < 0.05


# --- API ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", ["LR 209/3466", "Nairobi Block 82/288", "C.R. No. 1234", "I.R. 13537/208",
                                  "Narok/CIS Mara/Nairagie Enkare/939", "Ruiru/Ruiru East Block 4/T. 1890"])
def test_variants_round_trip(text):
    p = normalise(text)
    vs = variants(p)
    assert len(vs) >= 2
    assert all(normalise(v) == p for v in vs), [(v, key(v)) for v in vs]


def test_label_not_part_of_identity():
    a, b = normalise("Nairobi/Block 82/288"), normalise("NAIROBI BLOCK 82/288")
    assert a == b and hash(a) == hash(b)
    assert ParcelId("RL", "NAIROBI/BLOCK 82", "288", "x") == ParcelId("RL", "NAIROBI/BLOCK 82", "288", "y")


def test_text_pattern_is_digit_bounded():
    pat = text_pattern("Nairobi/Block 82/288")
    assert pat.search("Nairobi/Block 82/288,")
    for other in ("Nairobi/Block 82/2880", "Nairobi/Block 82/289", "Nairobi/Block 82/288A", "Nairobi/Block 82/288/1"):
        assert not pat.search(other)


# --- parquet ------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def notices():
    if not NOTICES_PARQUET.exists():
        pytest.skip("gazette_notices.parquet not present")
    pq = pytest.importorskip("pyarrow.parquet")
    return pq.read_table(NOTICES_PARQUET, columns=["notice_id", "parcel_refs", "raw_text"]).to_pylist()


def test_known_notice_found_for_buyer_variant(notices):
    def hits(q):
        return {n["notice_id"] for n in notices if find_in_text(q, n["raw_text"])}

    def ref_hits(q):
        return {n["notice_id"] for n in notices if refs_match(q, n["parcel_refs"])}

    assert "2024-11-15:14966" in hits("Nairobi/Block 93/228")
    assert "2024-11-15:14966" in ref_hits("nairobi block 93 / 228")
    for neighbour in ("Nairobi/Block 93/229", "Nairobi/Block 93/2280"):
        assert "2024-11-15:14966" not in hits(neighbour)
        assert "2024-11-15:14966" not in ref_hits(neighbour)


def test_parquet_coverage(notices):
    refs = [r for n in notices for r in (n["parcel_refs"] or [])]
    parsed = sum(1 for r in refs if normalise(r) is not None)
    assert parsed / len(refs) >= 0.85
