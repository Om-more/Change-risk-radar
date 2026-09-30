"""Merges the 4 agent outputs into one Risk Card JSON via a final bob call."""

import json
import re
from pathlib import Path

from orchestrator import prompts
from orchestrator.agents import run_bob, run_json, AgentError

RISK_CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "impact_level": {"type": "string", "enum": ["low", "medium", "high"]},
        "affected_services": {"type": "array", "items": {"type": "string"}},
        "missing_tests": {"type": "array", "items": {"type": "string"}},
        "drift_warnings": {"type": "array", "items": {"type": "string"}},
        "verdict": {"type": "string", "enum": ["approve", "review", "block"]},
    },
    "required": ["impact_level", "affected_services", "missing_tests", "drift_warnings", "verdict"],
}

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


def _verify_affected_services(repo_path: str, services: list) -> tuple:
    """Ground-truth check: does each claimed affected service actually
    exist as a directory in this repo? Catches hallucinated names before
    they reach the dashboard. Returns (verified, unverified)."""
    root = Path(repo_path)
    verified, unverified = [], []
    for s in services:
        name = s.strip().removeprefix("services/").rstrip("/")
        # Accepts a services/<name> dir (microservice layout), a bare dir
        # name anywhere, or a file path (single-app/module layout, e.g.
        # a Streamlit project with no services/ folder at all).
        if (
            (root / "services" / name).is_dir()
            or (root / name).is_dir()
            or (root / name).is_file()
        ):
            verified.append(s)
        else:
            unverified.append(s)
    return verified, unverified


_VERDICT_RANK = {"approve": 0, "review": 1, "block": 2}
_RANK_TO_VERDICT = {v: k for k, v in _VERDICT_RANK.items()}


def _apply_verdict_floor(card: dict) -> dict:
    """The LLM's verdict is a subjective call with no guardrails. These
    rules don't override a stricter LLM verdict -- they only raise a
    verdict that looks too lax given the card's own evidence, so
    calibration doesn't rest entirely on the model's judgment."""
    current = _VERDICT_RANK.get(card.get("verdict"), 1)
    floor = 0
    reasons = []

    if card.get("missing_tests"):
        floor = max(floor, _VERDICT_RANK["review"])
        reasons.append(f"{len(card['missing_tests'])} missing test(s) found")

    if card.get("drift_warnings"):
        floor = max(floor, _VERDICT_RANK["review"])
        reasons.append(f"{len(card['drift_warnings'])} drift warning(s) found")

    if len(card.get("affected_services") or []) >= 3:
        floor = max(floor, _VERDICT_RANK["block"])
        reasons.append(f"{len(card['affected_services'])} services affected")

    if floor > current:
        card["verdict"] = _RANK_TO_VERDICT[floor]
        card["verdict_floor_applied"] = (
            f"Raised from model's original verdict due to: {'; '.join(reasons)}"
        )
    return card


def _apply_verification(card: dict, repo_path: str) -> dict:
    services = card.get("affected_services") or []
    verified, unverified = _verify_affected_services(repo_path, services)
    card["affected_services"] = verified
    if unverified:
        card["unverified_claims"] = unverified
        existing_note = card.get("note", "")
        flag = f"{len(unverified)} claimed service(s) could not be verified on disk and were removed: {unverified}"
        card["note"] = f"{existing_note} {flag}".strip()
    return card


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
        raw = await run_json(prompts.RISK_CARD_ROLE, stdin_content, RISK_CARD_SCHEMA)
        parsed = json.loads(raw)
        return _apply_verdict_floor(_apply_verification(parsed, repo_path))
    except (AgentError, json.JSONDecodeError):
        pass  # schema-constrained call failed or returned bad JSON -- fall back below

    # Fallback: free-text call + regex extraction (the old path). Kept as
    # defense in depth for providers/models with weak schema support.
    try:
        raw = await run_bob(prompts.RISK_CARD_ROLE, stdin_content, repo_path, use_tools=False)
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

    return _apply_verdict_floor(_apply_verification(parsed, repo_path))
