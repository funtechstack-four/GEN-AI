"""Regex checks for data/scripts/extract_notices.py, using wording seen in real 2024 notices."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "data" / "scripts"))
from extract_notices import DAYS_RE, PARTY_RE, classify, parcel_refs  # noqa: E402


@pytest.mark.parametrize("text, expected", [
    ("registered under title No. Kajiado/Kaputiei South/2645, and whereas", ["Kajiado/Kaputiei South/2645"]),
    ("registered under title No. EM/KESSUP B/765, and whereas", ["EM/KESSUP B/765"]),
    ("registered under title Loc.19/Kiawambogo/1019, and whereas", ["Loc.19/Kiawambogo/1019"]),
    ("all that piece of land known as Kaptagat/Lotonyok Block 5 (Ngeleltarit)/661, situate in",
     ["Kaptagat/Lotonyok Block 5 (Ngeleltarit)/661"]),
    ("registered under title No. Ruiru/Ruiru East Block 4/T.1533, and whereas", ["Ruiru/Ruiru East Block 4/T.1533"]),
    ("registered under title No. Narok/CIS Mara/Nairagie\nEnkare/939, and whereas", ["Narok/CIS Mara/Nairagie Enkare/939"]),
    ("registered under title Nos. Miti Mingi/Mbaruk Block 5/4145, 4146 and 4147 (Kiungururia), and",
     ["Miti Mingi/Mbaruk Block 5/4145", "Miti Mingi/Mbaruk Block 5/4146", "Miti Mingi/Mbaruk Block 5/4147"]),
    ("known as L.R. No. 209/3466, situate in", ["L.R. No. 209/3466"]),
])
def test_parcel_refs(text, expected):
    assert parcel_refs(text) == sorted(expected)


def test_neighbouring_parcels_stay_distinct():
    a = parcel_refs("under title No. Nairobi/Block 82/288, and")
    b = parcel_refs("under title No. Nairobi/Block 82/289, and")
    assert a != b


@pytest.mark.parametrize("text, days", [
    ("after the expiration of sixty (60) days from the date hereof", 60),
    ("after the expiration of sixty\n(60) days from the date hereof", 60),
    ("after the expiration of thirty (30) days from the date hereof", 30),
])
def test_objection_days(text, days):
    assert int(DAYS_RE.search(text).group(1)) == days


@pytest.mark.parametrize("text, name", [
    ("WHEREAS Kisentu Orikae Kasikua (ID/0790881), is registered", "Kisentu Orikae Kasikua"),
    ("WHEREAS Sirma Korio Kibaliat, of P.O. Box 498, Iten", "Sirma Korio Kibaliat"),
    ("WHEREAS Margaret Nyokabi Mbugua, as the administrator of the estate of", "Margaret Nyokabi Mbugua"),
])
def test_party_names(text, name):
    assert PARTY_RE.search(text).group(1).strip() == name


@pytest.mark.parametrize("head, kind", [
    ("THE LAND REGISTRATION ACT\n(NO. 3 OF 2012)\nISSUE OF A NEW LAND TITLE DEED", "lost_title"),
    ("THE LAND REGISTRATION ACT\nISSUE OF A PROVISIONAL CERTIFICATE OF TITLE", "lost_title"),
    ("THE LAND REGISTRATION ACT\nREGISTRATION OF INSTRUMENT", "transfer"),
    ("THE LAND ACT\nINTENTION TO ACQUIRE LAND", "compulsory_acquisition"),
    ("THE LAND REGISTRATION ACT\nRECONSTRUCTION OF LOST OR DESTROYED LAND REGISTER", "other"),
])
def test_classify(head, kind):
    assert classify(head) == kind


from verify_pdfs import read_masthead  # noqa: E402


@pytest.mark.parametrize("head, expected", [
    ("THE KENYA GAZETTE\nVol. CXXVI—No. 147\nNAIROBI, 27th September, 2024\nPrice Sh. 60", ("147", "2024-09-27")),
    ("S P E C IA L IS S U E\nP r i ce Sh . 60 NAIROBI , 28th July, 2023 V ol . CX X V - No. 172 Ca u se", ("172", "2023-07-28")),
    ("Vol. CXXV �No. 245 �A� NAIROBI, 16th November, 2023", ("245a", "2023-11-16")),
    ("PRICE SH. 60 VOL. EXXV-NO. 231 CAUSE NO. E586", ("231", None)),
    ("Vol. CXXVI-No. 148 I., GAZETTE NOTICE", ("148", None)),
])
def test_read_masthead(head, expected):
    assert read_masthead(head) == expected


from extract_notices import ESTATE_RE, NOTICE_RE, WITHIN_DAYS_RE, is_land, petitioners  # noqa: E402


@pytest.mark.parametrize("text, number", [
    ("GAZETTE NOTICE NO. 12512 THE LAND REGISTRATION ACT", "12512"),
    ("GAZETTE NOTICE. NO. 12436", "12436"),
    ("G a zet t e N o t ice N o . 799 2 T HE C O N ST I T U T I O N", "7992"),
    ("Gazet t e Not ic e No . 12188 IN THE HIGH COURT", "12188"),
])
def test_notice_heading(text, number):
    assert NOTICE_RE.search(text).group(1).replace(" ", "") == number


def test_spaced_ocr_land_heading():
    assert is_land("T HE L A N D R EG IS T R A T I O N A C T\n(No. 3 of 2012)")
    assert classify("T HE L A N D R EG IS T R A T I O N A C T\nIS S U E OF A N EW L A N D T I T L E D EED") == "lost_title"


def test_transfer_citing_succession_cause_is_transfer():
    head = ("THE LAND REGISTRATION ACT\nREGISTRATION OF INSTRUMENT\nWHEREAS John Doe (deceased) ... letters of "
            "administration in Succession Cause No. 123 of 2020 ...")
    assert classify(head, "REGISTRATION OF INSTRUMENT") == "transfer"
    assert classify(head) == "transfer"


def test_acquired_in_text_is_not_acquisition():
    assert classify("THE LAND REGISTRATION ACT\nWHEREAS the land was acquired by purchase") == "other"


# Wording from Gazette 2024-03-25 No. 36, notices 3480 and 3485.
PROBATE = ("IN THE HIGH COURT OF KENYA AT NAKURU \nPROBATE AND ADMINISTRATION \nTAKE NOTICE that applications "
           "having been made in this court \nin: \nCAUSE NO. E150 OF 2023 \nBy (1) Justine Rutto and (2) James "
           "Kiprotich Ruto, both of P.O. \nBox 315221-20100, Nakuru in Kenya, for a grant of letters of \n"
           "administration intestate to the estate of Livingstone Kipkoech Ruto, \nwho died at Nairobi Women's "
           "Hospital in Kenya, on 22nd April, \n2023. \nCAUSE NO. E907 OF 2021 \nBy Heinrich Hellen Barchet, of "
           "Seelacher Weg, 95, 71522, \nBacknang, Germany, through Messrs. Albert Kamunde & Co., for a grant "
           "to the estate of \nMercy Njoki Mwangi Barchet, late of Murang'a, who died on 6th May, 2018. \n"
           "The Court will proceed to issue the same unless cause be shown to \nthe contrary and appearance in "
           "this respect entered within thirty (30) \ndays from the date of publication of this notice")


def test_probate_notice_is_kept_as_succession():
    assert is_land(PROBATE)
    assert classify(PROBATE, "IN THE HIGH COURT OF KENYA AT NAKURU") == "succession"


def test_probate_petitioners_and_days():
    assert petitioners(PROBATE) == ["Justine Rutto", "James Kiprotich Ruto", "Heinrich Hellen Barchet"]
    assert ESTATE_RE.findall(PROBATE)[0].strip() == "Livingstone Kipkoech Ruto"
    assert int(WITHIN_DAYS_RE.search(PROBATE).group(1)) == 30


def test_land_notice_keeps_plain_id_on_ocr_clash():
    from extract_notices import make_ids_unique
    rows = [{"notice_id": "2023-07-28:9889", "gazette_no": "172", "notice_type": "succession"},
            {"notice_id": "2023-07-28:9889", "gazette_no": "170", "notice_type": "other"}]
    make_ids_unique(rows)
    assert [r["notice_id"] for r in rows] == ["2023-07-28:9889/172", "2023-07-28:9889"]


def test_petitioner_through_advocates():
    text = "CAUSE NO. E1887 OF 2021 \nBy Beatrice Kainda Mwongera, the deceased's widow, through Messrs. X"
    assert petitioners(text) == ["Beatrice Kainda Mwongera"]
