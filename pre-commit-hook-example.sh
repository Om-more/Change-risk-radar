#!/bin/sh
# Copy this into <dummy-bank-repo>/.git/hooks/pre-commit (no extension).
# Sends the staged diff to the orchestrator, then auto-opens a browser
# window showing the result. No manual input required.

DIFF=$(git diff --cached)
REPO_PATH=$(pwd)
# The real commit hash doesn't exist yet at pre-commit time (the commit
# object is created after this hook runs) -- a content hash of the diff
# itself is the correct identifier here, and doubles as dedup for identical
# diffs analyzed twice.
DIFF_HASH=$(printf '%s' "$DIFF" | python -c "import sys,hashlib; print(hashlib.sha1(sys.stdin.buffer.read()).hexdigest()[:12])")

# The diff goes through STDIN, not argv -- a real diff can easily exceed
# the OS command-line length limit ("Argument list too long"), which a
# small toy diff never hits but a real project's diff will. Only the
# small values (repo path, hash) go through argv.
PAYLOAD=$(printf '%s' "$DIFF" | python -c "
import json, sys
diff = sys.stdin.read()
print(json.dumps({'repo_path': sys.argv[1], 'diff': diff, 'commit_hash': sys.argv[2]}))
" "$REPO_PATH" "$DIFF_HASH")

echo "Running Change Risk Radar..."
# --data-binary @- reads the payload from stdin too, same reasoning.
printf '%s' "$PAYLOAD" | curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  --data-binary @- > /dev/null

# Auto-open the dashboard, which fetches /latest and renders it
# immediately (no manual paste needed). webbrowser is cross-platform,
# more reliable than relying on `start`/`open` differing per shell.
python -c "import webbrowser; webbrowser.open('http://localhost:8000/dashboard')"

# To block the commit on a "block" verdict, parse the response and exit 1.
# Left permissive for the demo so it never blocks a real commit.
exit 0
