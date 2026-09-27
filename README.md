<div align="center">

# 🛡️ Change Risk Radar

### AI-powered pre-commit change impact & regression intelligence

**Know what your code change can break — before it reaches production.**

<p>
  <img src="https://img.shields.io/badge/IBM%20Bob-2.0-0F62FE?style=for-the-badge&logo=ibm" alt="IBM Bob 2.0"/>
  <img src="https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/Git-Pre--Commit-E44C30?style=for-the-badge&logo=git&logoColor=white" alt="Git"/>
  <img src="https://img.shields.io/badge/Multi--Agent-AI-7B61FF?style=for-the-badge" alt="Multi-Agent AI"/>
</p>

<p>
  <a href="#-why-change-risk-radar">Why?</a> •
  <a href="#-how-it-works">How it works</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-integrate-with-your-repository">Integration</a> •
  <a href="#-agents">Agents</a> •
  <a href="#-contributing">Contributing</a>
</p>

</div>

---

## 🚨 The Problem

A developer changes one function.

That change may silently affect:

- downstream services
- API contracts
- database models
- existing tests
- business rules
- historical bug patterns
- documentation and architecture assumptions

Today, developers often discover these consequences through manual code tracing, broad regression runs, code reviews, or — worst case — after deployment.

### The question

> **"What breaks if I make this change?"**

### The answer

**Change Risk Radar automatically investigates the change at commit time and gives the developer a risk report before the change moves further through the development lifecycle.**

---

## 💡 What Change Risk Radar Does

Change Risk Radar attaches to a Git repository through a **pre-commit hook**.

When the developer commits:

```bash
git commit -m "update statement service"
```

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

![Change Risk Radar Architecture](docs/architecture.png)

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
pip install -r requirements.txt
```

## 4. Configure environment variables

Create a `.env` file:

```env
IBM_BOB_API_KEY=your_key_here
IBM_BOB_MODEL=your_model_here

# Optional
RADAR_PORT=8000
RADAR_HOST=127.0.0.1
```

> Keep credentials out of Git. Add `.env` to `.gitignore`.

## 5. Start the Change Risk Radar server

```bash
uvicorn orchestrator.main:app --reload --port 8000
```

The API will be available at:

```text
http://127.0.0.1:8000
```

Dashboard:

```text
http://127.0.0.1:8000/dashboard
```

---

# 🔌 Integrate With Your Repository

The main goal is **zero-change developer workflow**.

The developer should continue using Git normally.

## Option A — Copy the pre-commit hook

Copy the provided hook into the repository being monitored:

```text
your-main-repo/
└── .git/
    └── hooks/
        └── pre-commit
```

Windows PowerShell example:

```powershell
Copy-Item "path\to\change-risk-radar\pre-commit-hook-example.sh" `
          -Destination ".git\hooks\pre-commit"
```

For Git Bash / macOS / Linux:

```bash
cp path/to/change-risk-radar/pre-commit-hook-example.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## Option B — Install the hook from the project

If your team wants a repeatable installation process, provide an installer:

```bash
./install-hook.sh
```

The installer should place the hook at:

```text
.git/hooks/pre-commit
```

and make it executable where required.

---

# 🔄 Developer Workflow

Once installed, the developer does **not** need to learn a new workflow.

### Normal workflow

```bash
git add .
git commit -m "update statement service"
```

### Behind the scenes

```text
git commit
    │
    ▼
pre-commit hook
    │
    ▼
Change Risk Radar API
    │
    ▼
5-agent analysis
    │
    ▼
Risk report generated
    │
    ▼
Dashboard opens
```

---

# 📊 Example Risk Report

A typical result can look like:

```text
┌───────────────────────────────────────────────┐
│              CHANGE RISK RADAR                │
├───────────────────────────────────────────────┤
│ STATUS: BLOCK                                 │
│ IMPACT: HIGH                                  │
│                                               │
│ AFFECTED SERVICES                             │
│ • statement_service                           │
│ • payment_service                             │
│ • fee_service                                 │
│                                               │
│ MISSING TESTS                                 │
│ • outstanding fee calculation                 │
│ • statement integration                       │
│ • unsettled payment scenario                  │
│                                               │
│ DRIFT WARNINGS                                │
│ • undocumented runtime dependency             │
│ • model changed without schema coverage       │
│ • service currently lacks test coverage       │
└───────────────────────────────────────────────┘
```

The purpose is not to replace the developer's judgment.

It is to surface **hidden impact before the change becomes a production problem**.

---

# 🤖 Agent Responsibilities

## 1. Code Impact Agent

Analyzes the changed code and traces relevant relationships.

```text
Changed function
      ↓
Callers
      ↓
Dependent functions
      ↓
Potentially affected components
```

Useful for answering:

> "What code directly or indirectly depends on this?"

---

## 2. Dependency Agent

Builds a dependency view across the project.

It can inspect:

- imports
- service references
- API usage
- configuration
- project structure
- documented architecture

Useful for answering:

> "Which services or components could be affected?"

---

## 3. Test Intelligence Agent

Analyzes existing tests against the change.

It identifies:

- relevant existing tests
- uncovered paths
- missing scenarios
- potentially affected test suites
- regression opportunities

Useful for answering:

> "What should I test because of this change?"

---

## 4. History Agent

Uses repository history and available incident/change records.

It looks for:

- similar changes
- previous failures
- related commits
- recurring defect patterns

Useful for answering:

> "Has something similar broken before?"

---

## 5. Risk Card Composer

Receives the outputs from the analysis agents and creates the final structured assessment.

It combines:

```text
Code Impact
     +
Dependencies
     +
Tests
     +
Historical Evidence
     ↓
Risk Card
```

The dashboard presents the result in a form that a developer can act on quickly.

---

# 🧩 Why Multi-Agent?

A single general-purpose prompt has to perform too many unrelated tasks.

Instead, Change Risk Radar separates the investigation:

```text
                  ┌──────────────────┐
                  │   Orchestrator   │
                  └────────┬─────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
       Code             Tests           History
       Agent            Agent            Agent
          │                │                │
          └────────────────┼────────────────┘
                           │
                           ▼
                    Risk Composer
```

This enables:

- specialized reasoning
- parallel analysis
- clearer agent outputs
- easier debugging
- easier extension with additional agents

---

# 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| **IBM Bob 2.0** | AI-assisted development and agent workflow |
| **Python** | Core implementation |
| **FastAPI** | Local orchestration API |
| **Git** | Source-control integration |
| **Git pre-commit hooks** | Automatic workflow trigger |
| **Async / parallel execution** | Concurrent agent analysis |
| **HTML/CSS/JavaScript** | Risk dashboard |
| **Git history** | Historical change context |
| **Project documentation** | Context for dependency / drift analysis |

---

# 📁 Suggested Repository Structure

```text
change-risk-radar/
│
├── orchestrator/
│   ├── main.py
│   ├── agents/
│   │   ├── code_impact.py
│   │   ├── dependency.py
│   │   ├── test_intelligence.py
│   │   ├── history.py
│   │   └── risk_composer.py
│   │
│   └── services/
│       ├── git_service.py
│       └── analysis_service.py
│
├── dashboard/
│   ├── index.html
│   ├── styles.css
│   └── app.js
│
├── hooks/
│   └── pre-commit-hook-example.sh
│
├── docs/
│   └── architecture.png
│
├── tests/
│
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

> Adapt the structure above to the actual repository layout.

---

# 🔐 Security & Repository Safety

Change Risk Radar should be treated as a developer-side engineering tool.

### Never commit:

```text
.env
API keys
tokens
passwords
private certificates
production credentials
```

Recommended:

```gitignore
.env
.venv/
__pycache__/
*.pyc
```

For enterprise adoption, the system should additionally support:

- secret redaction
- configurable file exclusions
- local-only analysis
- audit logging
- role-based access
- configurable retention
- organization-specific policies

---

# 🧪 Testing the Integration

Create a small change in the monitored repository:

```python
def calculate_fee(amount):
    return amount * 0.012
```

Then:

```bash
git add .
git commit -m "change transaction fee"
```

Expected workflow:

```text
✔ Git detects commit
✔ Pre-commit hook executes
✔ Radar receives change
✔ Agents analyze the change
✔ Risk card is composed
✔ Dashboard becomes available
```

---

# 🚦 Risk Policy

A deployment can configure its own thresholds.

Example:

| Risk | Meaning | Suggested action |
|---|---|---|
| 🟢 LOW | Limited impact detected | Continue |
| 🟡 MEDIUM | Review recommended | Continue with warning |
| 🔴 HIGH | Significant impact / missing verification | Review or block |

> Risk classification is an engineering aid, not an absolute guarantee of production safety.

---

# 🎯 Design Principle

Change Risk Radar is built around one simple question:

## **"What breaks if I make this change?"**

Traditional development tools primarily answer:

> **"Is my code syntactically correct?"**

Change Risk Radar aims to answer:

> **"What are the consequences of this change across the system?"**

That distinction is the core of the project.

---

# 🗺️ Roadmap

### Current

- [x] Git pre-commit integration
- [x] FastAPI orchestration
- [x] Multi-agent analysis
- [x] Parallel agent execution
- [x] Risk-card synthesis
- [x] Browser dashboard
- [x] Code / dependency / test / history analysis

### Next

- [ ] GitHub Pull Request integration
- [ ] GitLab / Bitbucket integration
- [ ] IDE notifications
- [ ] Inline PR comments
- [ ] Automatic regression-test generation
- [ ] Historical risk trends
- [ ] Configurable organization policies
- [ ] CI/CD quality gate
- [ ] Risk explanation with evidence links
- [ ] Repository-wide dependency graph

---

# 🤝 Contributing

Contributions are welcome.

### 1. Fork

```bash
git clone <your-fork-url>
cd change-risk-radar
```

### 2. Create a branch

```bash
git checkout -b feature/my-feature
```

### 3. Make your changes

```bash
git add .
git commit -m "feat: add dependency analysis"
```

### 4. Push

```bash
git push origin feature/my-feature
```

### 5. Open a Pull Request

Please include:

- problem being solved
- implementation details
- screenshots for UI changes
- tests added
- limitations / known issues

---

# 📜 License

Add the project's chosen license here, for example:

```text
MIT License
```

---

<div align="center">

### 🛡️ Change Risk Radar

**Catch the impact before production catches the bug.**

Built with ❤️ using **IBM Bob 2.0**

</div>
