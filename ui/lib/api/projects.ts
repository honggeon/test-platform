/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

import { apiClient } from "./client";
import type {
  PaginatedResponse,
  SuccessResponse,
  MessageResponse,
  ProjectInfo,
  ProjectCreate,
  ProjectUpdate,
} from "./types";

// 获取项目列表
export function getProjects(params?: { p?: number; page_size?: number }) {
  return apiClient.get<PaginatedResponse<ProjectInfo>>("/projects", {
    params,
  });
}

// 获取单个项目详情
export function getProject(identifier: string) {
  return apiClient.get<SuccessResponse<ProjectInfo>>(
    `/projects/${identifier}`
  );
}

// 创建项目
export function createProject(data: ProjectCreate) {
  return apiClient.post<SuccessResponse<ProjectInfo>>("/projects", data);
}

// 更新项目
export function updateProject(identifier: string, data: ProjectUpdate) {
  return apiClient.patch<SuccessResponse<ProjectInfo>>(
    `/projects/${identifier}`,
    data
  );
}

// 删除项目
export function deleteProject(identifier: string) {
  return apiClient.delete<MessageResponse>(`/projects/${identifier}`);
}

