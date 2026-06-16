#!/bin/bash
# Deploy the Modal Llama 3.3 70B endpoint and block until it answers HTTP 200.
#
# `modal deploy` returns before vLLM finishes loading the model, so the endpoint serves
# HTTP 303 (loading) / 404 (stopped) until ready. This script deploys then polls
# GET <url>/models with the bearer token until 200, up to a 15-minute deadline.
# Exit 0 = endpoint ready; exit 1 = timeout. NEVER launch sims until this exits 0.
set -uo pipefail
cd /Users/nsander/workspace/schmidt-poc
LOG=/tmp/llama_deploy.log
URL=$(grep -oE '"meta-llama/Llama-3.3-70B-Instruct":"[^"]+"' .env | sed 's/.*:"//;s/"$//')
KEY=$(grep -E '^SELF_HOSTED_API_KEY=' .env | head -1 | cut -d= -f2-)

if [ -z "$URL" ] || [ -z "$KEY" ]; then
  echo "$(date) ABORT: SELF_HOSTED url/key missing from .env" >> "$LOG"; exit 1
fi

echo "=== $(date) deploying llama-3-3-70b-instruct ===" >> "$LOG"
VIRTUAL_ENV= uv run --no-sync modal deploy modal/serve_llama.py >> "$LOG" 2>&1
echo "$(date) deploy command returned; polling $URL/models for HTTP 200" >> "$LOG"

deadline=$(( $(date +%s) + 900 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 20 "$URL/models" -H "Authorization: Bearer $KEY" 2>/dev/null)
  echo "$(date) /models -> $code" >> "$LOG"
  if [ "$code" = "200" ]; then
    echo "=== $(date) ENDPOINT READY ===" >> "$LOG"
    exit 0
  fi
  sleep 20
done
echo "=== $(date) TIMEOUT waiting for endpoint (still not 200 after 15 min) ===" >> "$LOG"
exit 1
