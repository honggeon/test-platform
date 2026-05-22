/**
 * 诊断报告 API 客户端
 * 对应后端: backend/app/api/v2/diagnosis.py
 */

import { apiClient } from "./client";
import type {
  DiagnosisReport,
  DiagnosisReportListItem,
  PaginatedDiagnosisReports,
  RuleStats,
  CreateDiagnosisResponse,
  RetryDiagnosisResponse,
  CleanupDiagnosisResponse,
  SuccessResponse,
} from "@/types/diagnosis";

// ==================== API 函数 ====================

/**
 * 创建诊断报告（触发分析）
 * POST /projects/{project_identifier}/diagnosis/reports?run_id=xxx
 */
export function createDiagnosisReport(
  projectId: string,
  runId: string,
  sourceType: string = "api_test"
) {
  return apiClient.post<SuccessResponse<CreateDiagnosisResponse>>(
    `/projects/${projectId}/diagnosis/reports`,
    undefined,
    {
      params: { run_id: runId, source_type: sourceType },
    }
  );
}

/**
 * 获取诊断报告详情
 * GET /projects/{project_identifier}/diagnosis/reports/{report_id}
 */
export function getDiagnosisReport(projectId: string, reportId: string) {
  return apiClient.get<SuccessResponse<DiagnosisReport>>(
    `/projects/${projectId}/diagnosis/reports/${reportId}`
  );
}

/**
 * 获取诊断报告列表（分页）
 * GET /projects/{project_identifier}/diagnosis/reports?run_id=&status=&page=&page_size=
 */
export function listDiagnosisReports(
  projectId: string,
  options?: {
    run_id?: string;
    status?: string;
    page?: number;
    page_size?: number;
  }
) {
  return apiClient.get<SuccessResponse<PaginatedDiagnosisReports>>(
    `/projects/${projectId}/diagnosis/reports`,
    {
      params: {
        page: options?.page ?? 1,
        page_size: options?.page_size ?? 20,
        ...(options?.run_id ? { run_id: options.run_id } : {}),
        ...(options?.status ? { status: options.status } : {}),
      },
    }
  );
}

/**
 * 重新诊断
 * POST /projects/{project_identifier}/diagnosis/reports/{report_id}/retry
 */
export function retryDiagnosisReport(projectId: string, reportId: string) {
  return apiClient.post<SuccessResponse<RetryDiagnosisResponse>>(
    `/projects/${projectId}/diagnosis/reports/${reportId}/retry`
  );
}

/**
 * 刷新规则库
 * POST /projects/{project_identifier}/diagnosis/rules/reload
 */
export function reloadDiagnosisRules(projectId: string) {
  return apiClient.post<SuccessResponse<void>>(
    `/projects/${projectId}/diagnosis/rules/reload`
  );
}

/**
 * 获取规则命中率统计
 * GET /projects/{project_identifier}/diagnosis/rules/stats?days=7
 */
export function getRuleStats(projectId: string, days: number = 7) {
  return apiClient.get<SuccessResponse<RuleStats>>(
    `/projects/${projectId}/diagnosis/rules/stats`,
    {
      params: { days },
    }
  );
}

/**
 * 清理过期诊断报告
 * POST /projects/{project_identifier}/diagnosis/cleanup?days=90
 */
export function cleanupDiagnosisReports(
  projectId: string,
  days: number = 90
) {
  return apiClient.post<SuccessResponse<CleanupDiagnosisResponse>>(
    `/projects/${projectId}/diagnosis/cleanup`,
    undefined,
    {
      params: { days },
    }
  );
}
