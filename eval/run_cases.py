"""Runs the demo cases and gates in eval/cases.yaml against the agents API.

    python eval/run_cases.py                 # API at http://localhost:8000
    python eval/run_cases.py --api http://localhost:8000 --skip-meterless

Exit code 0 when everything passes, 1 otherwise (--skip-meterless always exits 1). Works the same with SAMPLE_MODE=true
on the API side, which is how it should run on a clean clone with no network.
"""
from __future__ import annotations

import argparse
import copy
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CASES = ROOT / "eval" / "cases.yaml"
TRACE_DIR = ROOT / "logs"


# ---------- helpers (unit-tested in tests/test_eval_helpers.py) ----------

def norm(text: str) -> str:
    """Whitespace and ligatures only, the same normalisation the Evidence Critic uses."""
    text = text.replace("ﬁ", "fi").replace("ﬂ", "fl")
    return re.sub(r"\s+", " ", text).strip()


def banned_hits(text: str, words: list[str]) -> list[str]:
    return [w for w in words if re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE)]


def without_quotes(dossier: dict) -> dict:
    """Copy of the dossier with verbatim quotes blanked: they're source text, not our wording."""
    d = copy.deepcopy(dossier)
    for key in ("timeline", "unverified"):
        for c in d.get(key, []):
            c["quote"] = ""
    return d


def cites(claims: list[dict], source_id: str, kind: str | None = None) -> bool:
    """True if a claim cites exactly this notice ID (and has this kind, when given)."""
    return any(c.get("source_id") == source_id and (kind is None or c.get("kind") == kind) for c in claims)


def check_case(dossier: dict, expect: dict, events: set[str]) -> list[str]:
    """Returns a list of failure messages; empty means the case passed."""
    fails = []
    confirmed = dossier.get("timeline", [])
    every_claim = confirmed + dossier.get("unverified", [])

    if "verdict" in expect and dossier.get("verdict") != expect["verdict"]:
        fails.append(f"verdict {dossier.get('verdict')!r}, expected {expect['verdict']!r}")
    if "min_confirmed" in expect and len(confirmed) < expect["min_confirmed"]:
        fails.append(f"{len(confirmed)} confirmed claims, expected at least {expect['min_confirmed']}")
    if "max_confirmed" in expect and len(confirmed) > expect["max_confirmed"]:
        fails.append(f"{len(confirmed)} confirmed claims, expected at most {expect['max_confirmed']}")
    for want in expect.get("cite_sources", []):
        if not cites(confirmed, want["source_id"], want.get("kind")):
            fails.append(f"no confirmed {want.get('kind', 'claim')} citing {want['source_id']}")
    if "may_cite_sources" in expect:
        allowed = {w["source_id"] for w in expect.get("cite_sources", [])} | set(expect["may_cite_sources"])
        extra = sorted({c.get("source_id") or "<none>" for c in confirmed
                        if c.get("source_type") == "gazette"} - allowed)
        if extra:
            fails.append(f"confirmed claims cite unexpected sources {extra}")
    for src in expect.get("never_cite_sources", []):
        if cites(confirmed, src):
            fails.append(f"a confirmed claim cites {src}, which belongs to another parcel")
    for snippet in expect.get("quotes_contain", []):
        if not any(norm(snippet) in norm(c.get("quote", "")) for c in confirmed):
            fails.append(f"no confirmed quote contains {snippet!r}")
    for w in expect.get("objection_windows", []):
        got = [x for x in dossier.get("objection_windows", []) if x.get("notice_id") == w["notice_id"]]
        if not got:
            fails.append(f"no objection window for {w['notice_id']}")
        elif got[0].get("closes_on") != w["closes_on"] or got[0].get("open") != w["open"]:
            fails.append(f"objection window {got[0]}, expected {w}")
    if "remaining_checks" in expect and len(dossier.get("remaining_checks", [])) != expect["remaining_checks"]:
        fails.append(f"{len(dossier.get('remaining_checks', []))} remaining checks, expected {expect['remaining_checks']}")
    for ev in expect.get("trace_events", []):
        if ev not in events:
            fails.append(f"trace has no {ev!r} event")
    for ev in expect.get("never_trace_events", []):
        if ev in events:
            fails.append(f"trace has a {ev!r} event, expected none")
    if expect.get("critic_reject_if_any_claim") and every_claim and "critic_reject" not in events:
        fails.append("claims were found but the critic rejected none of them")
    return fails


def check_quotes(dossiers: list[dict], texts: dict[str, str]) -> list[str]:
    """Gate C: every confirmed Gazette claim has a non-empty quote found in its notice."""
    fails, n = [], 0
    for d in dossiers:
        for c in d.get("timeline", []):
            if c.get("source_type") != "gazette":
                continue
            n += 1
            quote, src = norm(c.get("quote") or ""), texts.get(c.get("source_id", ""))
            if not quote:
                fails.append(f"{c.get('claim_id')}: empty quote")
            elif src is None:
                fails.append(f"{c.get('claim_id')}: unknown source_id {c.get('source_id')!r}")
            elif quote not in norm(src):
                fails.append(f"{c.get('claim_id')}: quote not in {c.get('source_id')}")
    if n == 0:
        fails.append("no confirmed Gazette claims to check")
    return fails


# ---------- talking to the API ----------

class ApiError(Exception):
    pass


def post_dossier(api: str, intake: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(f"{api}/dossier", data=json.dumps(intake).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
    except urllib.error.HTTPError as err:
        raise ApiError(f"API returned {err.code} {err.reason}") from err
    except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
        raise ApiError(f"API not reachable at {api} ({err})") from err
    try:
        d = json.loads(body)
    except ValueError as err:  # covers bad JSON and bad UTF-8
        raise ApiError(f"API returned something that isn't JSON: {body[:80]!r}") from err
    if not isinstance(d, dict):
        raise ApiError(f"API returned JSON that isn't a dossier object: {str(d)[:80]}")
    return d


def trace_events(run_id: str) -> set[str]:
    f = TRACE_DIR / f"{run_id}.jsonl"
    if not f.exists():
        return set()
    events = set()
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            events.add(json.loads(line).get("event"))
        except (ValueError, AttributeError):
            continue  # skip blank or broken lines
    return events


def source_texts(path: str = "data/extracts/gazette_notices.parquet") -> dict[str, str]:
    import pyarrow.parquet as pq
    t = pq.read_table(ROOT / path, columns=["notice_id", "raw_text"])
    return dict(zip(t.column("notice_id").to_pylist(), t.column("raw_text").to_pylist()))


# ---------- main ----------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--skip-meterless", action="store_true")
    args = ap.parse_args()

    spec = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    gates = {g["id"]: g for g in spec["gates"]}
    results, dossiers = [], []
    print("EVALUATION RUN: Land Title Due-Diligence Agent\n")

    for case in spec["cases"] + [gates["gate-a"]]:
        start = time.time()
        try:
            d = post_dossier(args.api, case["intake"])
        except ApiError as err:
            results.append((case["id"], False, str(err)))
            continue
        secs = time.time() - start
        dossiers.append(d)
        fails = check_case(d, case["expect"], trace_events(d.get("run_id", "")))
        if "max_seconds" in case["expect"] and secs > case["expect"]["max_seconds"]:
            fails.append(f"took {secs:.1f}s, expected under {case['expect']['max_seconds']}s")
        results.append((case["id"], not fails, f"{d.get('verdict')} in {secs:.1f}s" if not fails else "; ".join(fails)))

    # gate B: banned words in what we write (quotes are verbatim source text, so they're excluded)
    words = gates["gate-b"]["banned_words"]
    hits = [h for d in dossiers for h in banned_hits(json.dumps(without_quotes(d)), words)]
    msg = "no dossiers to check" if not dossiers else (f"banned words found: {hits}" if hits else "none found")
    results.append(("gate-b", bool(dossiers) and not hits, msg))

    # gate C: every confirmed Gazette quote is in its notice's raw text
    if not dossiers:
        results.append(("gate-c", False, "no dossiers to check"))
    else:
        try:
            bad = check_quotes(dossiers, source_texts(gates["gate-c"]["source_table"]))
        except (FileNotFoundError, ImportError) as err:
            bad = [f"can't load the source table ({err})"]
        results.append(("gate-c", not bad, "; ".join(bad) if bad else "all quotes verbatim"))

    # gate D: Meterless conformance suites
    skipped = []
    if args.skip_meterless:
        skipped.append(("gate-d", "skipped (--skip-meterless), so this run can't count as a full pass"))
    else:
        runs = [subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True)
                for cmd in gates["gate-d"]["commands"]]
        errs = [r.stderr.strip().splitlines()[-1] for r in runs if r.returncode and r.stderr.strip()]
        msg = f"exit codes {[r.returncode for r in runs]}" + (f": {errs}" if errs else "")
        results.append(("gate-d", all(r.returncode == 0 for r in runs), msg))

    for rid, ok, msg in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {rid:<8} {msg}")
    for rid, msg in skipped:
        print(f"[SKIP] {rid:<8} {msg}")
    passed = sum(ok for _, ok, _ in results)
    print(f"\n{passed} of {len(results)} passed" + (f", {len(skipped)} skipped" if skipped else ""))
    return 0 if passed == len(results) and not skipped else 1


if __name__ == "__main__":
    sys.exit(main())
