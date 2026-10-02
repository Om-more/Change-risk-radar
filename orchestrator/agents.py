"""Agent runner backed by Groq (OpenAI-compatible API) instead of Bob Shell.

Each agent = a role prompt + the content to analyze + a small set of
read-only repo tools (list_dir, read_file, grep). The model calls tools
in a loop until it produces a final text answer. No CLI, no Windows .cmd
or transcript-cleaning issues: the SDK returns clean text.

Env vars:
  GROQ_API_KEY          required
  GROQ_MODEL            default: llama-3.3-70b-versatile (check the Groq
                        console for current tool-calling models)
  GROQ_MAX_CONCURRENCY  default: 2 (lower = fewer 429s on the free tier)
"""

import asyncio
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIError

from orchestrator import callgraph, prompts

load_dotenv()

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
MAX_TOOL_ROUNDS = int(os.getenv("MAX_TOOL_ROUNDS", "4"))
MAX_TOOL_OUTPUT_CHARS = int(os.getenv("MAX_TOOL_OUTPUT_CHARS", "4000"))   # keep tool results small: free tier is token-limited
MAX_RETRIES = 4
_semaphore = threading.Semaphore(int(os.getenv("GROQ_MAX_CONCURRENCY", "4")))

TOOL_HINT = (
    "\n\nThe content to analyze is in the user message. Wherever the role "
    "above mentions 'stdin' or '@path', that means the user message or files "
    "you can open with your tools. Use list_dir, read_file and grep to "
    "explore the repository before answering. Be concise. Plain text only."
)

TOOLS = [
    {"type": "function", "function": {
        "name": "list_dir",
        "description": "List files and folders in a directory of the repo.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Relative path, '.' for repo root"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a text file from the repo.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Relative file path"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "find_callers",
        "description": (
            "Ground truth (not a guess): every call site of a Python "
            "function/method/class name, found by parsing the AST of "
            "every .py file. Use this instead of grep for 'who calls X'."
        ),
        "parameters": {"type": "object", "properties": {
            "symbol": {"type": "string", "description": "Exact function/class name"}},
            "required": ["symbol"]}}},
    {"type": "function", "function": {
        "name": "symbol_exists",
        "description": "Ground truth check: does this exact function/class name exist anywhere in the repo's Python files? Use this before citing a symbol you're not 100% sure of.",
        "parameters": {"type": "object", "properties": {
            "symbol": {"type": "string"}},
            "required": ["symbol"]}}},
    {"type": "function", "function": {
        "name": "git_history_for_file",
        "description": (
            "Search this file's real git commit history for past fixes, "
            "bugs, reverts, or regressions (keyword search on commit "
            "messages: fix, bug, hotfix, revert, regression, broke). "
            "This is real project history, not a guess -- use it for "
            "'has this broken before' questions."
        ),
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "Relative file path"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "grep",
        "description": "Search the repo for a regex pattern. Returns file:line: text.",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string", "description": "Relative dir or file, default '.'"}},
            "required": ["pattern"]}}},
]

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache"}

# Never let a tool read these into a prompt that gets sent to an external
# API. This was harmless against the toy bank repo (no real secrets in
# it) -- it is not harmless against a real project.
_SECRET_PATTERNS = (
    ".env", "secret", "credential", "password", "token", ".pem", ".key",
    "id_rsa", ".pfx", ".p12", "service-account", "aws/credentials",
)


def _looks_like_secret(rel_path: str) -> bool:
    lower = rel_path.lower()
    return any(pat in lower for pat in _SECRET_PATTERNS)

# Built once per /analyze request (main.py calls invalidate_graph_cache()
# before each run) and shared across all 5 agents in that request, so we
# don't re-parse the whole repo 5+ times for one commit.
_graph_cache: dict = {}


def _get_graph(repo_path: str):
    if repo_path not in _graph_cache:
        _graph_cache[repo_path] = callgraph.build(repo_path)
    return _graph_cache[repo_path]


def invalidate_graph_cache(repo_path: str | None = None) -> None:
    if repo_path is None:
        _graph_cache.clear()
    else:
        _graph_cache.pop(repo_path, None)


class AgentError(Exception):
    """Raised when an LLM call fails."""


# ---------------------------------------------------------------- tools
def _safe_path(repo_path: str, rel: str) -> Path:
    root = Path(repo_path).resolve()
    target = (root / (rel or ".")).resolve()
    if root != target and root not in target.parents:
        raise ValueError("path escapes the repository")
    return target


def _truncate(text: str) -> str:
    if len(text) <= MAX_TOOL_OUTPUT_CHARS:
        return text
    return text[:MAX_TOOL_OUTPUT_CHARS] + "\n...[truncated]"


def _tool_list_dir(repo_path: str, path: str = ".") -> str:
    target = _safe_path(repo_path, path)
    if not target.is_dir():
        return f"Not a directory: {path}"
    names = sorted(
        (p.name + ("/" if p.is_dir() else ""))
        for p in target.iterdir() if p.name not in SKIP_DIRS
    )
    return _truncate("\n".join(names) or "(empty)")


def _tool_read_file(repo_path: str, path: str) -> str:
    if _looks_like_secret(path):
        return f"Refused: '{path}' looks like a secret/credential file and will not be read."
    target = _safe_path(repo_path, path)
    if not target.is_file():
        return f"Not a file: {path}"
    return _truncate(target.read_text(encoding="utf-8", errors="replace"))


_INCIDENT_KEYWORDS = ("fix", "bug", "hotfix", "revert", "regression", "broke", "incident")


def _tool_git_history_for_file(repo_path: str, path: str) -> str:
    if _looks_like_secret(path):
        return f"Refused: '{path}' looks like a secret/credential file."
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--follow", "--", path],
            cwd=repo_path, capture_output=True, text=True, timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return f"Could not read git history: {exc}"
    if result.returncode != 0:
        return f"git log failed: {result.stderr.strip()}"

    lines = result.stdout.strip().splitlines()
    if not lines:
        return f"No git history found for {path} (new file, or not tracked)."

    flagged = [
        line for line in lines
        if any(kw in line.lower() for kw in _INCIDENT_KEYWORDS)
    ]
    summary = [f"{len(lines)} total commits touching {path}."]
    if flagged:
        summary.append(f"{len(flagged)} look like past fixes/incidents:")
        summary.extend(flagged[:15])
    else:
        summary.append("None look like bug fixes based on commit message keywords "
                        "(this only catches what commit messages actually say).")
    return _truncate("\n".join(summary))


def _tool_grep(repo_path: str, pattern: str, path: str = ".") -> str:
    root = Path(repo_path).resolve()
    target = _safe_path(repo_path, path)
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return f"Invalid regex: {exc}"
    files = [target] if target.is_file() else [
        p for p in target.rglob("*")
        if p.is_file() and not (set(p.parts) & SKIP_DIRS)
        and not _looks_like_secret(str(p.relative_to(root)))
    ]
    hits = []
    for f in files:
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if rx.search(line):
                    hits.append(f"{f.relative_to(root)}:{i}: {line.strip()}")
        except (UnicodeDecodeError, OSError):
            continue
        if len(hits) > 200:
            break
    return _truncate("\n".join(hits) or "No matches.")


def _tool_find_callers(repo_path: str, symbol: str) -> str:
    return callgraph.format_callers(_get_graph(repo_path), symbol)


def _tool_symbol_exists(repo_path: str, symbol: str) -> str:
    exists = _get_graph(repo_path).symbol_exists(symbol)
    return f"{symbol} exists: {exists}"


def _dispatch_tool(repo_path: str, name: str, args: dict) -> str:
    try:
        if name == "list_dir":
            return _tool_list_dir(repo_path, args.get("path", "."))
        if name == "read_file":
            return _tool_read_file(repo_path, args["path"])
        if name == "grep":
            return _tool_grep(repo_path, args["pattern"], args.get("path", "."))
        if name == "find_callers":
            return _tool_find_callers(repo_path, args["symbol"])
        if name == "symbol_exists":
            return _tool_symbol_exists(repo_path, args["symbol"])
        if name == "git_history_for_file":
            return _tool_git_history_for_file(repo_path, args["path"])
        return f"Unknown tool: {name}"
    except Exception as exc:  # tool errors go back to the model, not the caller
        return f"Tool error: {exc}"


# ------------------------------------------------------------ LLM loop
def _get_client() -> OpenAI:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise AgentError("GROQ_API_KEY is not set. Put it in .env or export it.")
    return OpenAI(api_key=key, base_url=GROQ_BASE_URL)


def _create_with_retry(client: OpenAI, **kwargs):
    delay = 2.0
    for attempt in range(MAX_RETRIES):
        try:
            return client.chat.completions.create(**kwargs)
        except RateLimitError:
            if attempt == MAX_RETRIES - 1:
                raise AgentError("Groq rate limit (429) persisted after retries.")
            time.sleep(delay)
            delay *= 2
        except APIError as exc:
            raise AgentError(f"Groq API error: {exc}") from exc


def _run_llm_sync(role: str, content: str, repo_path: str, use_tools: bool) -> str:
    client = _get_client()
    system = role + (TOOL_HINT if use_tools else "")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ]
    with _semaphore:
        for _ in range(MAX_TOOL_ROUNDS):
            kwargs = {"model": MODEL, "messages": messages, "temperature": 0.1}
            if use_tools:
                kwargs["tools"] = TOOLS
            msg = _create_with_retry(client, **kwargs).choices[0].message

            if not msg.tool_calls:
                return (msg.content or "").strip()

            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name,
                                  "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ],
            })
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": _dispatch_tool(repo_path, tc.function.name, args),
                })

        # Out of rounds: force a final answer without tools.
        messages.append({"role": "user",
                         "content": "Stop exploring and give your final answer now."})
        final = _create_with_retry(client, model=MODEL, messages=messages, temperature=0.1)
        return (final.choices[0].message.content or "").strip()


async def run_llm(role: str, content: str, repo_path: str, use_tools: bool = True) -> str:
    return await asyncio.to_thread(_run_llm_sync, role, content, repo_path, use_tools)


# Backwards-compatible name so risk_card.py / main.py keep working.
run_bob = run_llm


def _run_json_sync(role: str, content: str, schema: dict) -> str:
    """Single non-tool call constrained to a JSON schema (best-effort mode:
    broadly supported across Groq/OpenAI-compatible models). Falls back to
    plain json_object mode if the schema request itself errors, so this
    degrades gracefully on models/providers with partial support."""
    client = _get_client()
    messages = [{"role": "system", "content": role}, {"role": "user", "content": content}]
    with _semaphore:
        try:
            resp = _create_with_retry(
                client, model=MODEL, messages=messages, temperature=0.1,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "risk_card", "strict": False, "schema": schema},
                },
            )
        except AgentError:
            resp = _create_with_retry(
                client, model=MODEL, messages=messages, temperature=0.1,
                response_format={"type": "json_object"},
            )
    return (resp.choices[0].message.content or "").strip()


async def run_json(role: str, content: str, schema: dict) -> str:
    return await asyncio.to_thread(_run_json_sync, role, content, schema)


# ------------------------------------------------------------- pytest
def run_pytest_sync(repo_path: str) -> str:
    """Runs the real test suite and returns raw output (pass/fail)."""
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "-v"],
            cwd=repo_path, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
        return _truncate(result.stdout + "\n" + result.stderr)
    except FileNotFoundError:
        return "pytest not found in this environment."
    except subprocess.TimeoutExpired:
        return "pytest run timed out."


def changed_files_from_diff(diff: str) -> list[str]:
    """Extract changed paths from a unified git diff."""
    paths = []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
            if path != "/dev/null" and path not in paths:
                paths.append(path)
    return paths


def _related_test_files(repo_path: str, changed_files: list[str]) -> list[str]:
    root = Path(repo_path).resolve()
    tests = []
    stems = {Path(p).stem.replace("test_", "") for p in changed_files}
    for p in root.rglob("test_*.py"):
        if set(p.parts) & SKIP_DIRS:
            continue
        stem = p.stem.replace("test_", "")
        if stem in stems or any(s and s in stem for s in stems):
            tests.append(str(p.relative_to(root)))
    for p in root.rglob("*_test.py"):
        if set(p.parts) & SKIP_DIRS:
            continue
        stem = p.stem.replace("_test", "")
        if stem in stems or any(s and s in stem for s in stems):
            tests.append(str(p.relative_to(root)))
    return list(dict.fromkeys(tests))[:12]


def run_targeted_pytest_sync(repo_path: str, changed_files: list[str]) -> str:
    """Run only likely affected tests; full suite is opt-in."""
    if os.getenv("FULL_PYTEST", "0") == "1":
        return run_pytest_sync(repo_path)
    root = Path(repo_path).resolve()
    targets = _related_test_files(repo_path, changed_files)
    changed_tests = [p for p in changed_files if p.startswith(("test_", "tests/", "test/")) and (root / p).exists()]
    targets = list(dict.fromkeys(changed_tests + targets))
    if not targets:
        return "Targeted pytest: no directly matching test files found. Full suite was skipped for speed."
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "-q", *targets],
            cwd=repo_path, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=45,
        )
        return _truncate(result.stdout + "\n" + result.stderr)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return f"Targeted pytest unavailable or timed out: {exc}"


# -------------------------------------------------------------- agents
async def run_code_impact(diff: str, repo_path: str) -> str:
    return await run_llm(prompts.CODE_IMPACT_ROLE, prompts.build_agent_input(diff, repo_path), repo_path)


async def run_dependency(diff: str, repo_path: str) -> str:
    return await run_llm(prompts.DEPENDENCY_ROLE, prompts.build_agent_input(diff, repo_path), repo_path)


async def run_history(diff: str, repo_path: str) -> str:
    return await run_llm(prompts.HISTORY_ROLE, prompts.build_agent_input(diff, repo_path), repo_path)


async def run_test_intel(diff: str, repo_path: str) -> str:
    changed = changed_files_from_diff(diff)
    pytest_output = await asyncio.to_thread(run_targeted_pytest_sync, repo_path, changed)
    stdin_content = prompts.build_test_intel_stdin(diff, pytest_output)
    return await run_llm(prompts.TEST_INTEL_ROLE, stdin_content, repo_path)
