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
    """Bob sometimes wraps JSON in prose or code fences despite instructions."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
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
