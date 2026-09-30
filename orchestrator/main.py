"""FastAPI orchestrator: POST /analyze runs the 5-agent pipeline."""

import asyncio
import time
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from orchestrator import grounding, storage
from orchestrator.agents import (
    run_code_impact,
    run_dependency,
    run_history,
    run_test_intel,
    AgentError,
)
from orchestrator.risk_card import compose_risk_card

app = FastAPI(title="Change Risk Radar")

# Allow the local dashboard.html file (opened via file://, origin "null")
# to call this API. Wide open is fine for a hackathon demo running on
# localhost only -- do not ship this permissive a policy to production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    repo_path: str
    diff: str
    commit_hash: str | None = None  # hook should pass `git rev-parse HEAD` when available


DASHBOARD_PATH = Path(__file__).resolve().parent.parent / "dashboard.html"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(request: AnalyzeRequest) -> dict:
    repo_path = request.repo_path
    diff = request.diff

    from orchestrator.agents import invalidate_graph_cache
    invalidate_graph_cache(repo_path)

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

    grounding_report = grounding.score_all_reports(results, repo_path)

    result = {
        "risk_card": risk_card,
        "agent_reports": results,
        "agent_errors": errors or None,
        "grounding": grounding_report,
        "created_at": time.time(),
    }
    # Pre-commit runs before the commit object exists, so no real hash is
    # available yet; fall back to a generated id so every run is still
    # individually retrievable rather than overwriting the last one.
    commit_hash = request.commit_hash or f"pending-{uuid.uuid4().hex[:12]}"
    storage.save(commit_hash, repo_path, result)
    result["commit_hash"] = commit_hash
    return result


@app.get("/latest")
def latest() -> JSONResponse:
    result = storage.get_latest()
    if result is None:
        return JSONResponse(status_code=404, content={"detail": "No analysis run yet."})
    return JSONResponse(content=result)


@app.get("/result/{commit_hash}")
def result(commit_hash: str) -> JSONResponse:
    found = storage.get(commit_hash)
    if found is None:
        return JSONResponse(status_code=404, content={"detail": "No analysis for that commit hash."})
    return JSONResponse(content=found)


@app.get("/history")
def history(limit: int = 20) -> JSONResponse:
    return JSONResponse(content=storage.list_recent(limit))


@app.get("/dashboard")
def dashboard() -> FileResponse:
    return FileResponse(DASHBOARD_PATH)
