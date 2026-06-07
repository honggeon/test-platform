#!/usr/bin/env bash
# 探测本机已启动的 FastAPI / LangGraph 监听端口，导出 PUBLIC_API_URL、LANGGRAPH_API_URL。
# 供 Next.js 启动前 source，使代理地址与当前实际端口一致。
#
# 用法:
#   source scripts/detect-dev-ports.sh   # 导出环境变量
#   scripts/detect-dev-ports.sh          # 打印检测结果（不导出）
#
# 跳过自动探测（仅用 .env）:
#   SKIP_PORT_DETECT=1 npm run dev

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

_log() { echo "$@" >&2; }

_listen_port_for_pid() {
  local pid="$1"
  lsof -Pan -p "$pid" -iTCP -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {
    n = split($9, a, ":");
    print a[n];
    exit
  }'
}

_origin_from_env_files() {
  local key="$1"
  local default="$2"
  local f val
  for f in "$ROOT/.env" "$ROOT/backend/.env" "$ROOT/ui/.env.local"; do
    [ -f "$f" ] || continue
    val="$(grep -E "^[[:space:]]*${key}=" "$f" 2>/dev/null | tail -1 | cut -d= -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'\'']//' -e 's/["'\'']$//')"
    if [ -n "$val" ]; then
      echo "$val"
      return 0
    fi
  done
  echo "$default"
}

_detect_by_process() {
  local pattern="$1"
  local pid port
  for pid in $(pgrep -f "$pattern" 2>/dev/null || true); do
    port="$(_listen_port_for_pid "$pid")"
    if [ -n "$port" ]; then
      echo "http://127.0.0.1:${port}"
      return 0
    fi
  done
  return 1
}

_probe_http() {
  local path="$1"
  shift
  local port origin code
  for port in "$@"; do
    origin="http://127.0.0.1:${port}"
    code="$(curl -s -o /dev/null -w "%{http_code}" --max-time 1 "${origin}${path}" 2>/dev/null || echo "000")"
    if [ "$code" != "000" ] && [ "$code" -lt 500 ]; then
      echo "$origin"
      return 0
    fi
  done
  return 1
}

detect_backend_origin() {
  local origin=""
  if origin="$(_detect_by_process "uvicorn app.main:app")" \
    || origin="$(_detect_by_process "uvicorn app.main")" \
    || origin="$(_detect_by_process "app/main.py")" \
    || origin="$(_detect_by_process "app.main:app")"; then
    echo "$origin"
    return 0
  fi
  _probe_http "/health" 8000 8001 8002 8003 8004 8005 8080 8888
}

detect_langgraph_origin() {
  local origin=""
  if origin="$(_detect_by_process "start_server.py")" \
    || origin="$(_detect_by_process "langgraph_api.server")"; then
    echo "$origin"
    return 0
  fi
  _probe_http "/ok" 2026 2027 2028
}

detect_and_export_dev_ports() {
  if [ "${SKIP_PORT_DETECT:-}" = "1" ]; then
    _log "[detect-dev-ports] 已跳过自动探测 (SKIP_PORT_DETECT=1)，使用 .env 配置"
    return 0
  fi

  local backend langgraph
  local backend_fallback langgraph_fallback

  backend_fallback="$(_origin_from_env_files "PUBLIC_API_URL" "http://127.0.0.1:8000")"
  langgraph_fallback="$(_origin_from_env_files "LANGGRAPH_API_URL" "http://127.0.0.1:2026")"

  if backend="$(detect_backend_origin)"; then
    export PUBLIC_API_URL="$backend"
    export NEXT_PUBLIC_API_URL="$backend"
    _log "[detect-dev-ports] FastAPI  → $backend (已探测)"
  else
    export PUBLIC_API_URL="$backend_fallback"
    export NEXT_PUBLIC_API_URL="$backend_fallback"
    _log "[detect-dev-ports] FastAPI  → $backend_fallback (.env/默认，未探测到运行中的后端)"
  fi

  if langgraph="$(detect_langgraph_origin)"; then
    export LANGGRAPH_API_URL="$langgraph"
    _log "[detect-dev-ports] LangGraph → $langgraph (已探测)"
  else
    export LANGGRAPH_API_URL="$langgraph_fallback"
    _log "[detect-dev-ports] LangGraph → $langgraph_fallback (.env/默认，未探测到运行中的 LangGraph)"
  fi

  export PORT_DETECTED=1
}

# 被 source 时自动执行；直接执行时仅打印结果
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
  detect_and_export_dev_ports
else
  detect_and_export_dev_ports
  echo "PUBLIC_API_URL=${PUBLIC_API_URL:-}"
  echo "LANGGRAPH_API_URL=${LANGGRAPH_API_URL:-}"
fi
