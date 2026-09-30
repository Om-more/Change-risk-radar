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
from dataclasses import dataclass, field
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache"}


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


def build(repo_path: str) -> CallGraph:
    root = Path(repo_path).resolve()
    graph = CallGraph()
    for path in root.rglob("*.py"):
        if set(path.parts) & SKIP_DIRS:
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(path))
        except (SyntaxError, OSError):
            continue
        _Visitor(graph, str(path.relative_to(root))).visit(tree)
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
