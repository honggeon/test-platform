/**
 * LLM 配置 API
 */

import { apiClient } from "./client";

export type LLMProvider = "deepseek" | "openai" | "anthropic" | "ollama";

export interface LLMConfigData {
  provider: LLMProvider;
  model_name: string;
  api_key: string | null;
  base_url: string | null;
  temperature: number | null;
  max_tokens: number | null;
}

export interface LLMConfigResponse {
  id: string;
  project_id: string;
  provider: string;
  model_name: string;
  api_key: string | null;
  base_url: string | null;
  temperature: number | null;
  max_tokens: number | null;
  created_at: string;
  updated_at: string;
}

// Provider 配置元数据
export const PROVIDER_META: Record<LLMProvider, {
  label: string;
  icon: string;
  defaultModel: string;
  placeholder: string;
  needApiKey: boolean;
  needBaseUrl: boolean;
  baseUrlPlaceholder?: string;
  baseUrlHelper?: string;
}> = {
  deepseek: {
    label: "DeepSeek",
    icon: "🐋",
    defaultModel: "deepseek-chat",
    placeholder: "deepseek-chat",
    needApiKey: true,
    needBaseUrl: false,
  },
  openai: {
    label: "OpenAI",
    icon: "🤖",
    defaultModel: "gpt-4o",
    placeholder: "gpt-4o, gpt-4-turbo, gpt-3.5-turbo",
    needApiKey: true,
    needBaseUrl: true,
    baseUrlPlaceholder: "https://api.openai.com/v1 (default)",
    baseUrlHelper: "留空使用默认 OpenAI API，或设置代理地址",
  },
  anthropic: {
    label: "Anthropic",
    icon: "🧠",
    defaultModel: "claude-sonnet-4-20250514",
    placeholder: "claude-sonnet-4-20250514, claude-3-opus",
    needApiKey: true,
    needBaseUrl: false,
  },
  ollama: {
    label: "Ollama",
    icon: "🦙",
    defaultModel: "llama3.1",
    placeholder: "llama3.1, mistral, codellama",
    needApiKey: false,
    needBaseUrl: true,
    baseUrlPlaceholder: "http://localhost:11434",
    baseUrlHelper: "Ollama 服务地址，默认端口 11434",
  },
};

// 获取项目 LLM 配置
export function getLLMConfig(projectId: string) {
  return apiClient.get<{ success: boolean; data: LLMConfigResponse | null }>(
    `/llm-configs/${projectId}`
  );
}

// 保存项目 LLM 配置
export function saveLLMConfig(projectId: string, data: LLMConfigData) {
  return apiClient.post<{ success: boolean; data: LLMConfigResponse }>(
    `/llm-configs/${projectId}`,
    {
      provider: data.provider,
      model_name: data.model_name,
      api_key: data.api_key,
      base_url: data.base_url,
      temperature: data.temperature,
      max_tokens: data.max_tokens,
    }
  );
}
