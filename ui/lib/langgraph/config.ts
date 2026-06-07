/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

export interface StandaloneConfig {
  deploymentUrl: string;
  assistantId: string;
  langsmithApiKey?: string;
}

const CONFIG_KEY = "deep-agent-config";

/**
 * 检测 URL 是否为明显无效的本地开发地址（如端口 2025 等旧配置）。
 */
function isInvalidLocalDevUrl(url: string): boolean {
  // 2025 是旧默认端口，已废弃；当前 LangGraph 运行在 2026
  if (url.includes(":2025")) return true;
  // 如果 URL 以 http:// 开头但不是当前 origin，视为可能跨域/无效
  if (typeof window !== "undefined" && url.startsWith("http://localhost:")) {
    const expectedOrigin = window.location.origin;
    if (!url.startsWith(expectedOrigin)) return true;
  }
  return false;
}

/**
 * 将 LangGraph API URL 解析为绝对 URL。
 * 如果传入的是相对路径（如 /lg），补全 window.location.origin；
 * 否则原样返回。
 * 服务端渲染（SSR）时返回原始值。
 */
function resolveApiUrl(url: string): string {
  let resolved = url;
  if (typeof window !== "undefined" && url.startsWith("/")) {
    resolved = window.location.origin + url;
  }
  // LangGraph SDK 要求 apiUrl 以 / 结尾，否则拼接路径时会丢失最后一级路径（如 /lg）
  return resolved.endsWith("/") ? resolved : resolved + "/";
}

/**
 * 获取 LangGraph deploymentUrl，统一处理相对路径。
 * 优先用 getConfig() 中的值，否则回退到环境变量 + 默认值。
 */
export function getDeploymentUrl(): string {
  const config = getConfig();
  if (config) return config.deploymentUrl;
  const raw =
    process.env.NEXT_PUBLIC_LANGGRAPH_API_URL || "http://localhost:2026";
  return resolveApiUrl(raw);
}

export function getConfig(): StandaloneConfig | null {
  if (typeof window === "undefined") return null;

  const stored = localStorage.getItem(CONFIG_KEY);
  if (stored) {
    try {
      const parsed = JSON.parse(stored);
      const deploymentUrl = resolveApiUrl(parsed.deploymentUrl);
      // 如果 localStorage 中缓存了明显错误的旧地址，自动清理并回退
      if (isInvalidLocalDevUrl(deploymentUrl)) {
        console.warn("[LangGraph Config] 清除过期的本地缓存配置:", deploymentUrl);
        localStorage.removeItem(CONFIG_KEY);
        // fall through to env vars
      } else {
        return {
          ...parsed,
          deploymentUrl,
        };
      }
    } catch {
      // fall through to env vars
    }
  }

  // Fall back to environment variables
  const rawDeploymentUrl = process.env.NEXT_PUBLIC_LANGGRAPH_API_URL;
  const assistantId = process.env.NEXT_PUBLIC_TESTCASE_GENERATOR_ASSISTANT_ID;

  if (rawDeploymentUrl && assistantId) {
    return {
      deploymentUrl: resolveApiUrl(rawDeploymentUrl),
      assistantId,
      langsmithApiKey: process.env.NEXT_PUBLIC_LANGSMITH_API_KEY,
    };
  }

  return null;
}

export function saveConfig(config: StandaloneConfig): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(CONFIG_KEY, JSON.stringify(config));
}
