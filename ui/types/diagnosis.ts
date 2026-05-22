/**
 * 诊断报告相关类型定义
 * 对应后端: backend/app/models/mongodb/diagnosis_report.py
 */

// ==================== 降级信息 ====================
export interface DiagnosisDegradation {
  has_db_logs: boolean;
  has_kg_locations: boolean;
  has_llm_analysis: boolean;
  fallback_reason: string | null;
}

// ==================== 根因统计 ====================
export interface RootCauseCounts {
  token_expired: number;
  permission_denied: number;
  api_changed: number;
  data_error: number;
  network_timeout: number;
  script_error: number;
  unknown: number;
  [key: string]: number;
}

// ==================== 摘要 ====================
export interface DiagnosisSummary {
  total_failures: number;
  root_cause_counts: RootCauseCounts;
}

// ==================== 代码位置 ====================
export interface CodeLocation {
  strategy: string;
  result: Record<string, unknown>;
  confidence: number;
}

// ==================== 发现项 ====================
export interface DiagnosisFinding {
  failure_id: string;
  endpoint: string;
  method: string;
  status_code: number;
  error_message: string;
  root_cause_type: string;
  root_cause_detail: string;
  classifier: "rule" | "llm";
  matching_rule: string | null;
  code_locations: CodeLocation[];
  affects_apis: string[];
  fix_suggestions: string[];
  llm_cache_hit: boolean;
}

// ==================== LLM Token 成本 ====================
export interface LLMTokenCost {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
}

// ==================== 诊断报告（完整 MongoDB 文档） ====================
export interface DiagnosisReport {
  report_id: string;
  run_id: string;
  project_id: string;
  status: "pending" | "analyzing" | "completed" | "failed";
  dedup_key: string;
  retry_of_report_id?: string;
  source_type: string;
  test_type: string;
  degradation: DiagnosisDegradation;
  summary: DiagnosisSummary;
  findings: DiagnosisFinding[];
  analysis_duration_ms: number;
  llm_token_cost: LLMTokenCost;
  llm_provider: string;
  created_at: string;
  completed_at?: string;
}

// ==================== 列表项（PG 返回的精简结构） ====================
export interface DiagnosisReportListItem {
  id: string;
  run_id: string;
  status: string;
  source_type: string;
  error_count: number;
  degradation_level: "none" | "partial" | "severe";
  summary: DiagnosisSummary;
  created_at: string | null;
  completed_at: string | null;
}

// ==================== 分页列表响应 ====================
export interface PaginatedDiagnosisReports {
  total: number;
  page: number;
  page_size: number;
  items: DiagnosisReportListItem[];
}

// ==================== 规则统计 ====================
export interface RuleStats {
  total_rules: number;
  hit_counts: Record<string, number>;
  llm_fallback_count: number;
  total_classified: number;
  hit_rate: number;
  period_days: number;
}

// ==================== WebSocket 消息类型 ====================
export interface WSDiagnosisCompletedPayload {
  type: "diagnosis_completed" | "diagnosis_completed_replay";
  report_id: string;
  status: string;
  summary: DiagnosisSummary;
  degradation: DiagnosisDegradation;
}

export interface WSUnreadReportsPayload {
  type: "unread_reports";
  reports: WSDiagnosisCompletedPayload[];
}

export interface WSPingPayload {
  type: "ping";
}

export type WSClientMessage =
  | { type: "pong" }
  | { type: "ack"; report_id: string };

export type WSServerMessage =
  | WSPingPayload
  | WSDiagnosisCompletedPayload
  | WSUnreadReportsPayload;

// ==================== 创建诊断请求/响应 ====================
export interface CreateDiagnosisRequest {
  run_id: string;
  source_type?: string;
}

export interface CreateDiagnosisResponse {
  report_id: string;
  status: string;
  run_id: string;
}

export interface RetryDiagnosisResponse {
  report_id: string;
  status: string;
  dedup_key: string;
}

export interface CleanupDiagnosisResponse {
  deleted_count: number;
}

// ==================== 标准响应包装 ====================
export interface SuccessResponse<T> {
  success: boolean;
  data: T;
}
