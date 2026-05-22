/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

/**
 * 报告相关的 API 客户端函数
 */

import { apiClient } from "./client";

export interface RecentExecution {
  status: string;
  script_name: string | null;
  user_id: string;
  duration_ms: number | null;
  endpoint_id: string | null;
  executed_at: string | null;
}

export interface DashboardSummary {
  total_endpoints: number;
  endpoints_passed: number;
  endpoints_failed: number;
  total_executions: number;
  executions_passed: number;
  executions_failed: number;
  avg_duration_ms: number;
  pass_rate: number;
}

export interface DashboardData {
  summary: DashboardSummary;
  users: string[];
  recent_executions: RecentExecution[];
}

interface DashboardResponse {
  success: boolean;
  data: DashboardData;
}

export interface DashboardQueryParams {
  date_range?: string;
  user_id?: string;
}

/**
 * 获取项目仪表盘统计数据
 */
export function getDashboard(
  projectId: string,
  params?: DashboardQueryParams
) {
  return apiClient.get<DashboardResponse>(
    `/projects/${projectId}/reports/dashboard`,
    {
      params: params as Record<string, string | number | boolean | undefined>,
    }
  );
}
