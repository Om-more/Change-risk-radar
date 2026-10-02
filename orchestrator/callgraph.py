"""Static call graph for Python repos, built with `ast`, not an LLM guess.

Why this exists: letting the model discover callers via grep is
probabilistic -- it can miss call sites, string-based dispatch, or simply
not think to search the right file. This module parses every .py file
once, records every function/class definition and every call site, and
answers "who calls X" and "does X actually exist" as verified facts. The
LLM then reasons over this graph instead of guessing at it.

Scope: Python only, direct calls only (no reflection/dynamic dispatch,
no cross-language tracing). That's a real limitation -- documented, not
hidden -- but it's a strict improvement over grep for the common case.
"""

import ast
import json
import os
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache"}
CACHE_DIR_NAME = ".change_risk_cache"
CACHE_FILE_NAME = "callgraph.json"


@dataclass
class Definition:
    symbol: str
    file: str
    line: int
    kind: str  # "function" | "class" | "method"


@dataclass
class CallSite:
    symbol: str          # name being called, as written (best-effort resolved)
    file: str
    line: int
    caller: str           # enclosing function/method name, or "<module>"


@dataclass
class CallGraph:
    definitions: dict = field(default_factory=dict)   # symbol -> list[Definition]
    calls: dict = field(default_factory=dict)          # symbol -> list[CallSite]

    def symbol_exists(self, symbol: str) -> bool:
        return symbol in self.definitions

    def find_callers(self, symbol: str) -> list[CallSite]:
        return self.calls.get(symbol, [])

    def find_definitions(self, symbol: str) -> list[Definition]:
        return self.definitions.get(symbol, [])


class _Visitor(ast.NodeVisitor):
    def __init__(self, graph: CallGraph, relpath: str):
        self.graph = graph
        self.relpath = relpath
        self._scope_stack = ["<module>"]

    def _record_def(self, symbol: str, node: ast.AST, kind: str) -> None:
        self.graph.definitions.setdefault(symbol, []).append(
            Definition(symbol, self.relpath, node.lineno, kind)
        )

    def _record_call(self, symbol: str, node: ast.AST) -> None:
        self.graph.calls.setdefault(symbol, []).append(
            CallSite(symbol, self.relpath, node.lineno, self._scope_stack[-1])
        )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        kind = "method" if len(self._scope_stack) > 1 and self._scope_stack[-1] != "<module>" else "function"
        self._record_def(node.name, node, kind)
        self._scope_stack.append(node.name)
        self.generic_visit(node)
        self._scope_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._record_def(node.name, node, "class")
        self._scope_stack.append(node.name)
        self.generic_visit(node)
        self._scope_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        name = None
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr  # best-effort: "obj.method()" -> "method"
        if name:
            self._record_call(name, node)
        self.generic_visit(node)


def _cache_path(root: Path) -> Path:
    cache = root / CACHE_DIR_NAME
    cache.mkdir(exist_ok=True)
    return cache / CACHE_FILE_NAME


def _file_fingerprint(path: Path) -> str:
    st = path.stat()
    return f"{st.st_mtime_ns}:{st.st_size}"


def build(repo_path: str) -> CallGraph:
    """Build an incrementally cached AST index.

    The repository is walked, but unchanged Python files are NOT parsed again.
    This makes repeated analyses much faster on large repositories.
    """
    root = Path(repo_path).resolve()
    cache_file = _cache_path(root)
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cache = {"files": {}}

    current = {}
    graph = CallGraph()
    files = [p for p in root.rglob("*.py") if not (set(p.parts) & SKIP_DIRS)]

    for path in files:
        rel = str(path.relative_to(root))
        try:
            fp = _file_fingerprint(path)
            current[rel] = fp
            cached = cache.get("files", {}).get(rel)
            if cached and cached.get("fingerprint") == fp:
                defs = cached.get("definitions", [])
                calls = cached.get("calls", [])
                for d in defs:
                    graph.definitions.setdefault(d["symbol"], []).append(
                        Definition(d["symbol"], rel, d["line"], d["kind"])
                    )
                for c in calls:
                    graph.calls.setdefault(c["symbol"], []).append(
                        CallSite(c["symbol"], rel, c["line"], c["caller"])
                    )
                continue

            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(path))
            local = CallGraph()
            _Visitor(local, rel).visit(tree)

            for symbol, defs in local.definitions.items():
                graph.definitions.setdefault(symbol, []).extend(defs)
            for symbol, calls in local.calls.items():
                graph.calls.setdefault(symbol, []).extend(calls)

            cache.setdefault("files", {})[rel] = {
                "fingerprint": fp,
                "definitions": [d.__dict__ for ds in local.definitions.values() for d in ds],
                "calls": [c.__dict__ for cs in local.calls.values() for c in cs],
            }
        except (SyntaxError, OSError, ValueError):
            continue

    # Drop deleted files from the persistent cache.
    cache["files"] = {k: v for k, v in cache.get("files", {}).items() if k in current}
    try:
        tmp = cache_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache), encoding="utf-8")
        os.replace(tmp, cache_file)
    except OSError:
        pass
    return graph


def format_callers(graph: CallGraph, symbol: str) -> str:
    sites = graph.find_callers(symbol)
    if not sites:
        return f"No callers found for '{symbol}' in the indexed Python files."
    lines = [f"{s.file}:{s.line} inside {s.caller}()" for s in sites]
    return "\n".join(lines)


def format_definitions(graph: CallGraph, symbol: str) -> str:
    defs = graph.find_definitions(symbol)
    if not defs:
        return f"'{symbol}' is not defined anywhere in the indexed Python files."
    lines = [f"{d.kind} {d.symbol} at {d.file}:{d.line}" for d in defs]
    return "\n".join(lines)
