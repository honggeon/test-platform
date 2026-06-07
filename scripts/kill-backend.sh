#!/usr/bin/env bash
# 停止本项目的 FastAPI / uvicorn 进程
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
killed=0

for pattern in "uvicorn app.main" "app/main.py" "app.main:app"; do
  for pid in $(pgrep -f "$pattern" 2>/dev/null || true); do
    if kill "$pid" 2>/dev/null; then
      echo "  🔪 已停止 FastAPI (PID $pid)"
      killed=1
    fi
  done
done

for port in 8000 8001 8002; do
  for pid in $(lsof -ti :"$port" 2>/dev/null || true); do
    if kill "$pid" 2>/dev/null; then
      echo "  🔪 已释放端口 $port (PID $pid)"
      killed=1
    fi
  done
done

if [ "$killed" = 0 ]; then
  echo "  ℹ️  未发现运行中的 FastAPI 进程"
else
  sleep 1
  echo "✅ 后端已停止"
fi
