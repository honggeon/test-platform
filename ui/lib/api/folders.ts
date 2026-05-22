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
  FolderInfo,
  FolderCreate,
  FolderUpdate,
  MessageResponse,
  PaginatedResponse,
  SuccessResponse,
} from "./types";

// 获取项目下的文件夹列表（根文件夹或子文件夹）
export function getFolders(projectId: string, folderType?: string, parentId?: string) {
  const params: Record<string, string> = {};
  if (folderType) params.folder_type = folderType;

  if (parentId) {
    return apiClient.get<PaginatedResponse<FolderInfo>>(
      `/projects/${projectId}/folders/${parentId}/sub-folders`,
      { params }
    );
  }
  return apiClient.get<PaginatedResponse<FolderInfo>>(
    `/projects/${projectId}/folders`,
    { params }
  );
}

// 获取文件夹详情
export function getFolder(projectId: string, folderId: string) {
  return apiClient.get<SuccessResponse<FolderInfo>>(
    `/projects/${projectId}/folders/${folderId}`
  );
}

// 创建文件夹
export function createFolder(projectId: string, data: FolderCreate) {
  return apiClient.post<SuccessResponse<FolderInfo>>(
    `/projects/${projectId}/folders`,
    data
  );
}

// 更新文件夹
export function updateFolder(
  projectId: string,
  folderId: string,
  data: FolderUpdate
) {
  return apiClient.patch<SuccessResponse<FolderInfo>>(
    `/projects/${projectId}/folders/${folderId}`,
    data
  );
}

// 删除文件夹
export function deleteFolder(projectId: string, folderId: string) {
  return apiClient.delete<MessageResponse>(
    `/projects/${projectId}/folders/${folderId}`
  );
}

// 移动文件夹
export function moveFolder(
  projectId: string,
  folderId: string,
  parentId: string | null
) {
  return apiClient.post<SuccessResponse<FolderInfo>>(
    `/projects/${projectId}/folders/${folderId}/move`,
    { parent_id: parentId }
  );
}

// 复制文件夹
export function copyFolder(projectId: string, folderId: string) {
  return apiClient.post<SuccessResponse<FolderInfo>>(
    `/projects/${projectId}/folders/${folderId}/copy`
  );
}

// 文件夹树形结构节点
export interface FolderTreeNode extends FolderInfo {
  children?: FolderTreeNode[];
  loading?: boolean;
  expanded?: boolean;
}
