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
| Environment and Land Court judgments, 2022 to 2026 ([Kenya Law](https://new.kenyalaw.org), CC BY-NC 4.0) | 14 hand-picked cases on lost-title notices, duplicate titles and title fraud, each with a verbatim excerpt | `data/extracts/judgments.csv` |
| Synthetic registry | Stand-in for an Ardhisasa search. Every row is marked `synthetic=true` | `data/extracts/synthetic_registry.csv` |

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
   │      Zetaris REST (configured read-only query) ◀─┘  Meterless bridge (:4001, Node + tsx)
   │      Gazette table currently configured             World Model + H-MEM local memory
   │            ▲
   └─ STOP early exit if serial in range        Meterless Runtime (:8088) → routed models
                                                 └─ recorded responses for SAMPLE_MODE
```

Each sponsor tool has one job:

- **Zetaris** is the read-only query path for configured live tables. The current local configuration uses the Gazette notices table; judgments and registry tables are optional and are not configured. Cancelled serials are checked from the local CSV in both sample and live modes.
- **Meterless** World Model and H-MEM persist and recall context locally from critic-confirmed claims. They provide memory context; they do not establish evidence or determine the verdict. The cancelled-serial early-stop path bypasses Meterless.
- **Meterless Runtime** is registered as the `meterless` OpenAI-compatible provider, next to the app's other data services. The classifier uses `meterless/auto` for bounded fallback calls when deterministic notice rules find no kind. The runtime returns routing-mode ids from `/v1/models`; proposed party names are retained only if they occur in source text. The Evidence Critic and code-driven rules determine which claims are confirmed and how the verdict is assigned.

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

`.env.example` lists the legacy environment fallback settings. Leave `SAMPLE_MODE=true` to run on recorded responses with no provider calls. Open `http://localhost:3100/providers` to configure Meterless Runtime, paste its token or a `/connect#k=...` link, and use Auto Detect or enter its URL. The local API imports `<stateDir>/proxy-token` into `.state/provider-settings.json` under `meterless_runtime_token`. Tokens and provider settings stay in ignored `.state/`; never commit them. For live data, set `SAMPLE_MODE=false` and configure `ZETARIS_REST_URL` and `ZETARIS_API_KEY` as before.

### Running the agents

The LangGraph workflow has focused roles for intake normalization, cancelled-serial triage, Gazette and court investigation, evidence criticism, and risk assessment. Confirmed sources are checked against the exact normalized parcel and their quotes must occur verbatim in the fetched source text. The verdict is code-driven; retrieved memories and model classifications cannot independently create evidence.

The Meterless bridge runs the vendored World Model and H-MEM reference engines without modifying `vendor/meterless/`. It persists the source graph and evidence-pattern memories in `.state/meterless/`. Start the bridge and agents API in separate terminals:

```powershell
cd services/meterless-bridge
npm install
npm start
```

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn agents.api:app --reload --port 8000
```

For AWS-backed reads, set `SAMPLE_MODE=false` in the untracked `.env`, provide the Zetaris API key and organization ID, and point `ZETARIS_REST_URL` at the EC2 instance's REST endpoint (or its existing local SSH tunnel). The account needs read access to the configured tables. Set the `ZETARIS_*_TABLE` values if their names differ. The client issues read-only SQL through Zetaris' SQL query endpoint. It does not create or modify tables. When Meterless Runtime is online, the classifier sends otherwise-unclassified notices to the `meterless/auto` route; party names must match source text, and only the Evidence Critic can confirm claims.

Open the existing Next.js intake at `http://localhost:3100` with `NEXT_PUBLIC_API_URL=http://localhost:8000`, or submit JSON directly to `POST /dossier`. `GET /health` checks the API. Runs append structured JSONL traces under `logs/`.

### Rebuilding the Gazette data

This takes about an hour, mostly downloading. The PDFs land in `data/raw/gazette/`, which git ignores.

```
python data/scripts/list_issues.py       # catalogue of 2022-2024 issues -> gazette_issues.csv
python data/scripts/download_issues.py   # fetch the PDFs (resumes if stopped; --year, --limit)
python data/scripts/verify_pdfs.py       # check each PDF's front page matches its issue -> gazette_pdf_check.csv
python data/scripts/extract_notices.py   # split into notices, keep the land ones -> gazette_notices.parquet
```

### Loading it into Zetaris

Upload the extract to `s3://tfts-land-extracts-361738333327-eu-north-1-an/`, then run each statement on its own (no trailing semicolon):

```sql
CREATE LIGHTNING FILESTORE TABLE gazette_notices FROM land_files FORMAT PARQUET OPTIONS (
  path "s3a://tfts-land-extracts-361738333327-eu-north-1-an/gazette_notices.parquet",
  isS3BucketPublic "true"
)
```

```sql
SELECT notice_type, COUNT(*) FROM land_files.gazette_notices GROUP BY notice_type
```

## Status

The LangGraph agent API and Meterless bridge are implemented. Sample mode reads the committed extracts; live mode reads the configured Zetaris tables. The web app remains at `web/` and sends requests to the agents API. Live AWS access requires the endpoint, API key, organization ID and table names in the local, untracked `.env` file.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) for how we name branches, write commits and open pull requests. In short: branch off `dev`, open your PR into `dev`, and never push to `main`.

## Team

Nathan, Rico (lead), Ryan and Chris.
