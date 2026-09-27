"""Merges the 4 agent outputs into one Risk Card JSON via a final bob call."""

import json
import re

from orchestrator import prompts
from orchestrator.agents import run_bob, AgentError

FALLBACK_CARD = {
    "impact_level": "unknown",
    "affected_services": [],
    "missing_tests": [],
    "drift_warnings": [],
    "verdict": "review",
    "note": "Composer failed; showing raw agent outputs instead.",
}


def _extract_json(text: str) -> dict | None:
    """Bob sometimes wraps JSON in prose or code fences despite instructions.
    It also renders long lines wrapped to the terminal's display width,
    which injects literal newlines (plus trailing padding spaces) into
    what should be continuous JSON string values -- making the result
    syntactically invalid JSON (raw control characters aren't allowed
    unescaped inside a JSON string). We collapse "whitespace, newline,
    whitespace" sequences back into a single space before parsing, which
    fixes the wrap artifacts without touching real JSON structure (commas,
    braces, brackets aren't line-wrapped mid-token by the CLI)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None

    candidate = match.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    dewrapped = re.sub(r"[ \t]*\n[ \t]*", " ", candidate)
    try:
        return json.loads(dewrapped)
    except json.JSONDecodeError:
        return None


async def compose_risk_card(
    repo_path: str,
    code_impact: str,
    dependency: str,
    test_intel: str,
    history: str,
) -> dict:
    stdin_content = prompts.build_risk_card_stdin(
        code_impact=code_impact,
        dependency=dependency,
        test_intel=test_intel,
        history=history,
    )
    try:
        raw = await run_bob(prompts.RISK_CARD_ROLE, stdin_content, repo_path)
    except AgentError as exc:
        card = dict(FALLBACK_CARD)
        card["note"] = f"Composer agent failed: {exc}"
        card["raw_reports"] = {
            "code_impact": code_impact,
            "dependency": dependency,
            "test_intel": test_intel,
            "history": history,
        }
        return card

    parsed = _extract_json(raw)
    if parsed is None:
        card = dict(FALLBACK_CARD)
        card["note"] = "Composer returned non-JSON output; showing it raw."
        card["raw_composer_output"] = raw
        return card

    return parsed
