"""FastAPI orchestrator: POST /analyze runs the 5-agent pipeline."""

import asyncio

from fastapi import FastAPI
from pydantic import BaseModel

from orchestrator.agents import (
    run_code_impact,
    run_dependency,
    run_history,
    run_test_intel,
    AgentError,
)
from orchestrator.risk_card import compose_risk_card

app = FastAPI(title="Change Risk Radar")


class AnalyzeRequest(BaseModel):
    repo_path: str
    diff: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(request: AnalyzeRequest) -> dict:
    repo_path = request.repo_path
    diff = request.diff

    # Code Impact, Dependency, History are independent -> run in parallel.
    # Test Intel runs its own real pytest pass first, so it's kicked off
    # alongside the others but awaited separately.
    tasks = {
        "code_impact": run_code_impact(diff, repo_path),
        "dependency": run_dependency(diff, repo_path),
        "history": run_history(diff, repo_path),
        "test_intel": run_test_intel(diff, repo_path),
    }

    results = {}
    errors = {}
    completed = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for name, outcome in zip(tasks.keys(), completed):
        if isinstance(outcome, AgentError):
            errors[name] = str(outcome)
            results[name] = f"[agent failed: {outcome}]"
        elif isinstance(outcome, Exception):
            errors[name] = str(outcome)
            results[name] = f"[unexpected error: {outcome}]"
        else:
            results[name] = outcome

    risk_card = await compose_risk_card(
        repo_path=repo_path,
        code_impact=results["code_impact"],
        dependency=results["dependency"],
        test_intel=results["test_intel"],
        history=results["history"],
    )

    return {
        "risk_card": risk_card,
        "agent_reports": results,
        "agent_errors": errors or None,
    }
