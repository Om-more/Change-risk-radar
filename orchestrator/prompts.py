"""Each agent = a short single-line ROLE prompt (safe for cmd.exe's -p arg)
plus a STDIN builder for the actual (possibly large/multi-line) content.
Never put multi-line content in the -p argument on Windows: cmd.exe
truncates at the first newline and has an ~8191 char command-line limit."""

CODE_IMPACT_ROLE = (
    "You are a Code Impact Agent. Read the diff piped into stdin, "
    "identify exactly which functions changed and what they do. "
    "Plain text only, no markdown."
)

DEPENDENCY_ROLE = (
    "You are a Dependency Agent. Read the diff piped into stdin, trace "
    "every caller of the changed function(s) across @services/. List "
    "affected services. Plain text only, no markdown."
)

TEST_INTEL_ROLE = (
    "You are a Test Intelligence Agent. Read the diff and pytest output "
    "piped into stdin. Identify which changed functions have NO test "
    "coverage. Plain text only, no markdown."
)

HISTORY_ROLE = (
    "You are a History Agent. Read the diff piped into stdin. If an "
    "incident-search tool is available, use it to find similar past "
    "incidents. If no such tool is available, say so plainly in one "
    "sentence and stop. Plain text only, no markdown."
)

RISK_CARD_ROLE = (
    "You are the Risk Card Composer. Read the four agent reports piped "
    "into stdin (separated by === lines). Output ONLY a single valid "
    "JSON object with exactly these keys: impact_level "
    '(one of "low"/"medium"/"high"), affected_services (array of '
    "strings), missing_tests (array of strings), drift_warnings (array "
    'of strings), verdict (one of "approve"/"review"/"block"). No '
    "markdown fences, no prose before or after the JSON."
)


def build_test_intel_stdin(diff: str, pytest_output: str) -> str:
    return f"DIFF:\n{diff}\n\n---PYTEST OUTPUT---\n{pytest_output}"


def build_risk_card_stdin(
    code_impact: str, dependency: str, test_intel: str, history: str
) -> str:
    return (
        f"CODE IMPACT REPORT:\n{code_impact}\n"
        f"===\n"
        f"DEPENDENCY REPORT:\n{dependency}\n"
        f"===\n"
        f"TEST INTELLIGENCE REPORT:\n{test_intel}\n"
        f"===\n"
        f"HISTORY REPORT:\n{history}"
    )
