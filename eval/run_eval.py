"""Golden-answer regression suite.

Run this after any change to prompts, the model, or the pipeline logic,
to check whether the change made results better or worse -- not just
"different." Each case in cases/*.json has an expected answer that was
independently verified against the real call graph (see each case's
"notes" field for how), not guessed.

Usage:
    python eval/run_eval.py [--repo /path/to/dummy/bank/repo]

Exit code is 0 if all cases pass, 1 if any fail -- wire this into CI.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.agents import (  # noqa: E402
    invalidate_graph_cache, run_code_impact, run_dependency,
    run_history, run_test_intel,
)
from orchestrator.risk_card import compose_risk_card  # noqa: E402
from orchestrator.grounding import score_all_reports  # noqa: E402

VERDICT_RANK = {"approve": 0, "review": 1, "block": 2}
CASES_DIR = Path(__file__).resolve().parent / "cases"


def load_cases() -> list:
    return [json.loads(p.read_text()) for p in sorted(CASES_DIR.glob("*.json"))]


async def run_case(case: dict, repo_path: str) -> dict:
    diff = case["diff"]
    invalidate_graph_cache(repo_path)

    reports = {}
    tasks = {
        "code_impact": run_code_impact(diff, repo_path),
        "dependency": run_dependency(diff, repo_path),
        "history": run_history(diff, repo_path),
        "test_intel": run_test_intel(diff, repo_path),
    }
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for name, outcome in zip(tasks.keys(), results):
        reports[name] = str(outcome) if isinstance(outcome, Exception) else outcome

    risk_card = await compose_risk_card(
        repo_path=repo_path,
        code_impact=reports["code_impact"],
        dependency=reports["dependency"],
        test_intel=reports["test_intel"],
        history=reports["history"],
    )
    grounding = score_all_reports(reports, repo_path)

    actual_services = set(risk_card.get("affected_services", []))
    expected_services = set(case["expected_affected_services"])
    true_positives = actual_services & expected_services
    precision = len(true_positives) / len(actual_services) if actual_services else 0.0
    recall = len(true_positives) / len(expected_services) if expected_services else 1.0

    actual_rank = VERDICT_RANK.get(risk_card.get("verdict"), -1)
    min_rank = VERDICT_RANK[case["min_verdict"]]
    verdict_ok = actual_rank >= min_rank

    passed = verdict_ok and recall == 1.0  # every expected service must be found

    return {
        "id": case["id"],
        "passed": passed,
        "verdict": {"actual": risk_card.get("verdict"), "min_required": case["min_verdict"], "ok": verdict_ok},
        "affected_services": {
            "actual": sorted(actual_services), "expected": sorted(expected_services),
            "precision": round(precision, 2), "recall": round(recall, 2),
        },
        "grounding_score": grounding["overall_score"],
        "hallucinated_symbols": [
            s for v in grounding["per_agent"].values() for s in v["hallucinated"]
        ],
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="/home/claude/dummy_repo/dummy_repo-main")
    args = parser.parse_args()

    cases = load_cases()
    if not cases:
        print(f"No cases found in {CASES_DIR}")
        return 1

    print(f"Running {len(cases)} eval case(s) against {args.repo}\n")
    outcomes = []
    for case in cases:
        result = await run_case(case, args.repo)
        outcomes.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {result['id']}")
        print(f"       verdict: {result['verdict']['actual']} (min required: {result['verdict']['min_required']})")
        print(f"       affected_services precision={result['affected_services']['precision']} "
              f"recall={result['affected_services']['recall']}  actual={result['affected_services']['actual']}")
        print(f"       grounding score: {result['grounding_score']}", end="")
        if result["hallucinated_symbols"]:
            print(f"  (hallucinated: {result['hallucinated_symbols']})")
        else:
            print()
        print()

    passed = sum(1 for o in outcomes if o["passed"])
    avg_grounding = round(sum(o["grounding_score"] for o in outcomes) / len(outcomes), 3)
    print(f"{passed}/{len(outcomes)} cases passed  |  avg grounding score: {avg_grounding}")

    _log_run(passed, len(outcomes), avg_grounding)
    return 0 if passed == len(outcomes) else 1


def _log_run(passed: int, total: int, avg_grounding: float) -> None:
    """Appends one line per eval run, so you can see whether a prompt or
    model change actually improved things over time, not just whether
    today's run passed."""
    import time
    log_path = Path(__file__).resolve().parent / "eval_history.jsonl"
    entry = {
        "timestamp": time.time(),
        "passed": passed,
        "total": total,
        "pass_rate": round(passed / total, 3) if total else 0,
        "avg_grounding_score": avg_grounding,
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"Logged to {log_path.name}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
