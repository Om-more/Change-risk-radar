"""Runs each agent by shelling out to `bob -p "<short role>"`, piping the
actual (possibly large/multi-line) content via stdin rather than embedding
it in the command-line argument. This avoids two Windows cmd.exe problems:
truncation at the first newline, and the ~8191-char command-line limit.
"""

import asyncio
import platform
import subprocess

from orchestrator import prompts

BOB_TIMEOUT_SECONDS = 45


class AgentError(Exception):
    """Raised when a bob call fails or times out."""


def _clean_bob_output(raw: str) -> str:
    """Bob's -p output is a full transcript (User/Assistant turns, box-
    drawing dividers, a trailing Task Summary block). We only want the
    final Assistant answer. This extracts the text between the LAST
    "Assistant (" marker and the final "Task Summary" marker, then drops
    any decorative divider lines (which may render as mojibake on some
    Windows consoles but always contain no alphanumeric characters,
    making them safe to filter out regardless of encoding)."""
    task_summary_idx = raw.rfind("Task Summary")
    before = raw[:task_summary_idx] if task_summary_idx != -1 else raw

    assistant_idx = before.rfind("Assistant (")
    segment = before[assistant_idx:] if assistant_idx != -1 else before

    def _is_divider(line: str) -> bool:
        """Divider/border lines (box-drawing chars, possibly mangled into
        mojibake like repeated 'â') are built from very few distinct
        characters repeated many times. Real prose has far more
        character variety. This catches them regardless of encoding,
        since mojibake letters still register as alphanumeric."""
        stripped = line.strip()
        if len(stripped) < 8:
            return False
        return len(set(stripped)) <= 3

    lines = segment.split("\n")[1:] if assistant_idx != -1 else segment.split("\n")
    cleaned_lines = [
        line for line in lines if line.strip() and not _is_divider(line)
    ]
    cleaned = "\n".join(cleaned_lines).strip()

    return cleaned if cleaned else raw.strip()


def _run_bob_sync(role: str, stdin_content: str, repo_path: str) -> str:
    """Blocking call to `bob -p <role>` with stdin_content piped in.
    Meant to be run inside asyncio.to_thread."""
    use_shell = platform.system() == "Windows"
    try:
        result = subprocess.run(
            ["bob", "-p", role],
            cwd=repo_path,
            input=stdin_content,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=BOB_TIMEOUT_SECONDS,
            shell=use_shell,
        )
    except FileNotFoundError as exc:
        raise AgentError(
            "`bob` command not found. Is Bob Shell installed and on PATH?"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AgentError(
            f"bob call timed out after {BOB_TIMEOUT_SECONDS}s"
        ) from exc

    if result.returncode != 0:
        raise AgentError(f"bob exited with error: {result.stderr.strip()}")

    return _clean_bob_output(result.stdout)


async def run_bob(role: str, stdin_content: str, repo_path: str) -> str:
    return await asyncio.to_thread(_run_bob_sync, role, stdin_content, repo_path)


def run_pytest_sync(repo_path: str) -> str:
    """Runs the real test suite and returns raw output (pass/fail/coverage)."""
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "-v"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        return result.stdout + "\n" + result.stderr
    except FileNotFoundError:
        return "pytest not found in this environment."
    except subprocess.TimeoutExpired:
        return "pytest run timed out."


async def run_code_impact(diff: str, repo_path: str) -> str:
    return await run_bob(prompts.CODE_IMPACT_ROLE, diff, repo_path)


async def run_dependency(diff: str, repo_path: str) -> str:
    return await run_bob(prompts.DEPENDENCY_ROLE, diff, repo_path)


async def run_history(diff: str, repo_path: str) -> str:
    return await run_bob(prompts.HISTORY_ROLE, diff, repo_path)


async def run_test_intel(diff: str, repo_path: str) -> str:
    pytest_output = await asyncio.to_thread(run_pytest_sync, repo_path)
    stdin_content = prompts.build_test_intel_stdin(diff, pytest_output)
    return await run_bob(prompts.TEST_INTEL_ROLE, stdin_content, repo_path)
