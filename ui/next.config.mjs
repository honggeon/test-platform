/** @type {import('next').NextConfig} */
import {
  loadMergedEnv,
  resolveBackendOrigin,
  resolveLanggraphOrigin,
} from "./dev-proxy-env.mjs";

const env = loadMergedEnv();
const backendOrigin = resolveBackendOrigin(env);
const langgraphOrigin = resolveLanggraphOrigin(env);

const detectHint = process.env.PORT_DETECTED
  ? "（启动时已自动探测）"
  : process.env.SKIP_PORT_DETECT === "1"
    ? "（SKIP_PORT_DETECT，使用 .env）"
    : "";
console.log(
  `[next.config] API 代理 → ${backendOrigin}/api/v2/* | Auth → ${backendOrigin}/auth/* | LangGraph → ${langgraphOrigin}/lg/* ${detectHint}`
);

const nextConfig = {
  typescript: {
    // 跳过类型检查（项目存在大量水印注释遗留的类型不匹配）
    ignoreBuildErrors: true,
  },
  // 与 rewrites 同源，供 WebSocket 等直连后端的客户端逻辑使用
  env: {
    NEXT_PUBLIC_API_URL: backendOrigin,
  },
  async rewrites() {
    return [
      {
        source: "/api/v2/:path*",
        destination: `${backendOrigin}/api/v2/:path*`,
      },
      {
        source: "/auth/:path*",
        destination: `${backendOrigin}/auth/:path*`,
      },
      {
        source: "/lg/:path*",
        destination: `${langgraphOrigin}/:path*`,
      },
    ];
  },
};

export default nextConfig;
