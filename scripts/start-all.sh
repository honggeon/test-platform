#!/usr/bin/env bash
# ─── 启动全部服务 ──────────────────────────────────────────────────────
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/logs"
PYTHON="$ROOT/.venv/bin/python"

mkdir -p "$LOG_DIR"

echo "启动所有服务..."

# 1. 清理残留进程和端口
echo "  🧹 清理残留进程..."
pkill -9 -f "next start" 2>/dev/null || true
pkill -9 -f "next-server" 2>/dev/null || true
sleep 1

for port in 8000 2026 3000; do
  pid=$(lsof -ti :$port 2>/dev/null || true)
  if [ -n "$pid" ]; then
    echo "  ⚠️  端口 $port 被 PID $pid 占用，清理中..."
    kill -9 "$pid" 2>/dev/null || true
    sleep 1
  fi
done

# 2. FastAPI 后端
echo "  ▶️  FastAPI 后端 (端口 8000)"
cd "$ROOT/backend"
PYTHONPATH=. nohup "$PYTHON" app/main.py > "$LOG_DIR/backend.log" 2>&1 &
echo $! > "$LOG_DIR/backend.pid"
sleep 2

# 验证后端
if lsof -ti :8000 >/dev/null 2>&1; then
  echo "    ✅ FastAPI 已就绪"
else
  echo "    ❌ FastAPI 启动失败:"
  tail -5 "$LOG_DIR/backend.log"
fi

# 3. LangGraph API
echo "  ▶️  LangGraph API (端口 2026)"
cd "$ROOT/backend"
nohup "$PYTHON" "$ROOT/start_server.py" > "$LOG_DIR/langgraph.log" 2>&1 &
echo $! > "$LOG_DIR/langgraph.pid"
sleep 3

if lsof -ti :2026 >/dev/null 2>&1; then
  echo "    ✅ LangGraph 已就绪"
else
  echo "    ⚠️  LangGraph 启动中..."
fi

# 4. Next.js 前端（探测当前后端 / LangGraph 端口后再构建，避免代理写死端口）
echo "  ▶️  探测服务端口并构建前端..."
# shellcheck source=detect-dev-ports.sh
source "$ROOT/scripts/detect-dev-ports.sh"
cd "$ROOT/ui"
npm run build > "$LOG_DIR/ui-build.log" 2>&1
if [ $? -ne 0 ]; then
  echo "    ❌ 前端构建失败:"
  tail -5 "$LOG_DIR/ui-build.log"
else
  echo "    ✅ 构建完成，启动服务..."
  # 注意：node 启动 next 后会 fork next-server 然后自己退出，
  # 所以不能用 $! 作为持久 PID。我们在 curl 成功后再抓实际 PID。
  # 构建后再次探测，防止启动间隔内端口变化
  # shellcheck source=detect-dev-ports.sh
  source "$ROOT/scripts/detect-dev-ports.sh"
  nohup env PUBLIC_API_URL="$PUBLIC_API_URL" LANGGRAPH_API_URL="$LANGGRAPH_API_URL" \
    NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" \
    node ./node_modules/.bin/next start -p 3000 > "$LOG_DIR/ui.log" 2>&1 &

  # 等待前端就绪（最长 15 秒）
  echo "    ⏳ 等待前端就绪..."
  for i in $(seq 1 15); do
    sleep 1
    if curl -s -o /dev/null --max-time 2 http://localhost:3000 2>/dev/null; then
      # 获取实际监听端口的 next-server PID
      actual_pid=$(ss -tlnp 2>/dev/null | grep ':3000' | grep -oP 'pid=\K[0-9]+' | head -1 || true)
      if [ -n "$actual_pid" ]; then
        echo "$actual_pid" > "$LOG_DIR/ui.pid"
        echo "    ✅ Next.js 已就绪 (PID $actual_pid)"
      else
        echo "    ✅ Next.js 已就绪"
      fi
      break
    fi
    if [ $i -eq 15 ]; then
      echo "    ❌ 前端启动超时:"
      tail -3 "$LOG_DIR/ui.log"
    fi
  done
fi

echo ""
echo "📍 FastAPI:    ${PUBLIC_API_URL:-http://localhost:8000}/docs"
echo "📍 LangGraph:  ${LANGGRAPH_API_URL:-http://localhost:2026}/docs"
echo "📍 前端:       http://localhost:3000"
echo "   (Next 代理: PUBLIC_API_URL=${PUBLIC_API_URL:-未设置})"
echo ""

# 最终状态检查
for pair in "FastAPI 后端:8000" "LangGraph API:2026" "Next.js 前端:3000"; do
  name="${pair%:*}"
  port="${pair#*:}"
  pid=$(lsof -ti :$port 2>/dev/null || true)
  if [ -z "$pid" ] && [ "$port" = "3000" ]; then
    pid=$(ss -tlnp 2>/dev/null | grep ':3000' | grep -oP 'pid=\K[0-9]+' | head -1 || true)
  fi
  if [ -n "$pid" ]; then
    echo "  ✅ $name (端口 $port, PID $pid)"
  else
    echo "  ❌ $name (端口 $port)"
  fi
done
