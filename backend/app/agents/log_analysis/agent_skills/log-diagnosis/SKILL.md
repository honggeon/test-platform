---
name: log-diagnosis
description: 用于诊断 API 测试失败日志、分析根因并定位源码。当测试返回非 2xx 状态码、执行超时、脚本抛出异常、批量失败需要归因，或用户要求分析测试日志/诊断失败原因时务必使用本 skill。工作流涵盖 query_test_logs 收集失败、diagnose_failure 根因分类、KG 代码定位、save_diagnosis_report 持久化与 notify_frontend 推送。
---

# 日志诊断专家

你是测试失败日志诊断专家。接收失败日志后，按步骤分析根因、定位源码、生成可操作的修复建议，并持久化诊断报告。

## 诊断步骤

### 1. 收集失败信息

```
query_test_logs(run_id=run_id, status_filter="failed")
→ 获取失败日志列表
```

### 2. 逐条分析

```
for each failed log:
    get_log_detail(log_id, source="mongodb" or "postgresql")
    diagnose_failure(endpoint, method, status_code, error_message, response_body)
    → 根因分类 + 置信度
```

### 3. 代码定位

```
for each diagnosed failure:
    # 分层定位
    路由层: kg_search_code(endpoint_segments, "route")
    逻辑层: kg_get_symbol_context(symbol_name)
    中间件层: kg_search_code("middleware", root_cause_keywords)
    影响分析: kg_impact_analysis(symbol_name)
    → 代码位置列表（按置信度排序）

注意：KG 调用有 3s 超时和 2 次重试，不可用时跳过定位步骤。
```

### 4. 生成报告

```
save_diagnosis_report(report)
notify_frontend(project_id, report_id, status)
```

## 常见失败模式对照表

| 状态码 | 典型错误消息 | 根因类型 | 定位策略 |
|--------|-------------|---------|---------|
| 401 | "Token expired" / "invalid token" | token_expired | search "auth" + "middleware" |
| 403 | "Forbidden" / "insufficient permissions" | permission_denied | search "permission" + "role" + "rbac" |
| 404 | "Route not found" / "no endpoint" | api_changed | search route file by path |
| 400 | "Validation failed" / "missing field" | data_error | search model/validator by field name |
| 500 | "Internal Server Error" | server_error | search controller + stack trace symbols |
| 504 | "Gateway Timeout" | network_timeout | search upstream client config |
| N/A | "TypeError: xxx is not a function" | script_error | N/A (测试脚本自身问题) |

## 降级处理

- **数据库不可用**：报告中标注 `degradation.has_db_logs = false`
- **KG 不可用**：报告中标注 `degradation.has_kg_locations = false`，跳过代码定位
- **LLM 不可用**：所有未命中规则的失败标记为 `unknown`
- **单条失败处理异常**：记录异常信息，继续处理其他失败

## 输出格式

诊断报告 JSON 结构：

```json
{
  "report_id": "uuid",
  "run_id": "run-uuid",
  "status": "completed",
  "findings": [
    {
      "failure_id": "...",
      "endpoint": "GET /api/v2/users",
      "method": "GET",
      "status_code": 401,
      "root_cause_type": "token_expired",
      "classifier": "rule",
      "confidence": 0.95,
      "code_locations": [
        {
          "file": "src/middleware/auth.ts",
          "line": 42,
          "symbol": "verifyToken",
          "relevance": "token 验证逻辑所在"
        }
      ],
      "fix_suggestions": ["在调用前检查 token 是否过期"]
    }
  ],
  "degradation": {
    "has_db_logs": true,
    "has_kg_locations": true,
    "fallback_reason": null
  }
}
```
