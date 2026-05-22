/**
 * 代码分析 API
 * 搜索、上下文、影响分析、变更影响分析
 * 支持多版本图谱查询（commit_hash）
 */

import { apiClient } from "./client";

export interface SearchResult {
  node_id: string;
  name: string;
  type: string;
  file_path: string | null;
  start_line: number | null;
  score: number;
  properties?: Record<string, any>;
}

export interface SymbolContext {
  node: {
    id: string;
    name: string;
    type: string;
    file_path: string | null;
    start_line: number | null;
    end_line: number | null;
  };
  relationships: Array<{
    id: string;
    type: string;
    source: string;
    target: string;
  }>;
  source: {
    start_line: number;
    end_line: number;
    content: string;
  } | null;
}

export interface ImpactResult {
  symbol: string;
  type: string;
  file_path: string | null;
  start_line: number | null;
  risk: string;
  upstream?: string[];
  downstream?: string[];
}

export interface CommitInfo {
  commit_hash: string;
  short_hash: string;
  commit_message: string | null;
  commit_author: string | null;
  commit_timestamp: string | null;
  node_count: number;
  rel_count: number;
  analyzed_at: string;
}

// 搜索代码（支持指定 commit 版本）
export function searchCode(
  projectId: string,
  query: string,
  nodeType?: string,
  limit = 20,
  mode = "hybrid",
  commitHash?: string,
) {
  const params: Record<string, string | number> = { q: query, limit, mode };
  if (nodeType) params.node_type = nodeType;
  if (commitHash) params.commit_hash = commitHash;
  return apiClient.get<{ success: boolean; data: SearchResult[] }>(
    `/projects/${projectId}/code-analysis/search`,
    { params }
  );
}

// 按类型搜索
export function searchByType(
  projectId: string,
  nodeType: string,
  limit = 100,
  commitHash?: string,
) {
  const params: Record<string, string | number> = { q: "", node_type: nodeType, limit, mode: "fts" };
  if (commitHash) params.commit_hash = commitHash;
  return apiClient.get<{ success: boolean; data: SearchResult[] }>(
    `/projects/${projectId}/code-analysis/search`,
    { params }
  );
}

// 获取符号上下文（支持指定 commit 版本）
export function getSymbolContext(projectId: string, symbol: string, commitHash?: string) {
  const params: Record<string, string> = { symbol };
  if (commitHash) params.commit_hash = commitHash;
  return apiClient.get<{ success: boolean; data: SymbolContext }>(
    `/projects/${projectId}/code-analysis/context`,
    { params }
  );
}

// 获取知识图谱数据（用于可视化，支持指定 commit 版本）
export function getGraphData(
  projectId: string,
  nodeLimit = 200,
  relLimit = 500,
  commitHash?: string,
) {
  const params: Record<string, string | number> = { node_limit: nodeLimit, rel_limit: relLimit };
  if (commitHash) params.commit_hash = commitHash;
  return apiClient.get<{ success: boolean; data: { nodes: Array<{ id: string; name: string; type: string; file_path: string | null }>; edges: Array<{ id: string; source: string; target: string; type: string }> } }>(
    `/projects/${projectId}/code-analysis/graph`,
    { params },
  );
}

// 列出已分析的 commit 版本
export function listCommits(projectId: string, limit = 20) {
  return apiClient.get<{ success: boolean; data: CommitInfo[] }>(
    `/projects/${projectId}/code-analysis/commits`,
    { params: { limit } }
  );
}

// 变更影响分析
export interface ChangeImpactRequest {
  mode: "manual" | "git_diff" | "compare_commits";
  file_path?: string;
  start_line?: number;
  end_line?: number;
  base_commit?: string;
  target_commit?: string;
  max_depth?: number;
}

export interface VersionDiff {
  added_count: number;
  removed_count: number;
  modified_count: number;
  added: Array<{ id: string; name: string; type: string; file_path: string | null }>;
  removed: Array<{ id: string; name: string; type: string; file_path: string | null }>;
  modified: Array<{ id: string; name: string; type: string; file_path: string | null }>;
}

export interface ChangeImpactResult {
  mode: string;
  base_commit?: string;
  target_commit?: string;
  changed_ranges?: Array<{ file: string; ranges: Array<[number, number]> }>;
  changed_symbols: Array<{ id: string; name: string; type: string; file_path: string | null }>;
  upstream: Array<{ id: string; name: string; type: string }>;
  downstream: Array<{ id: string; name: string; type: string }>;
  new_upstream?: Array<{ id: string; name: string; type: string }>;
  new_downstream?: Array<{ id: string; name: string; type: string }>;
  impacted_routes: Array<{ id: string; name: string }>;
  version_diff?: VersionDiff;
  risk: string;
  summary: string;
}

export function analyzeChangeImpact(projectId: string, data: ChangeImpactRequest) {
  return apiClient.post<{ success: boolean; data: ChangeImpactResult }>(
    `/projects/${projectId}/code-analysis/change-impact`,
    data,
  );
}

// 影响分析（支持指定 commit 版本）
export function getImpactAnalysis(
  projectId: string,
  symbol: string,
  direction = "upstream",
  commitHash?: string,
) {
  const params: Record<string, string> = { symbol, direction };
  if (commitHash) params.commit_hash = commitHash;
  return apiClient.get<{ success: boolean; data: ImpactResult }>(
    `/projects/${projectId}/code-analysis/impact`,
    { params }
  );
}

// 陈旧度检测
export interface StalenessReport {
  is_stale: boolean;
  indexed_commit: string | null;
  current_head: string | null;
  commits_behind: number;
  hint: string;
  status: string;
}

export function getStaleness(projectId: string) {
  return apiClient.get<{ success: boolean; data: StalenessReport }>(
    `/projects/${projectId}/code-analysis/staleness`,
  );
}

// 执行流调用链
export interface ProcessTraceStep {
  node_id: string;
  name: string;
  type: string;
  file_path: string | null;
  depth: number;
}

export interface ProcessTraceResult {
  process_id: string;
  name: string;
  entry_point: string | null;
  step_count: number;
  chain: ProcessTraceStep[];
}

export function getProcessTrace(projectId: string, processId: string) {
  return apiClient.get<{ success: boolean; data: ProcessTraceResult }>(
    `/projects/${projectId}/code-analysis/process-trace`,
    { params: { process_id: processId } },
  );
}
