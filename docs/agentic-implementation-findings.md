# Agentic implementation findings and draft plan

**Status:** Feasibility draft, 27 October 2026
**Branch:** `agent-draft`
**Scope:** Findings from the current repository and a staged proposal for more autonomous land due-diligence agents. This document does not claim integration access to any government registry.

## Executive summary

The current application is an evidence-led, mostly deterministic workflow. It can identify candidate Gazette and court records, validate some claims against parcel text and verbatim source excerpts, and produce a rule-based verdict. Meterless records evidence patterns after claim validation. The implementation does not currently verify the seller against a live official land register.

The recommended next step is to make evidence and source coverage transparent, then build an assisted ownership check around an official search result. Direct Ardhisasa automation should remain out of scope unless the State Department confirms an authorized API or integration route. The public portal and user guidance demonstrate interactive, authenticated services; they do not establish a third-party API contract.

A Nairobi cadastre map could improve parcel identity resolution and spatial checks. No cadastre dataset is currently present in this repository. It must be inspected for format, coordinate reference system, coverage, date, provenance, license, and parcel identifiers before implementation.

## What the current implementation reads

### Current local configuration

The repository-root `.env` currently sets `SAMPLE_MODE=false` and configures `land_files.gazette_notices_agent` as its Zetaris notices table. The judgments and registry table settings are blank. Secrets are intentionally not reproduced here.

### Source inventory

| Input | Current implementation | Runtime status / caveat |
|---|---|---|
| Kenya Gazette land notices | `data/extracts/gazette_notices.parquet` in sample mode; `land_files.gazette_notices_agent` in live mode. The extractor stores notice IDs, raw text, parcel references, and a `source_url`. | Live notices table is configured. The repository’s documented extract covers Gazette issues from 2022–2024, so absence from it is not proof that no notice exists outside that period. |
| Cancelled title serials | `data/extracts/cancelled_serials.csv` is loaded locally in both modes. It is derived from Gazette Notice 12436. The fast guard can return STOP before any Zetaris query. | Available locally, not a live serial-list query. The serial guard directly creates a confirmed claim; ensure its notice ID, matched range, excerpt, and source are validated together. |
| Environment and Land Court judgments | `data/extracts/judgments.csv` in sample mode, built from 14 selected Kenya Law decisions. | No live judgments table is configured. The sample is curated and small, not comprehensive. |
| Registry | `data/extracts/synthetic_registry.csv` in sample mode; each row is synthetic. | No live registry table is configured. It must never be presented as an official ownership check. |
| Seller details | Buyer can enter a seller name in the web form. | The current agent does not compare it to a registry proprietor. Avoid collecting identity data until there is an approved purpose, consent flow, and retention policy. |
| Survey/cadastre data | No active adapter or repository dataset found. | The buyer’s Nairobi map could add parcel geometry/identifier matching, subject to the map assessment below. |

The live Zetaris client is read-only and executes SQL through the configured Zetaris endpoint. It does not itself ingest or update source data. See `agents/sources.py`, `agents/config.py`, `data/scripts/`, and the source table in `README.md`.

## External source feasibility

Publicly viewable pages and documents do not by themselves imply an API, stable automated access, or permission to scrape. Before building each connector, confirm the source’s terms, rate limits, data reuse rights, supported access method, and any authentication requirements.

| Candidate source | Potential use | Feasibility assessment |
|---|---|---|
| [Kenya Law Gazette archive](https://kenyalaw.org/gazettes/) | Gazette issue pages and issue PDFs; extract notices, source IDs, text, and source URLs. | Existing scripts already list issues and download PDFs with a delay. This is the clearest available ingestion path, but it is a website/PDF workflow, not a confirmed API. Keep the current respectful rate limiting and record failures. |
| [Kenya Law judgments](https://new.kenyalaw.org) | Environment and Land Court decisions and other relevant judgments. | Repository tooling fetches a hand-picked set of pages. A wider search API or bulk feed has not been verified. Build only from documented/authorized interfaces and preserve decision URLs, court, case number, date, and paragraph/page anchors. |
| [Ardhisasa](https://ardhisasa.lands.go.ke/home) | Official search for registered proprietor and registered interests. | A portal workflow is documented; individual access describes identity verification and OTP login, and its FAQ defines a search as confirming ownership details and registered interests. No public third-party developer API documentation was identified in the official material reviewed. Treat API access as **unconfirmed**. Do not automate a buyer’s password/OTP flow or scrape behind login. Seek written integration authorization. |
| State Department search certificate | Official current register details and encumbrances. | The State Department describes the certificate as a direct registry search for ownership status and encumbrances. Near-term route: buyer obtains the official result and supplies it to the app for assisted extraction/comparison. An upload is sensitive data and needs explicit consent, encryption, limited access, and deletion controls. |
| State Department survey search / Nairobi cadastre | Plans, dimensions, survey numbers, beacons, and parcel geometry. | Potentially useful for resolving parcel identity and comparing boundaries, but does not establish registered ownership. Direct access is unconfirmed; the user's map must be assessed before selecting a parser or geospatial data store. |
| General web search / third-party property pages | Discovery leads only. | Do not treat scraped listings, blogs, or name matches as proof of ownership. They can generate leads for primary-source searches, clearly labeled as unverified. |

The Land Registration Act describes the register and official searches, and treats a certificate of title as prima facie evidence of proprietorship subject to statutory exceptions. This supports using official registry evidence as the ownership source of record, not substituting a model’s inference for it. See [Land Registration Act](https://new.kenyalaw.org/akn/ke/act/2012/3/~part_VII__sec_71__subsec_3) and [Land Registration (General) Regulations, official search](https://new.kenyalaw.org/akn/ke/act/ln/2017/278/eng%402017-11-24/source).

## Nairobi cadastre map assessment

The map is not currently present in the repository. Before integrating it, collect:

1. Original file(s) and format: vector GIS (GeoPackage, Shapefile, GeoJSON) is preferred; a georeferenced raster is usable; an image/PDF without georeferencing is only a visual reference.
2. Publisher/authority, license or permission to process it, publication/revision date, and known completeness.
3. Coordinate reference system, registration section/block coverage, parcel identifier fields, and whether parcel boundaries are authoritative or indicative.
4. A small set of independently checked sample parcels to measure geocoding and parcel-join errors.

If structured and authorized, index parcel polygons by normalized parcel ID and spatial index. Use the map to resolve aliases, detect duplicate/overlapping geometries, compare claimed location/area, and route ambiguous matches to review. Do not use geometry alone to infer owner, title validity, or a legal boundary determination. Keep source version and geometry provenance on every spatial result.

## Citation and explanation design

The current dossier includes claim kind, parcel, quote, source type, source ID, and status. Gazette raw records already carry `source_url`, but that URL is not carried into the API claim contract or rendered as a link. Add an evidence reference that preserves:

- Stable source ID, source authority/type, title/case/notice number, publication date, source URL, and retrieved-at timestamp.
- Immutable source snapshot hash/version and extraction method/version.
- Exact quote plus page/paragraph or character offsets to highlight it in the source excerpt.
- Parcel/serial match method and matched fields; distinguish exact match, normalized alias, and text-only candidate.
- Evidence status (`confirmed`, `unverified`, `rejected`) and, for rejected items, the reason.
- The explicit verdict rule that used the confirmed claim(s); keep model prose separate from the rule output.

In the UI, render inline numbered citations. Hover/focus may show a short preview; click opens a keyboard-accessible evidence card with context surrounding the verbatim quote, highlighted matching text, source metadata, and an external-source link where available. Provide an open-source action and a clear message when a source PDF/link is unavailable. Never rely on hover alone. Escape/sanitize source content and treat downloaded documents as untrusted input.

Each verdict should identify its contributing evidence and rule, then list searches not completed or sources unavailable. “No match found in the sources searched” must not be presented as proof of clean title or ownership.

## Agentic architecture proposal

Use bounded, inspectable graph nodes rather than one unconstrained agent:

1. **Intake and parcel resolver:** normalize parcel/title formats, use the cadastre only where its scope/provenance is known, return candidate identities when ambiguous.
2. **Search planner:** produce a structured, allow-listed query plan for registered source connectors; enforce source, request, time, and result limits.
3. **Source investigators:** run independent Gazette, court, survey, and official-registry tasks where access is authorized. Parallelize independent read-only lookups.
4. **Document extractor:** propose structured claims from PDFs/pages with exact quote spans and source anchors. LLM extraction may propose evidence; it cannot confirm it.
5. **Evidence verifier/critic:** deterministic parcel identity check, date and source validation, verbatim quote check, duplicate/contradiction handling, and freshness/authority classification.
6. **Ownership reconciler:** compare a buyer-supplied official search and title particulars with the parcel and seller-provided details; minimize PII and report mismatches rather than pronounce legal validity.
7. **Adversarial reviewer:** look for parcel collisions, stale/contradictory records, missing sources, and alternative interpretations. It can force abstention/escalation, not override evidence rules.
8. **Risk policy and dossier writer:** deterministic verdict rules consume only verifier-approved evidence. The writer explains the rule with citations and coverage limits.
9. **Follow-through coordinator:** prepares official-search and advocate/survey checklists and tracks missing documents; no transaction approval or filing/payment actions.

Meterless World Model/H-MEM can continue to store relationships/patterns derived from critic-confirmed claims. Memory is context for investigating or explaining; it is not a source of new factual claims and must never independently change a verdict.

## Ownership verification workflow

### Near-term assisted ownership check

1. Ask the buyer to obtain a fresh official search through the government channel, or use a formally authorized API if one becomes available.
2. Accept the official result through a consented, secure upload. Do not request or store Ardhisasa login credentials or OTPs.
3. Extract proprietor(s), parcel/title identifiers, tenure, encumbrances/restrictions/cautions/charges, and pending applications where present.
4. Compare those values with the buyer's parcel, supplied title particulars, and seller name. If identity comparison requires national ID data, scope and retention must be explicit; ideally use a privacy-minimized match and delete the raw ID after comparison.
5. Mark the document as buyer-supplied until authenticity is checked through an official verification mechanism. Show mismatches and missing fields for advocate review.
6. Keep physical possession, site boundaries, and questions of legal authority in the unresolved checklist unless an appropriately qualified source/process verifies them.

### Autonomy boundary

Automate retrieval, deduplication, parsing, cross-document matching, citation, completeness checks, and follow-up reminders. Do not claim the system proves that a seller is legally entitled to sell or that the physical land matches the register unless that result comes from an authoritative verification process. The Act identifies title as prima facie evidence and recognizes exceptions; legal interpretation and contested facts should be routed for qualified review.

## Recurring system evaluation

The current `eval/run_cases.py` and `eval/cases.yaml` are a starting harness, not a production self-certification system. Extend them into scheduled and event-triggered evaluation:

- **Triggers:** nightly/weekly run; every parser, rule, prompt/model, or source-corpus change; and before release.
- **Golden set:** human-adjudicated, versioned cases covering each claim type, parcel aliases/collisions, ambiguous matches, source conflicts, stale data, malformed documents, and no-evidence cases. Keep an untouched holdout set.
- **Evidence gates:** exact quote-to-snapshot match, citation completeness, parcel precision, expected evidence IDs, dates/windows, duplicate handling, and no confirmed unsupported claims.
- **Outcome gates:** verdict accuracy and false-negative/false-positive rates per claim type; safe abstention when sources are missing, stale, or contradictory.
- **Operational gates:** source freshness/coverage, ingestion/extraction failures, connector errors, rate limits, response latency, and browser/API mock-fallback rate.
- **Independent review:** periodically blind-audit randomly sampled dossiers with an advocate/qualified reviewer. Use a second model as a diagnostic only, not the sole judge.
- **Versioned report:** record code, model/prompt/rules, source snapshot hash, evaluation set version, metric deltas, and failures; keep PII and secrets out of logs.
- **Safe action:** alerts and blocks promotion or quarantines a failing parser/source path. No autonomous prompt/rule/model self-modification or automatic deployment based only on its own score.

## Phased delivery and acceptance criteria

### Phase 0 — Source inventory and trust labeling

- Publish an in-product source coverage panel: source name, live/sample/synthetic, coverage range, last successful retrieval, and missing connectors.
- Remove silent mock fallback or require a prominent demo-data banner with retry/error details.
- Add tests for serial-to-notice linkage and no-source/connector-failure abstention.

**Accept when:** a buyer can tell exactly which data sources ran, which did not, and whether results are live, sample, synthetic, or stale.

### Phase 1 — Evidence citations and verdict reasons

- Extend claim/API schema to carry source URL, authority, publication/retrieval dates, source snapshot/hash, excerpt anchors, match basis, and verdict rule references.
- Render citation cards and a “Why this verdict?” section with highlighted excerpts and explicit search coverage.

**Accept when:** every confirmed claim and every verdict reason opens its exact source evidence or shows why it cannot; excerpts are byte/text-verifiable against preserved source snapshots.

### Phase 2 — Broaden public-source ingestion

- Expand Kenya Gazette collection with respectful rate limits, retries, source snapshot checksums, and parser quality metrics.
- Expand Kenya Law judgments only through a verified permissible interface; record source IDs and exact paragraph anchors.
- Add relevant official public notices and survey sources only after source ownership/access/terms are confirmed.

**Accept when:** every connector has an approved access method, provenance fields, coverage/freshness limits, and parser regression cases.

### Phase 3 — Cadastre and assisted official-search matching

- Assess the user's Nairobi cadastre file against the checklist above; build an isolated import/validation spike after the actual file and terms are known.
- Add secure official-search document intake and deterministic field comparison; pursue direct Ardhisasa integration only after written authorization/API documentation.

**Accept when:** map matching reports source/coverage uncertainty; official-search ownership comparison cites document fields; no synthetic row is represented as a real registry result.

### Phase 4 — Bounded orchestration and exception handling

- Decompose current graph into explicit search/extraction/verification/reconciliation/review nodes; allow only registered read-only tools.
- Add budgets, timeouts, retries, idempotency, audit events, and escalation reasons.

**Accept when:** every agent action has an auditable tool/source record; claims cannot bypass verification; memory cannot create claims or verdicts.

### Phase 5 — Continuous evaluation and operations

- Schedule the expanded evaluation suite and source-health checks; publish result deltas and notify maintainers on regressions.
- Gate releases or quarantine degraded source connectors.

**Accept when:** a source or parser regression is detected before it can silently change buyer-facing results; rollback is documented and exercised.

## Open dependencies

1. Obtain the Nairobi cadastre file, source/authority/license details, and any accompanying projection or metadata.
2. Confirm with the State Department whether an authorized Ardhisasa/registry API or institutional integration exists and what permission, fees, and data terms apply.
3. Decide who may upload official-search certificates, how identity fields are handled, and retention/deletion periods.
4. Confirm permitted automated retrieval and reuse terms for Kenya Law Gazette and judgment content at the scale intended.
5. Expand the human-reviewed evaluation set before broadening sources or changing verdict policy.
