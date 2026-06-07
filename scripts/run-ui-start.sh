#!/usr/bin/env bash
# 启动 Next.js 生产模式前自动探测后端 / LangGraph 端口（需在 build 之前 source）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UI="$ROOT/ui"

# shellcheck source=detect-dev-ports.sh
source "$ROOT/scripts/detect-dev-ports.sh"

cd "$UI"
exec npm run start:next
