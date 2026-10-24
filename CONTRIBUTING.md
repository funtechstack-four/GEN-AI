# Repo rulebook

How we manage branches, commits, issues and pull requests in GEN-AI. Short version:
**issue → branch off `dev` → small commits → PR into `dev` → review → squash merge.**

## 1. Branches

| Branch | What it is | Who changes it |
|---|---|---|
| `main` | The default branch and what we submit. Always runs. | Only through a PR from `dev`. No direct pushes, ever. |
| `dev` | Integration branch. All work branches start here and merge back here. | Only through PRs. No direct pushes. |
| `<type>/<short-name>` | One piece of work. Lives for hours to a day or two. | Its author. Deleted after merge. |

GitHub enforces this: `main` and `dev` need a PR with 1 approval, all review comments resolved,
and can't be force-pushed or deleted. On `main` the rule also binds admins; on `dev` an admin can
override in an emergency (say so in the team chat if you do).

### Naming work branches

`<type>/<short-name-in-kebab-case>`, optionally with the issue number: `feat/12-gazette-extraction`.

| Type | Use it for | Example |
|---|---|---|
| `feat/` | New behaviour or new data | `feat/evidence-critic` |
| `fix/` | A bug fix | `fix/serial-range-off-by-one` |
| `docs/` | README, rulebook, write-ups | `docs/sponsor-writeup` |
| `test/` | Tests only | `test/near-identical-parcels` |
| `refactor/` | Restructure without changing behaviour | `refactor/zetaris-client` |
| `chore/` | Tooling, config, dependencies | `chore/pin-langgraph` |

Lower case, hyphens, no spaces, under ~40 characters.

## 2. Day-to-day workflow

```bash
git switch dev && git pull                      # start from the latest dev
git switch -c feat/evidence-critic              # one branch per issue
# ...work, commit in small steps...
git fetch origin && git rebase origin/dev       # catch up before opening the PR
git push -u origin feat/evidence-critic
gh pr create --base dev --title "feat(agents): add evidence critic" --body "Closes #14"
```

- Keep a branch to one issue. If you find a second problem, open a second issue.
- Rebase your **own** branch on `dev` to stay current. Use `git push --force-with-lease` only on your own branch. Never force-push `dev` or `main`.
- Pull `dev` at least every morning stand-up.

## 3. Commits ([Conventional Commits](https://www.conventionalcommits.org/))

```
<type>(<scope>): <what changed, imperative, lower case, no full stop>
```

- **Types:** same list as branches (`feat`, `fix`, `docs`, `test`, `refactor`, `chore`).
- **Scopes** match our folders: `agents`, `data`, `bridge` (services/meterless-bridge), `web`, `eval`, `docs`, `repo`.
- Subject line ≤ 72 characters. Add a body only to explain *why*.
- Examples: `feat(data): extract land notices from gazette pdfs` · `fix(agents): reject parcel 288 when source says 289` · `test(data): cover 30-day objection windows`
- One logical change per commit. A commit should build and pass tests on its own.
- No attribution lines (no `Co-Authored-By` for tools).

## 4. Issues

- **Title:** short and plain, starts with a verb. `Extract land notices from Gazette PDFs`.
- **Description:** 1–3 lines: what and why, plus "done when …".
- **Labels:** `enhancement`, `bug`, `documentation`. **Assignee:** whoever is doing it.
- Every PR closes at least one issue.

## 5. Pull requests

- **Base:** `dev`. GitHub suggests `main` because it's the default, so switch the base to `dev` (or use `gh pr create --base dev`). Only release PRs target `main`.
- **Title:** written as a commit message (`feat(data): …`). It becomes the squash commit on `dev`.
- **Description:** use the template: what changed, how to test, `Closes #<n>`.
- **Size:** aim under ~400 changed lines (generated data files don't count). Split big work.
- **Review:** 1 approval, ideally the folder owner (below). Reviewers respond within 2 hours during build hours.
- **Merge:** **squash and merge** into `dev`. The branch is deleted automatically.
- Don't merge with failing tests or unresolved review comments.

### Folder owners (review their folder's PRs)

| Folder | Owner |
|---|---|
| `data/` | P1 Data + Zetaris |
| `agents/` | P2 Agents + NVIDIA |
| `services/`, `vendor/`, `web/components/trace/` | P3 Meterless + trace UI |
| `eval/`, `web/app/`, README, deck | P4 Truth, eval, demo |

## 6. Releases (`dev` → `main`)

- Open a PR from `dev` to `main` after each nightly checkpoint passes (22:00 EAT) and before submission.
- Title: `release: <date or checkpoint>`, e.g. `release: day 3 checkpoint`.
- Merge with a **merge commit** (not squash), so `main` keeps the history of what was released.
- Tag the submitted commit: `git tag submission && git push origin submission`.

## 7. Never commit

- `.env`, API keys, tokens, `.pem` files, server IPs. Secrets live in `.env` only; `.env.example` has placeholders. If a key ever lands in a commit, **rotate it**. Don't try to rewrite history.
- Downloaded PDFs (`data/raw/`), `research/`, `node_modules/`, `.venv/`, run logs (except `logs/samples/`).
- Changes to `vendor/meterless/`. It's pre-existing open source and stays unmodified.

## 8. Hackathon rules that affect git

- All product commits are after 22 Oct 2026 00:00 UTC. Anything older is declared as pre-existing.
- **Feature freeze: Sun 25 Oct 23:59 EAT.** After that, only `fix/` and `docs/` branches.
- Target submission: Tue 27 Oct 20:00 EAT. The submitted commit is on `main`, tagged `submission`.
