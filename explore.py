"""Quick sanity check: does the model actually understand this repo?

Equivalent to `bob -p "Explain this project"` from the Bob Shell setup,
but using the Groq-backed agent with the same tools (list_dir, read_file,
grep, find_callers, symbol_exists, git_history_for_file) the real
pipeline uses. Run this FIRST on any new repo, before wiring up the
pre-commit hook -- if this doesn't produce a sensible answer, the full
5-agent pipeline won't either.

Usage:
    python explore.py --repo /path/to/repo
    python explore.py --repo /path/to/repo --prompt "List the main modules and what each does"
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from orchestrator.agents import run_llm, AgentError  # noqa: E402

DEFAULT_PROMPT = (
    "Explain this project: what it does, its main modules/files, and how "
    "they fit together. Use list_dir and read_file to actually look "
    "before answering -- don't guess from the repo name alone."
)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="Path to the repo to explore")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    args = parser.parse_args()

    if not Path(args.repo).is_dir():
        print(f"Not a directory: {args.repo}")
        return 1

    print(f"Asking the model to explore {args.repo} ...\n")
    try:
        answer = await run_llm(
            role="You are a code explorer. Use your tools before answering.",
            content=args.prompt,
            repo_path=args.repo,
        )
    except AgentError as exc:
        print(f"FAILED: {exc}")
        return 1

    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
