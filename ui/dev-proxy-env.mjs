/**
 * 开发环境代理地址解析（供 next.config.mjs 使用）
 *
 * 与后端共用同一套环境变量，避免 next.config 写死端口。
 * 优先级（高 → 低）：
 *   进程环境变量（scripts/detect-dev-ports.sh 在启动 Next 前注入）
 *   BACKEND_URL / PUBLIC_API_URL / NEXT_PUBLIC_API_URL
 *   BACKEND_HOST + BACKEND_PORT
 *   默认 http://localhost:8000
 *
 * 跳过自动探测：SKIP_PORT_DETECT=1 npm run dev
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const UI_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(UI_DIR, "..");

function parseEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const env = {};
  for (const line of fs.readFileSync(filePath, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    env[key] = value;
  }
  return env;
}

/** 合并仓库根、backend、ui 下的 .env（后加载的覆盖先加载的） */
export function loadMergedEnv() {
  const files = [
    path.join(REPO_ROOT, ".env"),
    path.join(REPO_ROOT, "backend", ".env"),
    path.join(UI_DIR, ".env"),
    path.join(UI_DIR, ".env.local"),
  ];
  const merged = {};
  for (const file of files) {
    Object.assign(merged, parseEnvFile(file));
  }
  for (const [key, value] of Object.entries(process.env)) {
    if (value !== undefined && value !== "") {
      merged[key] = value;
    }
  }
  return merged;
}

function originFromUrl(url, label) {
  try {
    return new URL(url).origin;
  } catch {
    console.warn(
      `[dev-proxy-env] 无效的 ${label}="${url}"，将尝试其它配置`
    );
    return null;
  }
}

/** FastAPI 后端 origin，如 http://localhost:8000 */
export function resolveBackendOrigin(env = loadMergedEnv()) {
  for (const key of ["BACKEND_URL", "PUBLIC_API_URL", "NEXT_PUBLIC_API_URL"]) {
    const origin = env[key] ? originFromUrl(env[key], key) : null;
    if (origin) return origin;
  }

  const host = env.BACKEND_HOST || "localhost";
  const port = env.BACKEND_PORT || "8000";
  return `http://${host}:${port}`;
}

/** LangGraph API origin，如 http://localhost:2026 */
export function resolveLanggraphOrigin(env = loadMergedEnv()) {
  for (const key of ["LANGGRAPH_API_URL"]) {
    const origin = env[key] ? originFromUrl(env[key], key) : null;
    if (origin) return origin;
  }

  const publicUrl = env.NEXT_PUBLIC_LANGGRAPH_API_URL || "";
  if (publicUrl.startsWith("http://") || publicUrl.startsWith("https://")) {
    const origin = originFromUrl(publicUrl, "NEXT_PUBLIC_LANGGRAPH_API_URL");
    if (origin) return origin;
  }

  const port =
    env.LANGGRAPH_PORT || env.NEXT_PUBLIC_LANGGRAPH_API_PORT || "2026";
  const host = env.LANGGRAPH_HOST || "localhost";
  return `http://${host}:${port}`;
}
