/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

// API 通用类型定义

// 分页信息
export interface PaginationInfo {
  page: number;
  page_size: number;
  count?: number;
  total: number;
  prev?: string | null;
  next?: string | null;
}

// 通用分页响应
export interface PaginatedResponse<T> {
  success: boolean;
  data: T[];
  info: PaginationInfo;
}

// 通用成功响应
export interface SuccessResponse<T> {
  success: boolean;
  data: T;
}

// 通用消息响应
export interface MessageResponse {
  success: boolean;
  message: string;
}

// 链接信息
export interface LinkInfo {
  self?: string;
  project?: string;
  folder?: string;
  parent?: string;
  sub_folders?: string;
  test_cases?: string;
}

// 项目信息
export interface ProjectInfo {
  identifier: string;
  name: string;
  description?: string | null;
  created_at: string;
  created_by: string;
  updated_at?: string | null;
  team_id?: number[] | null;
  test_cases_count: number;
  folders_count: number;
  links?: LinkInfo | null;
}

// 创建项目请求
export interface ProjectCreate {
  name: string;
  description?: string;
  team_id?: number[];
}

// 更新项目请求
export interface ProjectUpdate {
  name?: string;
  description?: string;
  team_id?: number[];
}

// 文件夹类型
export type FolderType = "test_case" | "api_test";

// API 端点简要信息（用于文件夹树展示）
export interface APIEndpointSummary {
  id: string;
  display_name: string;
  method: string;
  path: string;
  tag_group?: string | null;
  total_test_cases?: number;  // 该接口的测试用例数量
  total_test_runs?: number;   // 该接口被执行的次数
}

// 文件夹信息
// 显示格式: 直接用例数(总用例数)
// 例如: 2(10) 表示该目录直接有2条用例，该目录及所有子目录共10条用例
export interface FolderInfo {
  id: string;
  name: string;
  description?: string | null;
  parent_id?: string | null;
  project_identifier: string;
  folder_type?: FolderType;  // 文件夹类型：test_case 或 api_test
  created_at: string;
  updated_at?: string | null;
  direct_cases_count: number;  // 直接在该文件夹中的用例数量
  cases_count: number;         // 该文件夹及所有子文件夹的总用例数
  sub_folders_count: number;   // 直接子文件夹数量
  hierarchy_index: number;
  links?: LinkInfo | null;
  api_endpoints?: APIEndpointSummary[];  // API 端点列表（仅用于 API_TEST 类型文件夹）
  web_functions?: WebFunctionSummary[];  // Web 功能列表（仅用于 WEB_TEST 类型文件夹）
  total_sub_functions?: number;  // 该文件夹下所有功能的子功能总数（仅用于 WEB_TEST 类型文件夹）
}

// 创建文件夹请求
export interface FolderCreate {
  name: string;
  description?: string;
  folder_type?: FolderType;  // 文件夹类型
  parent_id?: string;
}

// 更新文件夹请求
export interface FolderUpdate {
  name?: string;
  description?: string;
}

// 测试用例优先级
export type Priority = "critical" | "high" | "medium" | "low";

// 测试用例状态（基于生命周期）
export type TestCaseState =
  // 设计阶段
  | "new"              // 新建
  | "review_pending"   // 待评审
  | "reviewed"         // 已评审
  // 执行阶段
  | "not_run"          // 未执行
  | "passed"           // 通过
  | "failed"           // 失败
  | "blocked"          // 阻塞
  | "skipped";         // 跳过

// 测试用例类型
export type TestCaseType =
  | "functional"
  | "smoke_sanity"
  | "regression"
  | "security"
  | "performance"
  | "usability"
  | "acceptance"
  | "compatibility"
  | "integration"
  | "exploratory"
  | "other";

// 自动化状态
export type AutomationStatus =
  | "not_automated"
  | "automated"
  | "in_progress";

// 测试用例模板
export type TestCaseTemplate = "test_case" | "test_case_bdd";

// 测试步骤
export interface TestStepInfo {
  id: string;
  order: number;
  step: string;
  result?: string;
}

// 创建测试步骤
export interface TestStepCreate {
  step: string;
  result?: string;
}

// 测试结果状态
export type TestResultStatus =
  | "passed"
  | "failed"
  | "skipped"
  | "blocked"
  | "not_executed";

// 最近一次测试结果
export interface LatestTestResultInfo {
  status: TestResultStatus;
  tested_at: string;
  test_run_id?: string | null;
}

// 测试用例信息
export interface TestCaseInfo {
  id: string;
  identifier: string;
  name: string;
  description?: string;
  preconditions?: string;
  priority: Priority;
  status: TestCaseState;
  case_type: TestCaseType;
  template: TestCaseTemplate;
  automation_status: AutomationStatus;
  project_id: string;
  folder_id?: string | null;
  owner?: string;
  created_by: string;
  created_at: string;
  updated_at?: string;
  version: number;
  tags: string[];
  issues: string[];
  custom_fields?: Record<string, unknown>;
  test_case_steps: TestStepInfo[];
  feature?: string;
  scenario?: string;
  background?: string;
  latest_test_result?: LatestTestResultInfo | null;
}

// 创建测试用例请求
export interface TestCaseCreate {
  name: string;
  description?: string;
  preconditions?: string;
  priority?: Priority;
  status?: TestCaseState;
  case_type?: TestCaseType;
  owner?: string;
  tags?: string[];
  issues?: string[];
  automation_status?: AutomationStatus;
  custom_fields?: Record<string, unknown>;
  test_case_steps?: TestStepCreate[];
  template?: TestCaseTemplate;
  feature?: string;
  scenario?: string;
  background?: string;
}

// 更新测试用例请求
export interface TestCaseUpdate {
  name?: string;
  description?: string;
  preconditions?: string;
  priority?: Priority;
  status?: TestCaseState;
  case_type?: TestCaseType;
  owner?: string;
  tags?: string[];
  issues?: string[];
  automation_status?: AutomationStatus;
  custom_fields?: Record<string, unknown>;
  test_case_steps?: TestStepCreate[];
  feature?: string;
  scenario?: string;
  background?: string;
}

// 测试计划信息
export interface TestPlanInfo {
  identifier: string;
  name: string;
  description?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  created_at: string;
  updated_at?: string | null;
  test_runs?: TestRunBrief[];
}

// 测试运行简要信息
export interface TestRunBrief {
  identifier: string;
  name: string;
  state: string;
}

// 测试运行信息
export interface TestRunInfo {
  identifier: string;
  name: string;
  description?: string | null;
  state: string;
  created_at: string;
  updated_at?: string | null;
  total_tests: number;
  passed_tests: number;
  failed_tests: number;
  skipped_tests: number;
  blocked_tests: number;
}

// Web 功能简要信息（用于文件夹树展示）
export interface WebFunctionSummary {
  id: string;
  identifier: string;
  display_name: string;
  name: string;
  description?: string | null;
  base_url?: string | null;
  business_module?: string | null;
  folder_id?: string | null;
  total_sub_functions: number;
  total_test_cases: number;
}
