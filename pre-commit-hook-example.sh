#!/bin/sh
# Copy this into <dummy-bank-repo>/.git/hooks/pre-commit (no extension).
# Sends the staged diff to the orchestrator, then auto-opens a browser
# window showing the result. No manual input required.

DIFF=$(git diff --cached)
REPO_PATH=$(pwd)

PAYLOAD=$(python -c "
import json, sys
print(json.dumps({'repo_path': sys.argv[1], 'diff': sys.argv[2]}))
" "$REPO_PATH" "$DIFF")

echo "Running Change Risk Radar..."
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" > /dev/null

# Auto-open the dashboard, which fetches /latest and renders it
# immediately (no manual paste needed). webbrowser is cross-platform,
# more reliable than relying on `start`/`open` differing per shell.
python -c "import webbrowser; webbrowser.open('http://localhost:8000/dashboard')"

# To block the commit on a "block" verdict, parse the response and exit 1.
# Left permissive for the demo so it never blocks a real commit.
exit 0
