#!/usr/bin/env bash
# ─── 停止全部服务 ──────────────────────────────────────────────────────

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT/logs"

echo "停止服务..."

# 从 PID 文件停止
if [ -d "$LOG_DIR" ]; then
  for pid_file in "$LOG_DIR"/*.pid; do
    if [ -f "$pid_file" ]; then
      pid=$(cat "$pid_file")
      name="${pid_file##*/}"
      name="${name%.pid}"
      if kill -9 "$pid" 2>/dev/null; then
        echo "  ✅ 已停止 $name (PID $pid)"
      else
        echo "  ⚠️  $name (PID $pid) 不存在"
      fi
      rm -f "$pid_file"
    fi
  done
fi

# 清理 Next.js 残留（node 启动 next-server 后自己退出，子进程可能变成孤儿）
pkill -9 -f "next start" 2>/dev/null || true
pkill -9 -f "next-server" 2>/dev/null || true
sleep 1

# 清理残留端口
for port in 8000 2026 3000; do
  pid=$(lsof -ti :$port 2>/dev/null || true)
  if [ -n "$pid" ]; then
    kill -9 "$pid" 2>/dev/null || true
    echo "  🔪 已清理端口 $port (PID $pid)"
  fi
done

echo "✅ 已停止"
