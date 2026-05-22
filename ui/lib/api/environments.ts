/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

/**
 * 测试环境相关的 API 客户端函数
 */

import { apiClient } from "./client";

export interface TestEnvironment {
  id: string;
  project_id: string;
  name: string;
  base_url: string;
  description: string | null;
  sort_order: number;
  is_default: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface TestEnvironmentCreate {
  name: string;
  base_url: string;
  description?: string;
  sort_order?: number;
  is_default?: boolean;
}

export interface TestEnvironmentUpdate {
  name?: string;
  base_url?: string;
  description?: string;
  sort_order?: number;
  is_default?: boolean;
}

interface EnvironmentsListResponse {
  success: boolean;
  data: TestEnvironment[];
}

interface EnvironmentResponse {
  success: boolean;
  data: TestEnvironment;
}

interface MessageResponse {
  success: boolean;
  message: string;
}

// 获取项目下所有测试环境
export function getEnvironments(projectId: string) {
  return apiClient.get<EnvironmentsListResponse>(
    `/projects/${projectId}/environments`
  );
}

// 获取项目的默认测试环境
export function getDefaultEnvironment(projectId: string) {
  return apiClient.get<EnvironmentResponse>(
    `/projects/${projectId}/environments/default`
  );
}

// 获取单个测试环境
export function getEnvironment(projectId: string, environmentId: string) {
  return apiClient.get<EnvironmentResponse>(
    `/projects/${projectId}/environments/${environmentId}`
  );
}

// 创建测试环境
export function createEnvironment(
  projectId: string,
  data: TestEnvironmentCreate
) {
  return apiClient.post<EnvironmentResponse>(
    `/projects/${projectId}/environments`,
    data
  );
}

// 更新测试环境
export function updateEnvironment(
  projectId: string,
  environmentId: string,
  data: TestEnvironmentUpdate
) {
  return apiClient.patch<EnvironmentResponse>(
    `/projects/${projectId}/environments/${environmentId}`,
    data
  );
}

// 删除测试环境
export function deleteEnvironment(projectId: string, environmentId: string) {
  return apiClient.delete<MessageResponse>(
    `/projects/${projectId}/environments/${environmentId}`
  );
}
