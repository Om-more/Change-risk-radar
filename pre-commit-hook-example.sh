#!/bin/sh
# Copy this into <dummy-bank-repo>/.git/hooks/pre-commit and chmod +x it.
# It sends the staged diff to the orchestrator and prints the risk card.

DIFF=$(git diff --cached)
REPO_PATH=$(pwd)

PAYLOAD=$(python3 -c "
import json, sys
print(json.dumps({'repo_path': sys.argv[1], 'diff': sys.argv[2]}))
" "$REPO_PATH" "$DIFF")

echo "Running Change Risk Radar..."
curl -s -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" | python3 -m json.tool

# To block the commit on a "block" verdict, parse the response and exit 1.
# Left permissive for the demo so it never blocks a real commit.
exit 0
