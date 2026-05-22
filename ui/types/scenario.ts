/**
 * 版权所有 (c) 2023-2026 北京慧测信息技术有限公司(但问智能) 保留所有权利。
 * 
 * 本代码版权归北京慧测信息技术有限公司(但问智能)所有，仅用于学习交流目的，未经公司商业授权，
 * 不得用于任何商业用途，包括但不限于商业环境部署、售卖或以任何形式进行商业获利。违者必究。
 * 
 * 授权商业应用请联系微信：huice666
 */

/**
 * 场景测试类型定义
 */

export interface Scenario {
  id: string;
  project_id: string;
  identifier: string;
  name: string;
  description: string | null;
  folder_id: string | null;
  status: 'draft' | 'active' | 'archived';
  global_variables: Record<string, any>;
  retry_count: number;
  timeout_seconds: number;
  parallel_execution: boolean;
  total_steps: number;
  last_run_status: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
  created_by: string | null;
}

export interface ScenarioStep {
  id: string;
  scenario_id: string;
  endpoint_id: string | null;
  step_order: number;
  name: string;
  description: string | null;
  request_override: Record<string, any>;
  headers_override: Record<string, any>;
  extractors: StepExtractor[];
  assertions: StepAssertion[];
  condition_expression: string | null;
  continue_on_failure: boolean;
  delay_ms: number;
  retry_count: number;
  data_mappings: DataMapping[];
  created_at: string;
  updated_at: string;
  endpoint?: {
    id: string;
    method: string;
    path: string;
    display_name: string;
  };
}

export interface StepExtractor {
  name: string;
  path: string;
  type?: string;
}

export interface StepAssertion {
  type: 'status' | 'jsonpath' | 'header';
  expected: any;
  path?: string;
  operator?: string;
}

export interface DataMapping {
  id: string;
  source_type: 'previous_response' | 'variable' | 'static';
  source_step_id: string | null;
  source_path: string | null;
  target_path: string;
  transform_expression: string | null;
  description: string | null;
}

export interface ScenarioRun {
  id: string;
  scenario_id: string;
  project_id: string;
  identifier: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  runtime_variables: Record<string, any>;
  execution_config: Record<string, any>;
  total_steps: number;
  passed_steps: number;
  failed_steps: number;
  skipped_steps: number;
  duration_ms: number | null;
  report_path: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  executed_by: string | null;
}

export interface StepResult {
  id: string;
  run_id: string;
  step_id: string;
  endpoint_id: string | null;
  step_order: number;
  status: 'passed' | 'failed' | 'skipped' | 'error';
  request_data: Record<string, any> | null;
  response_data: Record<string, any> | null;
  extracted_data: Record<string, any>;
  assertion_results: AssertionResult[];
  duration_ms: number | null;
  error_message: string | null;
  error_stack: string | null;
  created_at: string;
}

export interface AssertionResult {
  assertion: StepAssertion;
  passed: boolean;
  actual: any;
  expected: any;
  message: string;
}
