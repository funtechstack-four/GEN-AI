import json
import pathlib
import sys

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "eval"))
from run_cases import banned_hits, check_case, check_quotes, cites, norm, without_quotes  # noqa: E402

CASES = pathlib.Path(__file__).resolve().parents[1] / "eval" / "cases.yaml"


def claim(**kw):
    base = {"claim_id": "c1", "kind": "lost_title", "parcel_id": "RL:N/WANGA/MATUNGU/954",
            "quote": "registered under title No. N/Wanga/Matungu/954", "source_type": "gazette",
            "source_id": "2024-10-04:12679", "status": "confirmed", "reject_reason": None}
    base.update(kw)
    return base


def test_cases_file_loads_and_has_every_case():
    spec = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    assert [c["id"] for c in spec["cases"]] == ["case-1", "case-1b", "case-2", "case-3"]
    assert [g["id"] for g in spec["gates"]] == ["gate-a", "gate-b", "gate-c", "gate-d"]


def test_norm_only_touches_whitespace_and_ligatures():
    assert norm("title\n  deedﬁ") == "title deedfi"
    assert norm("L.R. No. 209/3466") == "L.R. No. 209/3466"


def test_banned_words_match_whole_words_only():
    assert banned_hits("This title is safe", ["safe"]) == ["safe"]
    assert banned_hits("Unsafe? Safeguard.", ["safe"]) == []
    assert banned_hits("a CLEAR TITLE", ["clear title"]) == ["clear title"]


def test_cites_needs_the_exact_notice_id():
    # same notice number, different year: must not count
    assert not cites([claim(source_id="2023-09-15:12436")], "2024-09-27:12436")
    assert not cites([claim(source_id="Gazette Notice 12436, 27 Sep 2024")], "12436")
    assert cites([claim(source_id="2024-09-27:12436")], "2024-09-27:12436")
    assert not cites([claim()], "2024-10-04:12679", kind="succession")


HIGH_RISK = {"verdict": "HIGH RISK", "min_confirmed": 2,
             "cite_sources": [{"source_id": "2024-05-17:5885", "kind": "lost_title"},
                              {"source_id": "2024-10-04:12679", "kind": "lost_title"}],
             "may_cite_sources": ["2024-06-21:7770", "2024-10-04:12777"],
             "quotes_contain": ["registered under title No. N/Wanga/Matungu/954"]}


def test_passing_high_risk_case():
    dossier = {"verdict": "HIGH RISK", "timeline": [claim(), claim(claim_id="c2", source_id="2024-05-17:5885"),
                                                    claim(claim_id="c3", kind="succession", source_id="2024-06-21:7770")],
               "unverified": [], "objection_windows": [], "remaining_checks": []}
    assert check_case(dossier, HIGH_RISK, events=set()) == []


def test_claim_with_wrong_kind_or_unlisted_source_fails():
    dossier = {"verdict": "HIGH RISK", "unverified": [],
               "timeline": [claim(kind="succession"), claim(claim_id="c2", source_id="2024-05-17:5885"),
                            claim(claim_id="c3", source_id="2022-01-07:111")]}
    fails = check_case(dossier, HIGH_RISK, events=set())
    assert any("2024-10-04:12679" in f for f in fails)
    assert any("unexpected sources" in f for f in fails)


def test_allow_list_ignores_registry_claims_and_survives_missing_source_id():
    base = [claim(), claim(claim_id="c2", source_id="2024-05-17:5885")]
    registry = claim(claim_id="c3", kind="registry", source_type="registry", source_id="registry:954")
    assert check_case({"verdict": "HIGH RISK", "timeline": base + [registry]}, HIGH_RISK, set()) == []
    no_id = claim(claim_id="c4", source_id=None)
    fails = check_case({"verdict": "HIGH RISK", "timeline": base + [no_id]}, HIGH_RISK, set())
    assert any("<none>" in f for f in fails)


def test_stop_must_not_search():
    expect = {"never_trace_events": ["tool_call"]}
    assert check_case({"timeline": []}, expect, {"verdict"}) == []
    assert check_case({"timeline": []}, expect, {"tool_call", "verdict"})


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_api_errors_are_reported_not_crashed(monkeypatch):
    import urllib.error
    import urllib.request

    import run_cases

    def server_error(*a, **k):
        raise urllib.error.HTTPError("http://x/dossier", 500, "Internal Server Error", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", server_error)
    with pytest.raises(run_cases.ApiError, match="API returned 500"):
        run_cases.post_dossier("http://x", {})

    for body, msg in [(b"<html>oops</html>", "isn't JSON"), (b'{"a": "\x80"}', "isn't JSON"), (b"[1, 2]", "isn't a dossier")]:
        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, b=body, **k: FakeResponse(b))
        with pytest.raises(run_cases.ApiError, match=msg):
            run_cases.post_dossier("http://x", {})


def test_broken_trace_lines_are_skipped(tmp_path, monkeypatch):
    import run_cases
    monkeypatch.setattr(run_cases, "TRACE_DIR", tmp_path)
    (tmp_path / "r1.jsonl").write_text('{"event": "tool_call"}\nnot json\n\n{"event": "verdict"}\n', encoding="utf-8")
    assert run_cases.trace_events("r1") == {"tool_call", "verdict"}


def test_gate_b_ignores_words_inside_verbatim_quotes():
    d = {"summary": "Two notices found.", "timeline": [claim(quote="kept in safe custody")], "unverified": []}
    assert banned_hits(json.dumps(without_quotes(d)), ["safe"]) == []
    assert d["timeline"][0]["quote"] == "kept in safe custody"  # original untouched


def test_gate_c_quote_checks():
    texts = {"2024-10-04:12679": "... registered under title No. N/Wanga/Matungu/954 ..."}
    assert check_quotes([{"timeline": [claim()]}], texts) == []
    assert "empty quote" in check_quotes([{"timeline": [claim(quote="")]}], texts)[0]
    assert "unknown source_id" in check_quotes([{"timeline": [claim(source_id="x")]}], texts)[0]
    assert "quote not in" in check_quotes([{"timeline": [claim(quote="made up")]}], texts)[0]
    assert check_quotes([{"timeline": []}], texts) == ["no confirmed Gazette claims to check"]


def test_neighbour_parcel_citing_954_fails():
    dossier = {"verdict": "HIGH RISK", "timeline": [claim()], "unverified": []}
    expect = {"verdict": "VERIFY FIRST", "max_confirmed": 0, "never_cite_sources": ["2024-10-04:12679"]}
    fails = check_case(dossier, expect, events=set())
    assert len(fails) == 3


def test_critic_must_reject_when_claims_surface():
    dossier = {"verdict": "VERIFY FIRST", "timeline": [], "unverified": [claim(status="rejected")]}
    expect = {"critic_reject_if_any_claim": True}
    assert check_case(dossier, expect, events={"tool_call"})
    assert check_case(dossier, expect, events={"critic_reject"}) == []


def test_objection_window_must_match():
    dossier = {"timeline": [], "objection_windows": [{"notice_id": "2024-10-04:12679", "closes_on": "2024-12-03", "open": True}]}
    ok = {"objection_windows": [{"notice_id": "2024-10-04:12679", "closes_on": "2024-12-03", "open": True}]}
    wrong = {"objection_windows": [{"notice_id": "2024-10-04:12679", "closes_on": "2024-12-04", "open": True}]}
    assert check_case(dossier, ok, set()) == []
    assert check_case(dossier, wrong, set())
