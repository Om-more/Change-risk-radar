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
    "You are a Dependency Agent. Read the diff piped into stdin. For "
    "every changed function or class name, call find_callers to get the "
    "ACTUAL call sites (ground truth, parsed from the AST) -- do not "
    "guess or rely on grep for this. Before naming any affected file or "
    "module in your answer, call symbol_exists to confirm the symbol is "
    "real. Use list_dir first if you're unsure how the repo is "
    "organized -- do not assume any particular folder layout. List "
    "affected files/modules based only on what find_callers returned. "
    "Plain text only, no markdown."
)

TEST_INTEL_ROLE = (
    "You are a Test Intelligence Agent. Read the diff and pytest output "
    "piped into stdin. Identify which changed functions have NO test "
    "coverage. Plain text only, no markdown."
)

HISTORY_ROLE = (
    "You are a History Agent. Read the diff piped into stdin. Identify "
    "which file(s) changed, then call git_history_for_file on each one "
    "to check for past fixes, bugs, or reverts touching that file. This "
    "is real commit history, not a guess. Report what you actually "
    "find -- if the tool shows no past incidents, say that plainly "
    "rather than speculating. This only sees what's in THIS repo's "
    "local git history, not incidents from other projects or team "
    "members. Plain text only, no markdown."
)

RISK_CARD_ROLE = (
    "You are the Risk Card Composer. Read the four agent reports piped "
    "into stdin (separated by === lines). Output ONLY a single valid "
    "JSON object with exactly these keys: impact_level "
    '(one of "low"/"medium"/"high"), affected_services (array of '
    "strings -- affected files, modules, or services, whichever this "
    "repo actually uses; do not assume a microservices layout), "
    "missing_tests (array of strings), drift_warnings (array "
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
