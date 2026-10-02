# Change Risk Radar
![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white)
![Groq](https://img.shields.io/badge/Groq-f55036?style=for-the-badge&logo=groq&logoColor=white)
![ChromaDB](https://img.shields.io/badge/ChromaDB-000000?style=for-the-badge&logo=chromadb&logoColor=white)
![Hugging Face](https://img.shields.io/badge/Hugging%20Face-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black)

**What breaks if you make this change?**

Change Risk Radar runs 5 analysis agents against your codebase every
time you commit, and shows you the blast radius — affected files/
services, missing test coverage, and doc/code drift — before you push.
It doesn't just prompt-and-hope: agents call real tools (an AST-based
call graph, git history, filesystem checks) and every claim is verified
against the actual repo before it reaches the dashboard.

Works on any Python repo, not just a specific project layout — see
[Project structure](#project-structure) for how it adapts.

## How it works

1. You commit code in your project
2. A git pre-commit hook sends the diff to a local orchestrator
3. The orchestrator runs 4 agents in parallel — Code Impact, Dependency,
   Test Intelligence, History — then a 5th agent (Risk Card Composer)
   merges their findings into one structured, schema-validated verdict
4. Your browser automatically opens to a dashboard showing the result —
   no manual steps, no copy-pasting a diff

This is a **local-only tool**, the same as ESLint, Husky, or a local
Postgres instance: it needs to be running in the background on your
machine for the hook to work. Everything happens on localhost; nothing
is hosted externally.


![Architecture diagram](architecture%20%281%29.png)

## Agent tools ("plugins")

Agents don't just guess from a prompt — each one calls real tools
against your repo, and results are grounded in what these actually
return:

| Tool | What it does |
|---|---|
| `list_dir` | Lists files/folders — lets an agent learn the repo's actual layout instead of assuming one |
| `read_file` | Reads a file's contents (blocked for anything matching a secret/credential pattern — see Security below) |
| `grep` | Regex search across the repo |
| `find_callers` | **Ground truth, not a guess** — every real call site of a function/class, found by parsing the AST of every `.py` file |
| `symbol_exists` | Confirms a function/class name is real before an agent cites it |
| `git_history_for_file` | Searches a file's real commit history for past fixes/reverts/regressions — this is what powers the History agent |

## Trust and verification layers

- **Structured output** — the Risk Card Composer uses JSON-schema-constrained
  output, not regex-parsed free text (with a fallback path for models/
  providers with weaker schema support)
- **Claim verification** — every `affected_services` entry is checked
  against the real filesystem before it reaches the dashboard; anything
  unverifiable is stripped out and flagged, not silently kept
- **Groundedness scoring** — `grounding.py` runs automatically on every
  commit, checking how many code symbols an agent cites actually exist
  in the repo vs. were hallucinated
- **Verdict floor** — deterministic rules prevent the verdict from being
  purely a subjective LLM call (e.g. missing tests or drift warnings
  can't silently result in "approve")
- **Regression eval suite** — `eval/run_eval.py` checks pipeline output
  against hand-verified golden answers, so you can tell whether a prompt
  or model change actually helped

## Security

`read_file` and `grep` refuse anything matching a secret/credential
pattern (`.env`, `*secret*`, `*.pem`, `id_rsa`, etc.) — these are never
sent to the LLM API. Still: any code and file content the agents *do*
read is sent to a third-party API (Groq). Don't point this at a repo
containing anything sensitive without reviewing what that implies for
your situation.

## Setup (one-time, ~2 minutes)

```powershell
git clone <YOUR_REPOSITORY_URL>
cd change-risk-radar
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set `GROQ_API_KEY` (get one free at
[console.groq.com/keys](https://console.groq.com/keys)).

**1. Start the orchestrator and leave it running:**

```
uvicorn orchestrator.main:app --reload
```

Keep this terminal open while you work — same as leaving any local dev
server running.

**2. Sanity-check the model actually understands your repo, before wiring anything up:**

```
python explore.py --repo /path/to/your/repo
```

**3. Install the git hook into the repo you want to protect:**

```powershell
Copy-Item pre-commit-hook-example.sh <target-repo>\.git\hooks\pre-commit
```

(No file extension on the destination — git looks for an exact filename.)

That's it. Every commit in `<target-repo>` now triggers analysis
automatically.

## Try it

Make a change in your target repo, then:

```
git add .
git commit -m "test"
```

A browser window opens automatically to `http://localhost:8000/dashboard`
showing the risk card for that change.

You can also trigger an analysis manually, via the "Run a manual test"
section on the dashboard, or directly:

```
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"repo_path": "/absolute/path/to/repo", "diff": "paste a git diff here"}'
```

## Running the eval suite

```
python eval/run_eval.py --repo /path/to/repo/the/cases/target
```

Checks pipeline output against hand-verified golden answers in
`eval/cases/*.json`, logs pass rate and groundedness score to
`eval/eval_history.jsonl` on every run. See that folder's cases for the
expected format — every `expected_affected_services` value should be
independently verified against `find_callers` before being written, not
guessed.

## Project structure

```
orchestrator/
  main.py       FastAPI app: /analyze, /latest, /result/{hash}, /history, /dashboard, /health
  agents.py     Runs each agent via Groq (OpenAI-compatible API) with the tool loop above
  callgraph.py  AST-based static call graph — ground truth for find_callers/symbol_exists
  grounding.py  Automatic hallucination/groundedness scoring for agent text
  storage.py    SQLite, keyed by commit hash (or diff-content hash from the hook)
  prompts.py    Role prompts for the 5 agents
  risk_card.py  Schema-constrained composer output, verification, verdict floor rules
dashboard.html  Auto-loads and renders the latest analysis on open
explore.py      Standalone sanity check: does the model understand a new repo?
eval/
  run_eval.py       Regression suite runner
  cases/*.json      Golden test cases with hand-verified expected answers
pre-commit-hook-example.sh   Copy into a target repo's .git/hooks/
requirements.txt
```

## Known limitations

- **Python only** for the ground-truth call graph (`ast`-based). On a
  JS/Java/Go repo, agents fall back to `grep`-based searching with no
  verified ground truth.
- **Single-user, local-only.** No team visibility — results live in a
  local SQLite file on one machine. See Roadmap below for the path to
  team-wide use.
- **History agent** only sees what this repo's own git commit messages
  say — it has no connection to Jira, PagerDuty, or any external
  incident tracker.
- **Windows-tested primarily.** The hook and orchestrator have been most
  heavily exercised on Windows; macOS/Linux should work but is less
  battle-tested.
- Never enforces anything — the hook always allows the commit through,
  even on a "block" verdict. The risk card is advisory only.

## Roadmap

- Swap the local git hook for a GitHub App / webhook on PR-open, so the
  whole team sees the same risk card on a pull request, not just the
  commit author
- Wire the History agent to a real incident tracker (Jira, PagerDuty)
  instead of local git log
- IDE integration (inline warning on save) instead of a browser popup
- Multi-language call graph support beyond Python

## Performance for larger repositories

Change Risk Radar uses incremental analysis so repeated scans do not rebuild the Python AST index from scratch. It also focuses agents on files in the supplied Git diff, runs targeted pytest by default, caches completed commit analyses, and runs independent agents concurrently.

Optional environment controls:

- `GROQ_MAX_CONCURRENCY=4` — concurrent LLM calls
- `MAX_TOOL_ROUNDS=4` — maximum tool-exploration rounds per agent
- `MAX_TOOL_OUTPUT_CHARS=4000` — cap tool output sent to the model
- `FULL_PYTEST=1` — opt into the full test suite instead of targeted tests
