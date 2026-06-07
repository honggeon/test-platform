/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

/**
 * API 端点相关的 API 客户端函数
 */

import { apiClient } from "./client";

// ==================== 类型定义 ====================

export interface APIEndpoint {
  id: string;
  display_name: string;
  path: string;
  method: string;
  summary: string | null;
  description: string | null;
  tag_group: string | null;
  parameters: any[] | null;
  request_body: any | null;
  responses: any | null;
  folder_id: string | null;
  project_id: number;
  sort_order: number;
  total_test_cases: number;
  total_test_runs: number;
  last_run_status: string | null;
  api_test_ids: string[] | null;
  created_at: string;
  updated_at: string | null;
}

export interface APIEndpointListResponse {
  success: boolean;
  data: APIEndpoint[];
}

// ==================== API 函数 ====================

/**
 * 获取项目的 API 端点列表
 */
export async function listAPIEndpoints(
  projectIdentifier: string,
  params?: {
    folder_id?: string;
    tag_group?: string;
  }
): Promise<APIEndpoint[]> {
  return apiClient.get<APIEndpoint[]>(
    `/projects/${projectIdentifier}/api-endpoints`,
    { params }
  );
}

/**
 * 获取 API 端点详情
 */
export async function getAPIEndpoint(
  endpointId: string
): Promise<APIEndpoint> {
  return apiClient.get<APIEndpoint>(
    `/api-endpoints/${endpointId}`
  );
}

/**
 * 获取 API 端点关联的测试脚本
 */
export async function getEndpointTestScripts(
  endpointId: string
): Promise<{
  endpoint_id: string;
  test_scripts: Array<{
    id: string;
    name: string;
    identifier: string;
    script_format: string;
    script_language: string;
    total_endpoints: number;
    total_scenarios: number;
    created_at: string;
    updated_at: string;
  }>;
}> {
  return apiClient.get<{
    endpoint_id: string;
    test_scripts: Array<any>;
  }>(
    `/api-endpoints/${endpointId}/test-scripts`
  );
}

/**
 * 获取 API 端点的测试执行报告
 */
export async function getEndpointTestRuns(
  endpointId: string,
  limit: number = 10
): Promise<{
  endpoint_id: string;
  test_runs: Array<{
    id: string;
    status: string;
    total_scenarios: number;
    passed_scenarios: number;
    failed_scenarios: number;
    skipped_scenarios: number;
    duration: number;
    created_at: string;
  }>;
  total_runs: number;
  last_run_status: string | null;
}> {
  return apiClient.get<{
    endpoint_id: string;
    test_runs: Array<any>;
    total_runs: number;
    last_run_status: string | null;
  }>(
    `/api-endpoints/${endpointId}/test-runs`,
    { params: { limit } }
  );
}

/**
 * 更新 API 端点
 */
export async function updateAPIEndpoint(
  endpointId: string,
  data: {
    display_name?: string;
    path?: string;
    method?: string;
    summary?: string;
    description?: string;
    tag_group?: string;
    parameters?: any[] | null;
    request_body?: any | null;
    responses?: any | null;
    custom_config?: any;
    total_test_cases?: number;
    total_test_runs?: number;
    last_run_status?: string;
    api_test_ids?: string[];
  }
): Promise<APIEndpoint> {
  return apiClient.patch<APIEndpoint>(
    `/api-endpoints/${endpointId}`,
    data
  );
}

/**
 * 删除 API 端点
 */
export async function deleteAPIEndpoint(
  endpointId: string
): Promise<void> {
  return apiClient.delete(
    `/api-endpoints/${endpointId}`
  );
}

/**
 * 批量删除 API 端点
 */
export async function bulkDeleteAPIEndpoints(
  endpointIds: string[]
): Promise<void> {
  return apiClient.post(
    `/api-endpoints/bulk-delete`,
    { endpoint_ids: endpointIds }
  );
}
