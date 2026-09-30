"""Automatic technical-accuracy check for agent report text.

This does NOT require a hand-labeled dataset -- it runs on every commit.
The idea: an agent's prose will naturally mention specific code symbols
("calculate_transaction_fee", "PaymentRequest"). We extract anything
that looks like a code identifier being called or instantiated, then
check each one against the real call graph (ground truth, not a guess).
A report that cites symbols which don't exist in the repo is making
things up -- this catches that mechanically, without needing a human to
read every response.

Known limitation, stated plainly: this only catches hallucinated
*symbol names*. It says nothing about whether the surrounding claim
("this breaks X because Y") is logically correct -- that still needs
the golden-dataset eval in eval/run_eval.py, or a human reviewer.
"""

import re

from orchestrator import callgraph

# Identifiers immediately followed by "(" are almost always a function
# call or class instantiation in this kind of technical prose -- plain
# English rarely writes "word(" like that. A short stoplist removes the
# few common false positives (control-flow keywords, generic verbs the
# model uses in sentences like "confirm(ed) that...").
_CANDIDATE_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_STOPLIST = {
    "if", "for", "while", "print", "len", "str", "int", "float", "list",
    "dict", "set", "confirm", "verify", "check", "note", "see", "e.g",
    "i.e", "given", "assuming", "return", "raise", "except",
}


def extract_claimed_symbols(text: str) -> set:
    candidates = {m.group(1) for m in _CANDIDATE_RE.finditer(text)}
    return {c for c in candidates if c.lower() not in _STOPLIST and len(c) > 2}


def score_report(text: str, graph: callgraph.CallGraph) -> dict:
    """Returns {claimed, verified, hallucinated, score}. score is
    verified/claimed, or 1.0 (trivially grounded) if nothing was claimed."""
    claimed = extract_claimed_symbols(text)
    verified = {c for c in claimed if graph.symbol_exists(c)}
    hallucinated = claimed - verified
    score = len(verified) / len(claimed) if claimed else 1.0
    return {
        "claimed_count": len(claimed),
        "verified": sorted(verified),
        "hallucinated": sorted(hallucinated),
        "score": round(score, 3),
    }


def score_all_reports(agent_reports: dict, repo_path: str) -> dict:
    """Scores every agent report and returns a per-agent + overall summary."""
    graph = callgraph.build(repo_path)
    per_agent = {
        name: score_report(text, graph)
        for name, text in agent_reports.items()
        if isinstance(text, str)
    }
    all_claimed = sum(v["claimed_count"] for v in per_agent.values())
    all_hallucinated = sum(len(v["hallucinated"]) for v in per_agent.values())
    overall_score = (
        1.0 if all_claimed == 0 else round(1 - all_hallucinated / all_claimed, 3)
    )
    return {"per_agent": per_agent, "overall_score": overall_score}
