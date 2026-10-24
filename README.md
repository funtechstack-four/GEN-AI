# Land Title Due-Diligence Agent

In Kenya, a buyer can pay for a plot and later find out the title deed was reported lost, the land is in a succession case, or the government has gazetted it for acquisition. All of that is public, but it's spread across thousands of Gazette pages and court judgments that nobody reads before a sale.

This agent reads them for you. Give it a parcel number, the title deed serial, the seller's name and the sale date. It checks the public record and returns a dossier with a timeline, every flag it found (each with the exact quote and a link to the page it came from), whether any objection window is still open, and one of three verdicts.

Built by The Fun Tech Stack for the Open Agent Hackathon 2026, Track 2.

## The three verdicts

The agent never says a title is "clean", "safe" or "clear". Forged titles and impersonated owners leave no public trace, so the best it can say is that it found nothing.

| Verdict | When |
|---|---|
| **STOP** | The title serial is one of the 367 cancelled serials (5253001 to 5253367), or a confirmed lost-title notice is dated within 12 months before the sale, or a confirmed court order stops dealings on the parcel. |
| **HIGH RISK** | At least one confirmed flag (older lost title, succession, transfer dispute, compulsory acquisition, court case) that doesn't trigger STOP. |
| **VERIFY FIRST** | Nothing confirmed. The dossier still lists four checks to do: an official search, matching the seller's ID to the register, a site visit with a beacon survey, and an advocate's review. |

A flag only counts as "confirmed" when the Evidence Critic has found its quote word for word in the source and matched the parcel on registration section, district and number. If two sources disagree, the dossier sends it to advocate review and doesn't pick a side.

## Where the data comes from

| Source | What we use | File |
|---|---|---|
| Kenya Gazette, 2022 to 2024 (659 issues from [Kenya Law](https://kenyalaw.org/gazettes/)) | 19,360 land notices: lost titles, transfers, compulsory acquisitions and more | `data/extracts/gazette_notices.parquet` |
| Gazette Notice 12436 (27 Sep 2024) | The 367 title serials reported lost and cancelled | `data/extracts/cancelled_serials.csv` |
| Environment and Land Court judgments | 10 to 20 hand-picked cases | `data/extracts/judgments.csv` (coming) |
| Synthetic registry | Stand-in for an Ardhisasa search. Every row is marked `synthetic=true` | `data/extracts/synthetic_registry.csv` (coming) |

The PDFs themselves aren't committed. The scripts in `data/scripts/` download them again and rebuild the extracts (see below).

## How it fits together

```
 Next.js (web/)  ──HTTP──▶  FastAPI (agents/api.py, :8000)
                                 │
                       LangGraph state machine (Python 3.11)
   ┌────────────┬───────────────┼────────────────┬───────────────┬──────────────┐
 Intake      Gazette         Court           Pattern         Evidence       Risk Assessor
 Normaliser  Investigator ◀─▶ Investigator   Analyst         Critic         + Dossier Writer
   │            │   party names ▲               │               │ reject→retry once→"unverified"
   │            ▼                │               ▼               │
   │      Zetaris REST (:8888) ◀─┘       Meterless bridge (:4001, Node + tsx)
   │      one SQL view over 4 tables     World Model (graph) + H-MEM (patterns)
   │            ▲
   └─ STOP early exit if serial in range        Meterless Nightshift (:8088) → NVIDIA Nemotron
                                                 └─ recorded responses for SAMPLE_MODE
```

Each sponsor tool has one job:

- **Zetaris** holds the four tables (Parquet and CSV files in the S3 bucket `tfts-land-extracts`, database `land_files`) behind one SQL view, plus a data-quality rule that flags notices whose parcel isn't in the registry.
- **Meterless** World Model keeps the graph of parcels, people, notices and cases. H-MEM remembers patterns across dossiers, such as one person named in three or more lost-title notices.
- **Meterless Nightshift** runs on the laptop and is the only AI provider the app talks to. It holds the NVIDIA key and passes calls on to **NVIDIA Nemotron**, which classifies notices and pulls out names and parcels.

## Repo layout

```
agents/                      LangGraph graph, agent nodes, Nemotron client, Evidence Critic, FastAPI
data/scripts/                Gazette lister, downloader, PDF checker, notice extractor
data/extracts/               The committed tables listed above
services/meterless-bridge/   Small Node server in front of the Meterless engines
vendor/meterless/            Meterless reference engines, copied unmodified (Apache-2.0)
web/                         Next.js app: intake form, dossier page, trace viewer
eval/                        Demo cases and the scoring script
tests/                       pytest tests
logs/                        One {run_id}.jsonl per run (only logs/samples/ is committed)
```

## Getting started

You need Python 3.11+ and Git.

```
git clone https://github.com/funtechstack-four/GEN-AI.git
cd GEN-AI
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then fill in your own keys
pytest tests
```

`.env.example` lists every setting. Leave `SAMPLE_MODE=true` to run on recorded responses with no keys and no network. Set it to `false` and fill in `METERLESS_RUNTIME_TOKEN` (from Nightshift), `ZETARIS_REST_URL` and `ZETARIS_API_KEY` to run live. Nightshift has to be running, with your NVIDIA key added in its Providers tab. Never commit `.env`.

### Rebuilding the Gazette data

This takes about an hour, mostly downloading. The PDFs land in `data/raw/gazette/`, which git ignores.

```
python data/scripts/list_issues.py       # catalogue of 2022-2024 issues -> gazette_issues.csv
python data/scripts/download_issues.py   # fetch the PDFs (resumes if stopped; --year, --limit)
python data/scripts/verify_pdfs.py       # check each PDF's front page matches its issue -> gazette_pdf_check.csv
python data/scripts/extract_notices.py   # split into notices, keep the land ones -> gazette_notices.parquet
```

### Loading it into Zetaris

Upload the extract to `s3://tfts-land-extracts/`, then run each statement on its own (no trailing semicolon):

```sql
CREATE LIGHTNING FILESTORE TABLE gazette_notices FROM land_files FORMAT PARQUET OPTIONS (
  path "s3a://tfts-land-extracts/gazette_notices.parquet",
  isS3BucketPublic "true"
)
```

```sql
SELECT notice_type, COUNT(*) FROM land_files.gazette_notices GROUP BY notice_type
```

## Status

The data layer is in place: the Gazette notices and cancelled serials are extracted and queryable in Zetaris. The agents, the Meterless bridge and the web app are next. Open issues show who is on what.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) for how we name branches, write commits and open pull requests. In short: branch off `dev`, open your PR into `dev`, and never push to `main`.

## Team

Nathan, Rico (lead), Ryan and Chris.
