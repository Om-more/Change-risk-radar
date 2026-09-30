# Change Risk Radar

**What breaks if you make this change?**

Change Risk Radar runs 5 analysis agents (via IBM Bob 2.0) against a
codebase every time you commit, and shows you the blast radius — affected
services, missing test coverage, and doc/code drift — before you push.

Built for the IBM Bob 2.0 Hackathon Challenge: *"improve a specific
developer workflow... build a working prototype that demonstrates a full
solution... leverage Agent mode, parallel tasks, subagents, and document
understanding to manage and improve multiple steps, not just assist with
coding."*

## How it works

1. You commit code in your project
2. A git pre-commit hook sends the diff to a local orchestrator
3. The orchestrator runs 4 agents in parallel via `bob -p` (Code Impact,
   Dependency, Test Intelligence, History), then a 5th agent (Risk Card
   Composer) merges their findings into one structured verdict
4. Your browser automatically opens to a dashboard showing the result —
   no manual steps, no copy-pasting a diff

This is a **local-only tool**, the same as ESLint, Husky, or a local
Postgres instance: it needs to be running in the background on your
machine for the hook to work. It does not require any hosting or
external server — everything happens on localhost.

## Setup (one-time, ~2 minutes)

```
<<<<<<< HEAD

the workflow becomes:

```text
Developer Commit
      │
      ▼
Git Pre-Commit Hook
      │
      ▼
FastAPI Orchestrator
      │
      ├──────────────┬──────────────┬──────────────┐
      ▼              ▼              ▼              ▼
 Code Impact     Dependency      Test Intel.     History
    Agent          Agent           Agent           Agent
      │              │               │              │
      └──────────────┴──────────────┴──────────────┘
                             │
                             ▼
                    Risk Card Composer
                             │
                             ▼
                      Risk Assessment
                             │
                             ▼
                         Dashboard
```

The developer gets the result **automatically**, without manually uploading code to an AI tool.

---

## 🧠 Architecture

<img width="1574" height="1125" alt="architecture (1)" src="https://github.com/user-attachments/assets/d243debe-9502-448f-8c03-55a1ffd8d467" />


### Agent orchestration

The system uses **five AI agents with distinct responsibilities**:

| Agent | Responsibility | Example output |
|---|---|---|
| 🔎 **Code Impact Agent** | Traces changed functions and callers | Affected functions / call paths |
| 🔗 **Dependency Agent** | Maps service and component dependencies | Affected services / APIs |
| 🧪 **Test Intelligence Agent** | Inspects and evaluates test coverage | Missing or relevant tests |
| 🕘 **History Agent** | Searches historical changes/incidents | Similar previous failures |
| 🧩 **Risk Card Composer** | Synthesizes all agent findings | Final risk / impact report |

The first four agents can work **in parallel**. The composer consumes their outputs and produces a single structured result.

---

# ⚡ Quick Start

## 1. Clone the project

```bash
git clone <YOUR_REPOSITORY_URL>
cd change-risk-radar
```

## 2. Create a virtual environment

### Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3. Install dependencies

```bash
=======
>>>>>>> 7107266 (final update)
pip install -r requirements.txt
```

This variant uses the Groq API instead of Bob Shell. Copy `.env.example` to
`.env` and set `GROQ_API_KEY` (get one at console.groq.com/keys).

**1. Start the orchestrator and leave it running:**

```
uvicorn orchestrator.main:app --reload
```

Keep this terminal open while you work — same as you'd leave a local dev
server running for any other tool.

**2. Install the git hook into the repo you want to protect:**

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

You can also trigger an analysis manually without committing, via the
"Run a manual test" section on the dashboard, or directly:

```
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"repo_path": "/absolute/path/to/repo", "diff": "paste a git diff here"}'
```

## Project structure

```
orchestrator/
  main.py       FastAPI app: /analyze, /latest, /dashboard, /health
  agents.py     Runs each agent via `bob -p`, handles Windows quirks
                (cmd.exe .cmd resolution, stdin piping for large content,
                transcript-output cleaning)
  prompts.py    Role prompts for the 5 agents
  risk_card.py  Merges the 4 agent reports into one JSON risk card
dashboard.html  Auto-loads and renders the latest analysis on open
pre-commit-hook-example.sh   Copy into a target repo's .git/hooks/
requirements.txt
```

## Sample repo

`dummy-bank/` (or wherever you keep it) is a toy banking microservices
codebase — Payment, Fee, Settlement, Statement, Fraud Rule Engine — used
to demo the tool against realistic cross-service dependencies, seeded
doc/code drift, and intentional test coverage gaps.

## Roadmap (beyond this hackathon)

- Swap the local git hook for a GitHub App / webhook on PR-open, so the
  whole team sees the same risk card on a pull request, not just the
  commit author
- Wire the History agent to a real incident tracker (Jira, PagerDuty)
  instead of the demo MCP incident store
- IDE integration (inline warning on save) instead of a browser popup
