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
  TestCaseInfo,
  TestCaseCreate,
  TestCaseUpdate,
  PaginationInfo,
  Priority,
  TestCaseState,
} from "./types";

interface TestCaseResponse {
  success: boolean;
  test_case: TestCaseInfo;
}

interface TestCaseListResponse {
  success: boolean;
  data?: TestCaseInfo[];
  test_cases?: TestCaseInfo[];
  info?: PaginationInfo;
}

interface TestCaseDeleteResponse {
  success: boolean;
  message: string;
}

export interface TestCaseQueryParams {
  p?: number;
  page_size?: number;
  folder_id?: string;
  search?: string;
  priority?: Priority | string;
  status?: TestCaseState | string;
  owner?: string;
  tags?: string;
  minify?: boolean;
}

// 获取项目下的测试用例列表
export function getTestCases(
  projectId: string,
  params?: TestCaseQueryParams
) {
  return apiClient.get<TestCaseListResponse>(
    `/projects/${projectId}/test-cases`,
    { params: params as Record<string, string | number | boolean | undefined> }
  );
}

// 获取文件夹下的测试用例
export function getFolderTestCases(
  projectId: string,
  folderId: string,
  params?: TestCaseQueryParams
) {
  return apiClient.get<TestCaseListResponse>(
    `/projects/${projectId}/folders/${folderId}/test-cases`,
    { params: params as Record<string, string | number | boolean | undefined> }
  );
}

// 获取测试用例详情
export function getTestCase(projectId: string, testCaseId: string) {
  return apiClient.get<TestCaseResponse>(
    `/projects/${projectId}/test-cases/${testCaseId}`
  );
}

// 创建测试用例
export function createTestCase(
  projectId: string,
  folderId: string | null,
  data: TestCaseCreate
) {
  const url = folderId
    ? `/projects/${projectId}/folders/${folderId}/test-cases`
    : `/projects/${projectId}/test-cases`;
  return apiClient.post<TestCaseResponse>(url, data);
}

// 更新测试用例
export function updateTestCase(
  projectId: string,
  testCaseId: string,
  data: TestCaseUpdate
) {
  return apiClient.patch<TestCaseResponse>(
    `/projects/${projectId}/test-cases/${testCaseId}`,
    data
  );
}

// 删除测试用例
export function deleteTestCase(projectId: string, testCaseId: string) {
  return apiClient.delete<TestCaseDeleteResponse>(
    `/projects/${projectId}/test-cases/${testCaseId}`
  );
}

// 移动测试用例到其他文件夹
export function moveTestCase(
  projectId: string,
  testCaseId: string,
  folderId: string | null
) {
  return apiClient.patch<TestCaseResponse>(
    `/projects/${projectId}/test-cases/${testCaseId}/move`,
    { folder_id: folderId }
  );
}

interface BulkOperationResponse {
  success: boolean;
  message: string;
  affected_count: number;
}

// 批量删除测试用例
export function bulkDeleteTestCases(
  projectId: string,
  testCaseIds: string[]
) {
  return apiClient.delete<BulkOperationResponse>(
    `/projects/${projectId}/test-cases`,
    {
      data: {
        test_case_ids: testCaseIds,
      },
    }
  );
}

// 批量更新测试用例
export function bulkUpdateTestCases(
  projectId: string,
  testCaseIds: string[],
  updateData: Partial<TestCaseUpdate>
) {
  return apiClient.post(`/projects/${projectId}/test-cases/bulk/update`, {
    test_case_ids: testCaseIds,
    update_data: updateData,
  });
}

