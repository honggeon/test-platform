/**
 * 全栈分析 - 代码仓库 API
 */

import { apiClient } from "./client";

export interface CodeRepoStatus {
  repo_url: string | null;
  repo_path: string | null;
  repo_branch: string | null;
  configured: boolean;
  cloned: boolean;
  analyzed: boolean;
  analyzing: boolean;
  message: string;
  progress: number;
  current_step: string;
}

export interface CodeRepoInfo {
  repo_url: string | null;
  repo_path: string | null;
  repo_branch: string | null;
  analyzed: boolean;
}

// 获取项目代码仓库分析状态
export function getCodeRepoStatus(projectId: string) {
  return apiClient.get<{ success: boolean; data: CodeRepoStatus }>(
    `/projects/${projectId}/code-repo/status`
  );
}

// 配置项目代码仓库地址
export function configureCodeRepo(
  projectId: string,
  data: { repo_url: string; repo_branch?: string }
) {
  return apiClient.put<{ success: boolean; data: CodeRepoInfo }>(
    `/projects/${projectId}/code-repo`,
    data
  );
}

// 触发代码分析
export function triggerCodeAnalysis(projectId: string) {
  return apiClient.post<{ success: boolean; data: CodeRepoStatus }>(
    `/projects/${projectId}/code-repo/analyze`
  );
}
