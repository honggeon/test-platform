#!/usr/bin/env bash
# Fetch JWT from arag-auth and export HAT_BEARER_TOKEN for HAT / platform test runs.
# Usage:
#   export HAT_TEST_EMAIL='your@email.com'
#   export HAT_TEST_PASSWORD='your-password'
#   source ./scripts/fetch-hat-bearer-token.sh
#   # or: eval "$(./scripts/fetch-hat-bearer-token.sh --export)"

set -euo pipefail

AUTH_BASE="${ARAG_AUTH_URL:-http://192.168.0.64:9011}"
EMAIL="${HAT_TEST_EMAIL:-}"
PASSWORD="${HAT_TEST_PASSWORD:-}"
EXPORT_MODE=0

for arg in "$@"; do
  case "$arg" in
    --export) EXPORT_MODE=1 ;;
    --help|-h)
      echo "Usage: HAT_TEST_EMAIL=... HAT_TEST_PASSWORD=... $0 [--export]"
      echo "Env: ARAG_AUTH_URL (default $AUTH_BASE)"
      exit 0
      ;;
  esac
done

if [[ -z "$EMAIL" || -z "$PASSWORD" ]]; then
  echo "error: set HAT_TEST_EMAIL and HAT_TEST_PASSWORD" >&2
  exit 1
fi

payload=$(python3 -c 'import json,os; print(json.dumps({"email": os.environ["HAT_TEST_EMAIL"], "password": os.environ["HAT_TEST_PASSWORD"]}))')

response=$(curl -sS -m 15 -X POST "${AUTH_BASE%/}/auth/v1/login" \
  -H "Content-Type: application/json" \
  -d "$payload")

token=$(printf '%s' "$response" | python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("", end="")
    sys.exit(0)
# arag-auth: {code, message, data} or flat LoginResponse {token, user}
if isinstance(data.get("data"), dict) and data["data"].get("token"):
    print(data["data"]["token"], end="")
elif data.get("token"):
    print(data["token"], end="")
')

if [[ -z "$token" ]]; then
  echo "error: login failed, response: $response" >&2
  exit 1
fi

export HAT_BEARER_TOKEN="$token"

if [[ "$EXPORT_MODE" -eq 1 ]]; then
  printf 'export HAT_BEARER_TOKEN=%q\n' "$token"
else
  echo "HAT_BEARER_TOKEN set (length ${#token})"
fi
