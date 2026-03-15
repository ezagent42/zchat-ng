#!/usr/bin/env bash
# Echo agent — reads JSONL stdin, echoes back JSONL stdout
# Implements CC headless protocol: system/init → user/assistant/result loop

SESSION_ID="echo-$(date +%s)"

# Init message
echo "{\"type\":\"system\",\"subtype\":\"init\",\"session_id\":\"$SESSION_ID\",\"model\":\"echo\"}"

# Read-reply loop
while IFS= read -r line; do
    # Extract text content from JSONL user message
    text=$(echo "$line" | python3 -c "
import sys, json
try:
    msg = json.load(sys.stdin)
    content = msg.get('message', {}).get('content', '')
    print(content if isinstance(content, str) else json.dumps(content))
except: print('')
" 2>/dev/null)

    # Assistant response
    escaped=$(echo "$text" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))")
    echo "{\"type\":\"assistant\",\"message\":{\"role\":\"assistant\",\"content\":[{\"type\":\"text\",\"text\":$escaped}]}}"

    # Result
    echo "{\"type\":\"result\",\"result\":$escaped,\"session_id\":\"$SESSION_ID\",\"cost_usd\":0,\"duration_ms\":50}"
done
