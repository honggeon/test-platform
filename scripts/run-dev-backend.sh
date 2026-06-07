#!/usr/bin/env bash
# 开发模式启动 FastAPI：端口已占用且 /health 正常则提示勿重复启动
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
PYTHON="$ROOT/.venv/bin/python"
PORT="${BACKEND_PORT:-8000}"
HOST="${BACKEND_HOST:-0.0.0.0}"

health_ok() {
  local p="$1"
  local code
  code="$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 "http://127.0.0.1:${p}/health" 2>/dev/null || echo "000")"
  [ "$code" != "000" ] && [ "$code" -lt 500 ]
}

if health_ok "$PORT"; then
  pid="$(lsof -ti :"$PORT" 2>/dev/null | head -1 || true)"
  echo ""
  echo "✅ FastAPI 已在运行，无需重复启动"
  echo "   地址: http://127.0.0.1:${PORT}/docs"
  [ -n "$pid" ] && echo "   PID:  $pid"
  echo ""
  echo "   需要热重载开发模式请先执行: make kill-backend"
  echo "   然后重新: make dev-backend"
  echo ""
  exit 0
fi

if lsof -ti :"$PORT" >/dev/null 2>&1; then
  echo "❌ 端口 ${PORT} 已被占用，但 /health 无响应（可能不是本后端）"
  lsof -iTCP:"$PORT" -sTCP:LISTEN -P 2>/dev/null || true
  echo ""
  echo "   可换端口启动: BACKEND_PORT=8001 make dev-backend"
  echo "   或释放端口:   make kill-backend"
  exit 1
fi

echo "▶️  启动 FastAPI (uvicorn --reload) → http://127.0.0.1:${PORT}"
cd "$BACKEND"
exec env PYTHONPATH=. "$PYTHON" -m uvicorn app.main:app \
  --host "$HOST" --port "$PORT" --reload
