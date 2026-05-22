/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

/**
 * MinIO 测试报告 API 客户端
 * 对应后端 api/v2/test_reports.py
 */

import { apiClient } from "./client";
// eslint-disable-next-line

// ==================== 类型定义 ====================

export interface TestReportSummary {
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  total_duration_ms: number;
}

export interface TestReportTestInfo {
  name: string;
  project: string;
  status: string;
  expected_status: string;
  ok: boolean;
  duration_ms: number;
  error?: string | null;
  stack?: string | null;
}

export interface TestReportListInfo {
  id: string;
  project_identifier: string;
  generated_at: string;
  minio_path: string;
  summary: TestReportSummary;
  presigned_url?: string | null;
  report_type?: string;
}

export interface TestReportInfo {
  id: string;
  project_identifier: string;
  framework: string;
  test_path: string;
  exit_code: number;
  summary: TestReportSummary;
  tests: TestReportTestInfo[];
  generated_at: string;
  minio_path: string;
  presigned_url?: string | null;
}

export interface PaginatedResponse<T> {
  success: boolean;
  data: T[];
  pagination: {
    total: number;
    page: number;
    page_size: number;
    prev?: string | null;
    next?: string | null;
  };
}

interface SuccessResponse<T> {
  success: boolean;
  data: T;
}

// ==================== API 函数 ====================

/**
 * 获取项目的测试报告列表（带分页）
 */
export function listTestReports(
  projectId: string,
  page: number = 1,
  pageSize: number = 20
) {
  return apiClient.get<PaginatedResponse<TestReportListInfo>>(
    `/projects/${projectId}/test-reports`,
    {
      params: { p: page, page_size: pageSize },
    }
  );
}

/**
 * 获取单个测试报告详情
 */
export function getTestReport(
  projectId: string,
  reportId: string
) {
  return apiClient.get<SuccessResponse<TestReportInfo>>(
    `/projects/${projectId}/test-reports/${reportId}`
  );
}
// FIXME
