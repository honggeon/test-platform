/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

/**
 * API 测试相关的扩展 API 客户端函数
 * 包含按文件夹查询等功能
 */

import { apiClient } from "./client";
import type {
  APITest,
  APITestListResponse,
} from "./api-tests";

/**
 * 获取指定文件夹下的 API 测试列表
 */
export function getFolderAPITests(
  projectIdentifier: string,
  folderId: string,
  params?: {
    page?: number;
    page_size?: number;
    search?: string;
  }
): Promise<APITestListResponse> {
  return apiClient.get<APITestListResponse>(
    `/projects/${projectIdentifier}/folders/${folderId}/api-tests`,
    { params }
  );
}
