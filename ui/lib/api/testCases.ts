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
  TestResultStatus,
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

// 更新测试用例最近一次测试结果
export function updateLatestTestResult(
  projectId: string,
  testCaseId: string,
  status: TestResultStatus | null
) {
  return apiClient.patch<{ success: boolean; data: TestCaseInfo }>(
    `/projects/${projectId}/test-cases/${testCaseId}/latest-test-result`,
    { status }
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

export interface TestCaseImportError {
  row: number;
  name?: string;
  message: string;
}

export interface TestCaseImportResponse {
  success: boolean;
  message: string;
  imported_count: number;
  failed_count: number;
  errors: TestCaseImportError[];
  test_cases?: TestCaseInfo[];
}

export async function importTestCases(
  projectId: string,
  file: File,
  folderId?: string | null
): Promise<TestCaseImportResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (folderId) {
    formData.append("folder_id", folderId);
  }

  const response = await fetch(
    `/api/v2/projects/${projectId}/test-cases/import`,
    {
      method: "POST",
      body: formData,
    }
  );

  const data = await response.json();
  if (!response.ok) {
    const detail = data?.detail;
    const message =
      data?.message ||
      (typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join("; ")
          : "导入失败");
    throw new Error(message);
  }
  return data as TestCaseImportResponse;
}

export function downloadTestCaseImportTemplate(projectId: string): void {
  const link = document.createElement("a");
  link.href = `/api/v2/projects/${projectId}/test-cases/import-template`;
  link.download = "test-cases-import-template.csv";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export async function importTestCasesFromApi(
  projectId: string,
  endpointIds: string[],
  folderId?: string | null
): Promise<TestCaseImportResponse> {
  return apiClient.post<TestCaseImportResponse>(
    `/projects/${projectId}/test-cases/import-from-api`,
    {
      endpoint_ids: endpointIds,
      folder_id: folderId || undefined,
    }
  );
}

